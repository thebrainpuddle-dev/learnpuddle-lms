# AI Classroom Overnight Automode - 2026-05-16

Shared source of truth for Claude + Codex while PR #41 is being stabilized.

## PR

- https://github.com/thebrainpuddle-dev/learnpuddle-lms/pull/41
- Branch: `codex/ai-classroom-full`
- Head: `37386a3d19a703dba773152ba93f508172f8353f`

## Current Standing

- `frontend-test`: green
- `backend-test`: red
- `e2e`: red
- Coverage in failed backend run: `76.93%`

## Immediate Fixes

1. Backend seed assertion:
   - File: `/Volumes/CrucialX9/learnpuddle-lms/backend/tests/courses/test_seed_maic_test_classroom.py`
   - Current bad expectation: one scene.
   - Correct contract: three deterministic seed scenes: base slide, image slide, PBL scene.
   - Fix test to assert the new contract. Do not shrink seed output.

2. PBL send-button selector:
   - File: `/Volumes/CrucialX9/learnpuddle-lms/frontend/e2e/maic-pbl-flow.spec.js`
   - Current issue: global "Send message" selector matches both PBL chat and classroom chat.
   - Fix test by scoping to PBL region/container. Do not skip or loosen.

## Operating Rule

Claude implements and pushes focused fixes. Codex monitors CI and reviews. Both agents use:

- Repo coordination: `/Volumes/CrucialX9/learnpuddle-lms/_coordination/`
- Claude inbox: `/Volumes/CrucialX9/learnpuddle-lms/_coordination/inbox/claude/`
- Reviewer inbox: `/Volumes/CrucialX9/learnpuddle-lms/_coordination/inbox/reviewer/`
- Shared log: `/Volumes/CrucialX9/learnpuddle-lms/_coordination/shared-log.md`

No fake acceptance. No mocks for AI Classroom-critical behavior. No merge until PR #41 is green.

## After Green

Next PR should be the vertical teacher-created AI Classroom slice:

- teacher wizard routes through v2/PBL-first
- class guide shapes outline, agents, slides, media, PBL, actions
- generated classroom opens in real teacher portal
- audio, active speaker, handoff, laser/spotlight, media, fullscreen, PBL, quiz, mobile all pass targeted Playwright coverage
