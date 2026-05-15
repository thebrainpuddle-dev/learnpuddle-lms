# AI Classroom CI Handoff - 2026-05-14

## Context

Codex stabilized the failed `main` push for LearnPuddle LMS after GitHub Actions run `25854008985` failed in `backend-test` job `75967193997`.

Source run:
- https://github.com/thebrainpuddle-dev/learnpuddle-lms/actions/runs/25854008985/job/75967193997

Original failed commit:
- `40c053d791d8aa54ef7220818acd41ebd1220f47`

The CI failure was not one AI Classroom bug. It was a cross-suite contract break after the AI Classroom/MAIC work activated stricter generation paths and exposed stale assumptions in legacy tests and app boundaries.

## What Codex Fixed

- Enabled MAIC v2 generation flags in CI and test bootstrap so CI tests the intended AI Classroom path.
- Restored backward-compatible login token aliases while preserving the nested `tokens` response.
- Fixed legacy 2FA test compatibility for old TOTP/static-device paths without weakening encrypted-secret storage.
- Restored patchable module-level contracts for chatbot, course generator, Outlook calendar provider, and reports tasks.
- Split raw request handlers from DRF-decorated API aliases where RequestFactory tests depend on plain Django requests.
- Hardened report export headers, report-builder CSV/XLSX task dispatch, SCORM manifest validity, cache fail-closed behavior, and notification unarchive CLI compatibility.
- Tightened progress/assessment/gamification contracts around quiz assignment lookup, cross-tenant bank validation, mastery duplicate handling, default gamification config, and single-content course-completion XP.
- Stabilized MAIC/PBL tests by avoiding stale ASGI settings and closing stale DB connections around sync helpers in websocket tests.
- Hardened semantic search under pytest eager Celery mode and excluded NULL embeddings from distance SQL.
- Updated dependency pins for security audit:
  - `Django==5.2.14`
  - `pypdf>=6.10.2,<7.0`

## Local Verification Completed

All of these were run locally on `/Volumes/CrucialX9/learnpuddle-lms` before commit/push:

- Backend CI-equivalent coverage:
  - `5919 passed, 24 skipped, 365 warnings`
  - coverage: `76.90%`
  - command included `--cov=apps --cov=utils --cov=config --cov-fail-under=60`
- PDF extractor smoke after pypdf upgrade:
  - `PDFExtractor().extract(...)` returned expected text.
  - `apps.courses.tasks._extract_pdf_text(...)` returned expected text.
- Python dependency audit:
  - `No known vulnerabilities found`
- Django system check:
  - `System check identified no issues`
- Frontend tests:
  - `211 passed test files`
  - `3344 passed tests`
- Frontend production build:
  - `vite build` completed successfully.

## Follow-up CI Fix

GitHub Actions run `25879661771` on commit `d7305ef` reduced the backend failure to one SCIM sorting assertion:

- `apps/users/tests_scim.py::TestSCIMListUsers::test_list_users_sortby_email_is_synonym_for_username`

Root cause: PostgreSQL's locale-dependent text collation can order `admin-...@...` before `a@...`, while the SCIM contract/test expects deterministic byte-style `userName`/email ordering.

Fix: `apps/users/scim_views.py` now uses explicit PostgreSQL `COLLATE "C"` ordering for SCIM user text sorts, with a non-PostgreSQL fallback to normal field ordering.

Follow-up local validation:

- Targeted SCIM sort tests: `7 passed`.
- Full SCIM user/group/cross-tenant cluster: `173 passed`.

## Second CI Finding - E2E Target Missing

GitHub Actions run `25881902706` on commit `8ec44c8` proved the backend and frontend jobs were green, then failed only in `e2e-test` before tests started:

- Run: https://github.com/thebrainpuddle-dev/learnpuddle-lms/actions/runs/25881902706
- Failing job: `e2e-test`
- Failing step: `Require E2E target is configured`
- Key log line: `E2E_BASE_URL secret is not configured. Set it to your staging URL to enable E2E tests, or set repository variable E2E_SKIP_BLOCKING=true to temporarily bypass.`

Repo inspection showed no Actions secrets or variables were configured for E2E, and the public demo/staging hosts were reachable but not usable with the deterministic local demo credentials. The fix is not to skip E2E by default. CI now resolves an E2E mode:

- `external` when `E2E_BASE_URL` is configured, preserving the existing staging/preview `e2e/` suite.
- `local` when `E2E_BASE_URL` is missing, starting a real local Postgres/Redis/Django/Vite stack, seeding `create_demo_tenant`, and running the MAIC Playwright suite with real browser playback.
- `skip` only when `E2E_SKIP_BLOCKING=true`, kept as an explicit temporary emergency bypass.

Claude should watch for this in PRs: do not reintroduce a missing-secret hard stop, and do not replace the local fallback with mocked browser/audio/websocket behavior.

## Remaining AI Classroom Foundation Work For Claude

This commit makes CI/build stable. It does not finish the OpenMAIC-level classroom experience. Claude should pull latest `main`, branch, and work in focused PRs.

Priority 1 - Runtime contract and action engine:
- Build the OpenMAIC-style contract discipline into our SaaS architecture: typed scene/action schema, strict validation, repair/retry boundaries, and explicit unsupported-action fallback.
- Add regression tests for malformed agent IDs, invalid widget fields, stale/duplicate handoffs, invalid media placeholders, and impossible timeline actions.

Priority 2 - Media lifecycle:
- Replace "image unavailable" and fake/static image placeholder behavior with real provider-backed media generation, tenant-scoped storage keys, and status/error visibility.
- Add tests for media prompt creation, provider failure isolation, rehosted storage URLs, missing-provider config, and classroom playback rendering.

Priority 3 - PBL/class guide generation quality:
- Move the teacher creation wizard fully to v2/PBL-first generation.
- Use the Step 2 class guide as a real planning contract: learning objective, misconception, agent choreography, discussion handoff, assessment, media, and interaction requirements.
- Add a quality gate that rejects thin/repetitive slide structures, repeated bullets, oversized/zoomed images, no-context media, and low-context quizzes.

Priority 4 - Playback and handoff robustness:
- Fix timeline synchronization for audio, active speaker, laser/spotlight, scene transitions, and PBL handoffs.
- Add a live Playwright harness that creates an AI Classroom from teacher portal, waits for generation, opens playback, verifies audio frames, active agent changes, media renders, PBL websocket events, issue completion, quiz submit, and fullscreen layout.

Priority 5 - Review and release discipline:
- No mocks/fakes for internal classroom behavior.
- Use production Django/Channels/LangGraph/Celery/media paths.
- Run backend suite, frontend tests/build, and the live teacher Playwright harness.
- Commit to a branch and open a PR.
- Explicitly ask: "Codex, please review this PR before merge."

## Suggested Claude Prompt

You are Claude working in `/Volumes/CrucialX9/learnpuddle-lms`. Pull latest `main` first. Your goal is to close the OpenMAIC gap for AI Classroom, not to create demo-only fixes. Use the Obsidian vault at `/Volumes/CrucialX9/obsidian-vault/agent-hq/projects/learnpuddle-lms/maic-rebuild/` as project memory, and compare implementation patterns against the open OpenMAIC repos at `https://github.com/THU-MAIC`.

Work in production-real slices. Do not mock internal libraries, audio, websocket, LangGraph, media, tenant isolation, or generation paths. If a unit test cannot run production-real, move it to Playwright or document a manual live smoke.

Start with:
1. Audit the current teacher AI Classroom wizard, v2 generation path, PBL renderer, action engine, media resolver, audio timeline, websocket handoffs, and classroom playback layout.
2. Produce a short file-level plan before editing.
3. Implement strict schema/action validation, media lifecycle hardening, v2/PBL-first teacher wizard routing, and a live teacher regression harness in small commits.
4. Validate with backend tests, frontend tests/build, and a real local teacher portal run.
5. Open a PR and state that Codex must review the work before merge.

Acceptance bar:
- No "image unavailable" for newly generated classrooms when a configured media provider is available.
- No repeated bullet/duplicated slide slop from the generator quality gate.
- No invalid `agentId` handoffs escaping validation.
- Audio, active speaker, laser/spotlight, and scene transitions remain synchronized through real playback.
- Fullscreen/classroom layout preserves image aspect ratios and avoids clipping/zooming.
- Teacher Step 2 class guide materially shapes the generated course.
- CI remains green.
