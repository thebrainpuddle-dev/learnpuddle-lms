# apps/courses/maic_tasks.py — Background tasks for MAIC AI Classrooms
#
# Pre-generates TTS audio for every speech action in a classroom so the
# player uses instant ``audioUrl`` fast-path instead of real-time server
# TTS. Drives the ``audioManifest`` state machine that the teacher detail
# endpoint + frontend progress bar consume.
#
# CG-P0-3: also hosts fill_classroom_images — moves image resolution
# (fetch_scene_image HTTP calls, 5 providers × per-scene) off the
# synchronous request thread and into a post-process Celery task.

import logging
import os
import time
from datetime import datetime, timezone

from celery import chord, shared_task
from django.core.cache import cache
from django.db import OperationalError, DatabaseError, connection, transaction

from apps.courses.maic_models import MAICClassroom, TenantAIConfig
from apps.courses._log_helpers import MAICPhase, log_extra
from apps.courses.maic_generation_service import generate_tts_audio
from apps.courses.maic_storage import storage_upload, storage_exists
from utils.tenant_middleware import set_current_tenant, clear_current_tenant

logger = logging.getLogger(__name__)


# ── SPRINT-2-BATCH-9-F2: orchestrator concurrency lock ────────────────────
# Guards against double-enqueue of ``pre_generate_classroom_tts`` for the
# same classroom (e.g. publish-button double-click, retry-on-timeout from
# the FE, two admins racing). Uses Django cache ``add`` (Redis SET-NX
# semantics under the production cache backend) keyed on classroom_id.
# 5-minute TTL bounds worst-case lock leakage if a worker dies mid-chord
# without dispatching the callback — the lock auto-expires and the next
# publish re-orchestrates.
_ORCHESTRATOR_LOCK_TTL_SECONDS = 300
_ORCHESTRATOR_LOCK_KEY_TEMPLATE = "maic:tts:orchestrator:lock:{classroom_id}"


# ── AUDIT-2026-04-25-10: fill_classroom_images Phase-1 time budget ────────
# Cap the per-task wall-clock spent in the synchronous Phase-1 fetch loop.
# Without this, a classroom with 30 scenes × 2 image elements served by a
# flaky upstream (Pollinations stalling at ~10s/req) can pin a worker for
# 10+ minutes head-of-line-blocking the queue. When the budget is
# exceeded, the loop breaks early, Phase 2 persists what was already
# collected, and the task re-enqueues itself with the remaining scene
# indices (countdown=5) so the FE poll loop sees forward progress.
#
# Overridable via env var IMAGE_FILL_PHASE1_DEADLINE_SECS (float, seconds).
# Pattern mirrors the VITE_QUOTA_*_WATERMARK reads in frontend/src/lib/maicDb.ts:
# validate at module load, fall back to default with a warning on bad input.
_env_phase1 = os.environ.get("IMAGE_FILL_PHASE1_DEADLINE_SECS")
_IMAGE_FILL_PHASE_1_DEADLINE_DEFAULT = 90.0
if _env_phase1 is not None:
    try:
        IMAGE_FILL_PHASE_1_DEADLINE_SECS: float = float(_env_phase1)
    except ValueError:
        logger.warning(
            "IMAGE_FILL_PHASE1_DEADLINE_SECS=%r is not a valid float; "
            "falling back to default %.1f s",
            _env_phase1,
            _IMAGE_FILL_PHASE_1_DEADLINE_DEFAULT,
        )
        IMAGE_FILL_PHASE_1_DEADLINE_SECS = _IMAGE_FILL_PHASE_1_DEADLINE_DEFAULT
else:
    IMAGE_FILL_PHASE_1_DEADLINE_SECS = _IMAGE_FILL_PHASE_1_DEADLINE_DEFAULT
# Countdown applied to the deferred follow-up task. Long enough that the
# broker has time to drain other queued work, short enough that the FE
# (poll period 5s) sees forward progress within ~2 polls.
IMAGE_FILL_DEFERRED_COUNTDOWN_SECS = 5


# ─── CG-P0-3: Async image fill ────────────────────────────────────────────────

