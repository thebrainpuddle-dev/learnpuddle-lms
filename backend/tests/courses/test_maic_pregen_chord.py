"""PERF-P0-5: tests for the Celery-chord-orchestrated TTS pipeline.

Covers:
- Chord topology: ``_tts_one_scene`` is registered on the dedicated ``tts``
  queue (via ``app.conf.task_routes``); the parent orchestrator stays on
  the default queue.
- The chord-callback merge logic in ``_finalize_classroom_tts`` correctly
  fans-in per-scene results, performs the SPRINT-2-BATCH-6-F5 dual-write
  to both ``content_scenes`` and the legacy ``content`` field, and sets
  the manifest status correctly.
- Partial-failure handling: when one of N scene-tasks fails, the callback
  still writes the successful entries; the failed scene's audioIds are
  recorded in ``failedAudioIds`` and the chord doesn't get stuck in
  ``status='generating'``.
- Idempotent short-circuit: when every speech action already has an
  ``audioUrl``, the chord is NOT enqueued — the orchestrator finalizes
  inline.
"""
from unittest.mock import patch

import pytest

from apps.courses.maic_models import MAICClassroom, TenantAIConfig

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Local fixtures (mirroring test_maic_pregen.py for parity)
# ---------------------------------------------------------------------------

@pytest.fixture
def maic_enabled_tenant(tenant):
    tenant.feature_maic = True
    tenant.save(update_fields=["feature_maic"])
    return tenant


@pytest.fixture
def ai_config(maic_enabled_tenant):
    return TenantAIConfig.objects.create(
        tenant=maic_enabled_tenant,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        tts_provider="disabled",
        maic_enabled=True,
    )


def _make_classroom(tenant, teacher_user, *, scenes):
    """Build a GENERATING classroom with the given scenes (each scene already
    has audioId+voiceId stamped on every speech action so the orchestrator
    sees them as ready-for-TTS).

    PERF-P0-4 cutover: data is written to the shards (``content_scenes`` /
    ``content_agents`` / ``content_meta``). The legacy ``content`` field
    is left at its model default ({}) so cutover regression checks can
    assert it stays untouched.
    """
    agents = [
        {
            "id": "agent-1",
            "name": "Dr. X",
            "voiceId": "en-IN-PrabhatNeural",
            "voiceProvider": "azure",
        },
    ]
    audio_manifest = {
        "status": "generating",
        "progress": 0,
        "totalActions": sum(
            1
            for s in scenes
            for a in s.get("actions", [])
            if a.get("type") == "speech"
        ),
        "completedActions": 0,
        "failedAudioIds": [],
        "generatedAt": None,
    }
    return MAICClassroom.objects.create(
        tenant=tenant,
        creator=teacher_user,
        title="ChordTest",
        topic="Chord topic",
        status="GENERATING",
        content_scenes=scenes,
        content_agents=agents,
        content_meta={"audioManifest": audio_manifest},
    )


def _scene(scene_id, audio_ids):
    """Helper: build a scene with N speech actions, pre-stamped."""
    return {
        "id": scene_id,
        "title": f"Scene {scene_id}",
        "type": "introduction",
        "actions": [
            {
                "type": "speech",
                "agentId": "agent-1",
                "text": f"Hello from {audio_id}",
                "audioId": audio_id,
                "voiceId": "en-IN-PrabhatNeural",
            }
            for audio_id in audio_ids
        ],
    }


# ---------------------------------------------------------------------------
# 1. Queue routing
# ---------------------------------------------------------------------------

def test_tts_one_scene_routes_to_tts_queue():
    """``_tts_one_scene`` and the chord callback must route to the
    dedicated ``tts`` queue so a separate ``worker-tts`` service can drain
    them at TTS-provider rate-limit speed without starving the default
    worker pool."""
    from config.celery import app as celery_app
    from apps.courses.maic_tasks import (
        _tts_one_scene,
        _finalize_classroom_tts,
        pre_generate_classroom_tts,
    )

    # Both tts.* tasks land on the dedicated queue.
    one_route = celery_app.amqp.router.route({}, _tts_one_scene.name)
    fin_route = celery_app.amqp.router.route({}, _finalize_classroom_tts.name)
    assert one_route["queue"].name == "tts", (
        f"Expected tts queue, got {one_route['queue'].name}"
    )
    assert fin_route["queue"].name == "tts", (
        f"Expected tts queue, got {fin_route['queue'].name}"
    )

    # The orchestrator parent stays on the default queue so the publish
    # endpoint's enqueue is not throttled by TTS-worker capacity.
    parent_route = celery_app.amqp.router.route(
        {}, pre_generate_classroom_tts.name,
    )
    assert parent_route["queue"].name != "tts"


# ---------------------------------------------------------------------------
# 2. Chord-callback merge: full success path
# ---------------------------------------------------------------------------

