# OpenMAIC Output Parity Runbook

## Purpose

This runbook is the release contract for replacing LearnPuddle's duplicated MAIC runtime with the
pinned OpenMAIC fork while retaining OpenMAIC-level classroom quality.

It covers generation, scenes, slides, renderers, images, video, voice, audio timing, interaction,
deep-interactive mode, PBL, editing, publishing, and playback. It does not permit a release merely
because the application starts or its unit tests pass.

The pinned reference is:

- Repository: `https://github.com/THU-MAIC/OpenMAIC`
- Commit: `153195ca73e03e68893eace9823d0f7181772a87`
- License SHA-256: `ba252563743227138231604c9138dd400faca5a10c3cf206b466e5466c565a19`
- LearnPuddle fork integration commit: `fbcf7efeca871221e82e2a229eebd5f805863638`

The architecture and rollout procedure remain in `docs/OPENMAIC_REPLACEMENT.md`. Both documents
are required for release approval.

## Current Status

| Area | Status |
|---|---|
| LearnPuddle SaaS integration foundation | Implemented in draft PR #48 |
| LearnPuddle implementation CI | Green on draft PR #48; every new head must pass again |
| Local OpenMAIC adapter fork | Implemented at `fbcf7efeca871221e82e2a229eebd5f805863638` |
| Organization fork and immutable GHCR image | Blocked until an organization owner creates or grants access to `thebrainpuddle-dev/OpenMAIC` |
| Live reference/candidate benchmark certification | Not yet run |
| Production load, migration, and rollback rehearsal | Not yet run |
| Authorization to delete legacy MAIC | Not granted |

Therefore, OpenMAIC-level output is the target and this document defines how it is proven. It is
not yet a certified production property of the current draft release.

## What "OpenMAIC-Level Output" Means

OpenMAIC-level output does not mean byte-for-byte identical JSON, identical wording, or identical
images. LLM, image, video, and TTS providers can be stochastic and may change behavior behind
unversioned model aliases.

Parity means all of the following:

1. The same pinned OpenMAIC prompts, agents, orchestration, scene builders, action builders,
   renderers, media adapters, TTS pipeline, interaction logic, and PBL runtime execute.
2. The reference and candidate use the same provider account, endpoint, model ID, model revision
   where available, thinking mode, generation options, language, media settings, and input.
3. LearnPuddle adapters change identity, credentials, persistence, queueing, usage, and billing
   only. They do not rewrite educational content or substitute a second generation pipeline.
4. Every candidate classroom is schema-valid, fully renderable, playable, audible when TTS is
   enabled, interactive, durable, tenant-isolated, and no worse than the reference under the
   acceptance thresholds below.
5. A provider failure fails visibly. The runtime must not silently switch provider, model, prompt,
   deterministic generator, local TTS, or placeholder media to make a run appear successful.

## Non-Negotiable Runtime Invariants

### Protected OpenMAIC product surface

The following behavior is upstream-owned:

- Classroom and agent profile generation
- Scene outlines, scene content, scene actions, and action validation
- Prompt text and prompt assembly
- Slide and element schemas
- Stage renderers and playback state machine
- OpenMAIC application shell, editor, player controls, styles, fonts, transitions, and responsive
  behavior
- Image and video request construction
- TTS text splitting, synthesis, voice mapping, and action/audio association
- Chat, interaction, deep-interactive mode, quiz behavior, and PBL
- OpenMAIC editing and export behavior

Changes outside `lib/integrations/learnpuddle/` are allowed only when they replace an I/O boundary
with an adapter call while preserving the original input and output shape. Any prompt, agent,
generation, renderer, timing, or media-policy change requires a separate product-quality review and
a new parity baseline.

### LearnPuddle-owned surface

LearnPuddle may own only:

- Tenant, user, role, entitlement, and launch context
- Encrypted LearnPuddle-managed provider credential lookup
- Provider/model allowlists
- Durable queueing and job status
- Canonical classroom and media persistence
- Course, section, assignment, visibility, and progress relationships
- Usage, quota, billing, audit, metrics, and incident handling
- Tenant branding and the return link