@shared_task(
    name="apps.courses.maic_tasks.fill_classroom_images",
    # Retry transient infrastructure failures only. Provider-level HTTP errors
    # are caught inside fetch_scene_image and handled via the circuit breaker
    # (CG-P0-4) — they surface as placeholder URLs, never as task failures.
    autoretry_for=(OperationalError, DatabaseError, ConnectionError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def fill_classroom_images(classroom_id: str, scene_indices: list[int] | None = None) -> None:
    """Fill empty image src fields in classroom.content_scenes with real image URLs.

    Idempotent — slides whose ``src`` is already a valid http/https URL are
    skipped, so re-running on a fully-filled classroom is a no-op.

    Args:
        classroom_id: UUID string of the target MAICClassroom.
        scene_indices: Optional list of 0-based scene indices to restrict
            processing. When None, all scenes are processed. Useful for
            targeted re-runs on a subset of scenes.

    State machine:
        On entry  — classroom.images_pending should be True (set by caller).
        On exit   — images_pending is flipped to False regardless of whether
                    all images were successfully fetched (partial fills are
                    acceptable; placeholders render on the frontend).

    Structured log fields (metric=image_fill):
        classroom_id, scene_count, provider_outcomes (counts by provider
        extracted from the URL pattern — used for observability without
        adding a Prometheus dep).
    """
    # Deferred import to avoid circular imports at module load time.
    from apps.courses.image_service import fetch_scene_image  # noqa: F401 (used below)

    try:
        # Use all_objects to bypass TenantManager filtering — the task
        # identifies the classroom by PK so cross-tenant contamination is
        # impossible.  We then call set_current_tenant so any nested queries
        # that do use TenantManager work correctly.
        classroom = MAICClassroom.all_objects.get(id=classroom_id)
    except MAICClassroom.DoesNotExist:
        logger.warning(
            "fill_classroom_images: classroom %s not found, skipping",
            classroom_id,
            extra=log_extra(
                MAICPhase.FILL_IMAGES,
                classroom_id,
                metric="image_fill_not_found",
                outcome="classroom_not_found",
            ),
        )
        return

    set_current_tenant(classroom.tenant)
    try:
        # F4: Early-exit guard — if images_pending is already False (e.g. the
        # task was enqueued twice due to a broker retry), skip all work.  The
        # per-element idempotency check (http-prefix skip) would make a re-run
        # safe anyway, but this saves the full scene-walk on a no-op retry.
        if not classroom.images_pending:
            logger.info(
                "fill_classroom_images: skipping classroom %s — images_pending=False",
                classroom_id,
                extra=log_extra(
                    MAICPhase.FILL_IMAGES,
                    classroom_id,
                    metric="image_fill_skipped",
                    outcome="not_pending",
                ),
            )
            return {"skipped": True, "reason": "not_pending"}

        # ── Phase 1: fetch images (OUTSIDE the transaction) ──────────────────
        # We read a snapshot of content here solely to extract keyword strings
        # for each image element.  The actual write is done in Phase 2 via a
        # merge so that any teacher PATCH that lands while we are fetching is
        # not overwritten.
        # PERF-P0-4 cutover: read from the content_scenes shard. The legacy
        # ``content`` JSONField is no longer written to, so falling back to
        # it would only return stale data. Migration 0043 backfilled every
        # existing row's shard from the legacy blob, so a fresh shard read
        # is always sufficient.
        snapshot_scenes = list(classroom.content_scenes or [])

        # Normalise scene_indices: None means all scenes
        if scene_indices is None:
            target_indices: list[int] = list(range(len(snapshot_scenes)))
        else:
            target_indices = [i for i in scene_indices if 0 <= i < len(snapshot_scenes)]

        # Track per-provider outcomes for structured logging.
        # Key = inferred provider label, value = count of URLs resolved.
        provider_outcomes: dict[str, int] = {}

        total_images = 0
        filled_images = 0

        # collected_diffs: maps (scene_idx, "slides"|"content", slide_idx,
        #   element_idx) → fetched_url  so we can apply them without holding
        #   the DB row locked during slow HTTP calls.
        collected_diffs: dict[tuple, str] = {}

        # AUDIT-2026-04-25-10: per-task wall-clock deadline. When exceeded,
        # we break out of the Phase-1 loop, persist the diffs we already
        # collected via Phase 2, and re-enqueue the remaining scene indices.
        # This caps worst-case task duration on a flaky upstream provider
        # so a single slow classroom does not head-of-line-block the queue.
        _phase_1_started = time.monotonic()
        _phase_1_deadline = IMAGE_FILL_PHASE_1_DEADLINE_SECS
        deferred_indices: list[int] = []

        for loop_pos, scene_idx in enumerate(target_indices):
            # Check budget BEFORE starting a new scene's fetches. If the
            # deadline has passed, skip this scene and every remaining one
            # so they can be processed in a follow-up task.
            if (time.monotonic() - _phase_1_started) > _phase_1_deadline:
                deferred_indices = list(target_indices[loop_pos:])
                logger.warning(
                    "fill_classroom_images: Phase-1 deadline exceeded — "
                    "deferring %d remaining scenes for classroom %s",
                    len(deferred_indices), classroom_id,
                    extra=log_extra(
                        MAICPhase.FILL_IMAGES,
                        classroom_id,
                        metric="image_fill_deadline",
                        outcome="phase1_deadline_exceeded",
                        deferred_count=len(deferred_indices),
                        elapsed_secs=time.monotonic() - _phase_1_started,
                    ),
                )
                break

            scene = snapshot_scenes[scene_idx]

            # Walk top-level slides array.
            for slide_idx, slide in enumerate(scene.get("slides", [])):
                for el_idx, element in enumerate(slide.get("elements", [])):
                    if not isinstance(element, dict):
                        continue
                    if element.get("type") != "image":
                        continue
                    total_images += 1
                    existing_src = (element.get("src") or "").strip()
                    if existing_src and (
                        existing_src.startswith("https://")
                        or existing_src.startswith("http://")
                    ):
                        provider_outcomes["already_filled"] = (
                            provider_outcomes.get("already_filled", 0) + 1
                        )
                        continue
                    keyword = element.get("content", "educational illustration")
                    try:
                        url = fetch_scene_image(keyword)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "fill_classroom_images: image fetch failed keyword=%r err=%s",
                            keyword, exc,
                            extra=log_extra(
                                MAICPhase.FILL_IMAGES,
                                classroom_id,
                                metric="image_fill_fetch_error",
                                outcome="fetch_error",
                                scene_idx=scene_idx,
                                el_idx=el_idx,
                                error_type=type(exc).__name__,
                            ),
                        )
                        url = "https://placehold.co/800x450?text=image"
                    collected_diffs[("slides", scene_idx, slide_idx, el_idx)] = url
                    filled_images += 1
                    provider = _infer_provider(url)
                    provider_outcomes[provider] = provider_outcomes.get(provider, 0) + 1

            # Walk scene-level content blob (parallel structure).
            scene_content = scene.get("content") or {}
            if isinstance(scene_content, dict):
                for el_idx, element in enumerate(scene_content.get("elements", [])):
                    if not isinstance(element, dict):
                        continue
                    if element.get("type") != "image":
                        continue
                    total_images += 1
                    existing_src = (element.get("src") or "").strip()
                    if existing_src and (
                        existing_src.startswith("https://")
                        or existing_src.startswith("http://")
                    ):
                        provider_outcomes["already_filled"] = (
                            provider_outcomes.get("already_filled", 0) + 1
                        )
                        continue
                    keyword = element.get("content", "educational illustration")
                    try:
                        url = fetch_scene_image(keyword)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "fill_classroom_images: image fetch failed keyword=%r err=%s",
                            keyword, exc,
                            extra=log_extra(
                                MAICPhase.FILL_IMAGES,
                                classroom_id,
                                metric="image_fill_fetch_error",
                                outcome="fetch_error",
                                scene_idx=scene_idx,
                                el_idx=el_idx,
                                error_type=type(exc).__name__,
                            ),
                        )
                        url = "https://placehold.co/800x450?text=image"
                    collected_diffs[("content", scene_idx, el_idx)] = url
                    filled_images += 1
                    provider = _infer_provider(url)
                    provider_outcomes[provider] = provider_outcomes.get(provider, 0) + 1

        # ── Phase 2: merge diffs into a FRESH read under select_for_update ───
        # Re-read the classroom row inside a transaction with a row-level lock.
        # Any teacher PATCH that landed during the fetch phase is now in the DB;
        # we apply ONLY the image-src diffs computed above, leaving everything
        # else (titles, agent IDs, keywords the teacher may have edited) intact.
        with transaction.atomic():
            # F4: Set a 5-second lock timeout so we don't block indefinitely if
            # a teacher PATCH is holding the row lock inside its own transaction.
            # When the timeout fires, PostgreSQL raises OperationalError (sqlstate
            # 55P03 / lock_not_available) which Celery's autoretry_for picks up
            # and retries with exponential backoff.
            with connection.cursor() as _cur:
                _cur.execute("SET LOCAL lock_timeout = '5s'")

            fresh = MAICClassroom.all_objects.select_for_update().get(id=classroom_id)

            # F2: Re-check images_pending INSIDE the row lock.  Two concurrent
            # task instances can both pass the outer early-exit (both see
            # images_pending=True before either holds the lock).  The first one
            # acquires the lock, fills images, and flips images_pending=False.
            # The second one now sees images_pending=False here and bails out,
            # preventing redundant HTTP writes and extra Unsplash API calls.
            if not fresh.images_pending:
                logger.info(
                    "fill_classroom_images: inner re-check — classroom %s already filled by concurrent task, skipping",
                    classroom_id,
                    extra=log_extra(
                        MAICPhase.FILL_IMAGES,
                        classroom_id,
                        metric="image_fill_skipped",
                        outcome="already_filled_by_other_task",
                    ),
                )
                return {"skipped": True, "reason": "already_filled_by_other_task"}

            # PERF-P0-4 cutover: read directly from the content_scenes
            # shard. Legacy fallback removed — see comment at the Phase-1
            # snapshot read above.
            fresh_scenes = list(fresh.content_scenes or [])

            for key, url in collected_diffs.items():
                try:
                    if key[0] == "slides":
                        _, s_idx, sl_idx, el_idx = key

                        # F3: fingerprint check — verify the element at this
                        # index still matches the snapshot we took in Phase 1.
                        # A concurrent scene-prepend/delete shifts indices, so
                        # what was scene[0] might now be scene[1].  We compare
                        # the snapshot element's keyword (content) against the
                        # fresh element at the same index.  If they diverge, we
                        # skip the diff to avoid writing an image into the wrong
                        # scene (silent misplacement bug).
                        snap_el = snapshot_scenes[s_idx]["slides"][sl_idx]["elements"][el_idx]
                        fresh_el = fresh_scenes[s_idx]["slides"][sl_idx]["elements"][el_idx]
                        # F1 (BATCH-7): fingerprint is a (id, content) tuple so
                        # that two scenes sharing the SAME keyword (e.g. both
                        # "photosynthesis") can still be distinguished by their
                        # element id.  id is generated per-element at content-
                        # creation time and does not change on scene title edits
                        # or reordering.  If id is absent (legacy rows without
                        # stable ids), the tuple degrades to (None, content) —
                        # same collision behaviour as the pre-BATCH-7 code but
                        # without crashing.
                        snap_fingerprint = (snap_el.get("id"), snap_el.get("content", ""))
                        fresh_fingerprint = (fresh_el.get("id"), fresh_el.get("content", ""))
                        if snap_fingerprint != fresh_fingerprint:
                            logger.warning(
                                "fill_classroom_images: index-shift detected at %s — "
                                "snapshot keyword %r != fresh keyword %r, skipping diff",
                                key, snap_fingerprint, fresh_fingerprint,
                                extra=log_extra(
                                    MAICPhase.FILL_IMAGES,
                                    classroom_id,
                                    metric="image_fill_index_shift",
                                    outcome="index_shift_detected",
                                    diff_key=str(key),
                                ),
                            )
                            continue

                        fresh_scenes[s_idx]["slides"][sl_idx]["elements"][el_idx]["src"] = url
                    else:  # "content"
                        _, s_idx, el_idx = key
                        # Apply same fingerprint check for scene-level content elements.
                        snap_el = snapshot_scenes[s_idx]["content"]["elements"][el_idx]
                        fresh_el = fresh_scenes[s_idx]["content"]["elements"][el_idx]
                        # Same (id, content) composite fingerprint as above.
                        if (snap_el.get("id"), snap_el.get("content", "")) != (fresh_el.get("id"), fresh_el.get("content", "")):
                            logger.warning(
                                "fill_classroom_images: index-shift detected at %s — skipping diff",
                                key,
                                extra=log_extra(
                                    MAICPhase.FILL_IMAGES,
                                    classroom_id,
                                    metric="image_fill_index_shift",
                                    outcome="index_shift_detected",
                                    diff_key=str(key),
                                ),
                            )
                            continue
                        fresh_scenes[s_idx]["content"]["elements"][el_idx]["src"] = url
                except (IndexError, KeyError, TypeError):
                    # The scene/slide/element was removed by a concurrent PATCH —
                    # skip silently; we can't apply a diff to a removed element.
                    logger.debug(
                        "fill_classroom_images: diff key %s no longer exists in fresh content, skipping",
                        key,
                        extra=log_extra(
                            MAICPhase.FILL_IMAGES,
                            classroom_id,
                            metric="image_fill_not_found",
                            outcome="element_removed",
                            diff_key=str(key),
                        ),
                    )

            # ── PERF-P0-4 cutover: shard-only write ───────────────────────────
            # Pre-cutover this site dual-wrote the legacy ``content`` JSONField
            # alongside ``content_scenes`` so callers still reading the legacy
            # blob saw fresh image URLs. Post-cutover the shard is the sole
            # source of truth — every reader has been switched to
            # ``composed_content`` / direct shard access. The legacy column is
            # left untouched here (NOT dropped — that's a follow-up migration
            # once we've shipped one full release on shard-only reads).
            #
            # AUDIT-2026-04-25-8: route the shard write through
            # ``update_content_section`` (BATCH-6-F7 cross-tenant guard
            # choke-point) rather than mutating ``fresh.content_scenes``
            # directly. ``save=False`` stages the change; we then save the
            # shard + flag in a single round-trip below.
            fresh.update_content_section("scenes", fresh_scenes, save=False)
            # AUDIT-2026-04-25-10: keep ``images_pending=True`` when work
            # was deferred so the FE poll loop continues to spin until the
            # follow-up task finishes the remaining scenes.
            fresh.images_pending = bool(deferred_indices)

            fresh.save(update_fields=["content_scenes", "images_pending", "updated_at"])

        # AUDIT-2026-04-25-10: enqueue the follow-up task OUTSIDE the
        # transaction so the broker dispatch can't roll back along with a
        # late DB error. We capture deferred_indices from the Phase-1
        # break above; if empty, this is a no-op and the task ends here.
        if deferred_indices:
            try:
                fill_classroom_images.apply_async(
                    args=[classroom_id],
                    kwargs={"scene_indices": deferred_indices},
                    countdown=IMAGE_FILL_DEFERRED_COUNTDOWN_SECS,
                )
                logger.info(
                    "fill_classroom_images: deferred %d scenes for follow-up "
                    "task on classroom %s",
                    len(deferred_indices), classroom_id,
                    extra=log_extra(
                        MAICPhase.FILL_IMAGES,
                        classroom_id,
                        metric="image_fill_deferred_enqueued",
                        outcome="phase1_deferral_enqueued",
                        deferred_count=len(deferred_indices),
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                # If the broker is unreachable we still don't want the
                # whole task to look failed — the FE will eventually time
                # out on images_pending=True and the next publish/retry
                # path can re-enqueue. Log and recover.
                logger.error(
                    "fill_classroom_images: failed to enqueue deferred "
                    "task for classroom %s: %s",
                    classroom_id, exc,
                    extra=log_extra(
                        MAICPhase.FILL_IMAGES,
                        classroom_id,
                        metric="image_fill_deferred_enqueue_error",
                        outcome="enqueue_error",
                        error_type=type(exc).__name__,
                    ),
                )

        logger.info(
            "fill_classroom_images complete",
            extra=log_extra(
                MAICPhase.FILL_IMAGES,
                classroom_id,
                metric="image_fill_complete",
                scene_count=len(target_indices),
                total_images=total_images,
                filled_images=filled_images,
                provider_outcomes=provider_outcomes,
            ),
        )
    except Exception:
        # Make sure images_pending is cleared even on unexpected failures so
        # the frontend doesn't spin indefinitely. The classroom still renders
        # with placeholder URLs in that case.
        # Note: set_current_tenant is already active here (called before the
        # try block), so this recovery save is tenant-scoped correctly.
        try:
            MAICClassroom.all_objects.filter(id=classroom_id).update(
                images_pending=False
            )
            logger.warning(
                "fill_classroom_images: fail-open recovery — cleared images_pending for classroom %s",
                classroom_id,
                extra=log_extra(
                    MAICPhase.FILL_IMAGES,
                    classroom_id,
                    metric="image_fill_recovery",
                    outcome="recovery",
                ),
            )
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        clear_current_tenant()


def _fill_elements(
    elements: list,
    *,
    provider_outcomes: dict[str, int],
) -> tuple[int, int]:
    """Walk an elements list and fetch images for any element with empty src.

    Mutates ``elements`` in-place.

    Returns:
        (total_image_elements_seen, filled_image_elements)

    Provider inference for ``provider_outcomes``:
        - "unsplash"      — URL contains "unsplash.com"
        - "pexels"        — URL contains "pexels.com"
        - "pollinations"  — URL contains "pollinations.ai"
        - "storage"       — URL contains "/media/" (saved to Django storage)
        - "placeholder"   — URL starts with "https://placehold.co/"
        - "data_url"      — URL starts with "data:" (Imagen/NanoBanana without storage)
        - "already_filled"— element already had a valid http(s) URL
        - "other"         — any other URL
    """
    from apps.courses.image_service import fetch_scene_image

    total = 0
    filled = 0

    for element in elements:
        if not isinstance(element, dict):
            continue
        if element.get("type") != "image":
            continue

        total += 1
        existing_src = (element.get("src") or "").strip()

        # Skip elements that already have a valid http(s) URL.  This is the
        # idempotency check — re-running on a partially-filled classroom
        # only fetches images for remaining empty slots.
        if existing_src and (
            existing_src.startswith("https://")
            or existing_src.startswith("http://")
        ):
            provider_outcomes["already_filled"] = (
                provider_outcomes.get("already_filled", 0) + 1
            )
            continue

        # Fetch (or get placeholder from circuit breaker).
        keyword = element.get("content", "educational illustration")
        try:
            url = fetch_scene_image(keyword)
        except Exception as exc:  # noqa: BLE001 — fail open
            logger.warning(
                "fill_classroom_images: image fetch failed keyword=%r err=%s",
                keyword, exc,
            )
            url = "https://placehold.co/800x450?text=image"

        element["src"] = url
        filled += 1

        # Infer provider from URL for observability.
        provider = _infer_provider(url)
        provider_outcomes[provider] = provider_outcomes.get(provider, 0) + 1

    return total, filled


def _infer_provider(url: str) -> str:
    """Infer the image provider from a resolved URL for observability logging."""
    if not url:
        return "empty"
    if url.startswith("data:"):
        return "data_url"
    if "placehold.co" in url:
        return "placeholder"
    if "unsplash.com" in url:
        return "unsplash"
    if "pexels.com" in url:
        return "pexels"
    if "pollinations.ai" in url:
        return "pollinations"
    if "/media/" in url:
        return "storage"
    return "other"


# ─── PERF-P0-5: chord-orchestrated TTS pipeline ─────────────────────────────
#
# Topology:
#
#     pre_generate_classroom_tts(classroom_id)        [default queue]
#         │  builds N per-scene work items
#         │
#         ├── _tts_one_scene(scene_payload)           [tts queue]
#         ├── _tts_one_scene(scene_payload)           [tts queue]
#         └── _tts_one_scene(scene_payload)           [tts queue]
#                          │  fan-in via chord
#                          ▼
#         _finalize_classroom_tts(results, …)         [tts queue]
#                          │
#                          └─ dual-write (shards + legacy content) under
#                             a single SELECT FOR UPDATE
#
# Per-scene tasks are routed to the dedicated ``tts`` queue (see
# ``config/celery.py``) so the worker pool can be sized to the TTS
# provider's rate limit independently of the default worker.  The
# orchestrator parent stays on the default queue so the publish
# endpoint's enqueue is not throttled by TTS capacity.

# ── Tunables ──
_TTS_MAX_ATTEMPTS = 3                    # per-action retry budget
_TTS_BACKOFF_BASE_SECONDS = 2            # 2**attempt seconds
_DEFAULT_AUDIO_MANIFEST = {
    "status": "generating",
    "progress": 0,
    "totalActions": 0,
    "completedActions": 0,
    "failedAudioIds": [],
    "generatedAt": None,
}


def _build_speech_payload(scene_idx, scene, classroom_id, tenant_id):
    """Extract the per-action payload that ``_tts_one_scene`` needs.

    We intentionally pass JSON-serialisable primitives only — Celery's JSON
    serializer rejects rich objects.  The scene's full ``actions`` list is
    not sent across the wire; only the speech actions that need work are.
    """
    actions_payload = []
    for action_idx, action in enumerate(scene.get("actions", [])):
        if action.get("type") != "speech":
            continue
        audio_id = action.get("audioId")
        voice_id = action.get("voiceId")
        if not audio_id or not voice_id:
            continue
        storage_key = (
            f"tenant/{tenant_id}/maic/tts/{classroom_id}/{audio_id}.mp3"
        )
        actions_payload.append({
            "action_idx": action_idx,
            "audio_id": audio_id,
            "voice_id": voice_id,
            "text": action.get("text", ""),
            "storage_key": storage_key,
            "existing_audio_url": action.get("audioUrl"),
        })
    return {
        "scene_idx": scene_idx,
        "actions": actions_payload,
    }


def _all_scenes_already_cached(scenes):
    """Return True iff every speech action already carries a valid audioUrl
    AND the publish endpoint already stamped audioId/voiceId.

    Used to short-circuit the chord dispatch when a re-publish does not
    change any speech text (the storage_exists check in ``_tts_one_scene``
    will keep it idempotent in any case, but skipping the chord saves
    a Redis round-trip per scene).
    """
    for scene in scenes:
        for action in scene.get("actions", []):
            if action.get("type") != "speech":
                continue
            if not action.get("audioUrl"):
                return False
    return True


@shared_task(
    name="apps.courses.maic_tasks.pre_generate_classroom_tts",
    # Retry only on transient infrastructure failures (DB disconnects, Redis
    # hiccups). Per-TTS-action failures are caught locally and recorded as
    # failedAudioIds without bouncing the whole task.
    autoretry_for=(OperationalError, DatabaseError, ConnectionError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def pre_generate_classroom_tts(classroom_id: str) -> None:
    """Orchestrator: fan-out per-scene TTS work onto the ``tts`` queue.

    Contract (unchanged from the pre-PERF-P0-5 sequential implementation):
    - The publish endpoint is expected to have stamped each speech action
      with ``audioId`` and ``voiceId`` and seeded ``audioManifest`` with
      ``status='generating'`` before enqueuing this task.
    - Actions already carrying an ``audioUrl`` are skipped (idempotence).
    - Each TTS call is retried up to 3 times with exponential back-off.
      A failure after retries adds the audioId to ``failedAudioIds`` but
      the loop continues.
    - Final status (set by ``_finalize_classroom_tts``):
        no failures   -> manifest.status='ready',   classroom='READY'
        some failures -> manifest.status='partial', classroom='READY'
        all failed    -> manifest.status='failed',  classroom='FAILED'

    PERF-P0-5: this orchestrator now dispatches a Celery ``chord`` of
    per-scene ``_tts_one_scene`` tasks (parallel fan-out on the dedicated
    ``tts`` queue), with ``_finalize_classroom_tts`` as the callback that
    performs the dual-write merge under a single transaction.

    The function still works as a synchronous fall-through when called
    directly (``pre_generate_classroom_tts(classroom_id)`` instead of
    ``.delay()``) — under ``CELERY_TASK_ALWAYS_EAGER`` or when no scenes
    require work, the chord short-circuits to an inline finalize.
    """
    # ── SPRINT-2-BATCH-9-F2: serialise concurrent orchestrator runs ─────
    # Acquire a short-lived advisory lock keyed on classroom_id BEFORE we
    # read the row, so two parallel publish-button calls cannot both pass
    # the ``_all_scenes_already_cached`` predicate and both dispatch
    # chords. ``cache.add`` returns True iff the key was absent — the
    # second caller short-circuits with skipped=True.
    lock_key = _ORCHESTRATOR_LOCK_KEY_TEMPLATE.format(classroom_id=classroom_id)
    try:
        acquired = cache.add(lock_key, "1", timeout=_ORCHESTRATOR_LOCK_TTL_SECONDS)
    except Exception:  # noqa: BLE001 — cache backend hiccup must not block orchestration
        logger.warning(
            "pre_generate_classroom_tts: cache.add failed for %s — proceeding without lock",
            classroom_id,
        )
        acquired = True
    if not acquired:
        logger.info(
            "pre_generate_classroom_tts: skipping concurrent run for classroom %s",
            classroom_id,
        )
        return {"skipped": True, "reason": "concurrent_orchestrator"}

    classroom = MAICClassroom.objects.get(id=classroom_id)

    # Ensure tenant-scoped managers keep working for any nested queries.
    set_current_tenant(classroom.tenant)
    try:
        # PERF-P0-4 cutover: shard-only read. Legacy ``content`` is no
        # longer mirrored; migration 0043 backfilled all rows.
        scenes = list(classroom.content_scenes or [])
        # audioManifest lives in content_meta; init if absent.
        meta = dict(classroom.content_meta or {})
        if "audioManifest" not in meta:
            meta["audioManifest"] = dict(_DEFAULT_AUDIO_MANIFEST)
        manifest = meta["audioManifest"]

        try:
            config = TenantAIConfig.objects.get(tenant=classroom.tenant)
        except TenantAIConfig.DoesNotExist:
            logger.info(
                "No TenantAIConfig for tenant %s — marking classroom failed",
                classroom.tenant_id,
            )
            manifest["status"] = "failed"
            manifest["generatedAt"] = datetime.now(timezone.utc).isoformat()
            # PERF-P0-4 cutover: shard-only write. The legacy ``content`` field
            # is no longer mirrored — every reader has been switched to
            # ``composed_content`` / shards.
            classroom.content_meta = meta
            classroom.status = "FAILED"
            classroom.save(update_fields=["content_meta", "status", "updated_at"])
            # AUDIT-2026-04-25-3: this early-return path does NOT dispatch
            # a chord, so no callback will fire to release the lock.
            # Release it inline before returning.
            try:
                cache.delete(lock_key)
            except Exception:  # noqa: BLE001
                pass
            return
        # config existence asserted via the try/except above — providers are
        # resolved inside ``_tts_one_scene`` from the classroom's tenant.
        # The early-existence check here ensures a missing config still
        # surfaces the FAILED state without enqueuing useless work.

        # Total speech-action count for the manifest header.
        speech_actions = [
            (scene_idx, action_idx, action)
            for scene_idx, scene in enumerate(scenes)
            for action_idx, action in enumerate(scene.get("actions", []))
            if action.get("type") == "speech"
        ]
        total = len(speech_actions)
        manifest["totalActions"] = total

        # ── Idempotent short-circuit ────────────────────────────────────
        # If every speech action already has an audioUrl, skip the chord
        # entirely. The per-action storage_exists() check inside the worker
        # would catch this anyway, but enqueuing N no-op tasks per scene is
        # wasteful when nothing has changed.
        if total == 0 or _all_scenes_already_cached(scenes):
            _finalize_classroom_tts.run(
                results=[
                    {"scene_idx": scene_idx, "audio_updates": []}
                    for scene_idx in range(len(scenes))
                ],
                classroom_id=classroom_id,
            )
            return

        # ── Build per-scene work units ───────────────────────────────────
        # One task per scene that contains ≥1 unfilled speech action.
        scene_payloads = []
        for scene_idx, scene in enumerate(scenes):
            payload = _build_speech_payload(
                scene_idx, scene, classroom_id, classroom.tenant_id,
            )
            # Skip scenes with nothing to do — keeps the chord narrow.
            if payload["actions"]:
                scene_payloads.append(payload)

        if not scene_payloads:
            # All scenes were empty / invalid — finalize immediately so the
            # manifest doesn't stay stuck at "generating" forever.
            _finalize_classroom_tts.run(
                results=[],
                classroom_id=classroom_id,
            )
            return

        # ── Fan-out via chord ────────────────────────────────────────────
        # AUDIT-2026-04-25-2: ``link_error`` fires the dedicated
        # ``_finalize_classroom_tts_failed`` handler (NOT the success-path
        # finalizer). Celery's link_error semantics call the linked sig
        # with the FAILED task's UUID-string as the first positional arg —
        # not a chord-results list. The success-path finalizer iterates
        # ``results`` as a list of dicts; if it's invoked with a UUID
        # string, the for-loop iterates characters, every entry fails the
        # ``isinstance(_, dict)`` guard, and the callback wrongly flips
        # status to READY with no audio. The dedicated failed handler
        # treats any invocation as "at least one chord member crashed"
        # and marks the classroom FAILED.
        #
        # AUDIT-2026-04-25-3: lock ownership transfers from the
        # orchestrator to whichever finalizer eventually runs. Both
        # ``_finalize_classroom_tts`` (success path) and
        # ``_finalize_classroom_tts_failed`` (link_error path) release
        # the lock when they complete. We do NOT release here in the
        # happy path — ``chord(header)(callback)`` only DISPATCHES; the
        # chord itself may run for minutes. Releasing now would let a
        # concurrent publish dispatch a second chord that races on
        # ``content_scenes`` / ``audioManifest`` writes.
        error_callback = _finalize_classroom_tts_failed.s(
            classroom_id=classroom_id,
        )
        header = [
            _tts_one_scene.s(classroom_id, payload).set(
                link_error=error_callback,
            )
            for payload in scene_payloads
        ]
        callback = _finalize_classroom_tts.s(classroom_id=classroom_id).set(
            link_error=error_callback,
        )
        try:
            chord(header)(callback)
        except Exception:
            # Broker unreachable / chord dispatch failed: the callback
            # will NEVER run, so the orchestrator must release the lock
            # itself before re-raising for Celery's autoretry_for to
            # pick up. (The 5-minute TTL is the ultimate safety net.)
            try:
                cache.delete(lock_key)
            except Exception:  # noqa: BLE001
                pass
            raise
        # Chord successfully dispatched: lock ownership now belongs to
        # whichever finalizer runs (success or failed). Do NOT release
        # here — the chord is still in-flight on the ``tts`` queue.
        chord_dispatched = True
    except Exception:
        # Anything that raised BEFORE chord dispatch (e.g. DB read error)
        # means the callback will never run — release the lock here so
        # the next publish attempt isn't blocked by the 5-minute TTL.
        chord_dispatched = locals().get("chord_dispatched", False)
        if not chord_dispatched:
            try:
                cache.delete(lock_key)
            except Exception:  # noqa: BLE001
                pass
        raise
    finally:
        clear_current_tenant()


@shared_task(
    name="apps.courses.maic_tasks.tts.one_scene",
    autoretry_for=(OperationalError, DatabaseError, ConnectionError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def _tts_one_scene(classroom_id: str, payload: dict) -> dict:
    """Fetch + upload TTS audio for every speech action in ONE scene.

    Per-action behaviour matches the legacy sequential implementation:
    - 3 attempts with exponential back-off on TTS provider errors.
    - storage_exists() short-circuit when the URL is already cached.
    - On final failure the audio_id is recorded; the scene-task does NOT
      raise, so a single bad voice does not abort the whole chord.

    Args:
        classroom_id: parent classroom UUID — needed to load the
            ``TenantAIConfig`` for the correct provider/voice settings.
        payload: ``{"scene_idx": int, "actions": [{action_idx, audio_id,
            voice_id, text, storage_key, existing_audio_url}]}`` produced
            by ``_build_speech_payload``.

    Returns:
        Dict consumed by ``_finalize_classroom_tts``::

            {
              "scene_idx": int,
              "audio_updates": [{"action_idx": int, "audio_url": str}, …],
              "failed_audio_ids": [str, …],
            }

        ``audio_updates`` only contains successful uploads; failures are
        listed separately so the finalizer can append them to the
        manifest's ``failedAudioIds`` without overwriting any cached URLs.
    """
    classroom = MAICClassroom.all_objects.get(id=classroom_id)
    set_current_tenant(classroom.tenant)
    try:
        try:
            config = TenantAIConfig.objects.get(tenant=classroom.tenant)
        except TenantAIConfig.DoesNotExist:
            # Mid-flight config deletion — fail every action in this scene
            # so the finalizer's status calculation reflects reality.
            return {
                "scene_idx": payload["scene_idx"],
                "audio_updates": [],
                "failed_audio_ids": [a["audio_id"] for a in payload["actions"]],
            }

        audio_updates: list[dict] = []
        failed_audio_ids: list[str] = []

        for action_payload in payload["actions"]:
            audio_id = action_payload["audio_id"]
            voice_id = action_payload["voice_id"]
            text = action_payload["text"]
            storage_key = action_payload["storage_key"]

            # Idempotent re-publish: skip if we already have a URL AND the
            # underlying storage file still exists.
            if action_payload.get("existing_audio_url") and storage_exists(storage_key):
                continue

            audio_bytes = None
            for attempt in range(_TTS_MAX_ATTEMPTS):
                try:
                    audio_bytes = generate_tts_audio(text, config, voice_id=voice_id)
                    if audio_bytes:
                        break
                except Exception as e:  # noqa: BLE001 — TTS provider errors vary wildly
                    logger.warning(
                        "TTS attempt %d failed for %s: %s",
                        attempt + 1, audio_id, e,
                    )
                    if attempt < _TTS_MAX_ATTEMPTS - 1:
                        time.sleep(_TTS_BACKOFF_BASE_SECONDS ** attempt)

            if audio_bytes:
                try:
                    url = storage_upload(storage_key, audio_bytes, "audio/mpeg")
                    audio_updates.append({
                        "action_idx": action_payload["action_idx"],
                        "audio_url": url,
                    })
                except Exception as e:  # noqa: BLE001
                    logger.error("Storage upload failed for %s: %s", audio_id, e)
                    failed_audio_ids.append(audio_id)
            else:
                failed_audio_ids.append(audio_id)

        return {
            "scene_idx": payload["scene_idx"],
            "audio_updates": audio_updates,
            "failed_audio_ids": failed_audio_ids,
        }
    finally:
        clear_current_tenant()


@shared_task(
    name="apps.courses.maic_tasks.tts.finalize",
    autoretry_for=(OperationalError, DatabaseError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def _finalize_classroom_tts(results, classroom_id: str) -> None:
    """Chord callback: merge per-scene results into the classroom + dual-write.

    Args:
        results: list of dicts returned by ``_tts_one_scene`` (one per
            scene). Failed siblings may be missing from the list; we treat
            absent entries as "no updates" and let the manifest still
            close out so the FE doesn't spin indefinitely.
        classroom_id: parent classroom UUID.

    Behaviour:
        Performs the SPRINT-2-BATCH-6-F5 dual-write — rebuilds the
        ``audioManifest`` + ``scenes`` on top of the FRESH content from
        the DB (preserving any teacher PATCH that landed mid-flight) and
        writes both the ``content_scenes`` shard and the legacy
        ``content`` field in a single ``select_for_update`` transaction.
    """
    classroom = MAICClassroom.all_objects.get(id=classroom_id)
    set_current_tenant(classroom.tenant)
    try:
        # ── Re-read under row lock so concurrent teacher PATCHes are not
        #    clobbered. We only mutate the fields we own (audio URLs +
        #    audioManifest); everything else is left as-the-DB-has-it.
        with transaction.atomic():
            fresh = MAICClassroom.all_objects.select_for_update().get(id=classroom_id)
            # PERF-P0-4 cutover: shard-only read.
            scenes = list(fresh.content_scenes or [])
            meta = dict(fresh.content_meta or {})
            if "audioManifest" not in meta:
                meta["audioManifest"] = dict(_DEFAULT_AUDIO_MANIFEST)
            manifest = meta["audioManifest"]

            # ── Merge per-scene audio updates into the live scenes list ──
            results_list = list(results or [])
            failed: list[str] = list(manifest.get("failedAudioIds") or [])

            for scene_result in results_list:
                if not isinstance(scene_result, dict):
                    # link_error path may pass an exception repr; ignore it
                    # and continue so partial successes still land.
                    continue
                scene_idx = scene_result.get("scene_idx")
                if scene_idx is None or not (0 <= scene_idx < len(scenes)):
                    continue
                actions = scenes[scene_idx].get("actions", []) or []
                for upd in scene_result.get("audio_updates", []) or []:
                    a_idx = upd.get("action_idx")
                    url = upd.get("audio_url")
                    if a_idx is None or not url:
                        continue
                    if not (0 <= a_idx < len(actions)):
                        continue
                    actions[a_idx]["audioUrl"] = url
                for fid in scene_result.get("failed_audio_ids", []) or []:
                    if fid and fid not in failed:
                        failed.append(fid)

            # ── Compute final status from the merged scenes ──────────────
            speech_actions = [
                action
                for scene in scenes
                for action in scene.get("actions", [])
                if action.get("type") == "speech"
            ]
            total = len(speech_actions)
            completed = sum(
                1 for a in speech_actions if a.get("audioUrl") or a.get("audioId") in failed
            )

            if not failed:
                manifest["status"] = "ready"
                fresh.status = "READY"
            elif len(failed) < total:
                manifest["status"] = "partial"
                fresh.status = "READY"
            else:
                manifest["status"] = "failed"
                fresh.status = "FAILED"

            manifest["progress"] = (
                int(completed / total * 100) if total else 100
            )
            manifest["totalActions"] = total
            manifest["completedActions"] = completed
            manifest["failedAudioIds"] = list(failed)
            manifest["generatedAt"] = datetime.now(timezone.utc).isoformat()

            # ── PERF-P0-4 cutover: shard-only write ──────────────────────
            # Pre-cutover this site dual-wrote the legacy ``content`` field
            # alongside ``content_scenes`` / ``content_meta``. Post-cutover
            # all readers go through ``composed_content`` / shards, so the
            # legacy mirror was dropped. The legacy column itself stays
            # (NOT dropped) until one full release ships on shard-only
            # reads — see PERF-P0-4 follow-up note.
            #
            # AUDIT-2026-04-25-8: route both shard writes through
            # ``update_content_section`` so the BATCH-6-F7 cross-tenant
            # guard fires if ``set_current_tenant`` was not called.
            fresh.update_content_section("scenes", scenes, save=False)
            # Pass the FULL meta dict through the meta-merge path. The
            # merge updates audioManifest in-place without clobbering any
            # sibling top-level shard keys.
            fresh.update_content_section("meta", meta, save=False)
            fresh.save(update_fields=[
                "content_scenes", "content_meta", "status", "updated_at",
            ])
    finally:
        clear_current_tenant()
        # AUDIT-2026-04-25-3: success-path finalizer owns the orchestrator
        # lock once chord(header)(callback) returned. Release it now that
        # the chord has actually completed (not when the orchestrator
        # merely dispatched). The 5-minute TTL on the cache key remains
        # the safety net for crashed callbacks.
        _release_orchestrator_lock(classroom_id)


def _release_orchestrator_lock(classroom_id: str) -> None:
    """Release the orchestrator concurrency lock for a classroom.

    Lifecycle (AUDIT-2026-04-25-3):
        1. ``pre_generate_classroom_tts`` acquires the lock via
           ``cache.add(lock_key, "1", timeout=300)``.
        2. The orchestrator dispatches the chord and returns. The lock
           STAYS HELD — the chord may run for minutes on the ``tts``
           queue.
        3. Either ``_finalize_classroom_tts`` (chord-success callback)
           OR ``_finalize_classroom_tts_failed`` (link_error callback)
           runs when the chord completes. Both call this helper to
           release the lock.
        4. Crash safety: if a callback never runs (worker dies,
           link_error didn't fire), the 5-minute cache TTL releases
           the lock so the next publish unblocks.

    Args:
        classroom_id: UUID string of the classroom whose lock to release.
    """
    lock_key = _ORCHESTRATOR_LOCK_KEY_TEMPLATE.format(
        classroom_id=classroom_id,
    )
    try:
        cache.delete(lock_key)
    except Exception:  # noqa: BLE001 — cache hiccup is not fatal; TTL releases
        logger.warning(
            "release_orchestrator_lock: cache.delete failed for %s — "
            "relying on TTL fallback",
            classroom_id,
        )


@shared_task(
    name="apps.courses.maic_tasks.tts.finalize_failed",
    autoretry_for=(OperationalError, DatabaseError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def _finalize_classroom_tts_failed(*args, classroom_id: str) -> None:
    """Chord ``link_error`` handler — mark the classroom FAILED.

    AUDIT-2026-04-25-2 fix.

    Celery's ``link_error`` callback semantics: when a chord member task
    raises a hard exception, the linked signature is invoked with the
    FAILED task's request UUID as the first POSITIONAL arg — NOT a
    chord-results list. The previous wiring used the success-path
    finalizer ``_finalize_classroom_tts`` as the link_error, which
    iterates ``results`` as if it were a list of dicts. When given a
    UUID string, the for-loop iterated characters, every entry failed
    the ``isinstance(_, dict)`` guard, ``failed`` stayed empty, and the
    callback wrongly flipped status to READY with no audio URLs.

    This dedicated handler treats any invocation as "at least one chord
    member crashed" and marks the classroom FAILED + manifest=failed.
    It NEVER touches per-action audio URLs and never iterates
    ``results``. Lock release lives in ``finally`` so a re-publish is
    not blocked by the 5-minute TTL.

    Args:
        *args: Celery may pass the failed task's UUID-string as the
            first positional argument. We accept and ignore it; the
            classroom_id kwarg is the only thing we need.
        classroom_id: UUID of the parent classroom (wired via
            ``.s(classroom_id=...)`` in the orchestrator).

    Idempotence:
        Safe to call twice. If the success-path finalizer raced and
        already set status=READY (extremely unlikely — link_error fires
        only when a member RAISED, so the chord-success callback would
        not have run with full results), we still flip to FAILED on the
        assumption that link_error means at least one scene's audio is
        unrecoverable.
    """
    failed_task_uuid = args[0] if args else None
    logger.warning(
        "MAIC TTS chord aborted: classroom=%s failed_task_uuid=%s — "
        "marking classroom FAILED via link_error handler",
        classroom_id, failed_task_uuid,
    )

    try:
        classroom = MAICClassroom.all_objects.get(id=classroom_id)
    except MAICClassroom.DoesNotExist:
        # Classroom was deleted while the chord was in flight. Still
        # release the lock so a future re-creation isn't blocked.
        _release_orchestrator_lock(classroom_id)
        return

    set_current_tenant(classroom.tenant)
    try:
        with transaction.atomic():
            fresh = MAICClassroom.all_objects.select_for_update().get(
                id=classroom_id,
            )
            # PERF-P0-4 cutover: shard-only read.
            meta = dict(fresh.content_meta or {})
            if "audioManifest" not in meta:
                meta["audioManifest"] = dict(_DEFAULT_AUDIO_MANIFEST)
            manifest = dict(meta["audioManifest"])
            manifest["status"] = "failed"
            manifest["generatedAt"] = datetime.now(timezone.utc).isoformat()
            meta["audioManifest"] = manifest

            # PERF-P0-4 cutover: shard-only write. The legacy ``content``
            # field is no longer mirrored; every reader has been switched
            # to ``composed_content`` / shards.
            #
            # AUDIT-2026-04-25-8: route the meta shard write through
            # ``update_content_section`` so the BATCH-6-F7 cross-tenant
            # guard fires if ``set_current_tenant`` was not called.
            fresh.update_content_section("meta", meta, save=False)
            fresh.status = "FAILED"
            fresh.save(update_fields=[
                "content_meta", "status", "updated_at",
            ])
    finally:
        clear_current_tenant()
        # AUDIT-2026-04-25-3: failed-path finalizer owns the lock once
        # the orchestrator dispatched the chord. Release it so the next
        # publish attempt (typically a retry from the FE after seeing
        # FAILED status) isn't blocked by the 5-minute TTL.
        _release_orchestrator_lock(classroom_id)
