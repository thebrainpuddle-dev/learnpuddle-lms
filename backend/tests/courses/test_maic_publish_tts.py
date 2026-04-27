"""PERF-P0-4 cutover (2026-04-26) — publish-tts no longer touches legacy ``content``.

Originally these tests guarded the AUDIT-2026-04-25-4 fix, which kept the
legacy ``classroom.content`` mirror in lock-step with the shards while
preserving any legacy-only top-level key. After the PERF-P0-4 cutover the
legacy mirror was retired entirely — every reader goes through
``composed_content`` / shards — so the original AUDIT-2026-04-25-4
contract is moot.

The tests below were rewritten to assert the cutover guarantee:
publish_classroom_tts must write only to ``content_scenes`` and
``content_meta``; the legacy ``content`` JSONField must be byte-equal to
its pre-publish value.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.courses.maic_models import MAICClassroom, TenantAIConfig

pytestmark = pytest.mark.django_db


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


@pytest.fixture
def teacher_client(teacher_user, maic_enabled_tenant):
    client = APIClient()
    client.force_authenticate(user=teacher_user)
    client.defaults["HTTP_HOST"] = f"{maic_enabled_tenant.subdomain}.lms.com"
    return client


def _publish_url(classroom_id):
    return f"/api/teacher/maic/classrooms/{classroom_id}/publish/"


# ---------------------------------------------------------------------------
# PERF-P0-4 cutover — legacy mirror removed
# ---------------------------------------------------------------------------


def test_publish_tts_does_not_touch_legacy_content_field(
    maic_enabled_tenant, teacher_user, ai_config, teacher_client,
):
    """PERF-P0-4 cutover guard. The publish handler must write only to
    ``content_scenes`` and ``content_meta``; the legacy ``content``
    JSONField must remain byte-equal to its pre-publish value.

    Pre-cutover (AUDIT-2026-04-25-4): the handler rebuilt ``content`` by
    overlaying the shards on top of any legacy-only keys so reads still
    saw the latest manifest. That mirror is now obsolete because every
    reader goes through ``composed_content`` / shards.
    """
    LEGACY_PREEXISTING = {
        "scenes": [],
        "discussion": {"x": 1, "nested": {"y": 2}},
        "_legacy_marker": "do-not-touch",
    }
    classroom = MAICClassroom.objects.create(
        tenant=maic_enabled_tenant,
        creator=teacher_user,
        title="No-legacy-writes",
        topic="Topic",
        status="DRAFT",
        content=dict(LEGACY_PREEXISTING),
        content_scenes=[],
        content_agents=[],
        content_meta={"otherShardKey": "value-from-shard"},
    )

    # Stub the Celery enqueue so the chord doesn't run synchronously and
    # confuse the assertion about the publish handler's writes.
    with patch("apps.courses.maic_tasks.pre_generate_classroom_tts.delay"):
        response = teacher_client.post(_publish_url(classroom.id))
    assert response.status_code == 202, response.data

    classroom.refresh_from_db()

    # ── Cutover guarantee: legacy ``content`` is unchanged. ──
    assert classroom.content == LEGACY_PREEXISTING, (
        "PERF-P0-4 regression: publish-tts mutated the legacy content "
        f"field. Got: {classroom.content!r}"
    )

    # ── Shards reflect the new state. ──
    # audioManifest landed in content_meta (and prior shard-only key was
    # preserved by the merge in update_content_section equivalent).
    assert classroom.content_meta.get("otherShardKey") == "value-from-shard"
    assert classroom.content_meta["audioManifest"]["status"] == "generating"


def test_publish_tts_writes_audio_manifest_to_meta_shard(
    maic_enabled_tenant, teacher_user, ai_config, teacher_client,
):
    """audioManifest now lives exclusively in ``content_meta`` after a
    publish call. Sanity check the shard payload (the legacy mirror that
    was previously also asserted on is now intentionally absent)."""
    classroom = MAICClassroom.objects.create(
        tenant=maic_enabled_tenant,
        creator=teacher_user,
        title="Manifest-shard-only",
        topic="Topic",
        status="DRAFT",
        content={},
        content_scenes=[],
        content_agents=[],
        content_meta={},
    )

    with patch("apps.courses.maic_tasks.pre_generate_classroom_tts.delay"):
        response = teacher_client.post(_publish_url(classroom.id))
    assert response.status_code == 202, response.data

    classroom.refresh_from_db()
    manifest = classroom.content_meta.get("audioManifest") or {}
    assert manifest.get("status") == "generating"
    # Legacy content remains untouched.
    assert classroom.content == {}
