# AI Classroom — Engineering Blueprint

**Status:** Draft for approval. No code touched until this is signed off.
**Reference codebases:** `THU-MAIC/OpenMAIC` (AGPL — read for architecture), `THU-MAIC/MAIC-Core` (Apache-2.0 — integratable), `THU-MAIC/MAIC-UI` (license TBD — sidecar only).
**Goal:** Replicate OpenMAIC's classroom experience inside learnpuddle-lms — multi-agent LangGraph orchestration, scene-action protocol, generative interactive widgets, distinct per-agent voices, project-based learning loop.

---

## 1. Why we're building, not adopting

We're not running OpenMAIC as a black-box sidecar. The orchestration core is the platform's USP and must live in our stack so we control:
- Multi-tenancy and roles (none of which OpenMAIC has)
- Course content sourcing from our LMS
- Per-tenant analytics and progress
- Custom action types as our pedagogy evolves

We **are** running purpose-built generators as sidecars where they're well-bounded services:
- VoxCPM2 TTS (an inference service — natural sidecar)
- MAIC-UI widget generator (separate Next.js service that produces self-contained HTML)

---

## 2. Architecture mirror (what OpenMAIC does, what we're building)

```
                         ┌────────────────────────────────────────────────────┐
                         │                  React LMS Frontend                │
                         │  ┌──────────────────────────────────────────────┐  │
                         │  │           Classroom Stage                    │  │
                         │  │  Slides │ Whiteboard │ Widgets │ ProactiveCard│  │
                         │  └──────────────────────────────────────────────┘  │
                         │            ▲                            ▲          │
                         │            │ Action stream (WS)         │ HTML iframe
                         │            │                            │          │
                         │  ┌─────────┴────────────┐  ┌─────────────┴─────────┐
                         │  │  Playback Engine     │  │  Widget Loader        │
                         │  │  (state machine)     │  │  (signed widget URL)  │
                         │  └──────────┬───────────┘  └───────────────────────┘
                         └─────────────┼────────────────────────────────────────┘
                                       │ WebSocket (Django Channels)
                                       ▼
   ┌──────────────────────────────────────────────────────────────────────────────┐
   │                         Django Backend (apps/maic/)                          │
   │                                                                              │
   │  ┌─────────────────────────────┐    ┌──────────────────────────────────┐     │
   │  │  ClassroomConsumer (WS)     │    │  Generation Pipeline (Celery)    │     │
   │  │  - SSE-style action stream  │    │  - outline → scenes → actions    │     │
   │  │  - per-session subgraph run │    │  - persists to MaicClassroom     │     │
   │  └──────────────┬──────────────┘    └──────────────┬───────────────────┘     │
   │                 │                                  │                          │
   │                 ▼                                  ▼                          │
   │  ┌───────────────────────────────────────────────────────────────────────┐   │
   │  │            LangGraph DirectorGraph (Python langgraph)                  │   │
   │  │                                                                       │   │
   │  │   START → director ──end──→ END                                       │   │
   │  │              │                                                        │   │
   │  │              └──next──→ agent_generate ──→ director (loop)            │   │
   │  │                                                                       │   │
   │  │   State: messages, storeState, agentResponses (reducer),              │   │
   │  │          whiteboardLedger (reducer), turnCount, currentAgentId        │   │
   │  └───────────┬───────────────────────────────────────┬───────────────────┘   │
   │              │                                       │                        │
   │              ▼                                       ▼                        │
   │  ┌────────────────────────┐            ┌─────────────────────────────┐       │
   │  │  Prompt Library        │            │  Action Protocol             │       │
   │  │  (templates + snippets)│            │  (Pydantic + JSON schema)    │       │
   │  └────────────────────────┘            └─────────────────────────────┘       │
   │                                                                              │
   │  ┌────────────────────────┐            ┌─────────────────────────────┐       │
   │  │  Agent Registry        │            │  PBL Subgraph (separate)     │       │
   │  │  (allowed_actions, voice)            │  (own MCP tool registry)     │       │
   │  └────────────────────────┘            └─────────────────────────────┘       │
   └──────────────────┬───────────────────────────┬─────────────┬─────────────────┘
                      │                           │             │
                      ▼                           ▼             ▼
              ┌──────────────┐           ┌──────────────┐  ┌──────────────┐
              │  VoxCPM2 TTS │           │  MAIC-UI     │  │  Object       │
              │  (sidecar)   │           │  (sidecar)   │  │  Storage      │
              │  /api/tts    │           │  /generate   │  │  (DO Spaces)  │
              └──────────────┘           └──────────────┘  └──────────────┘
```

