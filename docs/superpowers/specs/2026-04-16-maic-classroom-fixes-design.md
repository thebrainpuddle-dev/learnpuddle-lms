# MAIC Classroom Fixes + Indian Agent Selection — Design

**Date:** 2026-04-16
**Status:** Approved by product owner (in brainstorm, 2026-04-16)
**Scope:** Fix three production bugs in the existing MAIC AI Classroom + add a new agent-selection wizard step with LLM-generated Indian personas and Azure en-IN voices.
**Non-goals:** Re-implementing OpenMAIC's full prompt system, director graph, whiteboard ledger, or interactive/PBL scene generation. Those remain future work.

---

## 1. Problem Statement

Three production bugs block the current AI Classroom experience, and the generated agents feel generic:

1. **Student Q&A fails with "Teacher or admin access required."** Students in the classroom player hit hardcoded teacher-only endpoints when they use the chat/roundtable.
2. **Subtitles appear before audio plays.** The speech action sets subtitle state immediately, then awaits TTS fetch + audio load (~100–300ms), so viewers read before they hear.
3. **Navigating to a new slide or scene mid-playback breaks audio.** A race condition between scene-teardown and auto-play leaves stale audio callbacks firing against the new scene's state.

Separately, the LLM-generated agents (`professor` / `teaching_assistant` / `student_rep` / `moderator`) use generic Western names and feel interchangeable in voice and persona — not what our SaaS target audience (Indian K-12 / higher-ed) wants.

## 2. Goals

- Fix all three bugs so the classroom plays smoothly end-to-end for both teachers and students.
- Pre-generate all speech audio at publish time so playback is always lag-free.
- Let teachers (and students creating their own classrooms) see and tune their classroom's agents before content is generated. Agents have distinct Indian names, personas, and Azure en-IN voices.
- Wire the persona and speaking-style into downstream prompts so agents actually sound distinct during playback and chat.
- Ship production-ready — no half-implemented UI, no feature flags left half-enabled.

## 3. Decisions Locked In (from brainstorm)

| Decision | Choice | Rationale |
|---|---|---|
| Agent delivery | LLM-generated per classroom (Option B) | Fresh, topic-grounded agents each time; consistent Indian styling enforced via system prompt. |
| Where user sees agents | New wizard step between Topic and Outline (Option A) | Agents become authoritative input to outline generation — no retrofitting. |
| Agent controls | Regenerate-all + per-card regen + inline edit (Option B) | Balances control and UI complexity; no add/remove/reorder. |
| Voices | Azure en-IN only, with live preview (Option A) | 7 solid voices already wired; cheap; preview is a trivial 1-button fetch. |
| Audio strategy | Pre-generate all audio at publish (Option C) | Removes the network race entirely; matches OpenMAIC's server-generated flow. |

## 4. Architecture Overview

Five workstreams, delivered in dependency order:

| ID | Workstream | Depends On |
|---|---|---|
| **WS-A** | Permission fixes — frontend URL plumbing | — |
| **WS-B** | Agent-profile backend + system prompts | — |
| **WS-C** | Agent picker wizard step (UI) | WS-B |
| **WS-D** | Pre-gen audio pipeline + publish wiring | WS-B (voice id on agent) |
| **WS-E** | Speech action rewrite (frontend engine) | WS-D's URL schema |

WS-A and WS-B/C can run in parallel. WS-E blocks on WS-D. All together: ~3 engineer-days solo, ~1.5 days in parallel across 3 subagents.

### Guiding principles

- **Every async speech action carries a `generationToken`.** Incremented on stop or scene change. Stale callbacks are no-ops. This kills Bug 3 at the root.
- **Subtitles fire on the `<audio>` element's `playing` event, never on code execution order.** This kills Bug 2 at the root.
- **Pre-generated audio is the primary path.** Live TTS only for dynamic chat/discussion, and even then through the reading-time-estimate fallback if TTS is unavailable.
- **All persona + voice info travels with the classroom content JSON.** Backend is stateless across requests.
- **Idempotent re-publish.** Speech action `audioId` is a deterministic hash — re-publishing only re-generates changed text; unchanged audio is reused.

## 5. Data Model Changes

### 5.1 SpeechAction (type addition)

```ts
interface SpeechAction {
  type: 'speech';
  agentId: string;
  text: string;
  // New fields (stamped on publish):
  audioId: string;          // sha256(sceneId|actionIdx|text|voiceId).slice(0,12).
                            // Storage path includes `classroomId`, so hash collision scope is intra-classroom only.
  audioUrl?: string;        // /media/tenant/{tid}/maic/tts/{classroomId}/{audioId}.mp3
  voiceId?: string;         // Resolved voice so pre-gen can run without agent lookup.
}
```

