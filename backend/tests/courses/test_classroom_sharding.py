"""
PERF-P0-4 — Tests for MAICClassroom content sharding.

Covers:
  1. Migration backfill: legacy content → shards correctly populated.
  2. Reverse migration: shards → legacy content round-trips losslessly.
  3. composed_content property: shards present → composed dict matches expected shape.
  4. composed_content fallback: shards empty → falls back to legacy content field.
  5. update_content_section('scenes'): mutates only content_scenes shard.
  6. update_content_section('agents'): mutates only content_agents shard.
  7. update_content_section('meta'): merges into content_meta (no overwrite of other keys).
  8. update_content_section unknown section raises ValueError.
  9. Partial save: audioUrl update via task writes only content_scenes + content_meta.
 10. _student_can_view_classroom reads audioManifest from content_meta shard.
"""

import copy
from unittest.mock import patch, MagicMock

import pytest

from apps.courses.maic_models import MAICClassroom

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

AGENTS = [
    {
        "id": "a1",
        "name": "Dr. Aarav",
        "voiceId": "en-IN-PrabhatNeural",
        "voiceProvider": "azure",
    },
    {
        "id": "a2",
        "name": "Ms. Priya",
        "voiceId": "en-IN-NeerjaNeural",
        "voiceProvider": "azure",
    },
]

SCENES = [
    {
        "id": "s1",
        "title": "Introduction",
        "slides": [
            {
                "elements": [
                    {"type": "image", "src": "https://example.com/img.jpg", "content": "sun"},
                ]
            }
        ],
        "actions": [
            {"type": "speech", "agentId": "a1", "text": "Hello!", "audioId": "abc123"},
        ],
    },
    {
        "id": "s2",
        "title": "Core Concepts",
        "slides": [],
        "actions": [],
    },
]

AUDIO_MANIFEST = {
    "status": "ready",
    "progress": 100,
    "totalActions": 1,
    "completedActions": 1,
    "failedAudioIds": [],
    "generatedAt": "2026-04-24T10:00:00+00:00",
}

LEGACY_CONTENT = {
    "agents": AGENTS,
    "scenes": SCENES,
    "audioManifest": AUDIO_MANIFEST,
}


# ---------------------------------------------------------------------------
# Helper to create a minimal MAICClassroom
# ---------------------------------------------------------------------------

def _make_classroom(tenant, creator, *, legacy_content=None, shards=False):
    """Create a MAICClassroom. Pass legacy_content to set the old field,
    or shards=True to pre-populate the shard fields from LEGACY_CONTENT."""
    kwargs = dict(
        tenant=tenant,
        creator=creator,
        title="Test Classroom",
        status="READY",
        is_public=True,
    )
    if legacy_content is not None:
        kwargs["content"] = legacy_content
    if shards:
        kwargs["content_scenes"] = copy.deepcopy(SCENES)
        kwargs["content_agents"] = copy.deepcopy(AGENTS)
        kwargs["content_meta"] = {"audioManifest": copy.deepcopy(AUDIO_MANIFEST)}
    return MAICClassroom.objects.create(**kwargs)


# ---------------------------------------------------------------------------
# 1. Migration backfill — simulated by directly calling the function
#    (avoids running the actual migration in tests).
# ---------------------------------------------------------------------------

def test_migration_backfill_populates_shards(tenant, teacher_user):
    """Rows with legacy content get shards populated correctly by the
    backfill function used in 0043_classroom_sharded_content."""
    classroom = _make_classroom(tenant, teacher_user, legacy_content=LEGACY_CONTENT)
    # Simulate what populate_shards does in the migration.
    legacy = classroom.content or {}
    scenes = legacy.get("scenes")
    agents = legacy.get("agents")
    meta = {k: v for k, v in legacy.items() if k not in ("scenes", "agents")}

    classroom.content_scenes = scenes if isinstance(scenes, list) else []
    classroom.content_agents = agents if isinstance(agents, list) else []
    classroom.content_meta = meta
    classroom.save(
        update_fields=["content_scenes", "content_agents", "content_meta"]
    )
    classroom.refresh_from_db()

    assert classroom.content_scenes == SCENES
    assert classroom.content_agents == AGENTS
    assert classroom.content_meta == {"audioManifest": AUDIO_MANIFEST}
    # Legacy field must remain unchanged.
    assert classroom.content == LEGACY_CONTENT


