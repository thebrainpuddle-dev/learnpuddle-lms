"""
post_save signal that snapshots Course / Module / Content into
`ContentRevision` rows (TASK-048).

A thread-local (context-var) flag `_SUPPRESS_VERSIONING` is used by the
restore endpoint to avoid infinite loops: restore re-saves the same rows
but we don't want each re-save to create yet another revision.

Snapshot-equality dedup
-----------------------
`capture_revision` skips creating a revision when ``snapshot_json`` is
byte-identical to the previous revision's snapshot. This keeps the
revision trail free of noise from Django-internal re-saves (for example,
PostgreSQL ``search_vector`` refreshes trigger a ``save()`` but leave no
user-visible field changed).

**Side effect:** a deliberate admin "Save" action that touches zero
snapshotted fields will NOT produce a revision row.  The FE history
panel must not treat the absence of a revision as proof that the user
did not click save.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.db.models.signals import post_save

from .versioning_snapshot import serialize_instance

logger = logging.getLogger(__name__)


# Context-var so suppression is safe under ASGI / threads.
_SUPPRESS_VERSIONING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "suppress_versioning", default=False
)

# Max retries for a concurrent-save `unique_together` race on
# ``(content_type, object_id, revision_number)``. Each retry reads the
# new max ``revision_number`` and tries again. In practice one retry is
# almost always enough; 5 guards against a pathological burst.
_REVISION_NUMBER_MAX_RETRIES = 5


@contextmanager
def suppress_versioning():
    """Disable revision capture for the duration of the with-block."""
    token = _SUPPRESS_VERSIONING.set(True)
    try:
        yield
    finally:
        _SUPPRESS_VERSIONING.reset(token)


def _resolve_tenant(instance) -> Optional[object]:
    """Best-effort tenant lookup for Course / Module / Content."""
    # Course: has tenant FK directly.
    tenant = getattr(instance, "tenant", None)
    if tenant is not None:
        return tenant
    # Module → course.tenant
    course = getattr(instance, "course", None)
    if course is not None:
        return getattr(course, "tenant", None)
    # Content → module.course.tenant
    module = getattr(instance, "module", None)
    if module is not None:
        c = getattr(module, "course", None)
        if c is not None:
            return getattr(c, "tenant", None)
    return None


def capture_revision(sender, instance, created, raw=False, **kwargs):
    """
    post_save receiver — write a ContentRevision for this instance.

    Skips when:
    - ``raw=True`` (fixture load)
    - versioning is suppressed (e.g. inside ``restore_revision``)
    - tenant cannot be determined (incomplete fixture / test stub) —
      emits a WARNING log for observability instead of silent skip
    - ``snapshot_json`` is identical to the previous revision's
      (see module docstring for user-visible consequences)

    Concurrency
    -----------
    Two simultaneous ``save()`` calls on the same row can otherwise race
    and both try to insert the same ``revision_number``.  We handle that
    by catching :class:`django.db.IntegrityError` on the unique
    constraint and retrying with the recomputed next number, up to
    :data:`_REVISION_NUMBER_MAX_RETRIES` times.  The loser is preserved
    (gets the next integer), not silently dropped.
    """
    if raw:
        return
    if _SUPPRESS_VERSIONING.get():
        return

    # Local import to avoid circular import at module load time.
    from .versioning_models import ContentRevision

    tenant = _resolve_tenant(instance)
    if tenant is None:
        # Shouldn't happen for real traffic. Warn so fixture/test misuse
        # is visible in logs rather than silently dropped.
        logger.warning(
            "ContentVersioning: skipping %s pk=%s with tenant_id=None",
            sender.__name__,
            getattr(instance, "pk", None),
        )
        return

    try:
        ct = ContentType.objects.get_for_model(sender)
        snapshot = serialize_instance(instance)

        # Retry loop handles the concurrent-insert race on
        # (content_type, object_id, revision_number).
        # Each attempt is wrapped in its own savepoint so that a failed
        # INSERT does not poison the outer transaction — the savepoint is
        # rolled back on IntegrityError, and the next iteration opens a
        # fresh one to re-read the current max revision_number and retry.
        for attempt in range(_REVISION_NUMBER_MAX_RETRIES):
            try:
                with transaction.atomic():
                    last = (
                        ContentRevision.all_objects
                        .filter(content_type=ct, object_id=instance.pk)
                        .order_by("-revision_number")
                        .first()
                    )

                    # Dedup: skip if snapshot is byte-identical to the previous
                    # one. (Saves that only touched search_vector etc. don't
                    # create noise — see module docstring.)
                    if last is not None and last.snapshot_json == snapshot:
                        return

                    next_number = 1 if last is None else last.revision_number + 1
                    summary = "create" if created and last is None else "update"

                    ContentRevision.all_objects.create(
                        tenant=tenant,
                        content_type=ct,
                        object_id=instance.pk,
                        revision_number=next_number,
                        snapshot_json=snapshot,
                        change_summary=summary,
                    )
            except IntegrityError:
                # Lost the race for `next_number` — the savepoint above was
                # cleanly rolled back. Loop re-reads the new max and retries.
                if attempt == _REVISION_NUMBER_MAX_RETRIES - 1:
                    raise
                continue
            # Success.
            return
    except Exception:
        # Never break a user's save if versioning blows up — just log it.
        logger.exception(
            "Failed to capture ContentRevision for %s(%s)",
            sender.__name__, getattr(instance, "pk", None),
        )


def connect_versioning_signals():
    """Wire up the three post_save receivers. Called from apps.ready()."""
    from .models import Course, Module, Content

    post_save.connect(
        capture_revision,
        sender=Course,
        dispatch_uid="versioning_capture_course",
    )
    post_save.connect(
        capture_revision,
        sender=Module,
        dispatch_uid="versioning_capture_module",
    )
    post_save.connect(
        capture_revision,
        sender=Content,
        dispatch_uid="versioning_capture_content",
    )