### 5.2 MAICContent (shape addition)

```ts
interface MAICContent {
  agents: MAICAgent[];        // now the authoritative roster; referenced by id across scenes
  scenes: MAICScene[];
  audioManifest: {
    status: 'idle' | 'generating' | 'ready' | 'partial' | 'failed';
    progress: number;         // 0–100
    totalActions: number;
    completedActions: number;
    failedAudioIds: string[];
    generatedAt: string | null;   // ISO timestamp
  };
}
```

### 5.3 MAICAgent (field additions)

```ts
interface MAICAgent {
  id: string;               // "agent-1" … "agent-4"
  name: string;             // "Dr. Aarav Sharma"
  role: 'professor' | 'teaching_assistant' | 'student' | 'moderator';
                            // Canonical enum. Legacy value `student_rep` is renamed to `student`
                            // as part of WS-B; outline/actions/chat prompts migrated accordingly.
  avatar: string;           // emoji from curated set
  color: string;            // hex from fixed 6-color palette
  // New:
  voiceId: string;          // "en-IN-PrabhatNeural"
  voiceProvider: 'azure';   // future-proofing
  personality: string;      // 1–2 sentences, topic-grounded
  expertise: string;        // 1 sentence
  speakingStyle: string;    // e.g., "warm, reassuring, occasionally says 'theek hai?'"
}
```

### 5.4 Migration

Existing DRAFT/READY classrooms without `audioManifest` or the new speech fields: one-time Django data migration stamps `audioManifest={status:'idle', progress:0, totalActions:0, completedActions:0, failedAudioIds:[], generatedAt:null}`. Existing speech actions get `audioId` computed and stamped; `audioUrl`/`voiceId` remain null until next publish. No data loss. Republishing regenerates audio cleanly.

## 6. WS-A — Permission Fixes

### Root cause

Four hardcoded `/teacher/` URLs that students hit when using non-ChatPanel components.

### Changes

**New helper** `frontend/src/lib/maic/endpoints.ts`:
```ts
export function maicChatUrl(role: 'teacher' | 'student'): string {
  return `/api/v1/${role}/maic/chat/`;
}
export function maicTtsUrl(role: 'teacher' | 'student'): string {
  return `/api/v1/${role}/maic/generate/tts/`;
}
```

**Consumers:**

| File | Line | Current | Fix |
|---|---|---|---|
| `components/maic/RoundtablePanel.tsx` | 305 | hardcoded teacher | accept `role` prop, call `maicChatUrl(role)` |
| `lib/orchestration/director.ts` | 237 | hardcoded teacher | constructor takes `role`; thread to `streamMAIC` |
| `components/maic/PBLRenderer.tsx` | 189 | hardcoded teacher | accept `role` prop |
| `components/maic/ChatPanel.tsx` | 190 | role-aware ad-hoc | rewrite with helper for consistency |
| `lib/maicActionEngine.ts` | 333 | hardcoded teacher TTS | use `this.ttsEndpoint` (already role-aware from constructor) |

**Role plumbing:** `MAICPlayerPage.tsx` (teacher and student variants) already knows its role by which page it is. Pass `role` down through `Stage → RoundtablePanel / ChatPanel / PBLRenderer / Director`. Single prop drill, no context provider needed.

**Backend audit (defensive):** verify these have `@student_or_admin`, not `@teacher_or_admin`:
- `student_maic_chat`
- `student_maic_generate_tts`
- `student_maic_generate_scene_actions`
- `student_maic_quiz_grade`

### Tests

- Playwright: student logs in → opens published classroom → sends chat → 200 + agent reply arrives.
- pytest: `test_student_chat_succeeds_with_student_role`, `test_teacher_chat_rejects_student_role`.

### Effort

~3 hours. 5 file edits + 2 tests.

## 7. WS-B — Agent-Profile Backend + System Prompts

### 7.1 Voice roster

Hardcoded in `backend/apps/courses/maic_voices.py`:

```python
AZURE_IN_VOICES = [
    {"id": "en-IN-PrabhatNeural",   "gender": "male",   "tone": "authoritative", "age": "adult",       "suits": ["professor"]},
    {"id": "en-IN-NeerjaNeural",    "gender": "female", "tone": "warm",          "age": "adult",       "suits": ["teaching_assistant", "professor"]},
    {"id": "en-IN-AaravNeural",     "gender": "male",   "tone": "friendly",      "age": "young adult", "suits": ["student"]},
    {"id": "en-IN-AashiNeural",     "gender": "female", "tone": "youthful",      "age": "young adult", "suits": ["student"]},
    {"id": "en-IN-KavyaNeural",     "gender": "female", "tone": "energetic",     "age": "adult",       "suits": ["teaching_assistant", "moderator"]},
    {"id": "en-IN-KunalNeural",     "gender": "male",   "tone": "thoughtful",    "age": "adult",       "suits": ["moderator", "student"]},
    {"id": "en-IN-RehaanNeural",    "gender": "male",   "tone": "playful",       "age": "young adult", "suits": ["student"]},
]
```

### 7.2 Endpoints

**`GET /api/v1/maic/voices/`** — Returns `AZURE_IN_VOICES`. Cached client-side. No auth beyond tenant membership. Lightweight.

**`POST /api/v1/teacher/maic/generate/agent-profiles/`** — Already wired in `maic_urls.py:20` with a stub view; needs body implementation.

Request:
```json
{
  "topic": "Photosynthesis",
  "language": "en",
  "roleSlots": [
    {"role": "professor", "count": 1},
    {"role": "teaching_assistant", "count": 1},
    {"role": "student", "count": 2}
  ]
}
```

Response: `{ "agents": [MAICAgent, ...] }`

Flow: validate roster → build user prompt → `_call_llm(AGENT_PROFILES_SYSTEM_PROMPT, user_prompt, temperature=0.9, max_tokens=2048)` → parse JSON → validate (voice in roster, no duplicate voices, role counts match, gender balance with count ≥ 3) → if invalid, regenerate once with a corrective prompt → else return. On persistent failure: 500 with raw LLM output in `details` field (for debugging).

**`POST /api/v1/teacher/maic/agents/regenerate-one/`**

Request:
```json
{
  "topic": "Photosynthesis",
  "existingAgents": [...],
  "targetAgentId": "agent-2",
  "lockedFields": ["voiceId"]
}
```

Response: `{ "agent": MAICAgent }`

Shorter prompt: "Generate ONE replacement agent in the <role> slot, distinct from these existing agents: <list>. Preserve these locked fields: <list>."

**`POST /api/v1/teacher/maic/tts/preview/`**

Request: `{ "voiceId": "en-IN-NeerjaNeural", "text": "Hello students, let's begin today's lesson." }`
Response: `audio/mpeg` bytes.

Reuses `generate_tts_audio()`. Rate-limited 30/min per user.

### 7.3 System prompt for agent profiles

Stored in `backend/apps/courses/prompts/agent_profiles.md` so it can be edited without code changes (loaded once per process, cached).

Hard constraints baked into the prompt:

- Names are Indian. Mix Hindi/Tamil/Telugu/Bengali/Marathi/Punjabi/Malayalam surnames. Balanced gender. No stereotypes.
- Honorifics: professor → "Dr." or "Prof." prefix. TA → "Ms." / "Mr." prefix. Students → first-name only.
- `personality` ≤ 2 sentences, grounded in the topic ("helps learners connect cellular respiration to …").
- `speakingStyle` ≤ 2 sentences, includes one culturally grounded phrase hint: e.g., "warm, reassuring, occasionally says 'theek hai?' to check understanding" — use sparingly (one phrase per agent, not every line).
- `voiceId` must match the agent's role against the voice's `suits` list. No two agents share a voice. Gender balance: when total count ≥ 3, at least one male and one female.
- `color` picked from the fixed 6-color palette (deep indigo `#4338CA`, teal `#0F766E`, saffron `#D97706`, forest `#166534`, cranberry `#9F1239`, slate `#334155`).
- `avatar` picked from curated emoji set: 👨‍🏫 👩‍🏫 🧑‍🎓 👨‍🎓 👩‍🎓 🧕 🙋‍♀️ 🙋‍♂️.

Output is a strict JSON object matching the `MAICAgent[]` shape. No markdown, no commentary.

### 7.4 Persona propagation into downstream prompts

This is the "system prompt changes for seamlessness" the user asked for.

| Prompt | Current | Change |
|---|---|---|
| `OUTLINE_SYSTEM_PROMPT` (`maic_generation_service.py:131`) | LLM invents agents as part of outline output | Remove agent generation; accept `agents[]` as input; outline only produces `scenes` referencing `agentIds` |
| `generate_outline_sse()` user prompt | no agent context | Inject `agents: [...]` JSON as reference material so scene-to-agent assignments are grounded in real personas |
| `ACTIONS_SYSTEM_PROMPT` (`:585`) | passes `personality` in agent_details | Also pass `speakingStyle`; add explicit rule: "You MUST write speech that reflects each agent's `speakingStyle`, including any cultural phrases the style notes. Each agent's lines should be identifiable as that agent's voice." |
| `CHAT_SYSTEM_PROMPT` (`:832`) | ignores persona | Inject full agent list with `name/role/personality/speakingStyle`; instruct each agent to respond in their own voice; preserve the multi-agent response shape |