---

## 3. Component specs (what each thing IS, where it lives, what it talks to)

### 3.1 Action Protocol — the vocabulary
**Source of truth:** `backend/apps/maic/protocol/actions.py` (Pydantic) + `frontend/src/lib/maic/actions.ts` (TS), generated from a single JSON schema so they cannot drift.

**Action categories** (from upstream `lib/types/action.ts`, 21 types):

| Category | Actions | Behavior |
|---|---|---|
| Fire-and-forget visual | `spotlight`, `laser` | Don't block; queue next action immediately |
| Slide-only | `spotlight`, `laser` | Stripped server-side if scene type ≠ slide |
| Speech | `speech` | Wait for TTS audio (or reading-time fallback) |
| Whiteboard | `wb_open`, `wb_close`, `wb_clear`, `wb_delete`, `wb_draw_text`, `wb_draw_shape`, `wb_draw_chart`, `wb_draw_latex`, `wb_draw_table`, `wb_draw_line`, `wb_draw_code`, `wb_edit_code` | Wait for animation |
| Widget interaction | `widget_highlight`, `widget_setState`, `widget_annotation`, `widget_reveal` | Wait for iframe round-trip |
| Media | `play_video` | Wait for playback start |
| Discussion | `discussion` | Trigger ProactiveCard with 3s delay; user joins → enter `live` mode |

Each action has `id`, `title?`, `description?` plus type-specific fields. Coordinate space for whiteboard is `1000 × 562` (16:9). We will extend this protocol over time — `widget_quiz_submit`, `widget_drag_complete`, `simulation_step`, etc. — but start with these 21.

### 3.2 Director Graph — the LangGraph orchestrator
**File:** `backend/apps/maic/orchestration/director_graph.py`

Two nodes, looping until `should_end`:
- `director`: chooses next agent. Single-agent → pure code. Multi-agent → LLM call with director prompt.
- `agent_generate`: runs one agent; streams structured output (text + JSON actions interleaved); validates actions against agent's `allowed_actions`; appends whiteboard actions to ledger.

**State (LangGraph Annotation):**
```python
class OrchestratorState:
    # Input
    messages: list[Message]
    store_state: StoreState           # current scene, slides, whiteboard open?
    available_agent_ids: list[str]
    max_turns: int
    language_model: LanguageModel
    discussion_context: dict | None
    trigger_agent_id: str | None
    user_profile: dict | None
    agent_config_overrides: dict[str, AgentConfig]   # generated agents travel with request

    # Mutable
    current_agent_id: str | None
    turn_count: int
    agent_responses: list[AgentTurnSummary]   # reducer: append
    whiteboard_ledger: list[WhiteboardActionRecord]   # reducer: append
    should_end: bool
    total_actions: int
```

**Stateless contract:** every WS request carries the agent configs and prior turn state. Server holds nothing between requests. This is how upstream's `directorState` survives reconnects and crashes.

**Streaming:** events emitted via `config.writer()` — `agent_start`, `text_delta`, `action`, `agent_end`, `cue_user`, `thinking`, `error`. Django Channels consumer relays them as WebSocket frames. Frontend Playback Engine consumes them.

### 3.3 Agent Registry & Tool Schemas
**File:** `backend/apps/maic/orchestration/registry.py`

```python
class AgentConfig:
    id: str
    name: str
    role: Literal['teacher', 'assistant', 'student', 'student_rep', 'moderator']
    avatar: str
    color: str
    voice_id: str           # VoxCPM2 voice key
    voice_prompt: str       # for cloning, optional
    allowed_actions: list[ActionType]
    persona: str            # short bio used in prompt
    system_prompt_template: PromptId   # which template to load
    is_default: bool
```

Per-role action presets (mirrors upstream `tool-schemas.ts`):
- **Teacher**: full set (speech + all wb_* + spotlight + laser + discussion + widget_*)
- **Assistant**: speech + wb_draw_text + wb_draw_latex + spotlight + widget_*
- **Student**: speech + spotlight (cannot draw on whiteboard)
- **Moderator**: speech + discussion (cannot teach)

Stored in Postgres + cached in Redis. Generated agents (one-off, not in the default registry) travel inside the request — server stays stateless.

