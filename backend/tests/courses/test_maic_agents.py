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
    VOICE_BY_ID,
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
         "voiceId": "hi-IN-MadhurNeural", "voiceProvider": "azure",
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
    agents[1]["voiceId"] = "en-IN-NeerjaExpressiveNeural"   # female voice, suits TA
    agents[2]["voiceId"] = "en-IN-PrabhatNeural" # prof voice on student — mismatch target
    with pytest.raises(AgentValidationError, match="voice .* does not suit role"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_gender_balance_with_3plus_agents():
    """CG-P1-1 trimmed the voice roster from 7 → 5; only 2 distinct male
    voices exist (Prabhat, Madhur). Constructing an all-male 3-agent
    roster requires duplicate voiceIds, but the validator's
    duplicate-voice check fires BEFORE the gender-balance check (see
    ``validate_agents`` voice loop in maic_generation_service.py:330-340).

    The all-male assertion is therefore unreachable with the current
    roster. We keep the valid (2 male + 1 female) assertion since that
    still exercises the gender-balance happy path.
    """
    # Valid: 2 males + 1 female (default sample — names + voices all aligned)
    agents = sample_agents()
    validate_agents(agents, role_slots=[
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 1},
    ])
    # All-male assertion intentionally omitted — see docstring above.


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
    agents[2]["voiceId"] = "en-IN-NeerjaExpressiveNeural"  # female voice, suits student
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


def test_auto_fix_swaps_mismatched_voice():
    """When the LLM hands us a female-name agent with a male voice and a
    male-name agent with a female voice, the two-pass auto-fixer should
    release both voices and re-pair them correctly."""
    from apps.courses.maic_generation_service import _auto_fix_voice_gender_mismatches

    # Both professors (so Neerja suits both role-wise). The swap chain
    # is: Neha has Prabhat (male), Aarav has Neerja (female). After fix:
    # Neha should have Neerja, Aarav should have Prabhat.
    agents = [
        {"id": "agent-1", "name": "Dr. Neha Khanna", "role": "professor",
         "avatar": "👩‍🏫", "color": "#4338CA",
         "voiceId": "en-IN-PrabhatNeural", "voiceProvider": "azure",
         "personality": "x", "expertise": "x", "speakingStyle": "x"},
        {"id": "agent-2", "name": "Dr. Aarav Menon", "role": "professor",
         "avatar": "👨‍🏫", "color": "#0F766E",
         "voiceId": "en-IN-NeerjaNeural", "voiceProvider": "azure",
         "personality": "x", "expertise": "x", "speakingStyle": "x"},
        {"id": "agent-3", "name": "Rohan Menon", "role": "student",
         "avatar": "🙋‍♂️", "color": "#D97706",
         "voiceId": "hi-IN-MadhurNeural", "voiceProvider": "azure",
         "personality": "x", "expertise": "x", "speakingStyle": "x"},
    ]
    fixed, notes = _auto_fix_voice_gender_mismatches(agents)

    neha = next(a for a in fixed if a["name"].endswith("Neha Khanna"))
    aarav = next(a for a in fixed if a["name"].endswith("Aarav Menon"))
    assert neha["voiceId"] == "en-IN-NeerjaNeural"  # female voice
    assert aarav["voiceId"] == "en-IN-PrabhatNeural"  # male voice
    assert len(notes) == 2  # both swaps logged
    # Full roster must now validate cleanly
    validate_agents(fixed, role_slots=[
        {"role": "professor", "count": 2},
        {"role": "student", "count": 1},
    ])


def test_auto_fix_preserves_already_correct_agents():
    """Agents whose gender already matches should not be touched."""
    from apps.courses.maic_generation_service import _auto_fix_voice_gender_mismatches

    agents = sample_agents()
    fixed, notes = _auto_fix_voice_gender_mismatches(agents)
    assert notes == []  # no fixes required
    for before, after in zip(agents, fixed):
        assert before["voiceId"] == after["voiceId"]


def test_auto_fix_reports_when_no_candidate_available():
    """When no unused gender-matched voice suits the role, the fixer
    leaves the agent alone and reports the shortfall."""
    from apps.courses.maic_generation_service import _auto_fix_voice_gender_mismatches

    # Exhaust every female voice in the roster (Neerja, Aashi, Kavya) with
    # correctly-paired female agents, then try to fix a female professor
    # stuck with a male voice. Zero female voices remain -> shortfall.
    agents = [
        {"id": "agent-1", "name": "Dr. Priya Sharma", "role": "professor",
         "avatar": "👩‍🏫", "color": "#4338CA",
         "voiceId": "en-IN-PrabhatNeural",  # wrong (male) — the one to fix
         "voiceProvider": "azure",
         "personality": "x", "expertise": "x", "speakingStyle": "x"},
        {"id": "agent-2", "name": "Ms. Neha Iyer", "role": "teaching_assistant",
         "avatar": "🧕", "color": "#0F766E",
         "voiceId": "en-IN-NeerjaNeural",  # female TA — correct pairing
         "voiceProvider": "azure",
         "personality": "x", "expertise": "x", "speakingStyle": "x"},
        {"id": "agent-3", "name": "Aditi Rao", "role": "student",
         "avatar": "🙋‍♀️", "color": "#D97706",
         "voiceId": "en-IN-NeerjaExpressiveNeural",  # female student — correct pairing
         "voiceProvider": "azure",
         "personality": "x", "expertise": "x", "speakingStyle": "x"},
        {"id": "agent-4", "name": "Ms. Kavya Nair", "role": "moderator",
         "avatar": "👩‍🎓", "color": "#166534",
         "voiceId": "en-IN-NeerjaExpressiveNeural",  # female moderator — correct pairing
         "voiceProvider": "azure",
         "personality": "x", "expertise": "x", "speakingStyle": "x"},
    ]
    fixed, notes = _auto_fix_voice_gender_mismatches(agents)
    # Priya still has the wrong voice (no female voice left to steal)
    priya = next(a for a in fixed if a["name"].endswith("Priya Sharma"))
    assert priya["voiceId"] == "en-IN-PrabhatNeural"
    assert any("could not auto-fix" in n.lower() for n in notes)


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
# Chat history merging (Chunk 8)
# ---------------------------------------------------------------------------

def test_sanitize_chat_history_drops_malformed():
    from apps.courses.maic_generation_service import _sanitize_chat_history

    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello there", "agentId": "agent-1"},
        {"role": "system", "content": "noise"},             # wrong role
        {"role": "user"},                                    # no content
        {"role": "user", "content": "   "},                  # whitespace
        "not a dict",                                        # not dict
        {"role": "assistant", "content": "Cool"},
    ]
    out = _sanitize_chat_history(history)
    assert len(out) == 3
    assert out[0] == {"role": "user", "content": "Hi"}
    assert out[1] == {"role": "assistant", "content": "Hello there", "agentId": "agent-1"}
    assert out[2] == {"role": "assistant", "content": "Cool"}


