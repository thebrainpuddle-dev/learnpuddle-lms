# THU-MAIC Upstream Map For LearnPuddle AI Classroom - 2026-05-16

## Purpose

This is the upstream map Claude should use before the next AI Classroom PR. The product decision is hybrid OpenMAIC-first: stop rebuilding every behavior from scratch, and lift/adapt the THU-MAIC contracts where they fit our SaaS architecture.

Primary org:
- https://github.com/THU-MAIC

Current public repos inspected:
- `THU-MAIC/OpenMAIC`
- `THU-MAIC/MAIC-Core`
- `THU-MAIC/MAIC-UI`
- `THU-MAIC/SimClass`
- `THU-MAIC/Awesome-AI-Era-Edu`
- `THU-MAIC/MAIC-Vibe`

## License And Traceability Rules

- The user has stated LearnPuddle has permission/license access to use OpenMAIC code and methods.
- Public metadata currently shows `OpenMAIC` as AGPL-3.0 with commercial licensing advertised in the README.
- Obsidian ADR-001a records full OpenMAIC license rights. Verify that record before direct code lifts.
- `MAIC-Core` is GitHub-detected Apache-2.0.
- `MAIC-Vibe` is MIT.
- `MAIC-UI` has no GitHub-detected license and no root LICENSE file, but its root `package.json` declares MIT. Treat this as "usable only after explicit license/permission confirmation" for direct code copy.
- Directly lifted frontend/source files must include:
  `Source: THU-MAIC/OpenMAIC <commit-sha> <relative-path>`
- Backend TypeScript-to-Python ports must cite the upstream path in module docstrings and tests.

## Repo Priority

| Rank | Repo | Use For LearnPuddle | Do Not Use For |
|---|---|---|---|
| P0 | `OpenMAIC` | Main classroom engine contract: generation, prompts, action schema, playback, PBL, media, evals, export/import. | Tenant/auth/storage shell. LearnPuddle owns those. |
| P1 | `MAIC-Core` | Older algorithm/service reference: slide-to-lecture preclass pipeline, agenda/function execution model, in-class turn/input gating. | Direct runtime replacement for Django/Celery/Channels. |
| P1 scoped | `MAIC-UI` | Interactive HTML/courseware generation quality, heavy-mode validation/refinement ideas, prompt/validator references. | Default widget sidecar or primary classroom engine. OpenMAIC itself does not depend on it. |
| P2 | `SimClass` | Pedagogy and simulated-classroom agent behavior reference. | Implementation source. Data/code are minimal/not released. |
| P2 | `Awesome-AI-Era-Edu` | Research/eval reading list for quality rubrics. | Runtime implementation. |
| P3 | `MAIC-Vibe` | Optional Claude workflow/coaching ideas. | AI Classroom product implementation. |

## OpenMAIC: Primary Implementation Contract

Repo:
- https://github.com/THU-MAIC/OpenMAIC
- Latest inspected main commit: `47cc2a510c167a01aa158cdf86513fb325a2573a`
- Latest release inspected: `v0.2.1`
- Stack: Next.js 16, React 19, TypeScript, LangGraph, Vercel AI SDK, Zustand, Dexie, Playwright/Vitest.

What matters most:

1. Two-stage classroom generation
   - `lib/generation/outline-generator.ts`
   - `lib/generation/scene-generator.ts`
   - `lib/generation/scene-builder.ts`
   - `lib/generation/pipeline-types.ts`
   - `lib/generation/pipeline-runner.ts`
   - LearnPuddle goal: make teacher wizard v2/PBL-first by using this staged contract, not legacy v1 generation.