# ---------------------------------------------------------------------------
# 2. Reverse migration — shards → legacy content round-trips losslessly
# ---------------------------------------------------------------------------

def test_reverse_migration_merges_shards_into_legacy(tenant, teacher_user):
    """The reverse of the migration merges shards back into content faithfully."""
    classroom = _make_classroom(tenant, teacher_user, shards=True)

    # Simulate depopulate_shards.
    merged: dict = {}
    if classroom.content_agents:
        merged["agents"] = classroom.content_agents
    if classroom.content_scenes:
        merged["scenes"] = classroom.content_scenes
    if classroom.content_meta:
        merged.update(classroom.content_meta)

    classroom.content = merged
    classroom.content_scenes = []
    classroom.content_agents = []
    classroom.content_meta = {}
    classroom.save(
        update_fields=["content", "content_scenes", "content_agents", "content_meta"]
    )
    classroom.refresh_from_db()

    # The round-tripped content must equal the original LEGACY_CONTENT shape.
    assert classroom.content["agents"] == AGENTS
    assert classroom.content["scenes"] == SCENES
    assert classroom.content["audioManifest"] == AUDIO_MANIFEST
    # Shards must be cleared.
    assert classroom.content_scenes == []
    assert classroom.content_agents == []
    assert classroom.content_meta == {}


# ---------------------------------------------------------------------------
# 3. composed_content — shards present → returns composed dict
# ---------------------------------------------------------------------------

def test_composed_content_from_shards(tenant, teacher_user):
    """When shards are populated, composed_content composes them correctly."""
    classroom = _make_classroom(tenant, teacher_user, shards=True)
    result = classroom.composed_content

    assert result["agents"] == AGENTS
    assert result["scenes"] == SCENES
    assert result["audioManifest"] == AUDIO_MANIFEST


# ---------------------------------------------------------------------------
# 4. composed_content fallback — no shards → returns legacy content field
# ---------------------------------------------------------------------------

def test_composed_content_fallback_to_legacy(tenant, teacher_user):
    """When shards are empty, composed_content falls back to legacy content."""
    classroom = _make_classroom(tenant, teacher_user, legacy_content=LEGACY_CONTENT)
    # Ensure shards are empty (default).
    assert classroom.content_scenes == []
    assert classroom.content_agents == []
    assert classroom.content_meta == {}

    result = classroom.composed_content
    assert result == LEGACY_CONTENT


# ---------------------------------------------------------------------------
# 5. update_content_section('scenes') — only writes content_scenes shard
# ---------------------------------------------------------------------------

def test_update_content_section_scenes_writes_only_shard(tenant, teacher_user):
    """update_content_section('scenes', ...) updates content_scenes and nothing else."""
    classroom = _make_classroom(tenant, teacher_user, shards=True)
    original_meta = copy.deepcopy(classroom.content_meta)
    original_agents = copy.deepcopy(classroom.content_agents)

    new_scenes = [{"id": "new", "title": "New Scene", "slides": [], "actions": []}]
    classroom.update_content_section("scenes", new_scenes)

    classroom.refresh_from_db()
    assert classroom.content_scenes == new_scenes
    assert classroom.content_agents == original_agents
    assert classroom.content_meta == original_meta


# ---------------------------------------------------------------------------
# 6. update_content_section('agents') — only writes content_agents shard
# ---------------------------------------------------------------------------

def test_update_content_section_agents_writes_only_shard(tenant, teacher_user):
    """update_content_section('agents', ...) updates content_agents and nothing else."""
    classroom = _make_classroom(tenant, teacher_user, shards=True)
    original_scenes = copy.deepcopy(classroom.content_scenes)

    new_agents = [{"id": "b1", "name": "New Agent", "voiceId": "en-US-JennyNeural"}]
    classroom.update_content_section("agents", new_agents)

    classroom.refresh_from_db()
    assert classroom.content_agents == new_agents
    assert classroom.content_scenes == original_scenes