### 7.5 Tests

- Unit: `test_agent_profiles_validator_rejects_duplicate_voice`, `test_validator_enforces_gender_balance`, `test_validator_rejects_non_roster_voice`.
- Unit: `test_regenerate_one_preserves_locked_fields`.
- Integration: `test_generate_agent_profiles_returns_valid_indian_agents` (real LLM call behind a fixture, asserts name patterns).
- Integration: `test_voice_preview_returns_mpeg_bytes` (mocks Azure TTS).

## 8. WS-C — Agent Picker Wizard Step (UI)

### 8.1 Flow

Current: `Topic → Config → Generate Outline → Review Outline → Generate Content → Publish`
New:     `Topic → Config → **Generate Agents** → Generate Outline → Review Outline → Generate Content → Publish`

The agent roster is now input to outline generation. `MAICCreatePage.tsx` and `StudentMAICCreatePage.tsx` both get this step; the student version uses the same endpoints (tenant decorators still enforce quota).

### 8.2 Components

**`AgentGenerationStep.tsx`** (new, shared between teacher + student wizards) — orchestrates the step: fetch voices once, call `generate/agent-profiles` on mount, render cards, handle "Looks good → Next."

**`AgentCard.tsx`** (new) — single card: avatar, name, role badge, persona (truncated to 1 line, hover-expand), voice row with `▶ preview` button, `Edit` + `Regen` buttons.

**`AgentEditModal.tsx`** (new) — edit one agent: name (text), persona (textarea, 500 char limit), speakingStyle (textarea, 200 char limit), voice (dropdown populated from `/voices/`). Client-side validation. Save patches wizard state.

### 8.3 Layout

```
Step 2 of 5 — Meet your classroom

Your AI classroom has 4 agents. Preview their voices, tweak personas, or regenerate.

┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  👨‍🏫        │  │  👩‍🏫        │  │  🙋‍♂️       │  │  🙋‍♀️       │
│  Dr. Aarav  │  │  Ms. Priya  │  │  Rohan      │  │  Kavya      │
│  Sharma     │  │  Iyer       │  │  Menon      │  │  Reddy      │
│             │  │             │  │             │  │             │
│  Professor  │  │  TA         │  │  Student    │  │  Student    │
│             │  │             │  │             │  │             │
│  persona    │  │  persona    │  │  persona    │  │  persona    │
│  preview... │  │  preview... │  │  preview... │  │  preview... │
│             │  │             │  │             │  │             │
│  ▶ Prabhat  │  │  ▶ Neerja   │  │  ▶ Aarav    │  │  ▶ Aashi    │
│             │  │             │  │             │  │             │
│ [edit][⟳]   │  │ [edit][⟳]   │  │ [edit][⟳]   │  │ [edit][⟳]   │
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘

[ ⟳ Regenerate all ]                        [ ← Back ]  [ Looks good → ]
```

### 8.4 Behavior

- **Voice preview:** Click ▶ → POST `/tts/preview/` with agent's `voiceId` + a canned sample sentence ("Hello students, I'm excited to teach you about this topic today.") → play blob inline via `<audio>`. Button becomes ⏸ while playing. Blob URL revoked on card unmount or next preview.
- **Edit:** Modal form. Save patches local wizard state. Does NOT call backend — changes are persisted when user hits "Looks good."
- **Regen card:** POST `/agents/regenerate-one/` with existing agents + target id. Card shows skeleton during fetch. Voice preview for the new voice auto-plays once on success (optional — behind a setting).
- **Regenerate all:** POST `/generate/agent-profiles/` again with same roster. Confirmation dialog first (loses edits).
- **Looks good →:** Persist `agents[]` to `maicStageStore.agents`. Proceed to outline generation — which now gets `agents[]` in its request body.

### 8.5 State

Local to the wizard step until confirmed. Then pushed to `maicStageStore.agents`. Agents travel with subsequent outline + scene-content + scene-actions requests.

### 8.6 Error handling