### 3.4 Prompt Library — file-based templates + snippets
**Layout** (mirror of upstream `lib/prompts/`):
```
backend/apps/maic/prompts/
├── loader.py              # file I/O + cache + template engine
├── ids.py                 # PromptId enum
├── templates/
│   ├── agent-system/{system,user}.md
│   ├── agent-system-wb-teacher/system.md
│   ├── agent-system-wb-assistant/system.md
│   ├── agent-system-wb-student/system.md
│   ├── director/system.md
│   ├── slide-content/{system,user}.md
│   ├── slide-actions/{system,user}.md
│   ├── interactive-actions/{system,user}.md
│   ├── interactive-outlines/{system,user}.md
│   ├── code-content/{system,user}.md
│   ├── diagram-content/{system,user}.md
│   ├── game-content/{system,user}.md
│   ├── visualization3d-content/{system,user}.md
│   ├── simulation-content/{system,user}.md
│   ├── quiz-content/{system,user}.md
│   ├── quiz-actions/{system,user}.md
│   ├── pbl-design/{system,user}.md
│   ├── pbl-actions/{system,user}.md
│   ├── widget-teacher-actions/{system,user}.md
│   ├── requirements-to-outlines/{system,user}.md
│   └── web-search-query-rewrite/{system,user}.md
└── snippets/
    ├── action-types.md
    ├── element-types.md
    ├── image-instructions.md
    ├── json-output-rules.md
    ├── media-safety-guidelines.md
    ├── slide-image-instructions.md
    ├── slide-generated-image-instructions.md
    ├── slide-video-instructions.md
    ├── speech-guidelines.md
    ├── video-instructions.md
    └── whiteboard-reference.md
```

**Template syntax** (3 placeholder kinds):
- `{{variable}}` — interpolated from caller args
- `{{snippet:id}}` — file include at load time
- `{{#if condition}}...{{/if}}` — conditional block from caller args

We **port the .md files as-is** from upstream. The Python loader is ~80 lines.

### 3.5 Generation Pipeline (offline scene builder)
**Path:** topic → outline → scenes → actions → post-process → persist.

**Files:**
```
backend/apps/maic/generation/
├── pipeline_runner.py            # orchestrator (~100 lines)
├── outline_generator.py          # topic → list of scene outlines
├── scene_generator.py            # outline → scene with content
├── action_parser.py              # parse LLM JSON into Action objects
├── json_repair.py                # fix malformed LLM JSON (use python's json-repair)
├── interactive_post_processor.py # inject widget references
└── scene_builder.py              # final scene assembly
```

Runs as a Celery task chain. Each stage emits progress events to a WS channel (`maic_generation:{job_id}`) so the frontend's `GeneratingProgress` UI shows real progress.

### 3.6 Playback Engine (frontend, the live classroom)
**File:** `frontend/src/lib/maic/playback-engine.ts` (~750-line direct port from upstream `lib/playback/engine.ts`).

State machine:
```
                           start()                   pause()
       idle ───────────────────────→ playing ──────────────→ paused
         ▲                              ▲                       │
         │                              │ resume()              │
         │                              └───────────────────────┘
         │
         │  handleEndDiscussion()       confirmDiscussion() / handleUserInterrupt()
         │                                    │
         └──────────────────────────────── live ──────────────→ paused
                                              ▲                    │
                                              │ resume / msg       │
                                              └────────────────────┘
```

Per-action dispatch in `processNext()`:
- `speech` → `audioPlayer.play(audioId, audioUrl)`; on end, `processNext()`. Fallback to browser-native TTS (chunked to 15s for Chrome bug) or reading-time timer.
- `spotlight` / `laser` → fire `actionEngine.execute()` then `queueMicrotask(processNext)` (no await).
- `discussion` → 3s delay → show ProactiveCard → wait for user choice (`confirmDiscussion`/`skipDiscussion`).
- All `wb_*` and `widget_*` → `await actionEngine.execute()` then `processNext()`.

Snapshot/restore for crash recovery: `{sceneIndex, actionIndex, consumedDiscussions, sceneId}` saved to backend on every action.

### 3.7 TTS Service (sidecar)
**Service:** `services/tts/` — separate Python FastAPI, runs VoxCPM2 model in-process or via VoxCPM2's own API.

**Endpoints:**
- `POST /tts` — body `{text, voice_id, voice_prompt?, speed?, audio_id}` → `{audio_id, audio_b64, format}`. Provider abstraction internally (VoxCPM2 / Minimax / Azure / OpenAI / edge_tts as fallback).
- `GET /voices` — list of registered voice IDs.