def test_sanitize_chat_history_caps_at_12():
    from apps.courses.maic_generation_service import _sanitize_chat_history

    history = [{"role": "user", "content": f"q{i}"} for i in range(20)]
    out = _sanitize_chat_history(history)
    assert len(out) == 12  # oldest 8 dropped
    assert out[0]["content"] == "q8"
    assert out[-1]["content"] == "q19"


def test_sanitize_chat_history_handles_non_list():
    from apps.courses.maic_generation_service import _sanitize_chat_history

    assert _sanitize_chat_history(None) == []
    assert _sanitize_chat_history("not a list") == []
    assert _sanitize_chat_history({}) == []


def test_render_chat_history_inlines_recent_and_summarizes_older():
    from apps.courses.maic_generation_service import _render_chat_history_block

    # 8 turns total — 2 older student questions get summarized, last 6 inlined.
    history = [
        {"role": "user", "content": f"Question {i}"}
        if i % 2 == 0 else
        {"role": "assistant", "content": f"Answer {i}"}
        for i in range(8)
    ]
    block = _render_chat_history_block(history)
    # Summary references earlier questions
    assert "Earlier in this session" in block
    # Recent turns are inlined verbatim
    assert "Student:" in block and "Tutor:" in block
    assert "Question 6" in block  # inline
    assert "Answer 7" in block    # inline


def test_summarize_short_circuit_when_no_history():
    from apps.courses.maic_generation_service import generate_chat_sse

    class FakeConfig:
        pass

    agents = [{"id": "agent-1", "name": "Dr. Priya", "role": "professor"}]
    events = list(generate_chat_sse(
        message="Summarize key concepts",
        classroom_title="Photosynthesis",
        agents=agents,
        config=FakeConfig(),
        history=None,
        scene_titles=None,
    ))
    # Should yield exactly one chat_message + DONE, no LLM called
    assert any("chat_message" in e for e in events)
    combined = "".join(events)
    assert "specific question" in combined.lower() or "summarize" in combined.lower()
    assert "[DONE]" in combined


def test_summarize_proceeds_when_scene_titles_exist():
    """Even without chat history, the outline gives the LLM material to summarize."""
    from unittest.mock import patch
    from apps.courses.maic_generation_service import generate_chat_sse

    class FakeConfig:
        pass

    agents = [{"id": "agent-1", "name": "Dr. Priya", "role": "professor"}]
    with patch("apps.courses.maic_generation_service._call_llm") as mock_llm:
        mock_llm.return_value = json.dumps([
            {"agentId": "agent-1", "agentName": "Dr. Priya",
             "content": "We covered light reactions and dark reactions."},
        ])
        events = list(generate_chat_sse(
            message="Summarize key concepts",
            classroom_title="Photosynthesis",
            agents=agents,
            config=FakeConfig(),
            history=None,
            scene_titles=["Light reactions", "Dark reactions", "Calvin cycle"],
        ))
    combined = "".join(events)
    # LLM was consulted (scene titles substitute for chat history)
    mock_llm.assert_called_once()
    assert "light reactions" in combined.lower()


