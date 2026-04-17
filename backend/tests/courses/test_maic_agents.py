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
from apps.courses.maic_voices import (
    infer_gender_from_name,
    voices_for_gender,
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
    # Rename agent-0 to a female professor so we can keep NeerjaNeural (female
    # voice that suits professor) and still have a male student voice free for
    # the mismatch on agent-2. The name↔voice gender check that landed with
    # Chunk 4 would otherwise trip before this assertion.
    agents[0]["name"] = "Dr. Neha Sharma"
    agents[0]["avatar"] = "👩‍🏫"
    agents[0]["voiceId"] = "en-IN-NeerjaNeural"  # female voice, suits professor
    agents[1]["voiceId"] = "en-IN-KavyaNeural"   # female voice, suits TA
    agents[2]["voiceId"] = "en-IN-PrabhatNeural" # prof voice on student — mismatch target
    with pytest.raises(AgentValidationError, match="voice .* does not suit role"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_gender_balance_with_3plus_agents():
    # Valid: 2 males + 1 female (default sample — names + voices all aligned)
    agents = sample_agents()
    validate_agents(agents, role_slots=[
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 1},
    ])

    # Invalid: all male — all names AND voices are male so the stricter
    # name↔voice check still passes per agent and only the cross-roster
    # gender-balance rule fires.
    all_male = [
        {**agents[0], "name": "Dr. Arjun Sharma", "voiceId": "en-IN-PrabhatNeural"},
        {**agents[1], "name": "Mr. Rahul Menon", "role": "moderator",
         "voiceId": "en-IN-KunalNeural"},
        {**agents[2], "name": "Karan Singh", "voiceId": "en-IN-AaravNeural"},
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
# Name ↔ voice gender alignment (Chunk 4)
# ---------------------------------------------------------------------------

def test_infer_gender_from_name_known_female():
    assert infer_gender_from_name("Priya") == "female"
    assert infer_gender_from_name("Dr. Priya Reddy") == "female"
    assert infer_gender_from_name("Prof. Neha Sharma") == "female"
    assert infer_gender_from_name("Ms. Aditi Rao") == "female"
    assert infer_gender_from_name("Kavya") == "female"


def test_infer_gender_from_name_known_male():
    assert infer_gender_from_name("Arjun") == "male"
    assert infer_gender_from_name("Dr. Prabhat Kumar") == "male"
    assert infer_gender_from_name("Mr. Aarav Gupta") == "male"
    assert infer_gender_from_name("Rahul Menon") == "male"


def test_infer_gender_from_name_unknown_falls_back():
    # Names outside the curated table should return 'unknown' so the
    # validator doesn't trash-can novel names in the long tail.
    assert infer_gender_from_name("Zarmina") == "unknown"
    assert infer_gender_from_name("Rumplestiltskin") == "unknown"
    assert infer_gender_from_name("") == "unknown"
    assert infer_gender_from_name("   ") == "unknown"


def test_infer_gender_handles_honorific_only_gracefully():
    # If the entire name collapses to honorifics (no real first name),
    # we must still return 'unknown' rather than crash.
    assert infer_gender_from_name("Dr.") == "unknown"
    assert infer_gender_from_name("Mr. Prof.") == "unknown"


def test_validate_rejects_female_name_on_male_voice():
    # The canonical bug from the Keystone demo: "Dr. Priya Reddy" was
    # handed the male Prabhat voice and shipped.
    agents = sample_agents()
    agents[0]["name"] = "Dr. Priya Reddy"
    agents[0]["voiceId"] = "en-IN-PrabhatNeural"  # male voice
    with pytest.raises(AgentValidationError, match="reads as female"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_validate_rejects_male_name_on_female_voice():
    agents = sample_agents()
    agents[2]["name"] = "Arjun Singh"
    agents[2]["voiceId"] = "en-IN-AashiNeural"  # female voice, suits student
    with pytest.raises(AgentValidationError, match="reads as male"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_validate_allows_unknown_name_on_any_voice():
    # Unknown-gender names should NOT block validation — otherwise novel
    # or region-specific names would thrash the regen loop.
    agents = sample_agents()
    agents[2]["name"] = "Zarmina Novikova"  # unknown -> skip gender check
    validate_agents(agents, role_slots=[
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 1},
    ])


def test_voices_for_gender_returns_matching_voices():
    female_voices = voices_for_gender("female")
    assert all(v["gender"] == "female" for v in female_voices)
    assert any(v["id"] == "en-IN-NeerjaNeural" for v in female_voices)

    male_voices = voices_for_gender("male")
    assert all(v["gender"] == "male" for v in male_voices)
    assert any(v["id"] == "en-IN-PrabhatNeural" for v in male_voices)

    assert voices_for_gender("unknown") == []
    assert voices_for_gender("other") == []


# ---------------------------------------------------------------------------
# Action post-processing (Chunk 5)
# ---------------------------------------------------------------------------

def test_stamp_action_durations_fills_speech():
    from apps.courses.maic_generation_service import _stamp_action_durations

    actions = [
        {"type": "speech", "agentId": "agent-1", "text": "Hello everyone!"},
        {"type": "speech", "agentId": "agent-2", "text": "Hi"},   # very short
        {"type": "spotlight", "elementId": "el-1", "duration": 2000},
        {"type": "pause", "duration": 200},
    ]
    _stamp_action_durations(actions)
    assert actions[0]["durationMs"] == max(800, round(len("Hello everyone!") * 55))
    assert actions[1]["durationMs"] == 800  # min floor
    assert "durationMs" not in actions[2]   # spotlight untouched
    assert "durationMs" not in actions[3]   # pause untouched


def test_stamp_action_durations_preserves_existing():
    from apps.courses.maic_generation_service import _stamp_action_durations

    actions = [
        {"type": "speech", "agentId": "agent-1", "text": "Hello",
         "durationMs": 1234},
    ]
    _stamp_action_durations(actions)
    assert actions[0]["durationMs"] == 1234  # preserved


def test_stamp_discussion_defaults_to_manual_trigger():
    from apps.courses.maic_generation_service import _stamp_action_durations

    actions = [
        {"type": "discussion", "sessionType": "qa", "topic": "Why?",
         "agentIds": ["agent-1"]},
        {"type": "discussion", "sessionType": "qa", "topic": "How?",
         "agentIds": ["agent-1"], "triggerMode": "auto"},
    ]
    _stamp_action_durations(actions)
    assert actions[0]["triggerMode"] == "manual"
    assert actions[1]["triggerMode"] == "auto"  # preserved


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


# ---------------------------------------------------------------------------
# Follow-up fixes from Chunk 2 review (2026-04-16)
# ---------------------------------------------------------------------------

def test_color_outside_palette_rejected():
    agents = sample_agents()
    agents[0]["color"] = "#FF0000"   # not in canonical palette
    with pytest.raises(AgentValidationError, match="not in palette"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_avatar_outside_allowed_set_rejected():
    agents = sample_agents()
    agents[0]["avatar"] = "🦄"   # not in curated emoji set
    with pytest.raises(AgentValidationError, match="not in allowed emoji set"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_persona_flavored_appends_style_fragment():
    from apps.courses.maic_generation_service import _persona_flavored
    agent = {"speakingStyle": "Warm, unhurried. Occasionally asks 'theek hai?' to check understanding."}
    out = _persona_flavored("Let me walk you through this.", agent)
    assert out.startswith("Let me walk you through this.")
    assert "warm" in out.lower()


def test_persona_flavored_handles_missing_style():
    from apps.courses.maic_generation_service import _persona_flavored
    assert _persona_flavored("Hi there.", {}) == "Hi there."
    assert _persona_flavored("Hi there.", {"speakingStyle": ""}) == "Hi there."


def test_fallback_actions_carries_persona_hints():
    """_fallback_actions must not strip the speaking-style flavoring — losing it here
    would undo WS-B the moment the LLM action path fails."""
    from apps.courses.maic_generation_service import _fallback_actions
    agents = [
        {"id": "agent-1", "name": "Dr. Aarav Sharma", "role": "professor",
         "speakingStyle": "Warm, unhurried, says 'theek hai?' to check in"},
        {"id": "agent-2", "name": "Ms. Priya Iyer", "role": "teaching_assistant",
         "speakingStyle": "Crisp and encouraging, uses 'bilkul' when she agrees"},
    ]
    scene = {"title": "Photosynthesis", "content": {"slides": [{"elements": [], "speakerScript": ""}]}}
    result = _fallback_actions(scene, agents)
    speeches = [a["text"] for a in result["actions"] if a["type"] == "speech"]
    # At least one line per agent should carry the style fragment
    agent1_lines = [t for a in result["actions"] if a["type"] == "speech" and a.get("agentId") == "agent-1" for t in [a["text"]]]
    agent2_lines = [t for a in result["actions"] if a["type"] == "speech" and a.get("agentId") == "agent-2" for t in [a["text"]]]
    assert any("warm" in t.lower() for t in agent1_lines), f"agent-1 lines lack persona hint: {agent1_lines}"
    assert any("crisp" in t.lower() or "bilkul" in t.lower() for t in agent2_lines), f"agent-2 lines lack persona hint: {agent2_lines}"