School users do not configure providers. LearnPuddle operations provisions the exact certified
profile and the school-admin surface exposes readiness and usage only.

### No hidden fallback

For `DEPLOYMENT_MODE=learnpuddle`:

- Leave `MODEL_ROUTES` unset for the first pilot unless the vanilla reference uses the exact same
  route map. A process-wide route can otherwise override a teacher's OpenMAIC model selection.
- Do not set a process-wide `DEFAULT_MODEL` that differs from the school default.
- Require an explicit LLM allowlist and default model for each pilot school.
- Record the effective provider and model for every generation stage in job evidence and usage.
- Treat missing provider configuration, an unsupported model, and media/TTS failure as errors.
- Do not fall back from paid image/video/TTS generation to placeholders or browser-native output.

### Provider selection rule for the first pilot

Until contract tests prove that every modality selects `is_default` rather than array order, enable
exactly one verified provider for each enabled modality per tenant:

- One LLM provider, with one pinned default model and only approved alternate models
- One TTS provider and approved voice/model configuration
- One image provider when image generation is enabled
- One video provider when video generation is enabled
- One ASR, PDF, and web-search provider when those capabilities are enabled

Multiple credentials may be stored for rotation, but only one provider per modality is enabled at
generation time during the initial pilot. Key rotation does not change the provider/model profile.

## Release Identity

Every candidate release must produce an immutable identity record containing:

```json
{
  "upstream_sha": "153195ca73e03e68893eace9823d0f7181772a87",
  "fork_sha": "REPLACE_WITH_FORK_COMMIT",
  "fork_release": "153195ca73e03e68893eace9823d0f7181772a87-lp.N",
  "image": "ghcr.io/thebrainpuddle-dev/openmaic-learnpuddle:TAG@sha256:DIGEST",
  "integration_schema": "1",
  "license_sha256": "ba252563743227138231604c9138dd400faca5a10c3cf206b466e5466c565a19",
  "provider_profile_id": "REFERENCE_PROFILE_VERSION",
  "benchmark_manifest_sha256": "REPLACE_WITH_SHA256"
}
```

The image digest, not a mutable tag, is deployed. The web and worker services must run the same
digest. `/api/health` must report the upstream SHA, fork release, and integration schema expected by
the release record.

## Phase 1: Publish the Fork

An owner of `thebrainpuddle-dev` must create or grant access to
`thebrainpuddle-dev/OpenMAIC`. The active implementation commit currently exists only in the local
fork worktree.

After the organization repository exists:

```bash
cd /Volumes/CrucialX9/OpenMAIC-learnpuddle
git remote add origin https://github.com/thebrainpuddle-dev/OpenMAIC.git
git push -u origin learnpuddle
git tag lp-v1
git push origin lp-v1
```

The `LearnPuddle immutable image` workflow must:

1. Verify the pinned upstream SHA is an ancestor.
2. Verify the license digest.
3. Install with the frozen lockfile.
4. Pass TypeScript and the unchanged upstream test suite.
5. Build one image used by both web and worker.
6. Publish the immutable tag and record its digest.

Do not deploy an image built locally, cloned from floating `main`, or lacking release evidence.

## Phase 2: Define the Reference Provider Profile

The first certified profile is committed at
`backend/apps/ai_classroom/reference_profiles/openmaic-153195ca-default-v1.json`. Its canonical
SHA-256 is `cb99093bf90d58ac2b8ecb7bd1f4f38446e28e6dfa50ee7e8df3802e514b850e`.
It is configuration, never a credential dump. Store secret values only in the appropriate provider
stores.

The profile pins OpenAI `gpt-5.5` with medium thinking, Seedream
`doubao-seedream-5-0-260128`, Seedance `doubao-seedance-2-0-260128`, OpenAI TTS
`gpt-4o-mini-tts` with voice `alloy` at speed `1.0`, OpenAI ASR
`gpt-4o-mini-transcribe`, `unpdf`, Tavily, no model routes, and serial scene generation. The
OpenMAIC adapter applies these settings after browser-state rehydration, so stale local settings
cannot change the certified baseline.