**Per-action streaming:** when the director graph emits a `speech` action, the consumer immediately fans out a TTS request in parallel. The action ships to the frontend with `audioId`; the audio binary streams in via a separate WS frame keyed by `audioId`. Frontend's `audioPlayer.play(audioId, audioUrl)` waits for the audio if it hasn't arrived yet, otherwise plays immediately.

**Voice cloning:** each generated agent gets a unique voice. For VoxCPM2 auto-voice mode, the agent's persona becomes the voice prompt — produces a consistent character voice without manual setup.

### 3.8 MAIC-UI Widget Service (sidecar)
**Service:** `services/widgets/` — runs upstream `THU-MAIC/MAIC-UI` Docker as-is.

**Flow:**
1. Generation pipeline detects an `interactive` scene type (e.g., "Pizza Chef Challenge for fractions")
2. Calls MAIC-UI's `/generate` with topic + spec
3. MAIC-UI returns self-contained HTML (TailwindCDN + KaTeX + vanilla JS, exactly like the Numerator/Denominator examples)
4. Backend stores HTML in DO Spaces under `tenant/{tid}/widgets/{scene_id}.html`
5. Scene's actions reference `widget_url` → frontend renders in iframe
6. Widget posts events back via `postMessage` → frontend dispatches `widget_*` actions

**License gate:** MAIC-UI has no LICENSE file. Treat as proprietary until clarified. We can integrate it but cannot redistribute the service container.

### 3.9 PBL Subsystem (separate loop)
**Path:** `backend/apps/maic_pbl/`

PBL is a different mode — not a lecture, but a project chat with tool use. Mirrors upstream `app/api/pbl/chat/route.ts` and `lib/pbl/`.

**Components:**
- `pbl_design_graph.py` — generates a PBL project from a topic (one-shot)
- `pbl_chat_graph.py` — interactive loop, agent has access to MCP-style tools (search, citation, run-code, draw-diagram)
- `pbl_tools/` — tool registry (each tool = one Python class with `name`, `schema`, `invoke`)
- Own session storage (separate from classroom session): `MaicPBLSession`

PBL session is a separate Django model and separate WS channel. It does not share state with classroom playback.

---

## 4. Stack translation (TS → Python)

| Upstream (TS) | Ours (Python/Django) |
|---|---|
| `@langchain/langgraph` | `langgraph` (Python — same primitives: StateGraph, Annotation, START, END) |
| `@langchain/core` | `langchain-core` (Python) |
| Vercel AI SDK (`ai`) | `langchain` chat models directly + LiteLLM for provider abstraction |
| Next.js API routes (SSE via `Response`) | Django Channels WS consumers |
| Next.js client | React 19 + Vite (already what we have) |
| Vercel KV / browser storage | Postgres for persistence + IndexedDB on client (we already have Dexie) |

**LangGraph Python parity check:** `StateGraph`, `Annotation.Root`, reducers, `add_node`, `add_edge`, `add_conditional_edges`, `compile()`, `astream` with `stream_mode='custom'` and `config.writer` — all present in `langgraph >= 0.2`. No primitives missing.

---

## 5. Phased build plan

Each phase is independently shippable. Each ends with a working demo.

### Phase 0 — Foundation (1 week)
**Acceptance:** A WebSocket connection runs an empty LangGraph and streams a hello-world event.
- Add deps: `langgraph`, `langchain-core`, `langchain-anthropic`, `langchain-openai`, `litellm` to `requirements.txt`
- Create `backend/apps/maic/` Django app
- Define `OrchestratorState` Annotation
- Build empty `director_graph.py` (just emits `agent_start` → `agent_end`)
- Wire `ClassroomConsumer` (Channels WS) — accept token auth, run graph, relay events
- Frontend: minimal `useMaicClassroomChannel` hook that opens WS and logs frames
- **Delete:** nothing yet — old code stays running in parallel.

### Phase 1 — Action Protocol + Single-Agent Speech (1.5 weeks)
**Acceptance:** A scripted 3-slide scene plays end-to-end with speech actions; pause/resume works.
- Define all 21 action types in `actions.py` (Pydantic) — generate JSON schema
- Generate `actions.ts` from JSON schema; share via codegen script
- Implement structured output parser (the `parseStructuredChunk` from upstream — text + actions interleaved with JSON markers)
- Port `agent-system` and `slide-actions` prompt templates
- Implement single-agent director path (code-only — dispatches single agent on turn 0, ends on turn 1)
- Implement `runAgentGeneration` with action validation
- Frontend: port `playback-engine.ts` — speech action only at first
- Frontend: port `audio-player.ts` with prefetch
- TTS: stub with edge_tts for now (real provider arrives in Phase 5)
- **Delete:** start gating old MAIC routes behind a feature flag.