def test_chat_sends_history_to_llm():
    """Prior turns must be injected into the user prompt so follow-up
    questions ('what about the next step?') land coherently."""
    from unittest.mock import patch
    from apps.courses.maic_generation_service import generate_chat_sse

    class FakeConfig:
        pass

    agents = [{"id": "agent-1", "name": "Dr. Priya", "role": "professor"}]
    history = [
        {"role": "user", "content": "Explain Ohm's Law"},
        {"role": "assistant", "content": "V = IR", "agentId": "agent-1"},
    ]
    with patch("apps.courses.maic_generation_service._call_llm") as mock_llm:
        mock_llm.return_value = json.dumps([
            {"agentId": "agent-1", "agentName": "Dr. Priya",
             "content": "Great follow-up!"},
        ])
        list(generate_chat_sse(
            message="What about power?",
            classroom_title="Circuits",
            agents=agents,
            config=FakeConfig(),
            history=history,
        ))
    # The user_prompt passed to the LLM must contain both the earlier
    # question and the earlier answer.
    call_args = mock_llm.call_args
    user_prompt = call_args[0][2]  # positional: (config, system, user, ...)
    assert "Ohm's Law" in user_prompt
    assert "V = IR" in user_prompt
    assert "What about power?" in user_prompt


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
    # Use a mismatch the voice auto-fixer cannot repair: duplicate colors.
    # That forces the LLM retry path to trigger.
    bad = sample_agents()
    bad[2]["color"] = bad[0]["color"]
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


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_agent_profiles_auto_fixes_gender_mismatch(mock_llm, ai_config):
    """When the LLM returns a fixable gender mismatch, we should NOT burn
    another LLM call — auto-fix resolves it in-process."""
    bad = sample_agents()
    # Priya (female) gets the male Prabhat voice — fixable by swapping
    # to Neerja which is free after the fixer releases it from Priya.
    # Wait: sample_agents already has Priya with Neerja. Let's swap:
    # agent-1 (Aarav, male) keeps Prabhat; force agent-2 (Priya, female)
    # onto MadhurNeural (male, student-suiting) — agent-3 will then need
    # its voice swapped too. The simpler path: swap agent-1 and agent-2
    # voices so Priya has Prabhat (male) and Aarav has Neerja (female).
    bad[0]["voiceId"] = "en-IN-NeerjaNeural"   # Aarav (male) + female voice
    bad[1]["voiceId"] = "en-IN-PrabhatNeural"  # Priya (female) + male voice
    mock_llm.return_value = json.dumps({"agents": bad})
    result = generate_agent_profiles_json(
        topic="X", language="en",
        role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ],
        config=ai_config,
    )
    # Exactly 1 LLM call — auto-fix resolved the mismatch without retry.
    assert mock_llm.call_count == 1
    # The fixed roster should have Aarav -> male voice, Priya -> female voice.
    by_name = {a["name"]: a["voiceId"] for a in result["agents"]}
    assert VOICE_BY_ID[by_name["Dr. Aarav Sharma"]]["gender"] == "male"
    assert VOICE_BY_ID[by_name["Ms. Priya Iyer"]]["gender"] == "female"


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_agent_profiles_repairs_role_count_drift(mock_llm, ai_config):
    """Small local models can return useful agents with one role duplicated.

    The product should preserve the roster and repair the role slot rather than
    failing the teacher wizard before classroom generation starts.
    """
    bad = sample_agents()
    bad[1]["role"] = "professor"  # duplicate professor, missing TA
    bad[1]["name"] = "Prof. Priya Reddy"
    mock_llm.return_value = json.dumps({"agents": bad})

    result = generate_agent_profiles_json(
        topic="Photosynthesis", language="en",
        role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ],
        config=ai_config,
    )

    assert mock_llm.call_count == 1
    assert [agent["role"] for agent in result["agents"]] == [
        "professor",
        "teaching_assistant",
        "student",
    ]
    assert result["agents"][1]["name"] == "Ms. Priya Reddy"
    validate_agents(result["agents"], role_slots=[
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 1},
    ])


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_agent_profiles_normalizes_role_aliases(mock_llm, ai_config):
    bad = sample_agents()
    bad[0]["role"] = "Prof"
    bad[1]["role"] = "teachingassistant"
    bad[2]["role"] = "learner"
    mock_llm.return_value = json.dumps({"agents": bad})

    result = generate_agent_profiles_json(
        topic="Photosynthesis", language="en",
        role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ],
        config=ai_config,
    )

    assert mock_llm.call_count == 1
    assert [agent["role"] for agent in result["agents"]] == [
        "professor",
        "teaching_assistant",
        "student",
    ]


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_agent_profiles_drops_extra_agents(mock_llm, ai_config):
    bad = sample_agents() + [
        {"id": "agent-4", "name": "Prof. Extra Rao", "role": "professor",
         "avatar": "👩‍🎓", "color": "#166534",
         "voiceId": "en-IN-NeerjaExpressiveNeural", "voiceProvider": "azure",
         "personality": "Extra.", "expertise": "Extra.", "speakingStyle": "Extra."},
    ]
    mock_llm.return_value = json.dumps({"agents": bad})

    result = generate_agent_profiles_json(
        topic="Photosynthesis", language="en",
        role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ],
        config=ai_config,
    )

    assert mock_llm.call_count == 1
    assert [agent["id"] for agent in result["agents"]] == ["agent-1", "agent-2", "agent-3"]
    validate_agents(result["agents"], role_slots=[
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 1},
    ])


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_agent_profiles_repairs_contract_after_persistent_llm_drift(
    mock_llm,
    ai_config,
):
    bad = [
        {"id": "agent-1", "name": "Dr. Aarav Sharma", "role": "professor",
         "avatar": "👨‍🏫", "color": "#4338CA",
         "voiceId": "en-IN-AaravNeural", "voiceProvider": "azure",
         "personality": "Patient.", "expertise": "Leads.", "speakingStyle": "Warm."},
        {"id": "agent-2", "name": "Prof. Lakshmi Iyer", "role": "professor",
         "avatar": "👨‍🏫", "color": "#4338CA",
         "voiceId": "en-IN-NeerjaNeural", "voiceProvider": "azure",
         "personality": "Kind.", "expertise": "Supports.", "speakingStyle": "Warm."},
        {"id": "agent-3", "name": "Rohan Menon", "role": "student",
         "avatar": "🙋‍♂️", "color": "#4338CA",
         "voiceId": "en-IN-AaravNeural", "voiceProvider": "azure",
         "personality": "Curious.", "expertise": "Asks.", "speakingStyle": "Friendly."},
        {"id": "agent-4", "name": "Aarav Nair", "role": "student",
         "avatar": "🙋‍♂️", "color": "#4338CA",
         "voiceId": "en-IN-PrabhatNeural", "voiceProvider": "azure",
         "personality": "Curious.", "expertise": "Asks.", "speakingStyle": "Friendly."},
    ]
    mock_llm.return_value = json.dumps({"agents": bad})
    role_slots = [
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 2},
    ]

    result = generate_agent_profiles_json(
        topic="Water quality",
        language="en",
        role_slots=role_slots,
        config=ai_config,
    )

    assert mock_llm.call_count == 3
    assert [agent["role"] for agent in result["agents"]] == [
        "professor",
        "teaching_assistant",
        "student",
        "student",
    ]
    validate_agents(result["agents"], role_slots=role_slots)
    assert len({agent["voiceId"] for agent in result["agents"]}) == 4
    assert len({agent["color"] for agent in result["agents"]}) == 4
    assert len({agent["avatar"] for agent in result["agents"]}) == 4


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_agent_profiles_repairs_five_agent_voice_scarcity(
    mock_llm,
    ai_config,
):
    """The teacher wizard commonly asks for professor + TA + 3 students.

    That exactly exhausts the five real Azure voices, so the repair pass must
    allocate student voices before broader adult roles consume them.
    """
    bad = [
        {"id": "agent-1", "name": "Dr. Lakshmi Iyer", "role": "professor",
         "avatar": "👩‍🏫", "color": "#4338CA",
         "voiceId": "hi-IN-SwaraNeural", "voiceProvider": "azure",
         "personality": "Patient.", "expertise": "Leads.", "speakingStyle": "Warm."},
        {"id": "agent-2", "name": "Rehaan Bose", "role": "teaching_assistant",
         "avatar": "👨‍🎓", "color": "#0F766E",
         "voiceId": "en-IN-NeerjaExpressiveNeural", "voiceProvider": "azure",
         "personality": "Kind.", "expertise": "Supports.", "speakingStyle": "Warm."},
        {"id": "agent-3", "name": "Meera Rao", "role": "student",
         "avatar": "🙋‍♀️", "color": "#D97706",
         "voiceId": "en-IN-NeerjaExpressiveNeural", "voiceProvider": "azure",
         "personality": "Curious.", "expertise": "Asks.", "speakingStyle": "Friendly."},
        {"id": "agent-4", "name": "Aashi Verma", "role": "student",
         "avatar": "🙋‍♀️", "color": "#D97706",
         "voiceId": "en-IN-NeerjaExpressiveNeural", "voiceProvider": "azure",
         "personality": "Curious.", "expertise": "Asks.", "speakingStyle": "Friendly."},
        {"id": "agent-5", "name": "Rohan Menon", "role": "student",
         "avatar": "🙋‍♀️", "color": "#D97706",
         "voiceId": "en-IN-AaravNeural", "voiceProvider": "azure",
         "personality": "Curious.", "expertise": "Asks.", "speakingStyle": "Friendly."},
    ]
    mock_llm.return_value = json.dumps({"agents": bad})
    role_slots = [
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 3},
    ]

    result = generate_agent_profiles_json(
        topic="Water quality",
        language="en",
        role_slots=role_slots,
        config=ai_config,
    )

    assert mock_llm.call_count == 3
    assert [agent["role"] for agent in result["agents"]] == [
        "professor",
        "teaching_assistant",
        "student",
        "student",
        "student",
    ]
    validate_agents(result["agents"], role_slots=role_slots)
    assert len({agent["voiceId"] for agent in result["agents"]}) == 5
    assert len({agent["color"] for agent in result["agents"]}) == 5
    assert len({agent["avatar"] for agent in result["agents"]}) == 5


# ---------------------------------------------------------------------------
# regenerate_one_agent tests
# ---------------------------------------------------------------------------

