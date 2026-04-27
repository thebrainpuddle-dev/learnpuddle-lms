# utils/soft_delete.py

from django.db import models
from django.utils import timezone

import logging

logger = logging.getLogger(__name__)


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that excludes soft-deleted records by default."""

    def delete(self):
        """Soft-delete all records in the queryset."""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """Permanently delete all records."""
        return super().delete()

    def alive(self):
        """Return only non-deleted records."""
        return self.filter(is_deleted=False)

    def dead(self):
        """Return only soft-deleted records."""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Manager that filters out soft-deleted records by default."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()

    def all_with_deleted(self):
        """Include soft-deleted records."""
        return SoftDeleteQuerySet(self.model, using=self._db)

    def deleted_only(self):
        """Return only soft-deleted records."""
        return SoftDeleteQuerySet(self.model, using=self._db).dead()


class SoftDeleteMixin(models.Model):
    """
    Mixin that adds soft-delete capability to any model.

    Usage:
        class MyModel(SoftDeleteMixin, models.Model):
            ...
            objects = SoftDeleteManager()
            all_objects = models.Manager()  # fallback to include deleted
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Soft-delete this record (alias for soft_delete with no user)."""
        self.soft_delete(user=None)

    def soft_delete(self, user=None):
        """
        Soft-delete this record and dispatch the ``soft_deleted`` signal.

        Callers that know the acting user should pass ``user`` so that
        audit trails (and signal receivers) have access to it.

        The ``soft_deleted`` signal is defined in ``apps.courses.signals``
        so that receivers in other apps (e.g. ``apps.semantic_search``) can
        connect without creating an import cycle back into ``apps.courses``.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        # Some sub-classes (e.g. Course via audit-logging views) set
        # ``deleted_by`` — honour that field when present on the model.
        # Use a concrete field-list lookup rather than hasattr() so we only
        # match actual Django model fields, not arbitrary attributes/properties.
        _model_field_names = {f.name for f in self._meta.get_fields()}
        if "deleted_by" in _model_field_names:
            self.deleted_by = user  # type: ignore[attr-defined]
            update_fields = ['is_deleted', 'deleted_at', 'deleted_by']
        else:
            update_fields = ['is_deleted', 'deleted_at']
        self.save(update_fields=update_fields)
        # Fire the signal AFTER the save so receivers see is_deleted=True.
        # Only the top-level import is wrapped in try/except ImportError — if
        # apps.courses is not installed (e.g. unit tests for other apps that
        # only install a subset of INSTALLED_APPS) we degrade gracefully.
        # Any exception raised during signal dispatch itself propagates so
        # callers are not silently swallowing real errors.
        try:
            from apps.courses.signals import soft_deleted
        except ImportError:
            logger.warning(
                "soft_delete: apps.courses.signals not importable; "
                "soft_deleted signal NOT sent for %s pk=%s",
                type(self).__name__,
                self.pk,
            )
            return
        soft_deleted.send(sender=type(self), instance=self, user=user)

    def hard_delete(self, using=None, keep_parents=False):
        """Permanently delete this record."""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])