2. Prompt system and prompt snippets
   - `lib/prompts/templates/requirements-to-outlines/*`
   - `lib/prompts/templates/slide-content/*`
   - `lib/prompts/templates/slide-actions/*`
   - `lib/prompts/templates/quiz-content/*`
   - `lib/prompts/templates/quiz-actions/*`
   - `lib/prompts/templates/pbl-design/*`
   - `lib/prompts/templates/pbl-actions/*`
   - `lib/prompts/templates/widget-teacher-actions/*`
   - `lib/prompts/snippets/*`
   - LearnPuddle goal: Step 2 class guide must feed these prompts as a structured planning contract: learning objective, grade, misconceptions, PBL brief, media needs, agent choreography, checks, handoffs.

3. Action contract
   - `lib/types/action.ts`
   - `lib/generation/action-parser.ts`
   - `lib/orchestration/tool-schemas.ts`
   - Key upstream discipline:
     - One action union for online and offline playback.
     - Fire-and-forget actions: spotlight, laser.
     - Synchronous actions: speech, video, whiteboard, discussion, widget actions.
     - Filter slide-only actions on non-slide scenes.
     - Whitelist allowed actions by agent/role.
     - Parse with JSON repair and partial JSON fallback.
   - LearnPuddle goal: invalid `agentId`, impossible actions, extra widget fields, stale handoffs, and slide-only action misuse must be blocked at schema/action-engine boundaries, not just patched after the fact.

4. LangGraph orchestration
   - `lib/orchestration/director-graph.ts`
   - `lib/orchestration/director-prompt.ts`
   - `lib/orchestration/prompt-builder.ts`
   - `lib/orchestration/registry/*`
   - `lib/orchestration/summarizers/*`
   - LearnPuddle goal: preserve the director/agent loop and streaming event contract while adapting to Django Channels, tenant-scoped generated agent configs, and real classroom sessions.

5. PBL tool-calling pipeline
   - `lib/pbl/generate-pbl.ts`
   - `lib/pbl/types.ts`
   - `lib/pbl/pbl-system-prompt.ts`
   - `lib/pbl/mcp/project-mcp.ts`
   - `lib/pbl/mcp/agent-mcp.ts`
   - `lib/pbl/mcp/issueboard-mcp.ts`
   - `lib/pbl/mcp/mode-mcp.ts`
   - `components/scene-renderers/pbl-renderer.tsx`
   - `components/scene-renderers/pbl/*`
   - Key upstream discipline:
     - Tool-calling loop builds project info, agents, issueboard, questions, judge agents.
     - PBL config is stateful and typed.
   - LearnPuddle goal: our PBL must use real tool-calling production model support, not local fallback slop. Pass class guide and project context into design and action prompts.

6. Media lifecycle
   - `lib/media/media-orchestrator.ts`
   - `lib/store/media-generation.ts`
   - `lib/server/classroom-media-generation.ts`
   - `lib/media/image-providers.ts`
   - `lib/media/video-providers.ts`
   - `lib/media/adapters/*`
   - `app/api/generate/image/route.ts`
   - `app/api/generate/video/route.ts`
   - `app/api/proxy-media/route.ts`
   - `app/api/classroom-media/[classroomId]/[...path]/route.ts`
   - Key upstream discipline:
     - Media request IDs are explicit placeholders.
     - Tasks move pending -> generating -> done/failed.
     - Provider errors persist visibly.
     - Generated files are rehosted and mapped back onto slide elements.
   - LearnPuddle goal: eliminate `Image unavailable` for configured providers. Persist media to tenant-prefixed DO Spaces keys, not browser IndexedDB. Expose status/errors in teacher generation UI and playback.

7. Slide/player/layout/action visuals
   - `components/slide-renderer/Editor/ScreenCanvas.tsx`
   - `components/slide-renderer/Editor/Canvas/hooks/useViewportSize.ts`
   - `components/slide-renderer/Editor/SpotlightOverlay.tsx`
   - `components/slide-renderer/Editor/LaserOverlay.tsx`
   - `components/slide-renderer/components/element/ImageElement/*`
   - `components/slide-renderer/components/element/VideoElement/*`
   - LearnPuddle goal: use stable 16:9 viewport math and percent geometry. Fix zoomed/cropped images, fullscreen sizing, slide bounds, and laser/spotlight alignment.