@patch("apps.courses.maic_generation_service._call_llm")
def test_regenerate_one_preserves_locked_voice(mock_llm, ai_config):
    existing = sample_agents()
    new_agent = dict(existing[1])
    new_agent["name"] = "Ms. Ananya Nair"
    new_agent["voiceId"] = "en-IN-NeerjaExpressiveNeural"  # LLM tries to change voice
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


# ---------------------------------------------------------------------------
# CG-P0-1: JSON-repair retry loop in _call_llm  (also covers TEST-P0-3)
# ---------------------------------------------------------------------------
#
# These tests exercise the retry wrapper `_call_llm_with_json_retry` directly
# and the public scene-content / scene-actions paths that wire it in.
#
# Note on fixtures: `json_repair` is aggressive — it "fixes" trailing commas
# and truncated outputs into valid-but-lossy JSON. So the fixtures we reach
# for here are the classes of LLM failure that defeat even json_repair:
#
#   - Non-JSON prose ("Sorry, I can't...", rate-limit HTML pages, stack
#     traces) — these collapse to None after repair.
#   - Structurally-valid JSON that's missing the required key (covered
#     via the validator arg). This is the common "LLM returned a dict
#     but the schema drifted" case — retry with a lowered temperature
#     usually recovers the right shape.
#
# Assertions:
#   (a) retry WAS invoked (mock called N>1 times on failure-then-success)
#   (b) successful re-parse returns the parsed dict
#   (c) total failure after 3 attempts returns None + caller falls through
#       to its fallback without raising.

_GOOD_SCENE_CONTENT = json.dumps({
    "slides": [
        {"id": "slide-1", "title": "Intro", "elements": [],
         "background": "#fff", "speakerScript": "Welcome."},
    ],
})

# Shapes that json_repair CAN'T salvage into valid JSON (returns None on parse):
_RATE_LIMIT_HTML = (
    "<!DOCTYPE html><html><head><title>429</title></head>"
    "<body>Too Many Requests — retry after 60s</body></html>"
)
_NON_JSON_APOLOGY = "I'm sorry, I can't generate that right now."
_BINARY_GARBAGE = "\x00\x01\x02\xff\xfe"

# Shapes that parse but fail validator (schema drift — common LLM failure):
_MISSING_SLIDES_KEY = json.dumps({"summary": "Hello world", "notes": []})
_MISSING_ACTIONS_KEY = json.dumps({"dialogue": "agent speaks"})


@patch("apps.courses.maic_generation_service._call_llm")
def test_json_retry_succeeds_on_second_attempt(mock_llm, ai_config):
    """Non-JSON first response + valid second response → parsed dict returned
    and LLM was invoked twice (the retry path kicked in)."""
    from apps.courses.maic_generation_service import _call_llm_with_json_retry

    mock_llm.side_effect = [_RATE_LIMIT_HTML, _GOOD_SCENE_CONTENT]

    parsed, raw = _call_llm_with_json_retry(
        ai_config, "system", "user",
        temperature=0.6, max_tokens=1024,
        validator=lambda p: isinstance(p, dict) and "slides" in p,
        context_label="test-scene-content",
        classroom_id="cr-abc",
        caller="test_json_retry_succeeds_on_second_attempt",
    )

    assert parsed is not None
    assert "slides" in parsed
    assert parsed["slides"][0]["id"] == "slide-1"
    assert mock_llm.call_count == 2  # first attempt broken, second succeeded


@patch("apps.courses.maic_generation_service._call_llm")
def test_json_retry_lowers_temperature_and_injects_tail(mock_llm, ai_config):
    """Second call must use temperature=0.2 and echo the broken tail in the prompt."""
    from apps.courses.maic_generation_service import _call_llm_with_json_retry

    mock_llm.side_effect = [_NON_JSON_APOLOGY, _GOOD_SCENE_CONTENT]
    _call_llm_with_json_retry(
        ai_config, "system", "original user prompt",
        temperature=0.7,
        validator=lambda p: isinstance(p, dict) and "slides" in p,
        caller="test_json_retry_lowers_temperature_and_injects_tail",
    )

    # Second call — temperature kwarg dropped to 0.2, user prompt contains
    # the continuation instruction + a slice of the broken tail.
    second_call = mock_llm.call_args_list[1]
    assert second_call.kwargs.get("temperature") == 0.2
    second_user_prompt = second_call.args[2]
    assert "original user prompt" in second_user_prompt
    assert "not valid JSON" in second_user_prompt
    assert "only valid json" in second_user_prompt.lower()
    # Tail of the broken response was injected so the LLM sees what it sent
    assert "sorry" in second_user_prompt.lower() or "can't generate" in second_user_prompt.lower()


@patch("apps.courses.maic_generation_service._call_llm")
def test_json_retry_returns_none_after_three_attempts(mock_llm, ai_config):
    """Three broken responses in a row → parsed is None, caller can fall back."""
    from apps.courses.maic_generation_service import _call_llm_with_json_retry

    mock_llm.side_effect = [_RATE_LIMIT_HTML, _NON_JSON_APOLOGY, _BINARY_GARBAGE]
    parsed, raw = _call_llm_with_json_retry(
        ai_config, "system", "user",
        validator=lambda p: isinstance(p, dict) and "slides" in p,
        caller="test_json_retry_returns_none_after_three_attempts",
    )
    assert parsed is None
    assert mock_llm.call_count == 3
    # raw is the last raw text — useful for logging
    assert raw is not None


@patch("apps.courses.maic_generation_service._call_llm")
def test_json_retry_stops_immediately_on_empty_response(mock_llm, ai_config):
    """Empty LLM response has no tail to retry against — skip the retry loop."""
    from apps.courses.maic_generation_service import _call_llm_with_json_retry

    mock_llm.return_value = None
    parsed, raw = _call_llm_with_json_retry(
        ai_config, "system", "user",
        validator=lambda p: isinstance(p, dict),
        caller="test_json_retry_stops_immediately_on_empty_response",
    )
    assert parsed is None
    assert raw is None
    assert mock_llm.call_count == 1  # did NOT burn extra attempts


@patch("apps.courses.maic_generation_service._call_llm")
def test_json_retry_validator_rejects_missing_key(mock_llm, ai_config):
    """Parseable JSON that's missing a required key should trigger a retry."""
    from apps.courses.maic_generation_service import _call_llm_with_json_retry

    # First response parses fine but is missing "actions"; second is valid.
    mock_llm.side_effect = [
        json.dumps({"notes": "hi"}),
        json.dumps({"actions": [{"type": "speech", "text": "ok"}]}),
    ]
    parsed, _raw = _call_llm_with_json_retry(
        ai_config, "system", "user",
        validator=lambda p: isinstance(p, dict) and "actions" in p,
        context_label="scene-actions",
        caller="test_json_retry_validator_rejects_missing_key",
    )
    assert parsed is not None
    assert "actions" in parsed
    assert mock_llm.call_count == 2


# --- Integration: public paths wire the retry helper -----------------------