- Agent generation fails (500 / network): error card with "Retry" button. No partial state.
- Voice preview fails: toast "Voice preview unavailable — the voice will still be used in playback."
- LLM returns invalid JSON after retry: backend returns 500 with `details`; frontend toast "Couldn't generate — try again or change the topic slightly."
- User clicks "Looks good" before any preview: allowed.

### 8.7 Tests

- Vitest: `AgentCard renders with preview button`, `EditModal saves updates to wizard state`, `Regenerate all confirms before discarding edits`.
- Playwright E2E: teacher opens wizard → agents generate → click ▶ on agent 1 → hear audio → click Edit on agent 2 → change name → save → click "Looks good" → advance to outline step → verify outline scene `agentIds` match the 4 agent ids.

## 9. WS-D — Pre-gen Audio Pipeline

### 9.1 Publish endpoint

`POST /api/v1/teacher/maic/classrooms/<id>/publish/` (new):

1. Validate status is `DRAFT` or `READY` (re-publish allowed). Inside a `select_for_update` block, REJECT with 409 if current status is `GENERATING` — no concurrent publishes; the teacher must wait for the current pre-gen to finish or fail.
2. Walk `content.scenes[].actions[]`. For each `type=='speech'`:
   - Resolve agent via `content.agents[]`.
   - Stamp `action.voiceId` from `agent.voiceId`.
   - Compute `action.audioId = sha256(sceneId + actionIdx + text + voiceId)[:12]`.
3. Initialize `content.audioManifest`:
   ```json
   { "status": "generating", "progress": 0, "totalActions": N, "completedActions": 0, "failedAudioIds": [], "generatedAt": null }
   ```
4. Set `classroom.status = 'GENERATING'`.
5. `save()` → `pre_generate_classroom_tts.delay(classroom_id)`.
6. Return 202 with current manifest.

### 9.2 Celery task rewrite — `pre_generate_classroom_tts`

Extend existing `maic_tasks.py:22-112`:

```python
def pre_generate_classroom_tts(classroom_id):
    classroom = MAICClassroom.objects.get(id=classroom_id)
    content = classroom.content
    speech_actions = [
        (scene_idx, action_idx, action)
        for scene_idx, scene in enumerate(content['scenes'])
        for action_idx, action in enumerate(scene.get('actions', []))
        if action.get('type') == 'speech'
    ]
    total = len(speech_actions)
    completed = 0
    failed = []
    config = TenantAIConfig.objects.get(tenant=classroom.tenant)

    for scene_idx, action_idx, action in speech_actions:
        audio_id = action['audioId']
        voice_id = action['voiceId']
        storage_key = f"tenant/{classroom.tenant_id}/maic/tts/{classroom_id}/{audio_id}.mp3"

        # Idempotency: skip if URL present and file exists
        if action.get('audioUrl') and storage_exists(storage_key):
            completed += 1
            continue

        # Retry transient TTS failures with exponential backoff (1s, 2s, 4s).
        audio_bytes = None
        for attempt in range(3):
            try:
                audio_bytes = generate_tts_audio(action['text'], config, voice_id=voice_id)
                if audio_bytes:
                    break
            except Exception as e:
                logger.warning("TTS attempt %d failed for %s: %s", attempt + 1, audio_id, e)
                if attempt < 2:
                    time.sleep(2 ** attempt)
        if audio_bytes:
            url = storage_upload(storage_key, audio_bytes, 'audio/mpeg')
            content['scenes'][scene_idx]['actions'][action_idx]['audioUrl'] = url
        else:
            failed.append(audio_id)

        completed += 1
        # Checkpoint every 5 actions: let UI progress bar move
        if completed % 5 == 0 or completed == total:
            content['audioManifest']['progress'] = int(completed / total * 100)
            content['audioManifest']['completedActions'] = completed
            content['audioManifest']['failedAudioIds'] = failed
            classroom.content = content
            classroom.save(update_fields=['content', 'updated_at'])

    # Final state
    if not failed:
        content['audioManifest']['status'] = 'ready'
        classroom.status = 'READY'
    elif len(failed) < total:
        content['audioManifest']['status'] = 'partial'
        classroom.status = 'READY'  # Partial is still playable (reading-time fallback covers gaps)
    else:
        content['audioManifest']['status'] = 'failed'
        classroom.status = 'FAILED'

    content['audioManifest']['generatedAt'] = now_iso()
    classroom.content = content
    classroom.save(update_fields=['content', 'status', 'updated_at'])
```

### 9.3 Student visibility gate

In `student_maic_classroom_list` and `student_maic_classroom_detail`, add:
```python
qs = qs.filter(
    status='READY',
    content__audioManifest__status__in=['ready', 'partial'],
)
```

