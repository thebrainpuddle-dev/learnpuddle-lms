# LearnPuddle LMS — Brain

Multi-tenant SaaS LMS for teacher professional development. Schools (tenants) get a subdomain (`{school}.learnpuddle.com`) with isolated data, branding, and users on a shared Django + React + Postgres stack.

## Sources of truth — read these before guessing

| Doc | Use it for |
|---|---|
| `ARCHITECTURE.md` (root) | Authoritative architecture, data flow diagrams, video pipeline, API map |
| `README.md` (root) | Quick local-dev recipe, CI/CD secrets, deploy fallback commands |
| `.claude/CLAUDE.md` | Older dev guide — **partially stale** (says Django 4.2/React 18; reality is 5.2/19). Trust ARCHITECTURE.md when they conflict |
| `docs/DEPLOY_FROM_SCRATCH.md`, `docs/MIGRATION_TO_PRODUCTION.md`, `docs/DIGITAL_OCEAN_ARCHITECTURE.md` | Prod deploy and DO Spaces layout |
| `DO_SPACES_STRUCTURE.md` | Object storage key layout (tenant-prefixed) |
| `_coordination/` | Active multi-agent task board (`_BACKLOG.md`, `tasks/`, `reviews/`, `inbox/`) |

## Stack (current as of clone)

- **Backend:** Django 5.2 + DRF, Gunicorn (`web`), Daphne/Channels (`asgi`), Celery 5.3 + beat, Postgres 15, Redis 7, ffmpeg, faster-whisper, edge-tts/kokoro, Stripe, pgvector
- **Frontend:** React 19 + TypeScript, Vite 6, TailwindCSS 3, Zustand 5, TanStack Query 5, react-router 6, hls.js, TipTap, recharts, @xyflow, Sentry, Playwright + Vitest
- **Infra:** Docker Compose (12 services prod), Nginx wildcard SSL, GitHub Actions CI

## Repo layout (one line each)

```
backend/         Django API; see backend/apps/ for the 24 domain apps
frontend/        Vite + React SPA (admin, super-admin, teacher portals)
e2e/             Playwright suites (also at frontend/e2e and backend/tests/e2e)
nginx/           Prod + staging nginx confs, includes/, proxy_params
openmaic/        Sidecar service Dockerfile (separate from web)
projects/        Sub-project artifacts
scripts/         Ops scripts: backup-db, deploy-droplet, check-origin-health, restart-celery-worker, restore-db, pre-deploy-check
docs/            Deployment + DigitalOcean + Cloudflare runbooks; review notes
.claude/         Agent coordination + (stale) dev guide; settings.local.json
_coordination/   Active task board for the multi-agent workflow
```

## Backend apps (`backend/apps/`)

| App | Purpose |
|---|---|
| `tenants` | Tenant model, branding, plans, trial expiry, feature flags |
| `users` | Custom User (email auth), JWT, SAML, Google OAuth, 2FA (TOTP) |
| `courses` | Course → Module → Content tree; video upload + HLS; teacher views |
| `course_generator` | AI course generation from PDF/DOCX/PPTX/YouTube transcripts |
| `progress` | TeacherProgress, Assignment, Quiz, QuizQuestion, submissions |
| `academics` | Higher-level academic structure on top of courses |
| `chatbot` | RAG chatbot (pgvector + tiktoken + PyMuPDF) |
| `semantic_search` | Vector search over course content |
| `discussions` | Threaded discussions |
| `notifications` | In-app bell + WebSocket channel |
| `reminders` | Bulk email/in-app reminders |
| `reports` / `reports_builder` | Analytics; openpyxl Excel export |
| `billing` | Stripe subscriptions |
| `media` | Media handling helpers |
| `uploads` | File-upload endpoints (size + MIME validation) |
| `ops` | Operational/admin endpoints |
| `webhooks` | Inbound webhooks |
| `translations` | i18n strings |
| `integrations_calendar` | Google Calendar + MS (icalendar, msal, google-api) |
| `integrations_chat` | Chat integrations + **SSRF guard** (`ssrf_guard.py` — see urllib3 floor-pin in requirements) |
| `integrations_common` | Shared integration plumbing |

## Frontend layout (`frontend/src/`)

```
App.tsx                 3 protected route groups: super-admin, admin, teacher
config/                 Axios + JWT interceptor, tenant theme (CSS vars)
stores/                 Zustand: authStore, tenantStore
services/               One service per domain (auth, teacher, admin, super-admin, …)
pages/{super-admin,admin,teacher,auth}/    Page components by role
components/{common,layout,teacher}/        Reusable UI; ContentPlayer = HLS + transcript
design-system/          Tokens + primitives
hooks/   lib/   utils/   types/   i18n/
```

## Docker Compose services (prod, 12)

`db, redis, web, asgi, worker, worker-tts, beat, flower, nginx, backend, frontend, (volumes)`

`worker-tts` is a separate Celery worker for text-to-speech (kokoro/edge-tts) — keep CPU-heavy TTS off the main worker queue.

## Run locally (the short version)

```bash
# DB + Redis + everything
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py create_demo_tenant

# URLs: api → :8000  |  frontend → :3000  |  flower → :5555
# Local tenant subdomain: use demo.localhost:8000 (or X-Tenant-Subdomain: demo)
```

Demo creds come from env: `DEMO_TENANT_ADMIN_EMAIL`, `DEMO_TENANT_ADMIN_PASSWORD`.

Bare-metal recipe (no Docker): see README.md "Backend Setup" / "Frontend Setup".

## Tests