### Phase 2 — Whiteboard + Visual Effects (1.5 weeks)
**Acceptance:** All 12 whiteboard actions render correctly; spotlight/laser overlay slides; agent's whiteboard ledger persists across slides.
- Implement whiteboard renderer (Canvas + SVG hybrid) — match upstream's component breakdown
- KaTeX for `wb_draw_latex`, Recharts for `wb_draw_chart`, Lowlight for `wb_draw_code`
- Element ID → ref mapping for `wb_delete` and `wb_edit_code`
- Spotlight overlay (dim non-target) and laser pointer (animated dot)
- Whiteboard ledger reducer in state
- **Delete:** old whiteboard component (`Whiteboard.tsx`).

### Phase 3 — Multi-Agent + Discussion Mode (2 weeks)
**Acceptance:** 3-agent classroom (teacher + 2 students) with proper handover; user can interrupt mid-scene to discuss; resumes correctly.
- Implement multi-agent director (LLM-based decision)
- Port `director-prompt.ts` template
- Port `prompt-builder.ts` (role guidelines, length targets, conversation summary)
- Implement `discussion` action: ProactiveCard, 3s delay, live mode transition
- Implement user interrupt → live mode → restored lecture
- Snapshot save/restore on every action
- ProactiveCardManager UI
- **Delete:** old `RoundtablePanel.tsx`, `RoundtableStrip.tsx` (after parity verified).

### Phase 4 — Generation Pipeline (1.5 weeks)
**Acceptance:** Type a topic → 10-scene classroom is generated; quality matches upstream output.
- Port `outline_generator.py` (topic → outlines)
- Port `scene_generator.py` (the heavy 1675-line module — this IS the magic recipe)
- Port `action_parser.py` + `json_repair` integration
- Port `interactive_post_processor.py`
- Celery task chain with progress WS events
- **Delete:** all 3,400 lines of `maic_generation_service.py`.

### Phase 5 — VoxCPM2 + Voice Per Agent (1 week)
**Acceptance:** Each agent has a distinct, on-the-fly cloned voice; first audio plays within 1.5s of scene start.
- Stand up `services/tts/` FastAPI sidecar with VoxCPM2
- Per-action TTS fan-out: when a `speech` action streams, kick off TTS in parallel via Celery
- Stream audio b64 over WS keyed by `audioId`
- Voice prompt = agent persona (auto-voice mode)
- Provider fallback chain: VoxCPM2 → Minimax → Azure → edge_tts
- **Delete:** edge_tts/gTTS code paths in the old `tts_service.py`.

### Phase 6 — MAIC-UI Widget Integration (1 week)
**Acceptance:** Generated classrooms include interactive HTML widgets matching the Numerator/Denominator quality bar; widget events flow back to actions.
- Stand up `services/widgets/` (run MAIC-UI Docker)
- License clarification: open issue on `THU-MAIC/MAIC-UI` requesting LICENSE; do not deploy commercially until answered. **This is a pre-deploy blocker, not a build blocker** — we can develop against it.
- Generation pipeline calls MAIC-UI for `interactive` scenes
- Storage in DO Spaces under `tenant/{tid}/widgets/`
- Widget action handlers in playback engine: `widget_highlight`, `widget_setState`, `widget_annotation`, `widget_reveal`
- Iframe with `postMessage` round-trip
- **Delete:** any stale "interactive content" stubs.

### Phase 7 — PBL Subsystem (1.5 weeks)
**Acceptance:** Teacher creates a PBL project; student converses with teacher agent; teacher uses tools (search, draw, run-code).
- New Django app: `backend/apps/maic_pbl/`
- Port `pbl-design` and `pbl-actions` templates
- Port `lib/pbl/generate-pbl.ts` to Python
- Implement MCP-style tool registry: `Tool` ABC + 4 starter tools (web search, citation, run-code via Pyodide kernel sidecar, draw-diagram)
- Separate WS channel `pbl:{session_id}`
- **Delete:** none (PBL was never in our codebase).

### Phase 8 — Cleanup + Demo Polish (1 week)
**Acceptance:** Old code is deleted; demo classroom (Numerator/Denominator) renders identically to upstream's output quality.
- Delete the old MAIC implementation in full:
  - `backend/apps/courses/maic_*` (8 files, ~5000 lines)
  - `frontend/src/components/maic/*` (60+ files — keep the new ones written in Phases 1–6)
  - `backend/apps/courses/tts_service.py`
  - All `tests_maic_*.py` for the old code