@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_scene_content_retries_on_schema_drift(mock_llm, ai_config):
    """generate_scene_content should re-ask the LLM if the first response
    is structurally-valid JSON but missing the `slides` key (schema drift),
    then return the parsed content once the retry recovers."""
    from apps.courses.maic_generation_service import generate_scene_content

    good_payload = json.dumps({
        "slides": [
            {"id": "slide-s1-1", "title": "Intro",
             "elements": [{"id": "el-1", "type": "image",
                           "content": "photosynthesis diagram"}],
             "background": "#fff", "speakerScript": "Welcome.", "duration": 40},
        ],
    })
    # Post CG-P0-1-F2: lecture validator now requires "slides" / "slide",
    # so schema-drift triggers a retry even if the bad response parses as
    # JSON. Use the hard-fail fixture — both paths exercise the retry.
    mock_llm.side_effect = [_RATE_LIMIT_HTML, good_payload]

    scene = {
        "id": "scene-1", "title": "Intro to photosynthesis",
        "type": "lecture", "slideCount": 1, "agentIds": ["agent-1"],
    }
    agents = [{"id": "agent-1", "name": "Dr. Aarav Sharma", "role": "professor"}]
    result = generate_scene_content(scene, agents, "en", ai_config)

    assert result is not None
    assert "slides" in result
    # The retry path was taken (two LLM calls, not one fallback)
    assert mock_llm.call_count == 2


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_scene_content_lecture_retries_on_missing_slides_key(
    mock_llm, ai_config,
):
    """CG-P0-1-F2: lecture scene-content validator now rejects parseable JSON
    that's missing the ``slides`` key (schema drift), not just unparseable
    responses. Confirms the helper's retry is engaged on the common path.
    """
    from apps.courses.maic_generation_service import generate_scene_content

    good_payload = json.dumps({
        "slides": [
            {"id": "slide-s1-1", "title": "Intro", "elements": [],
             "background": "#fff", "speakerScript": "Hi.", "duration": 30},
        ],
    })
    # Attempt 1 parses fine but has no "slides" → validator fails → retry.
    # Attempt 2 returns a valid payload.
    mock_llm.side_effect = [_MISSING_SLIDES_KEY, good_payload]

    scene = {
        "id": "scene-1", "title": "Intro", "type": "lecture",
        "slideCount": 1, "agentIds": ["agent-1"],
    }
    agents = [{"id": "agent-1", "name": "Dr. Aarav Sharma", "role": "professor"}]
    result = generate_scene_content(scene, agents, "en", ai_config)

    assert result is not None
    assert "slides" in result
    assert mock_llm.call_count == 2


@patch("apps.courses.maic_generation_service._fallback_scene_content")
@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_scene_content_falls_back_after_three_bad_responses(
    mock_llm, mock_fallback, ai_config,
):
    """Three unparseable responses → generate_scene_content calls its
    fallback and doesn't raise."""
    from apps.courses.maic_generation_service import generate_scene_content

    mock_llm.side_effect = [_RATE_LIMIT_HTML, _NON_JSON_APOLOGY, _BINARY_GARBAGE]
    mock_fallback.return_value = {"slides": [], "_fallback": True}

    scene = {"id": "scene-1", "title": "X", "type": "lecture",
             "slideCount": 1, "agentIds": []}
    agents = []
    result = generate_scene_content(scene, agents, "en", ai_config)

    assert result == {"slides": [], "_fallback": True}
    assert mock_llm.call_count == 3  # all 3 attempts exhausted
    assert mock_fallback.called


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_scene_actions_retries_on_schema_drift(mock_llm, ai_config):
    """generate_scene_actions validator rejects missing `actions` key →
    triggers the retry path, then succeeds on attempt 2."""
    from apps.courses.maic_generation_service import generate_scene_actions

    good_payload = json.dumps({
        "actions": [
            {"type": "speech", "agentId": "agent-1", "text": "Hello."},
            {"type": "speech", "agentId": "agent-2", "text": "Hi there."},
        ],
    })
    # First response is valid JSON but missing the required "actions" key —
    # exactly the schema-drift case the validator guards against.
    mock_llm.side_effect = [_MISSING_ACTIONS_KEY, good_payload]

    scene = {
        "id": "scene-1", "title": "Lecture", "type": "lecture",
        "agentIds": ["agent-1", "agent-2"],
        "content": {"slides": [{"elements": [], "speakerScript": "s"}]},
    }
    agents = [
        {"id": "agent-1", "name": "Dr. Aarav Sharma", "role": "professor"},
        {"id": "agent-2", "name": "Ms. Priya Iyer", "role": "teaching_assistant"},
    ]
    result = generate_scene_actions(scene, agents, "en", ai_config)

    assert result is not None
    assert "actions" in result
    assert mock_llm.call_count == 2


@patch("apps.courses.maic_generation_service._fallback_actions")
@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_scene_actions_falls_back_after_three_bad_responses(
    mock_llm, mock_fallback, ai_config,
):
    """generate_scene_actions → three unparseable responses → fallback path used."""
    from apps.courses.maic_generation_service import generate_scene_actions

    mock_llm.side_effect = [_RATE_LIMIT_HTML, _NON_JSON_APOLOGY, _BINARY_GARBAGE]
    mock_fallback.return_value = {"actions": [
        {"type": "speech", "agentId": "agent-1", "text": "fallback"},
    ]}

    scene = {
        "id": "scene-1", "title": "X", "type": "lecture",
        "agentIds": ["agent-1"],
        "content": {"slides": [{"elements": [], "speakerScript": ""}]},
    }
    agents = [{"id": "agent-1", "name": "Dr. Aarav Sharma", "role": "professor"}]
    result = generate_scene_actions(scene, agents, "en", ai_config)

    assert result is not None
    assert "actions" in result
    assert mock_llm.call_count == 3
    assert mock_fallback.called


# ---------------------------------------------------------------------------
# CG-P0-1-F5: Structured WARN/ERROR log observability for retry loop
# ---------------------------------------------------------------------------

@patch("apps.courses.maic_generation_service._call_llm")
def test_json_retry_emits_warn_with_structured_fields_on_retry(
    mock_llm, ai_config, caplog,
):
    """Attempt 1 fails (non-JSON), attempt 2 succeeds → one structured WARN
    emitted for attempt 1 with stable fields: metric, attempt, path,
    classroom_id."""
    import logging
    from apps.courses.maic_generation_service import _call_llm_with_json_retry

    mock_llm.side_effect = [_RATE_LIMIT_HTML, _GOOD_SCENE_CONTENT]

    with caplog.at_level(logging.WARNING,
                         logger="apps.courses.maic_generation_service"):
        parsed, _raw = _call_llm_with_json_retry(
            ai_config, "system", "user",
            validator=lambda p: isinstance(p, dict) and "slides" in p,
            caller="generate_scene_content:lecture",
            classroom_id="cr-test-001",
        )

    assert parsed is not None

    warn_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and getattr(r, "metric", None) == "llm_json_retry"
    ]
    assert len(warn_records) == 1, (
        f"Expected exactly 1 structured WARN; got: {[r.message for r in warn_records]}"
    )
    rec = warn_records[0]
    assert rec.attempt == 1
    assert rec.path == "generate_scene_content:lecture"
    assert rec.classroom_id == "cr-test-001"