Media requests retain the upstream scene intelligence. A missing image aspect ratio defaults to
`16:9`, and Seedream scales the scene-derived dimensions to its minimum accepted pixel count. A
missing Seedance option normalizes through OpenMAIC's native provider table to `5s`, `16:9`, and
`480p`. These values are release-profile assertions, not replacement media logic.

The profile records:

- LLM provider, exact model ID, base endpoint identity, and thinking configuration
- Any per-stage model routes; normally none for the first pilot
- Image provider, exact model, size/aspect/quality options
- Video provider, exact model, duration/resolution/aspect options
- TTS provider, exact model, voice IDs, language, speed, and provider defaults
- ASR, PDF extraction, and web-search provider choices
- OpenMAIC UI generation settings, including media toggles and classroom language
- Provider account region or project when it can affect model availability
- Date and time of provider verification

Use versioned model IDs where providers expose them. If only a moving alias exists, record the
alias and certification date and schedule weekly drift certification.

The reference and candidate must use the same provider account and profile. Using two different
API keys is acceptable only when both keys resolve to the same provider project, region, model,
quota tier, and endpoint behavior.

## Phase 3: Configure a Pilot School

1. Confirm the tenant subscription is active and AI Classroom is entitled.
2. Have LearnPuddle operations apply the atomic reference profile. It provisions distinct encrypted
   tenant credentials for every required modality and disables non-profile providers. The school
   admin must never receive or submit provider secrets.
3. Set the exact provider IDs and model allowlists from the reference profile.
4. Set one enabled/default provider per modality for the first pilot.
5. Verify each provider with a real request. Do not mark a key verified from string shape alone.
6. Confirm custom endpoints pass URL validation and DNS-rebind-safe egress policy.
7. Confirm image, video, and TTS modalities are included in the school's entitlements.
8. Confirm quota and storage reservations can be created and released.
9. Keep the tenant runtime on `legacy` until the parity report is approved.

Apply the complete profile in one transaction:

```bash
read -rsp 'OpenAI key: ' LP_OPENMAIC_OPENAI_API_KEY; echo
read -rsp 'Volcengine key: ' LP_OPENMAIC_VOLCENGINE_API_KEY; echo
read -rsp 'Tavily key: ' LP_OPENMAIC_TAVILY_API_KEY; echo
export LP_OPENMAIC_OPENAI_API_KEY LP_OPENMAIC_VOLCENGINE_API_KEY LP_OPENMAIC_TAVILY_API_KEY
docker compose -f docker-compose.prod.yml exec -T \
  -e LP_OPENMAIC_OPENAI_API_KEY \
  -e LP_OPENMAIC_VOLCENGINE_API_KEY \
  -e LP_OPENMAIC_TAVILY_API_KEY \
  web python manage.py apply_openmaic_reference_profile \
  --tenant demo --profile openmaic-153195ca-default-v1 --confirm
unset LP_OPENMAIC_OPENAI_API_KEY LP_OPENMAIC_VOLCENGINE_API_KEY LP_OPENMAIC_TAVILY_API_KEY
```

The runtime switch refuses `openmaic_fork` activation until the tenant fingerprint, provider set,
model allowlists, provider options, defaults, and encrypted secrets match this manifest.
The certified profile uses OpenMAIC's built-in provider endpoints; custom base URLs are not allowed
for this baseline. Generic provider edits clear the certification fingerprint. Rotate managed keys
through `apply_openmaic_reference_profile` so unchanged secrets are retained and the full profile is
revalidated atomically.

Blank credential updates retain the existing secret. Removal must be explicit. A worker job carries
only tenant/config IDs and fetches credentials at execution time.