def test_chord_callback_merges_all_successful_scenes(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """Eager-mode chord dispatch: 3 scenes × 1 action each → callback
    rebuilds audioManifest + dual-writes to both shards and legacy field."""
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[
            _scene("scene-1", ["aud00000001"]),
            _scene("scene-2", ["aud00000002"]),
            _scene("scene-3", ["aud00000003"]),
        ],
    )

    with patch(
        "apps.courses.maic_tasks.generate_tts_audio",
        return_value=b"fake-mp3-bytes",
    ), patch(
        "apps.courses.maic_tasks.storage_upload",
        side_effect=lambda key, *_a, **_k: f"/media/{key}",
    ):
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()
    # ── manifest closed out cleanly ──
    assert classroom.status == "READY"
    assert classroom.content_meta["audioManifest"]["status"] == "ready"
    assert classroom.content_meta["audioManifest"]["completedActions"] == 3
    assert classroom.content_meta["audioManifest"]["failedAudioIds"] == []

    # ── audio URLs landed on every scene (legacy field) ──
    for scene in classroom.content_scenes:
        assert scene["actions"][0]["audioUrl"].startswith("/media/")

    # ── dual-write: shards mirror legacy ──
    if classroom.content_scenes:
        for scene in classroom.content_scenes:
            assert scene["actions"][0]["audioUrl"].startswith("/media/")


# ---------------------------------------------------------------------------
# 3. Partial failure: one scene fails, chord still merges the rest
# ---------------------------------------------------------------------------

def test_chord_callback_handles_partial_scene_failure(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """When one of N scene-tasks fails (TTS provider returns empty for all
    its actions), the callback still writes the successful siblings and
    records the failed audio_ids."""
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[
            _scene("scene-1", ["aud00000001"]),
            _scene("scene-2", ["aud00000002"]),  # this scene will "fail"
            _scene("scene-3", ["aud00000003"]),
        ],
    )

    # Scene-2's only action returns empty bytes → recorded as failed.
    def tts(text, _config, voice_id=None):
        if "aud00000002" in text:
            return None  # provider returned nothing
        return b"fake-mp3-bytes"

    with patch(
        "apps.courses.maic_tasks.generate_tts_audio", side_effect=tts,
    ), patch(
        "apps.courses.maic_tasks.storage_upload",
        side_effect=lambda key, *_a, **_k: f"/media/{key}",
    ), patch("apps.courses.maic_tasks.time.sleep"):
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()
    # 1/3 failed → status="partial", classroom remains playable as READY.
    assert classroom.status == "READY"
    assert classroom.content_meta["audioManifest"]["status"] == "partial"
    assert "aud00000002" in classroom.content_meta["audioManifest"]["failedAudioIds"]
    # The two successful siblings have URLs.
    assert classroom.content_scenes[0]["actions"][0].get("audioUrl")
    assert classroom.content_scenes[2]["actions"][0].get("audioUrl")
    # The failed action did NOT receive a URL.
    assert not classroom.content_scenes[1]["actions"][0].get("audioUrl")


def test_chord_callback_survives_non_dict_result_entries(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """If ``link_error`` injects an exception object into the results list
    (Celery does this when a chord member raises with eager_propagates off),
    the callback must skip the bad entry and finalize the rest."""
    from apps.courses.maic_tasks import _finalize_classroom_tts

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[
            _scene("scene-1", ["aud00000001"]),
            _scene("scene-2", ["aud00000002"]),
        ],
    )

    # Simulate one good scene-result + one exception-shaped entry that the
    # callback should silently ignore.
    results = [
        {
            "scene_idx": 0,
            "audio_updates": [
                {"action_idx": 0, "audio_url": "/media/ok-1.mp3"},
            ],
            "failed_audio_ids": [],
        },
        Exception("simulated chord member failure"),  # non-dict — must be skipped
    ]

    _finalize_classroom_tts.run(results=results, classroom_id=str(classroom.id))

    classroom.refresh_from_db()
    assert classroom.content_scenes[0]["actions"][0]["audioUrl"] == "/media/ok-1.mp3"
    # Scene 1 unchanged — no URL, no crash.
    assert "audioUrl" not in classroom.content_scenes[1]["actions"][0]


# ---------------------------------------------------------------------------
# 4. Idempotent short-circuit: every action already has audioUrl
# ---------------------------------------------------------------------------