@patch("apps.courses.maic_generation_service._call_llm")
def test_json_retry_emits_error_with_outcome_fallback_on_exhaustion(
    mock_llm, ai_config, caplog,
):
    """All 3 attempts fail → one ERROR with metric=llm_json_retry,
    attempts=3, outcome=fallback, path and classroom_id fields set."""
    import logging
    from apps.courses.maic_generation_service import _call_llm_with_json_retry

    mock_llm.side_effect = [_RATE_LIMIT_HTML, _NON_JSON_APOLOGY, _BINARY_GARBAGE]

    with caplog.at_level(logging.ERROR,
                         logger="apps.courses.maic_generation_service"):
        parsed, _raw = _call_llm_with_json_retry(
            ai_config, "system", "user",
            validator=lambda p: isinstance(p, dict) and "slides" in p,
            caller="generate_scene_actions",
            classroom_id="cr-test-002",
        )

    assert parsed is None

    error_records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR
        and getattr(r, "metric", None) == "llm_json_retry"
    ]
    assert len(error_records) == 1, (
        f"Expected exactly 1 structured ERROR; got: {[r.message for r in error_records]}"
    )
    rec = error_records[0]
    assert rec.attempts == 3
    assert rec.outcome == "fallback"
    assert rec.path == "generate_scene_actions"
    assert rec.classroom_id == "cr-test-002"


# ---------------------------------------------------------------------------
# CG-P0-2: Server-side length-budget enforcement
# ---------------------------------------------------------------------------

def test_budget_truncates_slide_title_over_limit(caplog):
    """A slide title over `SLIDE_TITLE_MAX_CHARS` must be truncated with a WARN log.

    CG-P0-7 raised the cap from 120 → 160; derive overflow size from the
    constant so the fixture self-adapts to future cap changes.
    """
    import logging
    from apps.courses.maic_generation_service import _enforce_length_budgets, SLIDE_TITLE_MAX_CHARS

    long_title = "A" * (SLIDE_TITLE_MAX_CHARS - 1) + " overflow word here"
    parsed = {"slides": [{"title": long_title, "elements": []}]}

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        result = _enforce_length_budgets(parsed, "lecture")

    assert len(result["slides"][0]["title"]) <= SLIDE_TITLE_MAX_CHARS
    # Must have logged a structured WARN
    warn_records = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "length_budget_truncate"
        and getattr(r, "field", None) == "slide.title"
    ]
    assert len(warn_records) == 1
    rec = warn_records[0]
    assert rec.original_chars == len(long_title)
    assert rec.truncated_chars <= SLIDE_TITLE_MAX_CHARS
    assert rec.path == "lecture"


def test_budget_truncates_bullets_list_over_count(caplog):
    """A slide with `SLIDE_BULLETS_MAX_COUNT + 1` bullets must be trimmed
    with a WARN log. CG-P0-7 raised the cap from 7 → 12; derive the
    overflow count from the constant."""
    import logging
    from apps.courses.maic_generation_service import _enforce_length_budgets, SLIDE_BULLETS_MAX_COUNT

    overflow_count = SLIDE_BULLETS_MAX_COUNT + 1
    elements = [
        {"id": f"el-{i}", "type": "bullet", "content": f"Point {i}"}
        for i in range(overflow_count)
    ]
    parsed = {"slides": [{"title": "Slide", "elements": elements}]}

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        result = _enforce_length_budgets(parsed, "lecture")

    remaining_bullets = [
        el for el in result["slides"][0]["elements"]
        if el.get("type") == "bullet"
    ]
    assert len(remaining_bullets) == SLIDE_BULLETS_MAX_COUNT

    warn_records = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "length_budget_truncate"
        and getattr(r, "field", None) == "slide.bullets_count"
    ]
    assert len(warn_records) == 1
    assert warn_records[0].original_chars == overflow_count
    assert warn_records[0].truncated_chars == SLIDE_BULLETS_MAX_COUNT


def test_budget_truncates_speaker_notes_over_limit(caplog):
    """Speaker notes over `SPEAKER_NOTES_MAX_CHARS` must be truncated with a WARN.

    CG-P0-7 raised the cap from 1500 → 4000; the test derives overflow from
    the live constant so future cap changes don't re-stale this fixture.
    """
    import logging
    from apps.courses.maic_generation_service import _enforce_length_budgets, SPEAKER_NOTES_MAX_CHARS

    long_notes = "x" * (SPEAKER_NOTES_MAX_CHARS + 50) + " overflow"
    parsed = {"slides": [{"title": "T", "speakerScript": long_notes, "elements": []}]}

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        result = _enforce_length_budgets(parsed, "lecture")

    assert len(result["slides"][0]["speakerScript"]) <= SPEAKER_NOTES_MAX_CHARS

    warn_records = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "length_budget_truncate"
        and getattr(r, "field", None) == "slide.speakerScript"
    ]
    assert len(warn_records) == 1
    assert warn_records[0].original_chars == len(long_notes)
    assert warn_records[0].truncated_chars <= SPEAKER_NOTES_MAX_CHARS


def test_budget_truncates_quiz_option_over_limit(caplog):
    """A quiz option over `QUIZ_OPTION_MAX_CHARS` must be truncated with a WARN.

    CG-P0-7 raised the cap from 200 → 300; derive the overflow string size
    from the constant so the fixture self-adapts.
    """
    import logging
    from apps.courses.maic_generation_service import _enforce_length_budgets, QUIZ_OPTION_MAX_CHARS

    long_option = "B" * (QUIZ_OPTION_MAX_CHARS - 2) + " extra word here"
    parsed = {
        "questions": [
            {
                "text": "Which is correct?",
                "options": [
                    {"text": "Short option"},
                    {"text": long_option},
                ],
            }
        ]
    }

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        result = _enforce_length_budgets(parsed, "quiz")

    truncated_opt = result["questions"][0]["options"][1]["text"]
    assert len(truncated_opt) <= QUIZ_OPTION_MAX_CHARS
    # Short option untouched
    assert result["questions"][0]["options"][0]["text"] == "Short option"

    warn_records = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "length_budget_truncate"
        and getattr(r, "field", None) == "quiz.option_text"
    ]
    assert len(warn_records) == 1
    assert warn_records[0].original_chars == len(long_option)
    assert warn_records[0].truncated_chars <= QUIZ_OPTION_MAX_CHARS