- Demo content: regenerate the Numerator/Denominator classroom in the new system
- Performance pass: prefetch next scene, cache widget HTML, measure first-audio latency

**Total: ~10 weeks of focused work.** Compresses if we run Phase 4 (generation pipeline) in parallel with Phase 3 (multi-agent).

---

## 6. What gets deleted, in which phase

| File / dir | Lines | Phase to delete | Replacement |
|---|---:|---|---|
| `backend/apps/courses/maic_generation_service.py` | 3410 | 4 | `apps/maic/generation/*` |
| `backend/apps/courses/maic_models.py` | 471 | 4 | `apps/maic/models.py` (slim) |
| `backend/apps/courses/maic_tasks.py` | ? | 4 | `apps/maic/tasks.py` |
| `backend/apps/courses/maic_consumers.py` | ? | 1 | `apps/maic/consumers.py` |
| `backend/apps/courses/maic_storage.py` | ? | 4 | `apps/maic/storage.py` |
| `backend/apps/courses/maic_voices.py` | ? | 5 | TTS service handles voices |
| `backend/apps/courses/maic_views.py` | ? | 1 | `apps/maic/views.py` |
| `backend/apps/courses/maic_urls.py` | ? | 1 | `apps/maic/urls.py` |
| `backend/apps/courses/tts_service.py` | 731 | 5 | TTS sidecar |
| `frontend/src/components/maic/*` | 60 files | 1–6 incrementally | New components matching upstream component graph |
| `openmaic/Dockerfile` (the abandoned sidecar) | 1 file | 1 | gone |

Net delete: ~5,000+ lines. Net add: cleaner, smaller, and matches upstream quality.

---

## 7. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| `langgraph` Python lags features behind TS version | Med | Pin to a known-good version; if a feature blocks us, write a thin custom node (LangGraph state primitives are simple) |
| Scene generator port introduces quality drift vs upstream | High | Port test fixtures from upstream (`tests/prompts/`); run parallel A/B on identical topics; compare structured output |
| MAIC-UI license never clarified | Med | Pre-emptively budget time to write our own widget generator using the same prompt structure (we can read MAIC-UI's prompt templates even if we can't redistribute its code) |
| VoxCPM2 self-hosting on demo machine struggles (M4 Mac mini, 16GB RAM) | Med | Phase 5 spike: benchmark VoxCPM2 on the demo box first; fall back to Minimax cloud TTS for demo, keep self-host as Phase-9 hardening |
| Chrome browser-native TTS 15s cutoff | Low | Already known and handled by upstream's chunked playback; we port that pattern verbatim |
| Action parser can't handle every model's malformed JSON | Med | Use upstream's `json-repair` approach; widen test corpus over time |

---

## 8. Definition of done

The Keystone demo passes if, on a fresh tenant with no manual setup:
1. Teacher types "Numerator and Denominator" → generates a 10-scene classroom in < 90 s
2. Generated classroom contains ≥ 3 interactive widgets (Pizza Chef-class)
3. First audio plays within 1.5 s of scene start
4. Each agent has a distinct voice (verified by waveform diff on identical phrases)
5. Multi-agent handover: teacher introduces topic, student asks a question, teacher responds — without any visible latency between speakers
6. User clicks "Discuss" on a ProactiveCard → live discussion runs with the chosen agent → "End discussion" returns to lecture seamlessly
7. PBL session: separate from classroom; tool use visible (search results cited, code-run output rendered)
8. No mention of edge_tts or gTTS anywhere in the running code path
9. Old `maic_*` files fully removed; only new `apps/maic/` + `apps/maic_pbl/` remain

---

## 9. Open questions for sign-off

1. **MAIC-UI license** — open issue now, or wait until Phase 6 starts? (Recommend: open it this week.)
2. **TTS provider for demo machine** — self-hosted VoxCPM2 on M4 mini, or cloud Minimax for demo and self-host post-demo? (Recommend: cloud for demo, self-host as Phase 9.)
3. **Parallelism** — can two engineers work this? Phase 1 + Phase 4 can run concurrently after Phase 0; halves wall time.
4. **Old code freeze** — pause all changes to `apps/courses/maic_*` and old `frontend/src/components/maic/*` starting Phase 0? (Recommend yes; otherwise we keep moving the deletion target.)

Sign off on the four questions and I'll start Phase 0 in a branch, no code in main until each phase passes its acceptance.
