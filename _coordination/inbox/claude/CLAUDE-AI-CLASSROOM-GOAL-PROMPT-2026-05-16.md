# Claude Kickoff Prompt - AI Classroom OpenMAIC Parity

Copy this into Claude Code as the kickoff prompt.

```text
/goal
You are Claude working in /Volumes/CrucialX9/learnpuddle-lms.

Mission: make LearnPuddle AI Classroom production-grade and OpenMAIC-level by using a hybrid OpenMAIC-first approach. Do not rebuild every behavior from scratch. Use THU-MAIC/OpenMAIC as the primary implementation/reference contract, then adapt it into LearnPuddle's Django/React multi-tenant SaaS shell.

Read first, in this order:
1. /Volumes/CrucialX9/learnpuddle-lms/ARCHITECTURE.md
2. /Volumes/CrucialX9/learnpuddle-lms/README.md
3. /Volumes/CrucialX9/learnpuddle-lms/AGENTS.md
4. /Volumes/CrucialX9/learnpuddle-lms/_coordination/inbox/claude/AI-CLASSROOM-CI-HANDOFF-2026-05-14.md
5. /Volumes/CrucialX9/learnpuddle-lms/_coordination/inbox/claude/THU-MAIC-UPSTREAM-MAP-2026-05-16.md
6. /Volumes/CrucialX9/obsidian-vault/agent-hq/projects/learnpuddle-lms/maic-rebuild/reference/decisions.md
7. /Volumes/CrucialX9/obsidian-vault/agent-hq/projects/learnpuddle-lms/maic-rebuild/reference/THU-MAIC-UPSTREAM-MAP-2026-05-16.md
8. /Volumes/CrucialX9/obsidian-vault/agent-hq/projects/learnpuddle-lms/maic-rebuild/ops/AI-CLASSROOM-CI-STABILIZATION-2026-05-14.md

Upstream repos to study:
- https://github.com/THU-MAIC/OpenMAIC
- https://github.com/THU-MAIC/MAIC-Core
- https://github.com/THU-MAIC/MAIC-UI
- https://github.com/THU-MAIC/SimClass
- https://github.com/THU-MAIC/Awesome-AI-Era-Edu
- https://github.com/THU-MAIC/MAIC-Vibe

Local upstream clones if present:
- /Volumes/CrucialX9/OpenMAIC
- /Volumes/CrucialX9/MAIC-Core
- /Volumes/CrucialX9/MAIC-UI

Use these LearnPuddle paths as the work surface:
- /Volumes/CrucialX9/learnpuddle-lms/backend/apps/maic
- /Volumes/CrucialX9/learnpuddle-lms/backend/apps/maic_pbl
- /Volumes/CrucialX9/learnpuddle-lms/backend/apps/courses
- /Volumes/CrucialX9/learnpuddle-lms/frontend/src/pages/teacher
- /Volumes/CrucialX9/learnpuddle-lms/frontend/src/components/maic
- /Volumes/CrucialX9/learnpuddle-lms/frontend/src/services
- /Volumes/CrucialX9/learnpuddle-lms/frontend/e2e
- /Volumes/CrucialX9/learnpuddle-lms/e2e
- /Volumes/CrucialX9/learnpuddle-lms/docs/superpowers

Use these OpenMAIC blocks as the source contract:
- lib/generation/outline-generator.ts
- lib/generation/scene-generator.ts
- lib/generation/scene-builder.ts
- lib/generation/action-parser.ts
- lib/types/action.ts
- lib/orchestration/director-graph.ts
- lib/orchestration/tool-schemas.ts
- lib/pbl/generate-pbl.ts
- lib/pbl/mcp/*
- lib/pbl/types.ts
- lib/media/media-orchestrator.ts
- lib/store/media-generation.ts
- lib/server/classroom-media-generation.ts
- components/slide-renderer/Editor/ScreenCanvas.tsx
- components/slide-renderer/Editor/Canvas/hooks/useViewportSize.ts
- components/slide-renderer/Editor/SpotlightOverlay.tsx
- components/slide-renderer/Editor/LaserOverlay.tsx
- e2e/tests/full-happy-path.spec.ts
- e2e/tests/classroom-interaction.spec.ts
- eval/whiteboard-layout/*
- eval/outline-language/*

Your superpowers for this task:
1. Upstream parity auditor: compare LearnPuddle behavior against OpenMAIC contracts before editing.
2. SaaS integrator: preserve tenant/auth/DO Spaces/audit/student-teacher permissions while adapting upstream code.
3. Contract hardener: typed schemas, validation, repair/retry boundaries, unsupported-action fallback.
4. Media lifecycle engineer: provider call, tenant rehost, media manifest, status/error UI, no fake image URLs.
5. Playback systems engineer: audio, active speaker, laser, spotlight, fullscreen, scene navigation, handoffs.
6. PBL agent architect: tool-calling project/agent/issueboard flow using class-guide context.
7. Production-real QA: Playwright live teacher flow, real audio, real WebSocket, real generation paths.
8. Security reviewer: no cross-tenant leaks, no unscoped storage keys, no all_tenants shortcuts, no public media bypass.

Work plan:
1. Create a short file-level audit plan before edits.
2. Make the teacher wizard v2/PBL-first end to end.
3. Persist Step 2 class guide as a structured planning contract.
4. Lift/adapt OpenMAIC scene/action/media/PBL contracts.
5. Replace placeholder/missing media behavior with tenant-scoped real media lifecycle.
6. Fix player layout, fullscreen, sparse scene/slide bounds, audio restart, active-agent handoff, laser/spotlight geometry.
7. Add production-real regression tests for teacher create -> generate -> play -> media/audio/handoff/PBL/quiz/fullscreen/navigation.
8. Run backend tests, frontend tests/build, and the targeted live Playwright harness.
9. Update Obsidian with what changed, what remains, and exact validation results.
10. Commit to a branch, open a PR, and write: "Codex, please review this PR before merge."

Hard rules:
- No mocks/fakes for internal AI Classroom behavior.
- No fake audio.
- No fake WebSockets.
- No synthetic shortcut data for generation.
- No direct OpenMAIC code lift without Source traceability headers/docstrings.
- No MAIC-UI sidecar by default.
- No unscoped public media URLs.
- No tenant isolation bypass.
- Do not ship "Image unavailable" for newly generated classrooms when a provider is configured.
- If a unit test cannot run production-real, move it to Playwright or document a manual live smoke.

Acceptance bar:
- New teacher-created AI Classrooms use v2/PBL-first path.
- Class guide materially shapes outline, agents, slides, PBL, media, and actions.
- Media renders with preserved aspect ratios; no broken placeholders under configured providers.
- Audio, active speaker, laser/spotlight, discussion handoffs, and scene navigation stay synchronized.
- PBL has roles, issueboard, chat, issue completion, and contextual actions.
- Fullscreen player feels immersive and does not inherit broken portal sizing.
- CI remains green or failures are fully documented with next fixes.
```