A classroom mid-generation is invisible to students. Teachers still see it (and poll the manifest) via their own endpoints.

### 9.4 Teacher polling for progress

`teacher_maic_classroom_detail` returns `audioManifest` in its response body. Frontend's publish screen polls every 3s during `status='GENERATING'`, shows "Generating audio… 42/87 actions" progress bar. Stops polling at `ready`/`partial`/`failed`.

### 9.5 Re-publish idempotency

The `audioId` hash ensures edited-text actions get new audio; unchanged actions reuse cached. Cost-aware. Old `.mp3` files for removed actions are cleaned up by a separate nightly `cleanup_orphaned_tts_files` Celery task (out of scope for this spec; track as follow-up).

### 9.6 Tests

- `test_publish_enqueues_pregen`
- `test_pregen_stamps_audio_urls_and_updates_manifest`
- `test_republish_skips_unchanged_audio`
- `test_failed_tts_marks_partial_not_failed`
- `test_student_cannot_see_classroom_mid_generation`
- Integration: publish → poll → ready within 60s for a 20-action classroom (Celery eager mode in tests).

## 10. WS-E — Speech Action Rewrite

### 10.1 Key change: `generationToken`

`MAICActionEngine` gains a monotonic counter:

```ts
private generationToken = 0;

abortCurrentAction(): void {
  this.generationToken++;               // invalidate all in-flight callbacks
  this.currentFetchController?.abort();
  if (this.audioElement) {
    this.audioElement.onplaying = null;
    this.audioElement.onended = null;
    this.audioElement.onerror = null;
    this.audioElement.pause();
    this.audioElement.src = '';
    this.audioElement = null;
  }
  this.currentFetchController = null;
  this.audioResolve = null;
  if (this.readingTimer) { clearTimeout(this.readingTimer); this.readingTimer = null; }
}
```

Every speech execution snapshots `myToken = ++this.generationToken` and checks `myToken !== this.generationToken` at every await point and callback entry. Stale → no-op.

### 10.2 `executeSpeech` — rewrite

```ts
private async executeSpeech(action: SpeechAction): Promise<void> {
  // Per-action token increment is intentional — each speech owns a unique token window.
  // stop() and loadScene() also call abortCurrentAction() which increments the same counter,
  // so any in-flight fetch/audio from a prior action or scene is neutered at the source.
  const myToken = ++this.generationToken;
  const { agentId, text } = action;
  const agent = this.stageStore.getState().agents.find(a => a.id === agentId);
  const voiceId = action.voiceId
    || agent?.voiceId
    || ROLE_VOICE_MAP[agent?.role ?? 'professor'];

  // 1. Preferred: pre-generated audioUrl
  if (action.audioUrl) {
    return this.playAudioSynced(action.audioUrl, text, agentId, myToken);
  }

  // 2. Fallback: live TTS (chat/discussion, or pre-gen gap)
  const blobUrl = await this.fetchTtsBlob(text, voiceId, myToken);
  if (myToken !== this.generationToken) return;    // stale
  if (!blobUrl) {
    return this.readingTimeFallback(text, agentId, myToken);
  }
  return this.playAudioSynced(blobUrl, text, agentId, myToken);
}
```

### 10.3 `playAudioSynced` — subtitle-on-playing

```ts
private playAudioSynced(
  src: string, text: string, agentId: string, token: number
): Promise<void> {
  return new Promise((resolve) => {
    if (token !== this.generationToken) { resolve(); return; }

    const audio = new Audio();
    this.audioElement = audio;
    audio.src = src;
    audio.volume = this.settingsStore.getState().audioVolume;
    audio.playbackRate = this.settingsStore.getState().playbackSpeed;

    // Subtitle + speaking indicator fire on `playing`, not before.
    audio.onplaying = () => {
      if (token !== this.generationToken) { audio.pause(); return; }
      this.onSpeechStart?.(agentId, text);
      this.stageStore.getState().setSpeakingAgent(agentId);
      this.stageStore.getState().setSpeechText(text);
    };
    audio.onended = () => {
      if (token !== this.generationToken) return;
      this.onSpeechEnd?.();
      this.stageStore.getState().setSpeakingAgent(null);
      this.stageStore.getState().setSpeechText(null);
      resolve();
    };
    audio.onerror = () => {
      if (token !== this.generationToken) return;
      this.onSpeechEnd?.();
      resolve();      // fail-open: advance
    };
    audio.play().catch(() => {
      if (token !== this.generationToken) return;
      resolve();
    });
  });
}
```

### 10.4 `readingTimeFallback`

