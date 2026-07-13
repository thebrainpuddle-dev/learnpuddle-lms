# OpenMAIC Replacement Runbook

> Output quality is governed by `docs/OPENMAIC_OUTPUT_PARITY_RUNBOOK.md`. This architecture
> runbook is not, by itself, evidence that the fork produces OpenMAIC-level classrooms.

## Decision

LearnPuddle uses the complete OpenMAIC product behind a narrow SaaS integration boundary. The
fork preserves upstream prompts, orchestration, scene generation, rendering, playback, media,
voice, interaction, and PBL. LearnPuddle supplies tenant identity, authorization, encrypted
platform-managed credentials, classroom relationships, private storage, durable jobs, usage,
quota, billing, audit, and operations.

This is a managed AI product, not BYOK. A school pays LearnPuddle for its AI Classroom allowance.
LearnPuddle provisions the approved provider projects and credentials, pays the providers, meters
actual consumption, and enforces the school's subscription. School admins can see service
readiness and usage, but cannot add, rotate, remove, or view provider credentials or alter the
certified OpenMAIC model profile.

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
- Per-tenant, per-modality encrypted, LearnPuddle-managed provider credentials with model
  allowlists and explicit operator-controlled rotation/removal.
- Tenant-derived provider resolution inside the worker; credentials are never placed in BullMQ.
- Atomic classroom, job, and quota reservation creation with idempotency keys.
- BullMQ worker with one attempt, durable Django status, explicit failure, and stale-job recovery.
- Canonical OpenMAIC artifacts and content-addressed media under tenant/classroom Spaces prefixes.
- Immutable usage events, duplicate rejection, plan entitlements, and quota consume/release.
- LearnPuddle portal routing to the full OpenMAIC UI for opted-in tenants.
- Separate `openmaic-web` and `openmaic-worker` production services using one immutable image.
- School-admin UI for read-only managed-service readiness and usage, plus a reversible,
  audit-logged runtime switch controlled by LearnPuddle operations.

## Product Fidelity Contract

OpenMAIC is the classroom product surface. LearnPuddle must not substitute its own wizard, player,
renderer, slide components, asset loader, voice resolver, media pipeline, interaction engine, or
PBL interface when `openmaic_fork` is active. The portal performs a full-page launch into the
pinned OpenMAIC application. Branding is limited to launch context and a return-to-school link;
it must not modify classroom layout or generation behavior.

The exact certified provider profile covers every OpenMAIC-controlled setting: stage models,
thinking mode, prompts, image/video options, voice model and voice IDs, language, speed, media
toggles, scene settings, and interaction/PBL configuration. A release with a different effective
setting is a different quality baseline and cannot inherit the previous parity result.

## Managed Provider Billing

- Use a separate provider project/subaccount per school when the provider supports it. Otherwise,
  issue a distinct per-tenant key with tenant-specific rate and spend controls. Never use one
  unrestricted global production key for all schools.
- Provider secrets are entered only by LearnPuddle operations through the restricted provisioning
  workflow. They are encrypted at rest and fetched by the worker at execution time.
- The school subscription includes explicit classroom, concurrency, storage, and high-cost media
  allowances. LearnPuddle usage events reconcile against provider invoices.
- Reserve allowance before queueing, consume it only after success, and release it after failure.
  Uncertain provider calls are never silently replayed because that can double-charge LearnPuddle.
- Pricing must include measured LLM, image, video, TTS, storage, egress, worker, support, tax, and
  payment-processing costs plus operating margin. Provider commercial terms must permit the
  managed service before production sale.

## Pilot Activation

Before activation, verify the fork image digest, service secret, S3 storage, LearnPuddle-managed
provider credentials, quota, DNS/TLS for `classroom.learnpuddle.com`, and all release gates below.

Provisioning reads the secret from an operator-controlled environment variable so it never appears
in shell history or a process argument:

```bash
docker compose -f docker-compose.prod.yml exec -T \
  -e LP_PROVIDER_KEY web \
  python manage.py provision_openmaic_provider \
  --tenant demo --modality llm --provider openai \
  --models openai:gpt-4o-mini --api-key-env LP_PROVIDER_KEY --confirm
```

Provision and verify every modality in the certified reference profile before runtime activation.
The provisioning command deliberately marks changed credentials unverified.

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
2. Add real provider verification, provider-invoice reconciliation, and production egress pinning
   or an equivalent network policy. Runtime URL checks are present, but DNS rebinding must be
   closed before any operator-configured custom endpoint is allowed in the pilot.
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
