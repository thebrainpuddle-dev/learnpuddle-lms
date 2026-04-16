"""Tests for MAIC agent profile generation + validation."""
import json
from unittest.mock import patch

import pytest

from apps.courses.maic_generation_service import (
    AgentValidationError,
    generate_agent_profiles_json,
    regenerate_one_agent,
    validate_agents,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Local fixtures (keeps this test module self-contained)
# ---------------------------------------------------------------------------

@pytest.fixture
def ai_config(tenant):
    """Minimal TenantAIConfig for the tests. Not actually used for HTTP calls —
    the _call_llm function is mocked in every test that needs an LLM response."""
    from apps.courses.maic_models import TenantAIConfig
    return TenantAIConfig.objects.create(
        tenant=tenant,
        llm_provider="openrouter",
        llm_model="openrouter/auto",
        llm_base_url="",
        tts_provider="disabled",
    )


def sample_agents():
    return [
        {"id": "agent-1", "name": "Dr. Aarav Sharma", "role": "professor",
         "avatar": "👨‍🏫", "color": "#4338CA",
         "voiceId": "en-IN-PrabhatNeural", "voiceProvider": "azure",
         "personality": "Patient.", "expertise": "Leads.", "speakingStyle": "Warm."},
        {"id": "agent-2", "name": "Ms. Priya Iyer", "role": "teaching_assistant",
         "avatar": "👩‍🏫", "color": "#0F766E",
         "voiceId": "en-IN-NeerjaNeural", "voiceProvider": "azure",
         "personality": "Kind.", "expertise": "Supports.", "speakingStyle": "Warm."},
        {"id": "agent-3", "name": "Rohan Menon", "role": "student",
         "avatar": "🙋‍♂️", "color": "#D97706",
         "voiceId": "en-IN-AaravNeural", "voiceProvider": "azure",
         "personality": "Curious.", "expertise": "Asks.", "speakingStyle": "Friendly."},
    ]


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

def test_valid_agents_pass():
    validate_agents(sample_agents(), role_slots=[
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 1},
    ])


def test_duplicate_voice_rejected():
    agents = sample_agents()
    agents[1]["voiceId"] = "en-IN-PrabhatNeural"  # collide with agent-1
    with pytest.raises(AgentValidationError, match="duplicate voice"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_voice_role_mismatch_rejected():
    agents = sample_agents()
    agents[2]["voiceId"] = "en-IN-PrabhatNeural"  # prof voice on student
    # also fix duplicate on agent-1 so we test voice-role mismatch cleanly
    agents[0]["voiceId"] = "en-IN-NeerjaNeural"
    agents[1]["voiceId"] = "en-IN-KavyaNeural"
    with pytest.raises(AgentValidationError, match="voice .* does not suit role"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_gender_balance_with_3plus_agents():
    # Valid: 2 males + 1 female (default sample)
    agents = sample_agents()
    validate_agents(agents, role_slots=[
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 1},
    ])

    # Invalid: all male (3 agents, all male voices picked from roster where male suits each role)
    all_male = [
        {**agents[0], "voiceId": "en-IN-PrabhatNeural"},                 # male, suits professor
        {**agents[1], "role": "moderator", "voiceId": "en-IN-KunalNeural"},  # male, suits moderator
        {**agents[2], "voiceId": "en-IN-AaravNeural"},                   # male, suits student
    ]
    with pytest.raises(AgentValidationError, match="gender balance"):
        validate_agents(all_male, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "moderator", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_invalid_voice_id_rejected():
    agents = sample_agents()
    agents[0]["voiceId"] = "en-US-DavisNeural"  # not in roster
    with pytest.raises(AgentValidationError, match="not in roster"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_role_count_mismatch_rejected():
    agents = sample_agents()[:2]  # only 2 agents
    with pytest.raises(AgentValidationError, match="expected .* got"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


# ---------------------------------------------------------------------------
# generate_agent_profiles_json tests
# ---------------------------------------------------------------------------

@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_agent_profiles_returns_valid(mock_llm, ai_config):
    mock_llm.return_value = json.dumps({"agents": sample_agents()})
    result = generate_agent_profiles_json(
        topic="Photosynthesis",
        language="en",
        role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ],
        config=ai_config,
    )
    assert "agents" in result
    assert len(result["agents"]) == 3
    assert result["agents"][0]["role"] == "professor"


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_agent_profiles_retries_on_validation_error(mock_llm, ai_config):
    bad = sample_agents()
    bad[1]["voiceId"] = bad[0]["voiceId"]  # duplicate -> invalid
    good = sample_agents()
    mock_llm.side_effect = [
        json.dumps({"agents": bad}),
        json.dumps({"agents": good}),
    ]
    result = generate_agent_profiles_json(
        topic="X", language="en",
        role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ],
        config=ai_config,
    )
    assert len(result["agents"]) == 3
    assert mock_llm.call_count == 2  # retry happened


# ---------------------------------------------------------------------------
# regenerate_one_agent tests
# ---------------------------------------------------------------------------

@patch("apps.courses.maic_generation_service._call_llm")
def test_regenerate_one_preserves_locked_voice(mock_llm, ai_config):
    existing = sample_agents()
    new_agent = dict(existing[1])
    new_agent["name"] = "Ms. Ananya Nair"
    new_agent["voiceId"] = "en-IN-AashiNeural"  # LLM tries to change voice
    mock_llm.return_value = json.dumps({"agent": new_agent})

    result = regenerate_one_agent(
        topic="X", language="en",
        existing_agents=existing,
        target_agent_id="agent-2",
        locked_fields=["voiceId"],
        config=ai_config,
    )
    assert result["agent"]["voiceId"] == existing[1]["voiceId"]  # preserved
    assert result["agent"]["name"] == "Ms. Ananya Nair"  # new


# ---------------------------------------------------------------------------
# Outline service accepts agents as input
# ---------------------------------------------------------------------------

@patch("apps.courses.maic_generation_service._call_llm")
def test_outline_uses_provided_agents_not_generated(mock_llm, ai_config):
    from apps.courses.maic_generation_service import generate_outline_sse

    mock_llm.return_value = json.dumps({
        "scenes": [
            {"id": "scene-1", "title": "Intro", "type": "introduction",
             "estimatedMinutes": 3, "agentIds": ["agent-1", "agent-2"], "slideCount": 3},
            {"id": "scene-2", "title": "Lecture", "type": "lecture",
             "estimatedMinutes": 5, "agentIds": ["agent-1", "agent-3"], "slideCount": 5},
        ],
        "totalMinutes": 8,
    })
    agents = sample_agents()
    events = list(generate_outline_sse(
        topic="X", language="en", agents=agents, scene_count=2, pdf_text=None, config=ai_config,
    ))
    # find the outline event
    outline_event = next(e for e in events if "event: outline" in e)
    # Parse the data: {...} line out of the SSE payload
    data_line = [line for line in outline_event.split("\n") if line.startswith("data: ")][0]
    payload = json.loads(data_line[len("data: "):])
    allowed_ids = {a["id"] for a in agents}
    for scene in payload["scenes"]:
        for aid in scene["agentIds"]:
            assert aid in allowed_ids
    # The outline must pass through the supplied roster unchanged
    assert payload["agents"] == agents