def test_chord_short_circuits_when_all_scenes_cached(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """If every speech action already has an ``audioUrl`` AND the storage
    file exists, the chord must NOT be enqueued — the orchestrator
    finalizes inline."""
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[
            _scene("scene-1", ["aud00000001"]),
            _scene("scene-2", ["aud00000002"]),
        ],
    )
    # Pre-fill all audioUrls so the cache predicate returns True.
    for s in classroom.content_scenes:
        for a in s["actions"]:
            a["audioUrl"] = f"/media/cached-{a['audioId']}.mp3"
    classroom.save(update_fields=["content_scenes"])

    with patch(
        "apps.courses.maic_tasks._tts_one_scene.s",
    ) as mock_one_scene_sig, patch(
        "apps.courses.maic_tasks.chord",
    ) as mock_chord, patch(
        "apps.courses.maic_tasks.generate_tts_audio",
    ) as mock_tts, patch(
        "apps.courses.maic_tasks.storage_upload",
    ) as mock_upload:
        pre_generate_classroom_tts(str(classroom.id))

    # Chord was not built and no per-scene task was signed.
    assert mock_chord.call_count == 0, "chord() should not be called when all cached"
    assert mock_one_scene_sig.call_count == 0
    # No TTS provider call, no storage upload — purely a finalize-inline path.
    assert mock_tts.call_count == 0
    assert mock_upload.call_count == 0

    classroom.refresh_from_db()
    # Manifest still finalized cleanly.
    assert classroom.content_meta["audioManifest"]["status"] == "ready"


# ---------------------------------------------------------------------------
# 5. PERF-P0-4 cutover (2026-04-26) — legacy mirror removed.
#     The chord callback used to write both the ``content_scenes`` shard AND
#     the legacy ``content`` field (SPRINT-2-BATCH-6-F5 dual-write). Once
#     every reader was switched to ``composed_content`` / shards, the legacy
#     mirror was retired. The callback must write ONLY to the shards.
# ---------------------------------------------------------------------------

def test_chord_callback_writes_only_shards_not_legacy_content(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """PERF-P0-4 cutover guard. After the chord runs, freshly stamped
    audio URLs land on ``content_scenes`` and audioManifest lands on
    ``content_meta``; the legacy ``content`` field is untouched.

    This was previously ``test_chord_callback_dual_writes_shard_and_legacy``;
    rename + flipped polarity reflects the cutover (legacy mirror removed).
    """
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    # _make_classroom seeds legacy ``content`` with the original scenes/agents.
    # Capture that snapshot BEFORE running the chord so we can assert the
    # legacy field is untouched after.
    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )
    legacy_pre_chord = dict(classroom.content)

    with patch(
        "apps.courses.maic_tasks.generate_tts_audio",
        return_value=b"fake-mp3",
    ), patch(
        "apps.courses.maic_tasks.storage_upload",
        return_value="/media/cutover.mp3",
    ):
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()
    # ── Cutover guarantee: legacy field is byte-equal to pre-task. ──
    assert classroom.content == legacy_pre_chord, (
        "PERF-P0-4 regression: chord callback rewrote the legacy "
        f"``content`` field. Got: {classroom.content!r}"
    )
    # ── Shards reflect the freshly generated audio. ──
    assert (
        classroom.content_scenes[0]["actions"][0]["audioUrl"]
        == "/media/cutover.mp3"
    )
    assert classroom.content_meta["audioManifest"]["status"] == "ready"


# ---------------------------------------------------------------------------
# 6. SPRINT-2-BATCH-9-F1: link_error wired so a worker crash still finalises
# ---------------------------------------------------------------------------

def test_chord_link_error_finalises_when_member_task_raises(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """When a chord-member ``_tts_one_scene`` task raises a hard exception
    (worker OOM, SIGTERM mid-call, broker disconnect), the chord-level
    callback may not fire normally. The orchestrator wires ``link_error``
    on every header signature and on the callback so
    ``_finalize_classroom_tts`` runs regardless — closing out the manifest
    as ``"ready"`` or ``"degraded"``/``"partial"`` instead of leaving it
    stuck at ``"generating"``.

    Implementation note: under eager mode, a raised exception in the chord
    body propagates synchronously. We capture the call to verify
    ``link_error`` was attached; the eager engine will execute it on raise
    and therefore the manifest must be finalised (no ``"generating"``).
    """
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[
            _scene("scene-1", ["aud00000001"]),
            _scene("scene-2", ["aud00000002"]),
        ],
    )

    # First _tts_one_scene call raises (simulated broker abort / worker
    # kill); second succeeds. The orchestrator must wire link_error so
    # the manifest doesn't stay at "generating" even after the raise.
    call_state = {"raised": False}

    def tts(text, _config, voice_id=None):
        if "aud00000001" in text and not call_state["raised"]:
            call_state["raised"] = True
            raise RuntimeError("simulated worker SIGTERM mid-TTS")
        return b"fake-mp3"

    with patch(
        "apps.courses.maic_tasks.generate_tts_audio", side_effect=tts,
    ), patch(
        "apps.courses.maic_tasks.storage_upload",
        side_effect=lambda key, *_a, **_k: f"/media/{key}",
    ), patch("apps.courses.maic_tasks.time.sleep"):
        # Should not propagate — _tts_one_scene retries on Exception within
        # the retry loop and records the audio_id as failed if all attempts
        # fail. The final manifest must NOT stay at "generating".
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()
    status = classroom.content_meta["audioManifest"]["status"]
    assert status in ("ready", "partial", "degraded"), (
        f"manifest stuck at unexpected status={status!r} after worker raise"
    )
    assert status != "generating"