8. TTS and audio
   - `lib/audio/tts-providers.ts`
   - `lib/audio/tts-utils.ts`
   - `lib/audio/voice-resolver.ts`
   - `lib/audio/voxcpm.ts`
   - `lib/server/classroom-media-generation.ts`
   - LearnPuddle goal: audio IDs unique by scene/action, speech splitting, pre-generated TTS when provider exists, and active-speaker state tied to audio completion.

9. Export/import and persistence
   - `lib/export/use-export-classroom.ts`
   - `lib/export/classroom-zip-types.ts`
   - `lib/import/use-import-classroom.ts`
   - `lib/utils/playback-storage.ts`
   - `lib/server/classroom-storage.ts`
   - LearnPuddle goal: map OpenMAIC classroom ZIP/export contracts to SaaS import/export with tenant ownership and DO Spaces rehosting.

10. Evals and regression harness
    - `e2e/tests/full-happy-path.spec.ts`
    - `e2e/tests/classroom-interaction.spec.ts`
    - `eval/outline-language/*`
    - `eval/whiteboard-layout/*`
    - LearnPuddle goal: create equivalent Playwright tests through teacher portal, plus layout/eval scoring for whiteboard, media, action sync, PBL, fullscreen, and course quality.

## MAIC-Core: Algorithm And Execution Reference

Repo:
- https://github.com/THU-MAIC/MAIC-Core
- Latest inspected main commit: `4d7c92e46b17b5a4fd7cea9bc5311517145dff80`
- License: Apache-2.0.

Useful blocks:

1. Preclass Slide2Lecture pipeline
   - `service/preclass/README.md`
   - `service/preclass/main.py`
   - `service/preclass/processors/pptx2pdf.py`
   - `service/preclass/processors/pdf2png.py`
   - `service/preclass/processors/ppt2text.py`
   - `service/preclass/processors/gen_description.py`
   - `service/preclass/processors/gen_structure.py`
   - `service/preclass/processors/gen_readscript.py`
   - `service/preclass/processors/gen_showfile.py`
   - `service/preclass/processors/gen_askquestion.py`
   - LearnPuddle use: improve PPT/PDF-to-classroom course quality, agenda hierarchy, read scripts, show-file moments, and embedded questions.

2. InClass function/session execution
   - `service/inclass/README.md`
   - `service/inclass/classroom_session.py`
   - `service/inclass/functions/readScript.py`
   - `service/inclass/functions/showFile.py`
   - `service/inclass/functions/askQuestion.py`
   - LearnPuddle use: adapt the "one session, one function step, requeue if unfinished" pattern for robust handoffs, user input gating, continuous mode, and fair worker scheduling.

3. Data model references
   - `data/agenda.py`
   - `data/function_session.py`
   - `data/chat_action_flow.py`
   - `data/session.py`
   - LearnPuddle use: compare with `apps/maic`, `apps/maic_pbl`, and existing classroom/session persistence to ensure we store enough state for replay and recovery.

Do not port the MongoDB/RabbitMQ service as-is. LearnPuddle already uses Django, Celery, Channels, Postgres, Redis, and tenant middleware.

## MAIC-UI: Scoped Interactive HTML Quality Reference

Repo:
- https://github.com/THU-MAIC/MAIC-UI
- Latest inspected main commit: `aad58ddcc2103058b4c2deffc48a3c13e2c64dd6`
- Public GitHub license detection: none.
- Root `package.json`: `license: MIT`.

Useful blocks:

1. Interactive HTML generation modes
   - `backend/src/services/html_generation/base_generator.py`
   - `backend/src/services/html_generation/fast_generator.py`
   - `backend/src/services/html_generation/heavy_generator.py`
   - LearnPuddle use: borrow the fast/heavy split and staged generation/refinement concept for high-quality widgets or interactive scenes.