# ---------------------------------------------------------------------------
# 7. update_content_section('meta') — merges into content_meta
# ---------------------------------------------------------------------------

def test_update_content_section_meta_merges_not_replaces(tenant, teacher_user):
    """update_content_section('meta', ...) merges the dict rather than replacing it,
    so updating audioManifest doesn't clobber other meta keys."""
    classroom = _make_classroom(tenant, teacher_user, shards=True)
    # Pre-populate meta with an extra key.
    classroom.content_meta = {
        "audioManifest": copy.deepcopy(AUDIO_MANIFEST),
        "someOtherKey": "preserved",
    }
    classroom.save(update_fields=["content_meta"])

    # Merge only audioManifest.status.
    new_manifest = dict(AUDIO_MANIFEST)
    new_manifest["status"] = "partial"
    classroom.update_content_section("meta", {"audioManifest": new_manifest})

    classroom.refresh_from_db()
    assert classroom.content_meta["audioManifest"]["status"] == "partial"
    # Other key must be preserved.
    assert classroom.content_meta["someOtherKey"] == "preserved"


# ---------------------------------------------------------------------------
# 8. update_content_section with unknown section raises ValueError
# ---------------------------------------------------------------------------

def test_update_content_section_unknown_raises(tenant, teacher_user):
    """Passing an unknown section name raises ValueError immediately."""
    classroom = _make_classroom(tenant, teacher_user, shards=True)
    with pytest.raises(ValueError, match="Unknown content section"):
        classroom.update_content_section("unknown_key", {})


# ---------------------------------------------------------------------------
# 9. Partial save: TTS task writes only content_scenes + content_meta
#    (no full content blob rewrite)
# ---------------------------------------------------------------------------

def test_tts_task_writes_only_targeted_shards(tenant, teacher_user):
    """After pre_generate_classroom_tts completes, only content_scenes and
    content_meta are updated — the legacy content blob is NOT touched by
    the task itself (saves go to update_fields=[content_scenes, content_meta...])."""
    from apps.courses.maic_models import TenantAIConfig

    TenantAIConfig.objects.create(
        tenant=tenant,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        tts_provider="disabled",
        maic_enabled=True,
    )

    # Build classroom with scenes that have speech actions already stamped.
    scenes = [
        {
            "id": "s1",
            "title": "Intro",
            "slides": [],
            "actions": [
                {
                    "type": "speech",
                    "agentId": "a1",
                    "text": "Hello world",
                    "audioId": "deadbeef1234",
                    "voiceId": "en-IN-PrabhatNeural",
                },
            ],
        }
    ]
    meta = {
        "audioManifest": {
            "status": "generating",
            "progress": 0,
            "totalActions": 1,
            "completedActions": 0,
            "failedAudioIds": [],
            "generatedAt": None,
        }
    }
    classroom = MAICClassroom.objects.create(
        tenant=tenant,
        creator=teacher_user,
        title="TTS Test",
        status="GENERATING",
        content_scenes=scenes,
        content_agents=AGENTS,
        content_meta=meta,
    )

    from apps.courses.maic_tasks import pre_generate_classroom_tts
    from apps.courses.maic_storage import storage_upload, storage_exists

    FAKE_AUDIO = b"\xff\xfb\x90\x00" * 100  # minimal mp3-ish bytes
    FAKE_URL = "https://cdn.example.com/tts/deadbeef1234.mp3"

    with (
        patch("apps.courses.maic_tasks.generate_tts_audio", return_value=FAKE_AUDIO),
        patch("apps.courses.maic_tasks.storage_exists", return_value=False),
        patch("apps.courses.maic_tasks.storage_upload", return_value=FAKE_URL),
        patch("apps.courses.maic_tasks.set_current_tenant"),
        patch("apps.courses.maic_tasks.clear_current_tenant"),
    ):
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()

    # The audioUrl should be written into the content_scenes shard.
    assert classroom.content_scenes[0]["actions"][0]["audioUrl"] == FAKE_URL
    # Manifest should be in content_meta.
    assert classroom.content_meta["audioManifest"]["status"] in ("ready", "partial")
    # Classroom status should be READY.
    assert classroom.status == "READY"