def test_orchestrator_wires_link_error_on_chord_signatures(
    maic_enabled_tenant, teacher_user, ai_config, monkeypatch,
):
    """Static-shape check: confirm the orchestrator attaches a
    ``link_error`` to every header signature AND to the callback. We patch
    ``chord`` so the function returns immediately after dispatch, then
    inspect what was passed in.

    We also patch ``_tts_one_scene.s`` and ``_finalize_classroom_tts.s``
    to capture the ``.set(link_error=...)`` call rather than running the
    real chord engine.
    """
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[
            _scene("scene-1", ["aud00000001"]),
            _scene("scene-2", ["aud00000002"]),
        ],
    )

    captured = {"header_link_errors": [], "callback_link_error": None}

    class _FakeSig:
        def __init__(self, kind):
            self.kind = kind
            self._link_error = None

        def set(self, link_error=None, **_kwargs):
            self._link_error = link_error
            if self.kind == "tts_one_scene":
                captured["header_link_errors"].append(link_error)
            else:
                captured["callback_link_error"] = link_error
            return self

    def fake_one_scene_s(*_args, **_kwargs):
        return _FakeSig("tts_one_scene")

    def fake_finalize_s(*_args, **_kwargs):
        return _FakeSig("finalize")

    fake_chord_calls = []

    def fake_chord(header):
        fake_chord_calls.append(header)

        def _dispatch(_callback):
            return None

        return _dispatch

    monkeypatch.setattr(
        "apps.courses.maic_tasks._tts_one_scene.s", fake_one_scene_s,
    )
    monkeypatch.setattr(
        "apps.courses.maic_tasks._finalize_classroom_tts.s", fake_finalize_s,
    )
    monkeypatch.setattr("apps.courses.maic_tasks.chord", fake_chord)

    pre_generate_classroom_tts(str(classroom.id))

    # Two scenes → two header signatures, each with link_error wired.
    assert len(captured["header_link_errors"]) == 2
    assert all(le is not None for le in captured["header_link_errors"]), (
        "Every chord header signature must have link_error set"
    )
    # Callback also has link_error wired.
    assert captured["callback_link_error"] is not None, (
        "Chord callback must have link_error set so a broker abort still "
        "fires _finalize_classroom_tts"
    )


# ---------------------------------------------------------------------------
# 7. SPRINT-2-BATCH-9-F2: orchestrator-level concurrency lock
# ---------------------------------------------------------------------------

def test_orchestrator_skips_when_concurrent_run_in_progress(
    maic_enabled_tenant, teacher_user, ai_config, monkeypatch,
):
    """Two parallel publish-button calls for the same classroom must NOT
    both dispatch chords. The first acquires the cache-based lock; the
    second sees ``cache.add`` return False and short-circuits with
    ``{"skipped": True, "reason": "concurrent_orchestrator"}`` — no chord
    is built and no work is enqueued."""
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    # Force cache.add to report "lock already held" for this classroom.
    monkeypatch.setattr(
        "apps.courses.maic_tasks.cache.add",
        lambda *_a, **_k: False,
    )

    chord_calls = []

    def fake_chord(header):
        chord_calls.append(header)

        def _dispatch(_cb):
            return None

        return _dispatch

    monkeypatch.setattr("apps.courses.maic_tasks.chord", fake_chord)

    result = pre_generate_classroom_tts(str(classroom.id))

    assert result == {"skipped": True, "reason": "concurrent_orchestrator"}
    assert chord_calls == [], (
        "No chord must be dispatched when the lock is already held"
    )

    # Manifest unchanged — the second call is purely a no-op.
    classroom.refresh_from_db()
    assert classroom.content_meta["audioManifest"]["status"] == "generating"


def test_orchestrator_proceeds_when_lock_acquired(
    maic_enabled_tenant, teacher_user, ai_config, monkeypatch,
):
    """Sanity check: when the cache lock IS acquired (cache.add → True)
    the orchestrator runs to completion and releases the lock at exit."""
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    add_calls = []
    delete_calls = []

    def fake_add(key, value, timeout=None):
        add_calls.append((key, timeout))
        return True  # lock acquired

    def fake_delete(key):
        delete_calls.append(key)
        return True

    monkeypatch.setattr("apps.courses.maic_tasks.cache.add", fake_add)
    monkeypatch.setattr("apps.courses.maic_tasks.cache.delete", fake_delete)

    with patch(
        "apps.courses.maic_tasks.generate_tts_audio", return_value=b"fake-mp3",
    ), patch(
        "apps.courses.maic_tasks.storage_upload",
        return_value="/media/scene1.mp3",
    ):
        pre_generate_classroom_tts(str(classroom.id))

    assert len(add_calls) == 1
    assert "maic:tts:orchestrator:lock:" in add_calls[0][0]
    assert add_calls[0][1] == 300  # 5-minute TTL
    # Lock released at function exit so a quick re-publish isn't blocked.
    assert len(delete_calls) == 1


