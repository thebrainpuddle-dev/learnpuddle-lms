# AI Classroom — OpenMAIC Parity Audit (Chunk 1 deliverable)

Date: 2026-05-16
Branch: `codex/ai-classroom-v2-pbl-hardening`
Author: Claude (this PR)
Reviewer: Codex

This document is the audit Goal 1 / Chunk 1 of the kickoff prompt requires before any product edits. It is grounded in a direct file-level comparison between:

- LearnPuddle: `/Volumes/CrucialX9/learnpuddle-lms` @ `11e54ef` (origin/main)
- OpenMAIC: `/Volumes/CrucialX9/OpenMAIC` @ `10b1fc83cf77c769e8acac7b6c0569122b764bfd`
- MAIC-Core: `/Volumes/CrucialX9/MAIC-Core`
- MAIC-UI: `/Volumes/CrucialX9/MAIC-UI`

The handoff and upstream map docs (`_coordination/inbox/claude/{AI-CLASSROOM-CI-HANDOFF-2026-05-14, THU-MAIC-UPSTREAM-MAP-2026-05-16, CLAUDE-AI-CLASSROOM-GOAL-PROMPT-2026-05-16}.md`) were used as the contract source. This audit only reports what was observed; it intentionally makes no product-code edits (per the Chunk 1 instruction).

---

## Headline finding

LearnPuddle's MAIC backend already implements a large majority of the OpenMAIC P0 contracts cleanly, with `Source: THU-MAIC/OpenMAIC ...` traceability headers and Pydantic ports of the TypeScript types. The remaining parity gaps are concentrated in **four places**, in descending priority order:

1. **Frontend slide-element geometry for spotlight/laser overlays** (responsive/fullscreen alignment is fragile because we measure DOM rects in screen pixels rather than OpenMAIC's SVG viewBox 0-100 percent system).
2. **Media lifecycle visibility**: server-side flow exists end-to-end but the per-element status surfacing — especially the "no Image unavailable when a provider is configured" acceptance bar — is not currently guarded by a regression test.
3. **Class-guide → planning contract**: needs verification that Step 2 wizard data is persisted as structured fields and consumed by all downstream prompts (outline / scene / pbl / media), not just passed as free-form text.
4. **PBL tool-calling production-real wiring**: the design loop exists (`maic_pbl/design_graph.py` is a real port of `lib/pbl/generate-pbl.ts`); needs end-to-end verification that it is the path teacher creation actually drives, with class-guide context threaded through.

CI itself is green at `11e54ef`. Everything below is foundation work, not CI repair.

---

## Section A — Already at OpenMAIC parity (do not rebuild)

The following modules have been audited as clean, traceable ports / adaptations of the OpenMAIC contract. They are production-real and should not be rewritten:

### A.1 Action contract — STRONG PARITY

| OpenMAIC (TS) | LearnPuddle (Python) | Verdict |
|---|---|---|
| `lib/types/action.ts` (286 lines) | `backend/apps/maic/protocol/actions.py` (405 lines) | Pydantic discriminated union with all 21 action types, `extra="forbid"`, source header citing upstream path. Adds runtime `validate_action()` / `validate_actions()` raising `MaicProtocolError`, and `filter_for_scene()` mirroring `tool-schemas.ts` `getEffectiveActions`. Includes a built-in assert: `assert len(ALL_ACTION_TYPES) == 21`. |
| `lib/generation/action-parser.ts` (153 lines) | `backend/apps/maic/generation/action_parser.py` (426 lines) | Direct port + improvement: also accepts `agentId` / `agent_id` / `speakerId` / `speaker_id` on text-type items (upstream has no such hook). Falls back to `json_repair` like upstream uses `jsonrepair`. Discussion-must-be-last post-processing matches upstream. Allowed-actions whitelist matches upstream. |
| `lib/orchestration/tool-schemas.ts` (72 lines) | `backend/apps/maic/orchestration/tool_schemas.py` (176 lines) | Larger than upstream because it also exports test fixtures. Functionally equivalent. |

**Conclusion:** the action vocabulary, parser, and slide-only filter are at parity. The Chunk 2 "implement action contract" work item in the prompt is largely done — the remaining piece is **adding regression tests** for the specific failure modes the handoff calls out (invalid agentId, stale handoff, slide-only on non-slide scene, invalid widget fields, malformed media placeholder). See Section B.1.

### A.2 PBL design loop — STRONG PARITY

| OpenMAIC (TS) | LearnPuddle (Python) | Verdict |
|---|---|---|
| `lib/pbl/types.ts` (79 lines) | `backend/apps/maic_pbl/types.py` (189 lines) | Pydantic port with `extra='forbid'` on every model. Source header cites upstream. Adds module-level constants (`MODE_PROJECT_INFO`, `MODE_AGENT`, `MODE_ISSUEBOARD`, `MODE_IDLE`) so a typo in `design_graph.py` surfaces at import time. |
| `lib/pbl/generate-pbl.ts` (414 lines) | `backend/apps/maic_pbl/design_graph.py` (557 lines) | LangChain `StructuredTool` + mode-machine port; cites upstream commit. Implements the four-mode state machine (project_info → agent → issueboard → idle) with stop conditions: `set_mode('idle')` OR step counter ≥ 30 (matches upstream `stepCountIs(30)`). |
| `lib/pbl/mcp/{project,agent,issueboard,mode}-mcp.ts` | `backend/apps/maic_pbl/mcp/{project_mcp,agent_mcp,issueboard_mcp,mode_mcp}.py` | All four MCPs present with `agent_templates.py` matching `agent-templates.ts`. |
| `lib/pbl/pbl-system-prompt.ts` (30 lines) | `backend/apps/maic_pbl/system_prompt.py` (62 lines) | Built. |

**Conclusion:** Chunk 6 "real tool-calling PBL path" is structurally already in place. The remaining work is **wiring class-guide context into the design call** and a Playwright regression for the role / issueboard / chat / issue-completion path. See Section B.4.

### A.3 Media storage tenant boundary — STRONG PARITY (and architecturally cleaner than upstream)

| OpenMAIC (TS) | LearnPuddle (Python) | Verdict |
|---|---|---|
| Browser-side IndexedDB blob cache in `lib/media/media-orchestrator.ts` | `backend/apps/maic/media/storage.py` (106 lines) | LearnPuddle persists generated media to tenant-prefixed object storage keys `maic/<tenant_id>/<kind>/<media_id>.<ext>` via `default_storage` (S3Boto3Storage in prod). This is the correct multi-tenant SaaS pattern; upstream's IndexedDB approach would not satisfy our tenant isolation invariant. Refusing tenant-less writes is enforced (`raise ValueError("upload_media requires a non-empty tenant_id")`). |
| `lib/media/media-orchestrator.ts` (286 lines) | `backend/apps/maic/media/orchestrator.py` (173 lines) | LearnPuddle's orchestrator wraps adapter calls with bounded per-attempt timeout + retry (image 3 attempts, video 2 attempts; exponential backoff). Distinguishes `MaicConfigError` (permanent) from `MaicProviderError` (transient). Latency is measured at orchestrator level so retries are not counted in successful-attempt latency. Functionally correct; **structurally fewer lines than upstream because the queue/store state machine lives elsewhere** (per-task store on frontend, model row on backend). |

**Conclusion:** Chunk 4 "tenant-scoped storage keys" is done. The remaining gap is the **per-element status manifest → slide-element mapping → 'no Image unavailable' invariant**: see B.2.

### A.4 Backend generation pipeline — PRESENT, NEEDS PARITY VERIFICATION

| OpenMAIC (TS) | LearnPuddle (Python) | Verdict |
|---|---|---|
| `lib/generation/outline-generator.ts` (195) | `backend/apps/maic/generation/outline_generator.py` (437) | Present. |
| `lib/generation/scene-generator.ts` (1675) | `backend/apps/maic/generation/scene_generator.py` (2956) | Present. **76% larger than upstream** — likely contains both stage-1 and stage-2 paths plus tenant/llm-config glue; would benefit from a structural read in Chunk 3. |
| `lib/generation/scene-builder.ts` (234) | `backend/apps/maic/generation/scene_builder.py` (396) | Present; cites MAIC-915 wiring for `gen_img_<id>` placeholder resolution to the media orchestrator. |
| `lib/generation/pipeline-runner.ts` (98) | `backend/apps/maic/generation/pipeline_runner.py` (218) | Present. |
| `lib/prompts/templates/*` | `backend/apps/maic/prompts/templates/*` | Present (subdir exists with `SOURCES.txt` audit trail). |

**Conclusion:** the two-stage pipeline exists. The audit cannot certify line-by-line parity inside the 2956-line `scene_generator.py` without a deeper diff (out of scope for Chunk 1). Recommendation: in Chunk 3, isolate where Step 2 class-guide fields enter each prompt template and add a unit test per prompt for "with vs without class guide → materially different output" (snapshot-style).

---

## Section B — Concrete parity gaps with proposed fixes

### B.1 Action validation regression coverage (Chunk 2 closeout)

**Observation:** `backend/apps/maic/tests_protocol_actions.py` (245 lines) and `backend/apps/maic/generation/tests/` cover the happy path. The handoff specifically calls out five malformed-input cases as regression gaps:

| Failure mode | Where it must be blocked | Test target |
|---|---|---|
| Invalid `agentId` (no matching agent in registry) | `apps/maic/orchestration/director_graph.py` consumes `agentId`; should error or fall back before emitting WS event | `tests_director_graph_multi_agent.py` (248 lines, present) — add case |
| Stale / duplicate handoff (agent A handoff to B while B is already speaking) | director loop | director graph tests |
| Slide-only action on non-slide scene | `protocol/actions.filter_for_scene()` already strips at parser; verify it also strips at director-emit time | `tests_protocol_actions.py` — add `filter_for_scene("widget")` case |
| Extra / unknown widget field on `widget_setState` | `WidgetSetStateAction` has `state: dict[str, Any]`. Upstream is also permissive here. **Decision:** if we want strict mode, tighten `state` to a typed registry of known widget keys per widget kind. Likely defer; document as "permissive by design". |
| Invalid media placeholder (e.g. element references a `gen_img_xyz` that the manifest does not contain) | `scene_builder.py` placeholder resolver. Currently surfaces as `Image unavailable` UI — should fail loud during build so the teacher sees a generation error, not a silent fallback. | new test in `generation/tests/test_scene_builder.py` |

**Proposed fix scope (Chunk 2 closeout PR):** add five tests; tighten `scene_builder` to raise `MaicProtocolError` (not silently fall back) when a placeholder cannot be resolved. ~150 LoC, low risk.

### B.2 Media lifecycle: "no Image unavailable when a provider is configured"

**Observation chain:**

1. `frontend/src/pages/teacher/MAICPlayerPage.tsx:42-115` watches `images_pending` flip true → false and re-syncs slides/scenes from the classroom-detail API. This handles the **mid-playback** case. ✓
2. `frontend/src/stores/maicMediaGenerationStore.ts` (per-task store hydrated from `content_image_tasks` and the per-classroom WS channel) tracks **per-element** status. ✓
3. `frontend/src/lib/maicReadinessGate.ts` (`isClassroomPlayable`) decides when the play button enables. ✓ but the gate's exact policy when a provider is configured but generation has **failed** (vs still pending) needs to be re-read.
4. `backend/apps/maic/media/orchestrator.py` raises `MaicProviderError` on final failure. The view-layer translation is `502`. ✓
5. **GAP:** No regression test currently asserts: "given a tenant with a configured image provider, the rendered slide does not show 'Image unavailable' for any element whose media task is `done`." The wording in `maic-full-playback.spec.js` covers media renders but doesn't enforce the negative claim.

**Proposed fix (Chunk 4 closeout PR):**

- Frontend: assert `await expect(page.locator('text=Image unavailable')).toHaveCount(0)` in `frontend/e2e/maic-full-playback.spec.js` after the readiness gate opens.
- Backend: add a unit test in `apps/maic/media/tests_orchestrator.py` that asserts a tenant with a configured (mock-free, contract-only) provider has the orchestrator return a result whose `latency_ms > 0` rather than a placeholder URL. (This already exists in spirit; verify and tighten.)
- Documentation: add a one-paragraph note to `DO_SPACES_STRUCTURE.md` confirming `maic/<tenant_id>/<kind>/...` prefix invariant.

### B.3 Class-guide → planning contract (Chunk 3)

**Observation:**

- `frontend/src/pages/teacher/MAICCreatePage.tsx` is a 55-line shell; all logic is in `frontend/src/components/maic/GenerationWizard.tsx` (1179 lines).
- Backend entry: `POST /api/maic/v2/generate/` (`backend/apps/maic/views_generation.py`) accepts `{topic, agentCount, language, level, specifications, languageModelId}`. **`specifications` is the free-form string** that today carries the Step 2 class guide.
- For Step 2 to be a **structured planning contract** (per the handoff: learning objective, misconception, PBL brief, media needs, agent choreography, checks, handoffs), the API needs to accept a typed object — not just `specifications: str` — and the outline / scene / pbl / media prompts must consume specific fields rather than embedding the blob verbatim.

**Proposed fix (Chunk 3 PR — largest of the chunks):**

1. Add a typed request body field `classGuide: { learningObjective: str, gradeLevel: str, misconceptions: list[str], pblBrief: str | null, mediaNeeds: list[str], agentChoreography: list[str], successCriteria: list[str] } | None` on the v2 generate endpoint. Keep `specifications` backward-compatible (deprecated alias).
2. Persist `class_guide` JSON onto `MaicGenerationJob` (migration).
3. Plumb it through `outline_generator.py`, `scene_generator.py`, `scene_builder.py`, `media/orchestrator.py` (for image-prompt enrichment), and `maic_pbl/design_graph.py` (for the project description).
4. Update `GenerationWizard.tsx` Step 2 UI to capture the structured fields (with sensible defaults so it doesn't become a 20-field form — drive most off the topic/level + 2-3 explicit fields).
5. Tests: snapshot a fixture outline for the same topic with vs without class guide and assert the LLM prompt strings differ in specific ways (e.g. learning objective appears in outline prompt, success criteria appear in pbl design prompt).

### B.4 PBL Playwright regression (Chunk 6 closeout)

**Observation:** `frontend/e2e/maic-full-playback.spec.js` exists. PBL-specific assertions are not visible in the file list (only the three maic-{full,a11y,mobile}-playback specs). The handoff Goal 7 spells out the missing checks:
- role selection (PBL agent picker)
- issueboard renders with active issue
- chat messages stream from Question agent
- issue completion advances to next issue
- quiz submit

**Proposed fix (Chunk 6 closeout PR):** add `frontend/e2e/maic-pbl-flow.spec.js` covering the above against the local seeded teacher. Reuse the seeded READY classroom path from `frontend/e2e/maic-full-playback.spec.js`.

### B.5 Playback / spotlight / laser geometry (Chunk 5)

**Observation — the most concrete parity gap in the audit:**

OpenMAIC's `components/slide-renderer/Editor/SpotlightOverlay.tsx` measures the spotlight target inside an **SVG viewBox 0-100 percent** coordinate system, converting `getBoundingClientRect()` deltas relative to the canvas container. This is robust under fullscreen, browser zoom, responsive layouts, and 16:9 letterboxing.

LearnPuddle's equivalents diverge:

| LearnPuddle file | Behavior | Gap vs OpenMAIC |
|---|---|---|
| `frontend/src/components/maic/HighlightOverlay.tsx` (the **agent-driven** spotlight, despite the name) | Calls `document.getElementById(elementId).getBoundingClientRect()` and renders a full-viewport overlay with an SVG mask cutout in **screen pixel space**. | Misaligned under fullscreen / zoom because the cutout coordinates are not relative to a stable 16:9 canvas viewport. |
| `frontend/src/components/maic/SpotlightOverlay.tsx` | **Manual mouse-cursor spotlight** (move cursor, dim around cursor). Unrelated to the agent `spotlight` action. **Naming collision with upstream**. | Confusing for readers familiar with OpenMAIC. Consider renaming to `MouseCursorSpotlight.tsx` and renaming `HighlightOverlay.tsx` → `SpotlightOverlay.tsx`. |
| `frontend/src/components/maic/LaserPointer.tsx` | Uses `targetElementId` from `useMAICStageStore.laserElementId`; measurement approach not yet read in detail but presumed similar pattern. | Likely same percent-vs-pixel geometry gap. |

**Proposed fix (Chunk 5 PR):**

1. Lift `OpenMAIC components/slide-renderer/Editor/Canvas/hooks/useViewportSize.ts` into `frontend/src/hooks/useMaicViewportSize.ts` with traceability header.
2. Rewrite `HighlightOverlay.tsx` to render inside the slide canvas's stable 16:9 SVG viewBox 0-100 percent space (use `useMaicViewportSize` for letterboxing math).
3. Apply the same fix to `LaserPointer.tsx`.
4. Rename the existing `SpotlightOverlay.tsx` (mouse-cursor tool) → `PresentationCursorOverlay.tsx` to free the name; rename `HighlightOverlay.tsx` → `SpotlightOverlay.tsx` to match upstream.
5. Add `frontend/e2e/maic-overlay-geometry.spec.js`: in a 1280×720 viewport AND in fullscreen, take a screenshot of a spotlight on a known element ID and assert the bright region's centroid is within ±2% of the expected slide-percent coordinates.
6. **Player audio restart at scene 0**: handoff calls this out as a regression. `MAICPlayerPage.tsx:78-113` already restores `currentSceneIndex` / `currentSlideIndex` across the `images_pending` flip; verify the same protection exists for stale audio when scene navigation happens. Add a Playwright case that advances to scene N>0, triggers an `images_pending` re-sync, and asserts the player stays at scene N.

---

## Section C — Architectural callouts (no code change implied)

### C.1 Frontend media generation is server-side, not browser-side (CORRECT for SaaS)

OpenMAIC's `lib/media/media-orchestrator.ts` runs in the **browser**, hitting `/api/generate/image` with the user's BYOK API key in request headers, then caching the resulting blob in IndexedDB. This is the right pattern for a single-tenant Next.js app where every browser is its own user with its own keys.

LearnPuddle's pattern is **server-side Celery + DO Spaces + per-classroom WS channel + per-element store**. This is correct and not a parity gap — it is an architectural adaptation required by the multi-tenant SaaS boundary. Codex should not require this be "ported" to the browser-side approach; the upstream-map already records this.

### C.2 LangGraph / Channels boundary

`apps/maic/orchestration/director_graph.py` is a LangGraph port of `lib/orchestration/director-graph.ts`. WebSocket transport is Django Channels (`apps/maic/consumers.py`, `apps/maic_pbl/consumers.py`). Both layers are real. No mocks.

### C.3 MAIC-UI sidecar

Per the upstream map: **do not** make MAIC-UI the default widget engine. OpenMAIC itself does not depend on MAIC-UI; widget HTML is generated inline. LearnPuddle currently does not have a MAIC-UI sidecar, and that posture is correct. The audit found no `maic-ui` references in `package.json` or backend requirements — already at the desired state.

---

## Section D — Proposed PR sequence after this audit

Per the kickoff prompt's own splitting suggestion. Each row is one PR.

| # | Chunk | Scope | Risk | Test bar |
|---|---|---|---|---|
| 1 | **This PR** | Audit doc + commit pending inbox handoff updates | None | n/a |
| 2 | Action validation closeout | 5 regression tests + `scene_builder` placeholder strictness | Low — backend only, additive | backend pytest only |
| 3 | Class-guide planning contract | Typed `classGuide` field + DB migration + prompt plumbing + wizard UI | Medium — touches generation prompt strings | backend pytest + frontend vitest + 1 Playwright |
| 4 | Media-lifecycle regression coverage | Negative assertion in maic-full-playback spec + 1 backend test | Low — additive | E2E smoke |
| 5 | Overlay geometry + rename + audio scene-N restoration | Frontend overlay rewrite + rename + new Playwright spec | Medium — touches multiple component files | frontend vitest + E2E maic-overlay-geometry |
| 6 | PBL Playwright spec | New `maic-pbl-flow.spec.js` | Low — test only | E2E |
| 7 | scene_generator.py structural cleanup | If audit reveals dead code paths after Chunks 2-6 | Medium — defer until 2-6 land | full backend pytest |

This sequencing keeps each PR small enough to validate against the existing CI (5919 backend tests + 3344 frontend tests + local MAIC E2E smoke) without risking the green main.

---

## Section E — Hard guardrails carried forward

Recorded verbatim from the handoff so subsequent PRs inherit them:

- No mocks / fakes for internal classroom behavior.
- No fake audio.
- No fake WebSockets.
- No synthetic shortcut data for the generation path.
- No `.objects.all_tenants()` without security review.
- No unscoped public media URLs — persist via tenant storage.
- No MAIC-UI sidecar by default.
- No direct code copy without `Source: THU-MAIC/OpenMAIC <commit-sha> <path>` traceability header.
- No commit unless backend/frontend/e2e targeted validations pass or failures are documented.

---

## Validation performed in this PR

This PR contains only this audit doc + the three inbox handoff documents that arrived for the mission. **No product code is modified**, per Chunk 1's "Do not edit product code until the audit plan is written" instruction.

Therefore the validation bar for this PR is:
- `git diff --check` passes
- `markdownlint` (if wired) passes — not required by CI today

The full backend/frontend/E2E suites are not re-run because no product code changed.

Next PR (Chunk 2) will carry the first batch of backend tests + the `scene_builder` placeholder strictness fix and will run the full backend suite locally before push.

---

Codex, please review this PR before merge.