The school pays LearnPuddle, and LearnPuddle pays the providers. Before activation, confirm the
tenant plan allowance, provider-side project/spend limit, overage policy, and invoice-reconciliation
mapping. Provider account ownership must not change the certified model or generation profile.

## Phase 4: Build the Benchmark Corpus

Keep fixed, redistributable input fixtures and a versioned manifest. The corpus must exercise more
than a simple topic-to-slides path.

| ID | Classroom | Required coverage |
|---|---|---|
| `stem-photosynthesis` | Grade 6 photosynthesis | Diagrams, causal sequence, image, narration |
| `stem-newton-laws` | Grade 9 Newton's laws | Equations, examples, misconception handling |
| `math-quadratics` | Grade 10 quadratic equations | Math rendering, worked steps, quiz |
| `humanities-french-revolution` | Grade 8 French Revolution | Timeline, multiple viewpoints, source caution |
| `language-spanish-greetings` | Grade 5 Spanish greetings | Multilingual text, pronunciation, dialogue |
| `cs-data-types` | Grade 8 programming data types | Code blocks, comparisons, interactive check |
| `primary-water-cycle` | Grade 4 water cycle | Age fit, visual sequence, concise narration |
| `ela-persuasive-writing` | Grade 7 persuasive writing | Rubric, examples, student practice |
| `document-grounded` | Fixed PDF with text and images | Extraction, grounding, source-image handling |
| `pbl-sustainable-school` | Sustainable-school PBL | Agents, issue board, chat, evaluation, state |

Each manifest entry includes the exact topic, grade, subject, board/standard, class guide, language,
source-document checksum, selected agents, enabled modalities, model settings, and expected product
features. Input fixtures may be hand-authored; processing must use the real production pipeline.

## Phase 5: Generate Reference and Candidate Classrooms

For every benchmark entry:

1. Start vanilla OpenMAIC at the pinned upstream commit.
2. Start the LearnPuddle candidate image with the same upstream base.
3. Apply the same provider profile and teacher-visible settings.
4. Generate three independent vanilla runs and three independent candidate runs. Three runs reduce
   the chance that a single stochastic result hides a regression.
5. Do not copy a generated artifact from one system to the other.
6. Preserve raw provider request metadata without secrets, usage, timing, logs, final artifact,
   media checksums, screenshots, audio, and evaluator scores.
7. Record every effective provider/model selection. Any unexpected selection invalidates the run.
8. Re-run both sides if a provider incident, rate limit, or model outage affected either side.

Reference and candidate runs should be interleaved in time to reduce provider drift:

```text
reference-1, candidate-1, reference-2, candidate-2, reference-3, candidate-3
```

Do not compare a fresh candidate with a reference generated weeks earlier from a moving model.

## Phase 6: Automated Artifact and Playback Validation

Every candidate run must satisfy all of these conditions:

### Classroom structure

- Artifact passes the pinned OpenMAIC schema validator.
- At least one valid scene exists and no scene is empty.
- Scene, slide, element, agent, and action IDs are unique and resolvable.
- Candidate scene count is within 20 percent of the reference median unless the teacher requested
  a fixed count or a reviewer approves a pedagogically justified difference.
- Text contains no provider error, JSON fragment, prompt leakage, placeholder, or unresolved media
  token.
- Quiz answer keys and explanations do not leak into student-facing pre-submit state.

### Media and storage

- Every image, video, audio, poster, and attachment reference resolves.
- Every stored object is under
  `maic/{tenant_id}/classrooms/{classroom_id}/...` and matches its recorded SHA-256.
- Artifacts contain stable media IDs/URLs, never expiring presigned URLs.
- Generated images and videos are non-empty, decodable, relevant to the requested scene, and use
  the configured provider/model.
- No remote media URL can bypass the authenticated media gateway.

### Voice and timing

- With TTS enabled, every required speech action has decodable audio.
- Audio duration is positive and playback `currentTime` advances in real Chromium.
- Agent speaking state, subtitles, actions, and scene transitions follow the generated timeline.
- No overlapping narration occurs unless the OpenMAIC artifact explicitly schedules it.
- Voice, language, and pronunciation settings match the reference profile.