def test_budget_no_mutation_when_all_within_limits(caplog):
    """When all fields are within budget, no mutation occurs and no WARN is emitted."""
    import logging
    from apps.courses.maic_generation_service import _enforce_length_budgets

    parsed = {
        "slides": [
            {
                "title": "Short title",
                "speakerScript": "Brief notes.",
                "elements": [
                    {"id": "el-1", "type": "bullet", "content": "Short bullet"},
                ],
            }
        ],
        "actions": [
            {"type": "speech", "agentId": "agent-1", "text": "Hello."},
        ],
    }
    import copy
    original = copy.deepcopy(parsed)

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        result = _enforce_length_budgets(parsed, "lecture")

    # No WARN about length_budget_truncate
    budget_warns = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "length_budget_truncate"
    ]
    assert budget_warns == []
    # Content unchanged
    assert result["slides"][0]["title"] == original["slides"][0]["title"]
    assert result["slides"][0]["speakerScript"] == original["slides"][0]["speakerScript"]
    assert result["actions"][0]["text"] == original["actions"][0]["text"]


def test_budget_idempotent_no_second_log(caplog):
    """Running _enforce_length_budgets twice on already-truncated output must not
    emit a second WARN and must not further mutate the content."""
    import logging
    from apps.courses.maic_generation_service import _enforce_length_budgets, SLIDE_TITLE_MAX_CHARS

    long_title = "Z" * (SLIDE_TITLE_MAX_CHARS - 1) + " over"  # over budget
    parsed = {"slides": [{"title": long_title, "elements": []}]}

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        # First pass — truncates and logs once
        _enforce_length_budgets(parsed, "lecture")

    first_pass_warns = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "length_budget_truncate"
    ]
    assert len(first_pass_warns) == 1
    title_after_first = parsed["slides"][0]["title"]
    assert len(title_after_first) <= SLIDE_TITLE_MAX_CHARS

    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        # Second pass — already within budget, must be a no-op
        _enforce_length_budgets(parsed, "lecture")

    second_pass_warns = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "length_budget_truncate"
    ]
    assert second_pass_warns == [], "second pass must not emit additional WARN"
    assert parsed["slides"][0]["title"] == title_after_first  # no further mutation


# ---------------------------------------------------------------------------
# SPRINT-2-BATCH-2-F8: parametrized caller f-string for lecture vs quiz
# ---------------------------------------------------------------------------

_GOOD_QUIZ_CONTENT = json.dumps({
    "questions": [
        {
            "id": "q1",
            "text": "What is photosynthesis?",
            "options": [
                {"id": "o1", "text": "Option A", "isCorrect": False},
                {"id": "o2", "text": "Option B", "isCorrect": True},
            ],
            "explanation": "Because.",
            "type": "multiple_choice",
        }
    ],
})

_GOOD_LECTURE_CONTENT = json.dumps({
    "slides": [
        {
            "id": "slide-s1-1",
            "title": "Intro",
            "elements": [
                {"id": "el-1", "type": "image", "content": "photosynthesis diagram"},
            ],
            "background": "#fff",
            "speakerScript": "Welcome.",
            "duration": 40,
        },
    ],
})


@pytest.mark.parametrize("scene_type,good_payload,caller_suffix", [
    ("lecture", _GOOD_LECTURE_CONTENT, "lecture"),
    ("quiz", _GOOD_QUIZ_CONTENT, "quiz"),
])
@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_scene_content_caller_value_per_scene_type(
    mock_llm,
    ai_config,
    caplog,
    scene_type,
    good_payload,
    caller_suffix,
):
    """generate_scene_content passes caller=f'generate_scene_content:{scene_type}'
    to _call_llm_with_json_retry.  When the first response is broken (forces a
    retry WARN), the WARN record's ``path`` field must reflect the scene_type —
    so ops can filter retry rates by lecture vs. quiz without free-text grep.

    SPRINT-2-BATCH-2-F8: exercises both 'lecture' and 'quiz' variants via
    pytest.mark.parametrize over caller_suffix.
    """
    import logging
    from apps.courses.maic_generation_service import generate_scene_content

    # Attempt 1: break the response so the retry WARN fires.
    # Attempt 2: valid payload matching the scene_type shape.
    mock_llm.side_effect = [
        "<!DOCTYPE html>rate limit",  # parse failure → retry
        good_payload,
    ]

    scene = {
        "id": "scene-1",
        "title": "Photosynthesis overview",
        "type": scene_type,
        "slideCount": 1,
        "questionCount": 1,
        "agentIds": ["agent-1"],
    }
    agents = [{"id": "agent-1", "name": "Dr. Aarav Sharma", "role": "professor"}]

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        result = generate_scene_content(scene, agents, "en", ai_config)

    assert result is not None
    assert mock_llm.call_count == 2

    # The retry WARN's ``path`` field must equal the LLMCallPath caller value.
    # SPRINT-2-BATCH-8-F9 pinned the caller to `scene_content_{lecture,quiz}`.
    warn_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and getattr(r, "metric", None) == "llm_json_retry"
    ]
    assert len(warn_records) == 1, (
        f"Expected exactly 1 retry WARN for scene_type={scene_type!r}; "
        f"got {[r.message for r in warn_records]}"
    )
    rec = warn_records[0]
    expected_caller = f"scene_content_{caller_suffix}"
    assert rec.path == expected_caller, (
        f"path={rec.path!r} — expected {expected_caller!r} for scene_type={scene_type!r}"
    )


# ---------------------------------------------------------------------------
# SPRINT-2-BATCH-3-F7: actions[].text (speech) truncation coverage
# ---------------------------------------------------------------------------

def test_budget_truncates_speech_action_text_over_limit(caplog):
    """A speech action text over `SCENE_SPEECH_MAX_CHARS` must be truncated
    with a structured WARN (field=action.speech.text).

    SPRINT-2-BATCH-3-F7 — covers the `actions[*].type == "speech"` path.
    CG-P0-7 raised the cap from 2000 → 5000; this test now derives the
    overflow size from the live constant so future cap changes don't
    re-stale the fixture.
    """
    import logging
    from apps.courses.maic_generation_service import (
        _enforce_length_budgets,
        SCENE_SPEECH_MAX_CHARS,
    )

    # Always over the cap by ~10%, regardless of what the cap currently is.
    long_speech = "w" * (SCENE_SPEECH_MAX_CHARS + 10) + " overflow"
    assert len(long_speech) > SCENE_SPEECH_MAX_CHARS

    parsed = {
        "actions": [
            {"type": "speech", "agentId": "agent-1", "text": long_speech},
            {"type": "spotlight", "elementId": "el-1"},           # non-speech, untouched
            {"type": "speech", "agentId": "agent-2", "text": "Short enough text."},
        ]
    }

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        result = _enforce_length_budgets(parsed, "scene_actions")

    # Truncated to within budget
    truncated = result["actions"][0]["text"]
    assert len(truncated) <= SCENE_SPEECH_MAX_CHARS

    # Non-speech action untouched (no src field)
    assert result["actions"][1].get("text") is None

    # Short speech untouched
    assert result["actions"][2]["text"] == "Short enough text."

    # Structured WARN emitted exactly once with correct fields
    warn_records = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "length_budget_truncate"
        and getattr(r, "field", None) == "action.speech.text"
    ]
    assert len(warn_records) == 1, (
        f"Expected exactly 1 budget WARN; got: {[r.message for r in warn_records]}"
    )
    rec = warn_records[0]
    assert rec.original_chars == len(long_speech)
    assert rec.truncated_chars <= SCENE_SPEECH_MAX_CHARS
    assert rec.path == "scene_actions"