2. Prompt library
   - `backend/src/services/prompts/ai_prompts.py`
   - `backend/src/services/templates/heavy_mode_prompts.py`
   - LearnPuddle use: compare against OpenMAIC widget prompts for richer "learning process generation" and student manipulation/exploration language.

3. Validators and components
   - `backend/src/services/validators/html_validator.py`
   - `backend/src/services/validators/content_validator.py`
   - `backend/src/services/validators/sim_validator.py`
   - `backend/src/services/html_generation/components/*`
   - LearnPuddle use: build real validation gates for generated HTML/widgets: complete document, responsive design, interactivity, no placeholders, content alignment, simulation sanity.

Warnings:
- `heavy_generator.py` currently sets `is_valid, issues = True, None`, effectively bypassing validation in the inspected version. Do not copy that bug.
- MAIC-UI has its own auth/API/database/Next/FastAPI/nginx stack. Do not make it the default sidecar unless a later task explicitly accepts the operational and license scope.
- OpenMAIC itself does not use MAIC-UI as the widget engine; OpenMAIC generates widget HTML inline. Start from OpenMAIC first.

## SimClass: Pedagogy Reference Only

Repo:
- https://github.com/THU-MAIC/SimClass
- Latest inspected main commit: `49cdddfe830bcb7b2aee82bacc5ad376b6cde2d0`
- License detection: none.

Use for:
- Classroom-agent behavior paper/citation.
- Agent persona, simulated student, discussion behavior, classroom social dynamics.

Do not use for:
- Runtime implementation. README says code/data are part of MAIC and points to MAIC-Core; data is not released in the inspected README.

## Awesome-AI-Era-Edu: Research And Eval Rubric Source

Repo:
- https://github.com/THU-MAIC/Awesome-AI-Era-Edu
- Latest inspected main commit: `e8090a4eb53ee0d9ed46078848b060f155f0bb15`
- GitHub license detection: none.
- `pyproject.toml` declares MIT.

Use for:
- Quality rubrics and eval reading list: intelligent tutoring systems, learning analytics, content generation, assessment, evaluation benchmarks.
- Inspiration for what "good AI classroom" should be judged against.

Do not use for:
- Product runtime code.

## MAIC-Vibe: Optional Agent Workflow Reference

Repo:
- https://github.com/THU-MAIC/MAIC-Vibe
- Latest inspected main commit: `2e0cff3fc9fb9ee897e4d83427f30acba79bd900`
- License: MIT.

Use for:
- Claude/operator workflow improvements if useful.
- Possible coaching/checklist style for non-engineer collaboration.

Do not use for:
- AI Classroom engine, media, PBL, playback, or SaaS persistence.

## Claude Work Plan

Work on a branch. Pull latest `main` first.

### Goal 1: Upstream parity audit

Compare the current LearnPuddle modules against OpenMAIC P0 files:
- `backend/apps/maic/`
- `backend/apps/maic_pbl/`
- `frontend/src/components/maic/`
- `frontend/src/pages/teacher/ai-classroom*`
- `frontend/e2e/maic*.spec.*`

Output a short file-level plan before edits.

### Goal 2: Contract lift and validation

Implement or align:
- Typed scene outline schema.
- Typed action union.
- Action parser/repair.
- Slide-only action filtering.
- Agent/action whitelist.
- Structured unsupported-action fallback.
- Regression tests for invalid agent IDs, invalid widget fields, duplicate/stale handoffs, non-slide laser/spotlight, invalid media placeholders.

Use OpenMAIC files:
- `lib/types/action.ts`
- `lib/generation/action-parser.ts`
- `lib/orchestration/tool-schemas.ts`
- `lib/types/generation.ts`
- `lib/types/stage.ts`

### Goal 3: Teacher wizard v2/PBL-first

The Step 2 class guide must become a persisted planning contract, not just UI text.