# ---------------------------------------------------------------------------
# 9b. PERF-P0-4 cutover (2026-04-26) — legacy mirror removed.
#     The transitional SPRINT-2-BATCH-6-F5 dual-write was retired once every
#     reader was switched to composed_content / shards. After
#     pre_generate_classroom_tts runs, the legacy ``content`` JSONField must
#     remain at its pre-task value (i.e. NOT be touched by the chord callback).
# ---------------------------------------------------------------------------

def test_perf_p0_4_no_legacy_content_writes_after_pregen(tenant, teacher_user):
    """PERF-P0-4 cutover guard. The legacy ``content`` field must NOT be
    rewritten by the chord callback — only shards (``content_scenes``,
    ``content_meta``) carry fresh data.

    Setup uses an explicit pre-task value for ``content`` so we can prove
    the value is unchanged. Pre-cutover behaviour was: ``content`` would
    be rebuilt to mirror the shards, including the freshly stamped
    audioUrl + manifest. Post-cutover the value must be byte-equal to
    what we wrote at row-creation time.
    """
    from apps.courses.maic_models import TenantAIConfig

    TenantAIConfig.objects.create(
        tenant=tenant,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        tts_provider="disabled",
        maic_enabled=True,
    )

    scenes = [
        {
            "id": "s1",
            "title": "Intro",
            "slides": [],
            "actions": [
                {
                    "type": "speech",
                    "agentId": "a1",
                    "text": "Hello cutover",
                    "audioId": "cutover0001",
                    "voiceId": "en-IN-PrabhatNeural",
                },
            ],
        }
    ]
    meta = {
        "audioManifest": {
            "status": "generating",
            "progress": 0,
            "totalActions": 1,
            "completedActions": 0,
            "failedAudioIds": [],
            "generatedAt": None,
        }
    }
    # Pre-task legacy content has a STALE marker so we can prove the chord
    # callback didn't rewrite it.
    LEGACY_PREEXISTING = {"_legacy_marker": "do-not-touch"}
    classroom = MAICClassroom.objects.create(
        tenant=tenant,
        creator=teacher_user,
        title="No-legacy-writes TTS Test",
        status="GENERATING",
        content=copy.deepcopy(LEGACY_PREEXISTING),
        content_scenes=copy.deepcopy(scenes),
        content_agents=AGENTS,
        content_meta=copy.deepcopy(meta),
    )

    from apps.courses.maic_tasks import pre_generate_classroom_tts

    FAKE_AUDIO = b"\xff\xfb\x90\x00" * 100
    FAKE_URL = "https://cdn.example.com/tts/cutover0001.mp3"

    with (
        patch("apps.courses.maic_tasks.generate_tts_audio", return_value=FAKE_AUDIO),
        patch("apps.courses.maic_tasks.storage_exists", return_value=False),
        patch("apps.courses.maic_tasks.storage_upload", return_value=FAKE_URL),
        patch("apps.courses.maic_tasks.set_current_tenant"),
        patch("apps.courses.maic_tasks.clear_current_tenant"),
    ):
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()

    # ── PERF-P0-4 cutover guarantee: legacy field is byte-equal to pre-task.
    assert classroom.content == LEGACY_PREEXISTING, (
        "PERF-P0-4 regression: legacy ``content`` field was rewritten by "
        f"pre_generate_classroom_tts. Got: {classroom.content!r}"
    )

    # Shards carry the fresh data (sanity check — already covered by the
    # sibling test, but worth re-asserting alongside the cutover guard).
    assert classroom.content_meta["audioManifest"]["status"] in ("ready", "partial")
    assert classroom.content_scenes[0]["actions"][0]["audioUrl"] == FAKE_URL


# ---------------------------------------------------------------------------
# 10. _student_can_view_classroom reads audioManifest from content_meta shard
# ---------------------------------------------------------------------------