def test_budget_no_truncation_speech_at_exact_limit():
    """A speech action text at exactly SCENE_SPEECH_MAX_CHARS must NOT be
    truncated or warned about.  Confirms the `<= max_chars` short-circuit
    in `_truncate_to_word_boundary`.
    """
    from apps.courses.maic_generation_service import (
        _enforce_length_budgets,
        SCENE_SPEECH_MAX_CHARS,
    )

    at_limit = "x" * SCENE_SPEECH_MAX_CHARS
    parsed = {"actions": [{"type": "speech", "agentId": "agent-1", "text": at_limit}]}
    result = _enforce_length_budgets(parsed, "scene_actions")
    assert result["actions"][0]["text"] == at_limit  # unchanged


# ---------------------------------------------------------------------------
# SPRINT-2-BATCH-3-F8: string-form quiz options truncation coverage
# ---------------------------------------------------------------------------

def test_budget_truncates_string_form_quiz_options(caplog):
    """When quiz options are a list of plain strings (e.g. ['A', 'B', ...]),
    each over-budget string must be truncated and the list replaced in-place.

    SPRINT-2-BATCH-3-F8 — covers the string-list option path in
    `_enforce_length_budgets` at maic_generation_service.py:259-273.
    """
    import logging
    from apps.courses.maic_generation_service import (
        _enforce_length_budgets,
        QUIZ_OPTION_MAX_CHARS,
    )

    # Two over-limit strings, two within-limit strings.
    # CG-P0-7: derive sizes from the live constant so the fixture self-adapts.
    over_a = "A" * (QUIZ_OPTION_MAX_CHARS - 2) + " too long"
    over_b = "B" * (QUIZ_OPTION_MAX_CHARS - 1) + " also too long"
    short_c = "C short"
    short_d = "D also short"

    assert len(over_a) > QUIZ_OPTION_MAX_CHARS
    assert len(over_b) > QUIZ_OPTION_MAX_CHARS
    assert len(short_c) <= QUIZ_OPTION_MAX_CHARS
    assert len(short_d) <= QUIZ_OPTION_MAX_CHARS

    parsed = {
        "questions": [
            {
                "text": "Pick the right answer",
                "options": [over_a, over_b, short_c, short_d],
            }
        ]
    }

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_generation_service"):
        result = _enforce_length_budgets(parsed, "quiz")

    options_out = result["questions"][0]["options"]

    # All 4 strings preserved in order
    assert len(options_out) == 4

    # Over-limit options are now within budget
    assert len(options_out[0]) <= QUIZ_OPTION_MAX_CHARS
    assert len(options_out[1]) <= QUIZ_OPTION_MAX_CHARS

    # Short options unchanged
    assert options_out[2] == short_c
    assert options_out[3] == short_d

    # All output elements are still strings (type not changed)
    assert all(isinstance(o, str) for o in options_out)

    # Two structured WARN records (one per truncated option)
    warn_records = [
        r for r in caplog.records
        if getattr(r, "metric", None) == "length_budget_truncate"
        and getattr(r, "field", None) == "quiz.option_text"
    ]
    assert len(warn_records) == 2, (
        f"Expected 2 budget WARNs (one per over-limit option); "
        f"got {len(warn_records)}: {[r.message for r in warn_records]}"
    )
    for rec in warn_records:
        assert rec.truncated_chars <= QUIZ_OPTION_MAX_CHARS
        assert rec.path == "quiz"


def test_budget_string_quiz_options_within_limit_no_warn():
    """String-form options all within budget: no mutation, no WARN."""
    from apps.courses.maic_generation_service import _enforce_length_budgets, QUIZ_OPTION_MAX_CHARS

    options = ["Alpha", "Beta", "Gamma", "Delta"]
    assert all(len(o) <= QUIZ_OPTION_MAX_CHARS for o in options)

    parsed = {"questions": [{"text": "Q?", "options": options}]}
    result = _enforce_length_budgets(parsed, "quiz")

    assert result["questions"][0]["options"] == options  # unchanged reference-equal


# ---------------------------------------------------------------------------
# SPRINT-2-BATCH-3-F3: _truncate_to_word_boundary defensive whitespace fallback
# ---------------------------------------------------------------------------

def test_truncate_to_word_boundary_pure_whitespace_fallback():
    """Pure-whitespace input longer than max_chars returns "" after lstrip fallback.

    SPRINT-2-BATCH-5-F5 update: the fallback now tries lstrip() first.  For
    truly all-whitespace input lstrip() yields "" — the function returns ""
    and lets upstream callers decide whether to substitute a placeholder.
    This avoids shipping max_chars whitespace characters as "content".
    """
    from apps.courses.maic_generation_service import _truncate_to_word_boundary

    # 50 repetitions of 3 spaces = 150 chars of whitespace, well over max_chars=120
    whitespace_input = "   " * 50
    assert len(whitespace_input) == 150

    result = _truncate_to_word_boundary(whitespace_input, max_chars=120)

    # For all-whitespace input, lstrip() → "" → function returns "".
    assert result == "", (
        f"pure-whitespace input should return '' after lstrip fallback, got {result!r}"
    )
    assert len(result) <= 120, f"result length {len(result)} exceeds max_chars=120"


def test_truncate_to_word_boundary_leading_whitespace_lstrip_fallback():
    """Leading whitespace + real content: lstrip fallback returns non-empty hard-slice.

    SPRINT-2-BATCH-5-F5 — covers the `text.lstrip()[:max_chars]` path when
    rstrip after word-boundary snap yields empty but the input has real content
    after leading whitespace.
    """
    from apps.courses.maic_generation_service import _truncate_to_word_boundary

    # 30 leading spaces + real word at position 30; max_chars=10 forces the
    # truncated slice [:10] to be all-whitespace → rstrip → "" → lstrip fallback.
    leading_ws_input = " " * 30 + "hello world this is content"

    result = _truncate_to_word_boundary(leading_ws_input, max_chars=10)

    # lstrip removes the 30 spaces, then [:10] hard-slices to "hello worl"
    assert result == "hello worl", f"expected lstrip hard-slice fallback, got {result!r}"
    assert len(result) <= 10
