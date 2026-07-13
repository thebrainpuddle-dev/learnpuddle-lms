# OpenMAIC Replacement Runbook

## Decision

LearnPuddle uses the complete OpenMAIC product behind a narrow SaaS integration boundary. The
fork preserves upstream prompts, orchestration, scene generation, rendering, playback, media,
voice, interaction, and PBL. LearnPuddle supplies tenant identity, authorization, encrypted
school credentials, classroom relationships, private storage, durable jobs, usage, quota,
billing, audit, and operations.

Pinned upstream baseline:
`153195ca73e03e68893eace9823d0f7181772a87`.

The fork release must be built from `thebrainpuddle-dev/OpenMAIC` as
`ghcr.io/thebrainpuddle-dev/openmaic-learnpuddle:<upstream-sha>-lp.<release>` and Compose must pin
the resulting digest. Floating tags and deployment-time clones are rejected by
`scripts/pre-deploy-check.sh`.

## Implemented Foundation

- One-time, Redis-backed, 60-second launch codes and HttpOnly OpenMAIC sessions.
- HMAC-authenticated private integration API with timestamp and replay-safe nonce checks.
- Tenant runtime context loaded server-to-server; browser tenant/role headers are ignored.
- Per-tenant, per-modality encrypted provider credentials with model allowlists and explicit
  secret rotation/removal.
- Tenant-derived provider resolution inside the worker; credentials are never placed in BullMQ.
- Atomic classroom, job, and quota reservation creation with idempotency keys.
- BullMQ worker with one attempt, durable Django status, explicit failure, and stale-job recovery.
- Canonical OpenMAIC artifacts and content-addressed media under tenant/classroom Spaces prefixes.
- Immutable usage events, duplicate rejection, plan entitlements, and quota consume/release.
- LearnPuddle portal routing to the full OpenMAIC UI for opted-in tenants.
- Separate `openmaic-web` and `openmaic-worker` production services using one immutable image.
- Admin UI for normalized provider credentials and a reversible, audit-logged runtime switch.

## Pilot Activation

Before activation, verify the fork image digest, service secret, S3 storage, provider credentials,
quota, DNS/TLS for `classroom.learnpuddle.com`, and all release gates below.

Preview without changing data:

```bash
docker compose -f docker-compose.prod.yml exec -T web \
  python manage.py set_openmaic_runtime --tenant demo --runtime openmaic_fork
```

Activate one tenant:

```bash
docker compose -f docker-compose.prod.yml exec -T web \
  python manage.py set_openmaic_runtime \
  --tenant demo --runtime openmaic_fork --student-generation disabled --confirm
```

Rollback during the seven-day observation window:

```bash
docker compose -f docker-compose.prod.yml exec -T web \
  python manage.py set_openmaic_runtime \
  --tenant demo --runtime legacy --student-generation disabled --confirm
```

Runtime changes create `AI_CLASSROOM_RUNTIME_SWITCH` audit records. Do not activate a tenant by
editing `tenant_ai_runtime_configs` directly.

## Required Follow-up PRs

This foundation is not authorization to remove legacy MAIC yet. The remaining sequence is:

1. Publish the organization fork and immutable image; record the image digest and license evidence.
2. Add provider verification and production egress pinning or an equivalent network policy for
   school-configured custom base URLs. Runtime URL checks are present, but DNS rebinding must be
   closed before custom endpoints are allowed in the pilot.
3. Add OpenMAIC-native publish, course, and section assignment controls to the full-screen UI.
4. Build the legacy artifact migration through the pinned OpenMAIC importer/schema validator.
   Preserve IDs, creator, course, sections, visibility, and compatible media; archive failures.
5. Run production-real two-tenant, provider-rotation, worker-termination, storage, usage, PBL,
   audio, load, and ten-classroom parity certification. No fake provider, audio, network, or WS
   path may satisfy these gates.
6. Pilot demo, one real school, then ten schools. Keep legacy classrooms read-only for seven days.
7. Remove the runtime flag and delete the legacy Django MAIC, MAIC PBL, Celery, React player,
   wizard, duplicated renderers, and implementation-specific tests only after the rollback window.

## Release Blockers

- The organization fork must exist and its image workflow must publish successfully.
- Docker image and Nginx runtime validation must run on a host with Docker available.
- Live provider certification and the initial 100-viewer/10-generation load target must pass.
- Custom-provider egress must be resistant to DNS rebinding, not merely URL-validated.
- Migration dry-run must account for every legacy classroom and retain original artifacts.

Health output must expose the pinned upstream SHA, fork release, and integration schema. A green
unit suite alone is not a production cutover signal.