## Optional Smaller Goals

Use these if Claude needs to split work into PR-sized chunks.

```text
/goal AI Classroom Chunk 1: Upstream parity audit and contract plan.
Read the handoff/upstream map, compare LearnPuddle AI Classroom against OpenMAIC generation/action/media/PBL/player contracts, and produce a file-level implementation plan with risks and test commands. Do not edit product code until the audit plan is written.
```

```text
/goal AI Classroom Chunk 2: Teacher wizard v2/PBL-first and class-guide contract.
Make the teacher AI Classroom creation flow route through v2/PBL-first generation. Persist Step 2 as structured planning data and feed it into agents, outline, slide/quiz/interactive/PBL content, media prompts, and actions. Add tests.
```

```text
/goal AI Classroom Chunk 3: Real media lifecycle.
Lift/adapt OpenMAIC media lifecycle into LearnPuddle SaaS: collect media requests, call configured provider, persist to tenant-prefixed DO Spaces keys, map manifest back into slide elements, show provider errors clearly, and eliminate Image unavailable for configured providers.
```

```text
/goal AI Classroom Chunk 4: Playback/audio/handoff/layout.
Fix fullscreen/immersive player layout, sparse scene-slide bounds, audio restart/stale audio, active speaker, handoff sync, laser/spotlight geometry, and image aspect ratios using OpenMAIC viewport/action patterns. Add Playwright coverage.
```

```text
/goal AI Classroom Chunk 5: PBL tool-calling quality.
Use OpenMAIC PBL MCP/tool-calling design to make role selection, issueboard, question/judge agents, contextual project brief, issue completion, and PBL action prompts production-real and class-guide-aware.
```