When TTS is unavailable (204, error, no audio manifest yet), advance on a timer sized to the text:

```ts
private readingTimeFallback(text: string, agentId: string, token: number): Promise<void> {
  return new Promise((resolve) => {
    if (token !== this.generationToken) { resolve(); return; }
    this.onSpeechStart?.(agentId, text);
    this.stageStore.getState().setSpeakingAgent(agentId);
    this.stageStore.getState().setSpeechText(text);
    const ms = Math.max(2000, text.length * 60);       // 60ms/char, min 2s
    this.readingTimer = setTimeout(() => {
      if (token !== this.generationToken) return;
      this.onSpeechEnd?.();
      this.stageStore.getState().setSpeakingAgent(null);
      this.stageStore.getState().setSpeechText(null);
      resolve();
    }, ms);
  });
}
```

### 10.5 Scene navigation — `loadScene` cleanup

`hooks/usePlaybackEngine.ts:loadScene` becomes:

```ts
const loadScene = useCallback((scene: MAICScene) => {
  engineRef.current?.loadScene(scene);   // stop() → token++ → all stale callbacks neutered
  setActionCount(scene.actions?.length ?? 0);
  setCurrentActionIndex(0);
  setPlaybackState('idle');
  if (autoAdvanceRef.current && !classStoppedRef.current) {
    engineRef.current?.play();           // no setTimeout needed; token guarantees clean start
  }
}, []);
```

The 150ms `setTimeout` disappears. `stop()` is synchronous and complete. `play()` runs the new scene's first action with a fresh token.

### 10.6 Clicking a slide mid-playback

New `seekToSlide(slideIndex)` in `MAICPlaybackEngine`:

```ts
seekToSlide(slideIndex: number): void {
  // Find the nearest transition action at or before this slideIndex.
  // Start from there so audio for that slide plays from action 0 of that slide.
  const target = this.actions.findIndex(
    a => a.type === 'transition' && (a as TransitionAction).slideIndex === slideIndex
  );
  if (target === -1) return;
  this.stop();                  // token++, clean teardown
  this.currentActionIndex = target;
  this.setMode('playing');
  void this.processNext();      // fresh token; new scene's audio starts on canplay
}
```

Wired to slide thumbnail clicks in `SlideNavigator.tsx`.

### 10.7 Checkpoint fix (small, but worth pairing)

`maicPlaybackEngine.ts:290`:
```ts
this.checkpoint = { actionIndex: Math.max(0, this.currentActionIndex - 1) };
```
so the interrupted sentence replays on resume. Matches OpenMAIC's pattern.

### 10.8 Tests

- Vitest unit: `executeSpeech fires onSpeechStart only on audio.playing, not before`.
- Vitest unit: `abortCurrentAction mid-speech prevents onended from firing`.
- Vitest unit: `rapid scene switches × 10 leave no stale audio element`.
- Vitest unit: `readingTimeFallback advances after ~text.length * 60ms`.
- Playwright: publish classroom → student plays → click slide 3 mid-speech → verify `<audio>.currentSrc` matches slide 3's first audio and it plays cleanly. Click slide 5 → same. No audio overlap — assert via a test-mode hook exposed on `window.__maicEngine` returning the engine's internal `audioElement` reference (engine uses `new Audio()` off-DOM, so `document.querySelectorAll('audio')` is insufficient).

## 11. Rollout

1. **Merge WS-A** (permission fix) as its own PR. Minimal risk, unblocks students immediately.
2. **Merge WS-B** (backend: agent-profile endpoint + prompt changes + voice roster + preview endpoint) behind unused routes — no UI consumer yet.
3. **Merge WS-C** (wizard step). This is when teachers first see the new flow. Only affects newly-created classrooms.
4. **Merge WS-D** (publish endpoint + Celery task rewrite + manifest). Old DRAFT classrooms republish cleanly via migration.
5. **Merge WS-E** (speech action rewrite). This touches every classroom's playback. Ship after WS-D so pre-gen URLs exist for all freshly-published classrooms.

No feature flag needed. Each PR is independently deployable. Data migration (§5.4) runs on WS-D deploy.

## 12. Out of scope (future work)

- Full OpenMAIC prompt port (slide-content 980-line prompt, course-context continuity, director graph, whiteboard ledger).
- Interactive and PBL scene generation.
- ElevenLabs / Doubao / other premium voice providers.
- Additional voice languages beyond en-IN.
- Agent add/remove/reorder in the wizard.
- AI-generated images (still Unsplash/Pexels/Pollinations).
- Vision-mode PDF parsing (MinerU).
- Cleanup of orphaned TTS files (nightly job).