It must feed:
- Agent generation.
- Outline generation.
- Slide/quiz/interactive/PBL content.
- PBL design and PBL actions.
- Media prompts.
- Discussion and handoff constraints.

Use OpenMAIC files:
- `lib/generation/outline-generator.ts`
- `lib/generation/scene-generator.ts`
- `lib/prompts/templates/*`
- `lib/pbl/generate-pbl.ts`
- `lib/pbl/pbl-system-prompt.ts`

### Goal 4: Real media lifecycle

Implement:
- Tenant provider resolution.
- Media request collection from outlines.
- Task statuses.
- Provider call.
- Rehost into `tenant/{tenant_id}/...` DO Spaces keys.
- Manifest mapping into slide elements.
- Playback status/error UI.

Use OpenMAIC files:
- `lib/media/media-orchestrator.ts`
- `lib/store/media-generation.ts`
- `lib/server/classroom-media-generation.ts`
- `lib/media/adapters/*`

Acceptance:
- New generated classrooms do not show `Image unavailable` when a provider is configured.
- Missing provider config fails visibly and gracefully, not as broken slide layout.

### Goal 5: Playback, audio, laser, handoff, layout

Implement:
- Fullscreen/immersive player sizing.
- Stable 16:9 viewport math.
- Image object-fit/crop rules.
- Sparse scene/slide bounds resolver keyed by `sceneIdx`.
- Audio preloading and stale audio stop on scene navigation.
- Active speaker follows actual audio/action timeline.
- Laser/spotlight geometry maps to current slide elements.

Use OpenMAIC files:
- `components/slide-renderer/Editor/ScreenCanvas.tsx`
- `components/slide-renderer/Editor/Canvas/hooks/useViewportSize.ts`
- `components/slide-renderer/Editor/SpotlightOverlay.tsx`
- `components/slide-renderer/Editor/LaserOverlay.tsx`
- `lib/audio/*`

### Goal 6: PBL quality

Implement:
- Real tool-calling PBL path with project/agent/issueboard MCP tools.
- Class-guide-aware PBL design.
- PBL action prompts that reference the real role, issue, deliverable, constraints, and success criteria.
- Issue completion and chat handoff regression tests.

Use OpenMAIC files:
- `lib/pbl/generate-pbl.ts`
- `lib/pbl/mcp/*`
- `lib/pbl/types.ts`
- `components/scene-renderers/pbl/*`

### Goal 7: Production-real regression harness

Add a Playwright teacher flow:
- Login as teacher.
- Create AI Classroom from teacher portal.
- Fill Step 1 and Step 2 class guide.
- Generate via v2/PBL-first path.
- Wait for readiness.
- Open player.
- Verify media renders.
- Verify audio advances.
- Verify active agent changes.
- Verify laser/spotlight appears on the correct element.
- Verify PBL role selection, issueboard, chat, issue completion.
- Verify quiz submit.
- Verify fullscreen layout and scene navigation do not restart audio at scene 0.

Use OpenMAIC:
- `e2e/tests/full-happy-path.spec.ts`
- `e2e/tests/classroom-interaction.spec.ts`
- `eval/whiteboard-layout/*`
- `eval/outline-language/*`

## Hard Guardrails

- No mocks/fakes for internal classroom behavior.
- No fake audio.
- No fake WebSockets.
- No synthetic shortcut data for the generation path.
- No direct use of `.objects.all_tenants()` unless a security review explicitly approves it.
- No unscoped public media URLs. Persist via tenant storage.
- No MAIC-UI sidecar by default.
- No direct copy without source traceability.
- No commit unless backend/frontend/e2e targeted validations pass or failures are explicitly documented.

## PR Requirement

Claude must open a PR and explicitly write:

`Codex, please review this PR before merge.`

Codex will review for:
- Upstream parity.
- SaaS tenant/auth/storage correctness.
- Production-real test coverage.
- Media/audio/handoff/layout regressions.
- Source traceability headers/docstrings.