### Rendering and interaction

- Load the same canonical artifact in vanilla and LearnPuddle mode, capture desktop and mobile
  screenshots, and compare the OpenMAIC shell, editor, player, stage, controls, typography, spacing,
  transitions, and responsive breakpoints. Only the approved return-to-school control may differ.
- Confirm the browser loads OpenMAIC's renderer/player modules and assets. No legacy LearnPuddle
  MAIC wizard, player, renderer, audio engine, voice resolver, or PBL bundle may execute.
- Desktop and mobile render without blank stages, clipped primary controls, horizontal overflow,
  or uncaught console errors.
- All slide/element types in the artifact render through OpenMAIC's actual renderers.
- Teacher editing, save, reload, export, publish, and assignment preserve the canonical artifact.
- Student playback cannot access editing or teacher-only answers.
- Chat, deep-interactive actions, quizzes, and PBL use the real runtime and persist valid state.

### SaaS boundary

- Cross-tenant classroom, media, job, artifact, and usage IDs return 404 or 403.
- Usage provider/model fields match the effective generation profile.
- Quota is reserved once, consumed once on success, and released on failure.
- Worker termination creates a durable failure without silent provider replay.
- No credential appears in Redis payloads, artifacts, logs, browser responses, or evidence files.

Any failure above blocks the release, regardless of the human quality score.

## Phase 7: Human Quality Review

Use at least two reviewers for each classroom. Reviewers should not know whether a run is reference
or candidate until scoring is complete.

Score each run out of 100:

| Dimension | Points | Review question |
|---|---:|---|
| Correctness and grounding | 20 | Is the content accurate, coherent, and grounded in supplied material? |
| Pedagogy and age fit | 15 | Does sequencing, explanation, and practice fit the learner? |
| Scene and narrative design | 15 | Do scenes form a useful classroom rather than disconnected slides? |
| Visual and media relevance | 15 | Do media improve understanding and match the scene? |
| Voice and action synchronization | 15 | Is narration natural and synchronized with agents/actions? |
| Interaction and assessment | 10 | Are questions, chat, activities, and feedback meaningful? |
| PBL quality where applicable | 10 | Are roles, issues, decisions, and evaluation coherent and usable? |

Acceptance thresholds:

- Every candidate run has no critical correctness, safety, privacy, or playback defect.
- For every benchmark fixture, the candidate median is no more than 3 points below the reference
  median.
- Across the corpus, the candidate median is no more than 2 points below the reference median.
- No individual dimension is more than 1 point below the corresponding reference median after
  normalization to that dimension's scale.
- Review disagreement greater than 10 total points triggers a third blinded reviewer.

The candidate may score better. Do not alter upstream generation merely to optimize the scorecard;
upstream product changes belong in a separately reviewed release.

## Phase 8: Performance and Scale Certification

Quality parity is incomplete if the product times out or loses media under load.

Before the ten-school pilot:

- Run 100 concurrent authenticated viewers against completed classrooms.
- Queue ten real generations across at least two tenants.
- Confirm worker concurrency does not cross tenant/provider context.
- Confirm queue depth, stage duration, provider failures, storage failures, and stale jobs are
  observable.
- Confirm internal LearnPuddle integration API p95 is below 500 ms, excluding provider time.
- Confirm no classroom artifact is marked ready before its canonical manifest and required media
  are durable.
- Confirm provider rate limits produce explicit retryable failures, not partial ready classrooms.

Record CPU, memory, Redis, Postgres, Spaces, worker, and provider measurements with the release
evidence.

## Phase 9: Release Gate

A release may enter the demo tenant only when all boxes are checked:

```text
[ ] Organization fork exists and fork commit is reviewed
[ ] Immutable image digest and release identity recorded
[ ] Upstream tests run unchanged and pass
[ ] Adapter contract and LearnPuddle security tests pass
[ ] Reference provider profile verified with real requests
[ ] Ten fixtures x three reference and three candidate runs completed
[ ] Automated artifact/playback/storage/tenant checks are 100 percent green
[ ] Blinded human quality thresholds pass
[ ] 100-viewer and 10-generation targets pass
[ ] Migration dry-run accounts for every legacy classroom
[ ] Rollback command and legacy read-only path are tested
[ ] Operations dashboard and alerts are active
```

Unit tests, mocked provider tests, a static seeded classroom, or one successful live generation
cannot replace this gate.

## Phase 10: Tenant Cutover

Use the management command; never edit runtime rows directly.

Preview:

```bash
docker compose -f docker-compose.prod.yml exec -T web \
  python manage.py set_openmaic_runtime --tenant demo --runtime openmaic_fork
```

Activate:

```bash
docker compose -f docker-compose.prod.yml exec -T web \
  python manage.py set_openmaic_runtime \
  --tenant demo --runtime openmaic_fork --student-generation disabled --confirm
```

Rollout order:

1. Demo tenant
2. One real school
3. Remaining pilot schools, one cohort at a time
4. Ten-school pilot

For each cohort, verify launch, create, generate, edit, save, publish, assign, teacher playback,
student playback, interaction, PBL, usage, quota, and media before proceeding.

## Seven-Day Observation and Rollback

Keep legacy classrooms read-only and retain original artifacts for seven full days after each
tenant's cutover.

Rollback immediately for:

- Confirmed tenant or credential crossover
- Repeated artifact/media loss
- A provider/model mismatch or silent fallback
- A material quality regression against the certified profile
- Widespread audio/action desynchronization
- Queue behavior that can double-charge providers
- An unbounded security or availability incident

Rollback command:

```bash
docker compose -f docker-compose.prod.yml exec -T web \
  python manage.py set_openmaic_runtime \
  --tenant demo --runtime legacy --student-generation disabled --confirm
```

Do not delete candidate artifacts during incident response. Preserve job IDs, checksums, provider
metadata, usage, logs, and the release identity for diagnosis.

## Legacy Deletion Gate

Delete legacy MAIC only after:

1. Every pilot tenant completed the seven-day window.
2. No unresolved severity-1 or severity-2 parity/security incident remains.
3. All migrated and newly generated classrooms are accounted for.
4. The certified OpenMAIC image remains available by digest.
5. Rollback evidence is archived and product owners approve irreversible deletion.

Deletion happens in reviewed PRs: Django generation/PBL/Celery, then React wizard/player/runtime,
then implementation-specific tests and stale flags. Preserve SaaS integration, metadata,
relationships, provider settings, storage, usage, quotas, billing, audit, and portal links.

## Upstream Upgrade Procedure

Never move the pinned SHA by editing one variable and deploying.

For each upstream upgrade:

1. Create a new fork branch from the current release.
2. Merge or rebase the exact reviewed upstream commit.
3. Review prompt, agent, schema, renderer, media, TTS, interaction, PBL, and dependency diffs.
4. Update the pinned upstream and license evidence.
5. Run the unchanged upstream suite and adapter/security suites.
6. Re-run the complete benchmark and human review against vanilla OpenMAIC at the new commit.
7. Publish a new immutable release and digest.
8. Pilot through demo and one school before broader rollout.

Never compare a new fork commit with the old vanilla baseline and call it parity.

## Required Evidence Per Release

Archive the following without secrets:

- Release identity JSON and image digest
- Fork diff and code review
- Frozen dependency lockfiles and test results
- Provider profile with secret values redacted
- Benchmark manifest and input checksums
- Reference and candidate artifacts and media checksums
- Playwright reports, screenshots, console logs, and audio checks
- Usage and stage-duration records
- Blinded reviewer scorecards and adjudication
- Load-test report
- Migration dry-run and rollback rehearsal
- Final approval and pilot observation report

The release is OpenMAIC-level only when this evidence exists and all gates pass. Architecture alone
does not establish output parity.