## 13. Risks

| Risk | Mitigation |
|---|---|
| TTS generation takes >60s for very long classrooms | Progress polling already handles it; consider a max `totalActions` cap (e.g., 200) with friendly error. |
| Azure TTS rate limits under load | Per-tenant key, Azure's per-subscription quota is generous; if hit, retry with exponential backoff in task. |
| LLM returns agents with invalid voice ids | Validator rejects, regenerates once. Persistent failure → 500 with raw output for debugging. |
| Data migration breaks existing classrooms | Migration is additive only (stamps new fields with defaults). Reversible by removing fields. Tested against DB snapshot. |
| Cost blow-up from pre-gen | `audioId` hash ensures idempotency; re-publish only regenerates changed text. Azure en-IN is ~$4/1M chars; typical classroom ~15K chars → $0.06/publish. |
| Subtitle-on-playing event doesn't fire on Safari | Safari fires `playing` reliably per MDN. Fallback: listen to `play` event (fires on request-to-play) if `playing` not fired within 500ms. Covered by E2E test on Safari worker. |

## 14. Effort

| WS | Backend | Frontend | Tests | Total |
|---|---|---|---|---|
| A | 0.1d | 0.3d | 0.2d | 0.6d |
| B | 1.0d | 0 | 0.3d | 1.3d |
| C | 0 | 1.2d | 0.3d | 1.5d |
| D | 0.8d | 0.2d | 0.3d | 1.3d |
| E | 0 | 0.8d | 0.4d | 1.2d |

**Total:** ~5.9 engineer-days solo. With parallel subagents running A+B+C concurrently, then D, then E: ~3 wall-clock days.

## 15. Subagent Boundaries (for parallel execution)

To avoid file-level races when three subagents run concurrently:

| Subagent | Owns (exclusive write) | Reads (no write) |
|---|---|---|
| **Backend-Bugs** (WS-A backend + WS-D) | `backend/apps/courses/maic_views.py`, `backend/apps/courses/maic_tasks.py`, `backend/apps/courses/maic_urls.py`, `backend/apps/courses/migrations/*_maic_audio_manifest.py`, `backend/apps/courses/maic_voices.py` (new) | `maic_models.py`, `maic_generation_service.py` (WS-B owner modifies) |
| **Backend-Agents** (WS-B) | `backend/apps/courses/maic_generation_service.py`, `backend/apps/courses/prompts/agent_profiles.md` (new), `backend/apps/courses/prompts/` (if creating shared prompt dir) | `maic_views.py` (Backend-Bugs owner adds endpoints) — coordinate via spec §7.2 signatures |
| **Frontend-Bugs+Engine** (WS-A frontend + WS-E) | `frontend/src/lib/maic/endpoints.ts` (new), `frontend/src/lib/maicActionEngine.ts`, `frontend/src/lib/maicPlaybackEngine.ts`, `frontend/src/hooks/usePlaybackEngine.ts`, `frontend/src/components/maic/RoundtablePanel.tsx`, `frontend/src/lib/orchestration/director.ts`, `frontend/src/components/maic/PBLRenderer.tsx`, `frontend/src/components/maic/ChatPanel.tsx`, `frontend/src/components/maic/SlideNavigator.tsx` | `MAICPlayerPage.tsx` (both teacher + student), `types/maic-actions.ts` |
| **Frontend-Wizard** (WS-C) | `frontend/src/components/maic/AgentGenerationStep.tsx` (new), `frontend/src/components/maic/AgentCard.tsx` (new), `frontend/src/components/maic/AgentEditModal.tsx` (new), `frontend/src/services/openmaicService.ts` (add agent-profile + voice-preview methods), `frontend/src/pages/teacher/MAICCreatePage.tsx`, `frontend/src/pages/student/StudentMAICCreatePage.tsx` | `types/maic.ts`, `stores/maicStageStore.ts` |
| **Test-Harness** (parallel, reads all) | `backend/tests/courses/test_maic_*.py` (new), `frontend/src/**/__tests__/*.test.ts` (new), `e2e/tests/maic-*.spec.ts` (new) | Everything — runs last, pinned to the final merged state |

Shared touchpoints that need sequencing (not parallel):
- `types/maic-actions.ts` additions (SpeechAction audio fields) — Frontend-Bugs owner makes first, others `git pull` before continuing.
- `types/maic.ts` (MAICAgent + MAICContent additions) — Frontend-Wizard owner makes first.
- `maic_models.py` content-schema migration — Backend-Bugs owner makes first.