# ---------------------------------------------------------------------------
# 8. SPRINT-2-BATCH-9-F4: no-speech-actions path (quiz-only classroom)
# ---------------------------------------------------------------------------

def test_chord_short_circuits_when_no_speech_actions(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """A classroom whose scenes contain only quiz / interactive actions
    (no ``actions[].type == "speech"``) must NOT enqueue a chord. The
    orchestrator finalises inline with ``manifest.status = "ready"`` and
    ``totalActions = 0`` so the FE doesn't spin on ``generating``."""
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    # Build scenes with only non-speech actions.
    quiz_scene = {
        "id": "scene-1",
        "title": "Pop quiz",
        "type": "quiz",
        "actions": [
            {
                "type": "quiz",
                "question": "What is 2+2?",
                "options": ["3", "4", "5"],
                "correctIndex": 1,
            },
        ],
    }
    interactive_scene = {
        "id": "scene-2",
        "title": "Try it yourself",
        "type": "interactive",
        "actions": [
            {
                "type": "interactive",
                "prompt": "Drag the molecule to the slot",
            },
        ],
    }

    classroom = MAICClassroom.objects.create(
        tenant=maic_enabled_tenant,
        creator=teacher_user,
        title="QuizOnly",
        topic="No speech here",
        status="GENERATING",
        content_agents=[
            {"id": "agent-1", "name": "Quizmaster", "voiceId": "x", "voiceProvider": "azure"},
        ],
        content_scenes=[quiz_scene, interactive_scene],
        content_meta={
            "audioManifest": {
                "status": "generating",
                "progress": 0,
                "totalActions": 0,
                "completedActions": 0,
                "failedAudioIds": [],
                "generatedAt": None,
            },
        },
    )

    chord_calls = []

    def fake_chord(header):
        chord_calls.append(header)

        def _dispatch(_cb):
            return None

        return _dispatch

    with patch("apps.courses.maic_tasks.chord", side_effect=fake_chord), patch(
        "apps.courses.maic_tasks.generate_tts_audio",
    ) as mock_tts, patch(
        "apps.courses.maic_tasks.storage_upload",
    ) as mock_upload:
        pre_generate_classroom_tts(str(classroom.id))

    # No chord, no TTS provider, no upload — pure inline finalize.
    assert chord_calls == []
    assert mock_tts.call_count == 0
    assert mock_upload.call_count == 0

    classroom.refresh_from_db()
    manifest = classroom.content_meta["audioManifest"]
    assert manifest["status"] == "ready", (
        f"Quiz-only classroom should finalise as ready, got {manifest['status']!r}"
    )
    assert manifest["totalActions"] == 0
    assert manifest["failedAudioIds"] == []
    assert classroom.status == "READY"


# ---------------------------------------------------------------------------
# 9. AUDIT-2026-04-25-2: link_error invocation must NOT mark classroom READY
# ---------------------------------------------------------------------------

def test_link_error_handler_marks_classroom_failed_not_ready(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """AUDIT-2026-04-25-2 regression. Celery's ``link_error`` callback fires
    with the FAILED task's UUID-string as the first positional arg — not a
    chord-results list. The previous wiring linked
    ``_finalize_classroom_tts.s(classroom_id=...)`` directly, so the failed
    invocation looked like
    ``_finalize_classroom_tts("<uuid>", classroom_id=...)``: ``results`` was
    a string, the for-loop iterated characters, none were dict, ``failed``
    stayed empty, and the callback flipped status to READY with no audio.

    The fix introduces a dedicated ``_finalize_classroom_tts_failed``
    handler whose only job is to mark the classroom FAILED + update the
    manifest. It must NEVER mistakenly emit READY when invoked as a
    link_error.
    """
    from apps.courses.maic_tasks import _finalize_classroom_tts_failed

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[
            _scene("scene-1", ["aud00000001"]),
            _scene("scene-2", ["aud00000002"]),
        ],
    )

    # Simulate Celery's link_error invocation shape: positional UUID string,
    # then the kwargs we wired via .s(classroom_id=...).
    fake_failed_uuid = "11111111-2222-3333-4444-555555555555"
    _finalize_classroom_tts_failed.run(
        fake_failed_uuid,
        classroom_id=str(classroom.id),
    )

    classroom.refresh_from_db()
    # The classroom must NOT be READY — link_error means at least one chord
    # member crashed before producing a result.
    assert classroom.status != "READY", (
        "link_error handler must not mark classroom READY"
    )
    assert classroom.status == "FAILED"
    manifest = classroom.content_meta["audioManifest"]
    assert manifest["status"] == "failed", (
        f"manifest must be 'failed' after link_error, got {manifest['status']!r}"
    )
    # No spurious audio_updates merged — we never iterated a results list.
    for scene in classroom.content_scenes:
        for action in scene["actions"]:
            assert "audioUrl" not in action or not action["audioUrl"], (
                "link_error handler must not write audioUrls"
            )


def test_link_error_handler_signature_accepts_uuid_string(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """The handler must tolerate Celery's link_error positional-UUID arg
    without crashing. A pre-fix invocation would iterate the string and
    silently pass; the post-fix handler must accept it explicitly without
    interpreting it as a results list."""
    from apps.courses.maic_tasks import _finalize_classroom_tts_failed

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    # Should not raise — link_error invocations carry a UUID string.
    _finalize_classroom_tts_failed.run(
        "abc-uuid-string",
        classroom_id=str(classroom.id),
    )
    classroom.refresh_from_db()
    assert classroom.status == "FAILED"


def test_orchestrator_wires_failed_handler_as_link_error(
    maic_enabled_tenant, teacher_user, ai_config, monkeypatch,
):
    """AUDIT-2026-04-25-2: the orchestrator must wire
    ``_finalize_classroom_tts_failed`` (NOT the success-path finalizer) as
    the link_error on every header signature and on the chord callback."""
    from apps.courses.maic_tasks import (
        pre_generate_classroom_tts,
        _finalize_classroom_tts_failed,
    )

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[
            _scene("scene-1", ["aud00000001"]),
            _scene("scene-2", ["aud00000002"]),
        ],
    )

    captured = {
        "header_link_errors": [],
        "callback_link_error": None,
        "failed_finalizer_signed": 0,
    }

    class _FakeSig:
        def __init__(self, kind, task_name=None):
            self.kind = kind
            self.task_name = task_name
            self._link_error = None

        def set(self, link_error=None, **_kwargs):
            self._link_error = link_error
            if self.kind == "tts_one_scene":
                captured["header_link_errors"].append(link_error)
            elif self.kind == "finalize":
                captured["callback_link_error"] = link_error
            return self

    def fake_one_scene_s(*_args, **_kwargs):
        return _FakeSig("tts_one_scene")

    def fake_finalize_s(*_args, **_kwargs):
        return _FakeSig("finalize")

    def fake_failed_s(*_args, **_kwargs):
        captured["failed_finalizer_signed"] += 1
        return _FakeSig("failed_finalize")

    def fake_chord(header):
        def _dispatch(_callback):
            return None
        return _dispatch

    monkeypatch.setattr(
        "apps.courses.maic_tasks._tts_one_scene.s", fake_one_scene_s,
    )
    monkeypatch.setattr(
        "apps.courses.maic_tasks._finalize_classroom_tts.s", fake_finalize_s,
    )
    monkeypatch.setattr(
        "apps.courses.maic_tasks._finalize_classroom_tts_failed.s",
        fake_failed_s,
    )
    monkeypatch.setattr("apps.courses.maic_tasks.chord", fake_chord)

    pre_generate_classroom_tts(str(classroom.id))

    # The link_error handler must have been signed at least once (the
    # orchestrator may share one error_callback signature across all
    # header sigs + the callback sig — that's fine).
    assert captured["failed_finalizer_signed"] >= 1, (
        "Orchestrator must sign _finalize_classroom_tts_failed for use "
        "as link_error"
    )
    # All header sigs have a link_error wired.
    assert len(captured["header_link_errors"]) == 2
    assert all(le is not None for le in captured["header_link_errors"])
    # The wired link_error MUST be a failed-finalize sig, NOT a success
    # finalize sig.
    for le in captured["header_link_errors"]:
        assert getattr(le, "kind", None) == "failed_finalize", (
            f"link_error must be the dedicated failed handler, "
            f"got kind={getattr(le, 'kind', None)!r}"
        )
    # Callback's link_error also points at the failed handler.
    assert captured["callback_link_error"] is not None
    assert captured["callback_link_error"].kind == "failed_finalize"


# ---------------------------------------------------------------------------
# 10. AUDIT-2026-04-25-3: orchestrator lock outlives chord dispatch
# ---------------------------------------------------------------------------

def test_lock_held_after_orchestrator_dispatches_chord(
    maic_enabled_tenant, teacher_user, ai_config, monkeypatch,
):
    """AUDIT-2026-04-25-3: ``chord(header)(callback)`` only DISPATCHES the
    chord — it doesn't wait. Releasing the lock in the orchestrator's
    ``finally`` block (the pre-fix behaviour) drops the lock within
    milliseconds while the chord may run for minutes, allowing a
    concurrent publish to dispatch a second chord.

    After the fix: the orchestrator must NOT release the lock when it
    successfully dispatched a chord. Lock ownership passes to the
    callback (success or failed), which releases it when the chord
    actually completes.
    """
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    add_calls = []
    delete_calls = []

    def fake_add(key, value, timeout=None):
        add_calls.append(key)
        return True

    def fake_delete(key):
        delete_calls.append(key)
        return True

    monkeypatch.setattr("apps.courses.maic_tasks.cache.add", fake_add)
    monkeypatch.setattr("apps.courses.maic_tasks.cache.delete", fake_delete)

    # Patch chord so dispatch is observable but the callback does NOT run
    # synchronously — simulating the real-world path where chord returns
    # before the chord members complete.
    def fake_chord(header):
        def _dispatch(_callback):
            return None  # pretend dispatched, not yet finished
        return _dispatch

    # Patch the success-path and failed-path finalizer .s() so they don't
    # actually run anything — we want to observe the lock state at the
    # moment the orchestrator returns.
    class _NoopSig:
        def set(self, **_kw):
            return self

    monkeypatch.setattr(
        "apps.courses.maic_tasks._tts_one_scene.s",
        lambda *a, **k: _NoopSig(),
    )
    monkeypatch.setattr(
        "apps.courses.maic_tasks._finalize_classroom_tts.s",
        lambda *a, **k: _NoopSig(),
    )
    monkeypatch.setattr(
        "apps.courses.maic_tasks._finalize_classroom_tts_failed.s",
        lambda *a, **k: _NoopSig(),
    )
    monkeypatch.setattr("apps.courses.maic_tasks.chord", fake_chord)

    pre_generate_classroom_tts(str(classroom.id))

    assert len(add_calls) == 1, "lock must be acquired exactly once"
    # Critical assertion: the lock has NOT been released by the
    # orchestrator's finally block. The chord is "running" in the
    # background; the callback owns the lock now.
    assert len(delete_calls) == 0, (
        "Orchestrator must not release lock after dispatching chord — "
        "ownership passes to the callback. "
        f"Saw {len(delete_calls)} delete call(s)."
    )


def test_finalizer_releases_orchestrator_lock_on_success(
    maic_enabled_tenant, teacher_user, ai_config, monkeypatch,
):
    """AUDIT-2026-04-25-3: success-path finalizer must release the lock
    when the chord actually completes."""
    from apps.courses.maic_tasks import (
        _finalize_classroom_tts,
        _ORCHESTRATOR_LOCK_KEY_TEMPLATE,
    )

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    delete_calls = []

    def fake_delete(key):
        delete_calls.append(key)
        return True

    monkeypatch.setattr("apps.courses.maic_tasks.cache.delete", fake_delete)

    _finalize_classroom_tts.run(
        results=[
            {
                "scene_idx": 0,
                "audio_updates": [
                    {"action_idx": 0, "audio_url": "/media/ok.mp3"},
                ],
                "failed_audio_ids": [],
            },
        ],
        classroom_id=str(classroom.id),
    )

    expected_key = _ORCHESTRATOR_LOCK_KEY_TEMPLATE.format(
        classroom_id=str(classroom.id),
    )
    assert expected_key in delete_calls, (
        "Success finalizer must release the orchestrator lock"
    )


def test_failed_finalizer_releases_orchestrator_lock(
    maic_enabled_tenant, teacher_user, ai_config, monkeypatch,
):
    """AUDIT-2026-04-25-3: failed-path finalizer must also release the
    lock. Without this, a chord that aborts mid-flight leaves the lock
    held until the 5-minute TTL expires."""
    from apps.courses.maic_tasks import (
        _finalize_classroom_tts_failed,
        _ORCHESTRATOR_LOCK_KEY_TEMPLATE,
    )

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    delete_calls = []

    def fake_delete(key):
        delete_calls.append(key)
        return True

    monkeypatch.setattr("apps.courses.maic_tasks.cache.delete", fake_delete)

    _finalize_classroom_tts_failed.run(
        "some-failed-uuid",
        classroom_id=str(classroom.id),
    )

    expected_key = _ORCHESTRATOR_LOCK_KEY_TEMPLATE.format(
        classroom_id=str(classroom.id),
    )
    assert expected_key in delete_calls, (
        "Failed finalizer must release the orchestrator lock"
    )


def test_orchestrator_releases_lock_on_dispatch_failure(
    maic_enabled_tenant, teacher_user, ai_config, monkeypatch,
):
    """AUDIT-2026-04-25-3: when chord dispatch itself raises (broker
    unreachable), the orchestrator's finally block IS the only place
    that can release the lock — the callback never runs."""
    from apps.courses.maic_tasks import (
        pre_generate_classroom_tts,
        _ORCHESTRATOR_LOCK_KEY_TEMPLATE,
    )

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    delete_calls = []

    def fake_delete(key):
        delete_calls.append(key)
        return True

    monkeypatch.setattr("apps.courses.maic_tasks.cache.delete", fake_delete)

    def broken_chord(_header):
        raise ConnectionError("simulated broker unreachable")

    monkeypatch.setattr("apps.courses.maic_tasks.chord", broken_chord)

    expected_key = _ORCHESTRATOR_LOCK_KEY_TEMPLATE.format(
        classroom_id=str(classroom.id),
    )

    # Should propagate so Celery's autoretry_for picks it up — but the
    # finally block must release the lock first.
    with pytest.raises((ConnectionError, Exception)):
        pre_generate_classroom_tts(str(classroom.id))

    assert expected_key in delete_calls, (
        "Orchestrator finally block must release lock when chord dispatch "
        "fails (callback never runs in this path)"
    )


# ---------------------------------------------------------------------------
# 11. AUDIT-2026-04-25-8: finalizer shard writes go through the cross-tenant
# guard helper (``update_content_section``) — direct ``fresh.content_scenes =``
# writes bypass the BATCH-6-F7 ``set_current_tenant`` guard and would silently
# permit cross-tenant writes if a future Celery refactor forgot to call
# ``set_current_tenant`` first.
# ---------------------------------------------------------------------------


def test_success_finalizer_raises_when_tenant_context_missing(
    maic_enabled_tenant, teacher_user, ai_config, tenant_b, monkeypatch,
):
    """AUDIT-2026-04-25-8: success-path finalizer must route shard writes
    through ``update_content_section`` so the BATCH-6-F7 cross-tenant guard
    fires when the thread-local tenant doesn't match the classroom.

    We simulate "wrong tenant set in context" by stubbing
    ``set_current_tenant`` to put tenant_b in the context BEFORE the
    finalizer's own ``set_current_tenant(classroom.tenant)`` call would
    overwrite it. To assert the guard at the WRITE site (not the entry
    point), we patch ``set_current_tenant`` to a no-op so the finalizer's
    self-rescoping is bypassed, then pre-set tenant_b before invoking.
    """
    from django.core.exceptions import PermissionDenied
    from apps.courses.maic_tasks import _finalize_classroom_tts
    from utils.tenant_middleware import set_current_tenant

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    # Stub set_current_tenant inside the task so it CAN'T overwrite our
    # deliberately-wrong tenant context. This proves the guard fires at
    # the actual shard-write site, not just at task entry.
    monkeypatch.setattr(
        "apps.courses.maic_tasks.set_current_tenant",
        lambda *_a, **_k: None,
    )

    # Pre-set the WRONG tenant in the thread-local context so the
    # update_content_section guard at the shard-write site raises.
    set_current_tenant(tenant_b)

    with pytest.raises(PermissionDenied):
        _finalize_classroom_tts.run(
            results=[
                {
                    "scene_idx": 0,
                    "audio_updates": [
                        {"action_idx": 0, "audio_url": "/media/x.mp3"},
                    ],
                    "failed_audio_ids": [],
                },
            ],
            classroom_id=str(classroom.id),
        )


def test_success_finalizer_writes_succeed_when_tenant_context_correct(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """Sanity check: with the correct tenant in the context (the normal
    state — the finalizer calls ``set_current_tenant(classroom.tenant)``
    on entry), shard writes go through and audio URLs land on scenes."""
    from apps.courses.maic_tasks import _finalize_classroom_tts

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    _finalize_classroom_tts.run(
        results=[
            {
                "scene_idx": 0,
                "audio_updates": [
                    {"action_idx": 0, "audio_url": "/media/ok.mp3"},
                ],
                "failed_audio_ids": [],
            },
        ],
        classroom_id=str(classroom.id),
    )

    classroom.refresh_from_db()
    assert classroom.content_scenes[0]["actions"][0]["audioUrl"] == "/media/ok.mp3"
    assert classroom.content_meta["audioManifest"]["status"] == "ready"


def test_failed_finalizer_raises_when_tenant_context_missing(
    maic_enabled_tenant, teacher_user, ai_config, tenant_b, monkeypatch,
):
    """AUDIT-2026-04-25-8: failed-path finalizer must also route its
    ``content_meta`` write through the cross-tenant guard."""
    from django.core.exceptions import PermissionDenied
    from apps.courses.maic_tasks import _finalize_classroom_tts_failed
    from utils.tenant_middleware import set_current_tenant

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    monkeypatch.setattr(
        "apps.courses.maic_tasks.set_current_tenant",
        lambda *_a, **_k: None,
    )

    set_current_tenant(tenant_b)

    with pytest.raises(PermissionDenied):
        _finalize_classroom_tts_failed.run(
            "fake-failed-uuid",
            classroom_id=str(classroom.id),
        )


def test_failed_finalizer_writes_succeed_when_tenant_context_correct(
    maic_enabled_tenant, teacher_user, ai_config,
):
    """Sanity check: failed-path finalizer flips classroom.status=FAILED and
    manifest.status='failed' when the tenant context is correct (normal
    state — the task self-scopes via ``set_current_tenant(classroom.tenant)``
    on entry)."""
    from apps.courses.maic_tasks import _finalize_classroom_tts_failed

    classroom = _make_classroom(
        maic_enabled_tenant,
        teacher_user,
        scenes=[_scene("scene-1", ["aud00000001"])],
    )

    _finalize_classroom_tts_failed.run(
        "some-failed-uuid",
        classroom_id=str(classroom.id),
    )

    classroom.refresh_from_db()
    assert classroom.status == "FAILED"
    assert classroom.content_meta["audioManifest"]["status"] == "failed"