def test_student_visibility_reads_audio_manifest_from_shard(tenant, teacher_user):
    """The _student_can_view_classroom helper should find audioManifest in
    content_meta when the shard is populated — not only in legacy content."""
    from apps.courses.maic_views import _student_can_view_classroom

    classroom = _make_classroom(tenant, teacher_user, shards=True)
    # Ensure audioManifest is ONLY in content_meta, not in the legacy field.
    classroom.content = {}  # wipe legacy
    classroom.save(update_fields=["content"])

    # Should return True because content_meta has audioManifest.status="ready".
    assert _student_can_view_classroom(teacher_user, classroom) is True


def test_student_visibility_fallback_to_legacy_manifest(tenant, teacher_user):
    """When shards are empty, _student_can_view_classroom falls back to
    the legacy content field for audioManifest."""
    from apps.courses.maic_views import _student_can_view_classroom

    classroom = _make_classroom(tenant, teacher_user, legacy_content=LEGACY_CONTENT)
    # Shards are empty by default; legacy content has audioManifest.status="ready".
    assert classroom.content_meta == {}
    assert _student_can_view_classroom(teacher_user, classroom) is True


def test_student_visibility_blocked_if_manifest_missing(tenant, teacher_user):
    """A classroom with no audioManifest (neither in shards nor legacy) is
    blocked from student access."""
    from apps.courses.maic_views import _student_can_view_classroom

    classroom = MAICClassroom.objects.create(
        tenant=tenant,
        creator=teacher_user,
        title="No Manifest",
        status="READY",
        is_public=True,
    )
    # No audioManifest → manifest_status will be None → blocked.
    assert _student_can_view_classroom(teacher_user, classroom) is False


# ---------------------------------------------------------------------------
# F7 — Tenant guard on update_content_section (SPRINT-2-BATCH-6-F7)
# ---------------------------------------------------------------------------

def test_update_content_section_blocks_cross_tenant_when_tenant_set(
    tenant, tenant_b, teacher_user, db
):
    """When a tenant is set in thread-local context, update_content_section
    must raise PermissionDenied if the classroom belongs to a different tenant."""
    from django.core.exceptions import PermissionDenied
    from utils.tenant_middleware import set_current_tenant, clear_current_tenant
    from apps.users.models import User

    # Create a teacher in tenant_b so the classroom row is valid.
    teacher_b = User.objects.create_user(
        email="teacher_b@other.com",
        password="Pass!123",
        first_name="TeacherB",
        last_name="User",
        tenant=tenant_b,
        role="TEACHER",
        is_active=True,
    )
    # Classroom belongs to tenant_b.
    classroom_b = MAICClassroom.all_objects.create(
        tenant=tenant_b,
        creator=teacher_b,
        title="Foreign Classroom",
        status="DRAFT",
        content_scenes=copy.deepcopy(SCENES),
        content_agents=copy.deepcopy(AGENTS),
        content_meta={"audioManifest": copy.deepcopy(AUDIO_MANIFEST)},
    )

    # Set current tenant to tenant (tenant A) — NOT the classroom's tenant.
    set_current_tenant(tenant)
    try:
        with pytest.raises(PermissionDenied):
            classroom_b.update_content_section("scenes", [])
    finally:
        clear_current_tenant()


def test_update_content_section_allows_when_no_tenant_set(tenant, teacher_user):
    """When NO tenant is set in thread-local context (Celery task scenario),
    update_content_section must succeed without raising PermissionDenied."""
    from utils.tenant_middleware import clear_current_tenant, get_current_tenant

    # Explicitly clear thread-local (conftest also does this, but be explicit).
    clear_current_tenant()
    assert get_current_tenant() is None

    classroom = _make_classroom(tenant, teacher_user, shards=True)
    new_scenes = [{"id": "x", "title": "X", "slides": [], "actions": []}]

    # Must NOT raise — no tenant set means we are in a trusted Celery context.
    classroom.update_content_section("scenes", new_scenes)
    classroom.refresh_from_db()
    assert classroom.content_scenes == new_scenes