```bash
# Backend (pytest, configured via backend/pyproject.toml — DJANGO_SETTINGS_MODULE=config.settings)
cd backend && pytest                    # all
pytest apps/courses/                    # one app
./run_suite_a.sh / ./run_suite_b.sh     # split suites used in CI

# Frontend
cd frontend && npm test                 # vitest
npm run e2e                             # playwright (config: playwright.config.cjs)
```

CI runs both; deploy on push to `develop` (staging) and `main` (prod). Workflows: `.github/workflows/{ci,e2e}.yml`.

## Hard rule — production-real only (no mocks, no fakes, no synthetic shortcuts)

**This is a SaaS product, not a vibe-coded prototype.** Tests, demos, and dev probes must exercise the real production code path end-to-end. Specifically:

1. **No mocks of internal libraries** in `setupTests.ts` or anywhere else. If `lowlight`, `katex`, `recharts`, or any production dep doesn't run cleanly in jsdom/happy-dom, **find a way to make it run for real** (un-mock it, run the test in Playwright/real browser, or skip the test entirely with a TODO pointing to the e2e that covers it). Do **NOT** mock the dep just to make a unit test pass.
2. **No synthetic data shortcuts.** When a feature plays audio, sync agent state with audio, generate lessons via real LangGraph + edge_tts, etc. — the test must drive the real pipeline. Hand-crafting fixtures is fine for *input* (e.g., a hand-built scene), but the *processing* must be production code.
3. **No fake timers, fake delays, fake network.** If a test needs to wait 2 s for `wb_open`, the test waits 2 s (or runs as an e2e where waiting is acceptable). Don't inject a `delay: () => Promise.resolve()` to "skip" production timing — that hides bugs.
4. **No fake audio.** Audio is part of the product. Tests that touch audio playback run in Playwright with real Chromium.
5. **No fake WebSockets.** WS tests run against a real `daphne` + real LangGraph + real `edge_tts`. Phase 1's live-smoke at the close of the phase is the model: real backend, real WS, real audio, in a real browser.
6. **Test doubles are allowed only for I/O at the system boundary that can't physically run** in the test environment (e.g., a third-party HTTP service that's not deployed in dev). Even then, prefer recording a real response and replaying it (VCR-style) over hand-rolling a stub.
7. **Demos = real product.** The `/dev/maic-v2` probe page and any demo route must drive the real LangGraph + real edge_tts + real audio. Static demos are acceptable ONLY as a real-browser regression smoke (real renderers + hand-crafted state), not as a substitute for the live playback flow.

If a test can't run real, it doesn't ship in unit-test form — it becomes a Playwright e2e or a documented manual-QA step. Accountability matters: the user inspects this and reviews PRs against this rule.

## Conventions you MUST respect

1. **Multi-tenancy is a security boundary.** Models use `TenantManager` which auto-filters via thread-local set in `utils/tenant_middleware.py`. Never call `.objects.all_tenants()` casually — it bypasses isolation.
2. **Decorators in `utils/decorators.py`:** `@admin_only`, `@super_admin_only`, `@tenant_required`, `@teacher_or_admin`, `@check_feature("flag")`. Layer them on every protected view.
3. **Soft delete:** `SoftDeleteMixin` on courses & friends — default queryset hides deleted; use `.with_deleted()` to include.
4. **Audit log:** mutations call `utils/audit.log_audit(...)`. New admin actions should too.
5. **Tenant-prefixed storage keys:** `tenant/{tenant_id}/videos/{content_id}/…` — never write a media path without the tenant prefix.
6. **Frontend auth tokens** live in `sessionStorage` (or `localStorage` if "remember me"). Axios interceptor handles refresh.
7. **JWT custom claims** (`role`, `tenant_id`) are minted in `apps/users/tokens.py`; the frontend trusts them.

## Gotchas / things to know

- **`.claude/CLAUDE.md` is partially stale** — it predates the academics/billing/chatbot/course_generator/integrations_* apps and lists wrong framework versions. Don't quote it as canonical.
- **`urllib3` floor-pinned to 2.x** because `apps/integrations_chat/ssrf_guard.py` subclasses `HTTPSConnection` and wires it through `PoolManager.pool_classes_by_scheme`. A urllib3 v3 bump will silently re-open the SSRF/DNS-rebind hole fixed in BE-SEC-SSRF-OBS2 (2026-04-27 review). Do not unpin without re-auditing.
- **Video upload validates duration ≤ 3600s** before transcoding — fails the Celery chain early if longer.
- **LLM quiz generation has a fallback chain:** OpenRouter → Ollama → deterministic generator (set via `LLM_PROVIDER`).
- **Two compose files for non-prod:** root `docker-compose.staging.yml` and `backend/docker-compose.yml` (DB-only for local dev). Don't confuse them.
- **`ALLOWED_HOSTS` derives from `PLATFORM_DOMAIN`** — that env var is the single source of truth in prod (see `.env.production.example`).
- **`pyproject.toml` test paths:** `["tests", "apps"]` — pytest discovers tests inside each app, plus the top-level `tests/` tree.

## Quick refs

- API base: `/api/v1/` (also mirrored at `/api/`); docs at `/api/docs/` (Swagger) and `/api/redoc/` in dev
- Roles: `SUPER_ADMIN` (no tenant), `SCHOOL_ADMIN`, `TEACHER`, `HOD`, `IB_COORDINATOR`
- JWT lifetimes: 15m access / 7d refresh, rotation on
- Flower: `:5555`
- Local symlink: `~/learnpuddle-lms` → `/Volumes/CrucialX9/learnpuddle-lms`
