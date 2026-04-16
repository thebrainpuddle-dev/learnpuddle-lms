# MAIC Classroom Fixes + Indian Agent Selection — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch one subagent per Chunk; run Chunks 1+2+3 in parallel, then Chunk 4, then Chunk 5, then Chunk 6.

**Goal:** Fix 3 production bugs in the LearnPuddle MAIC AI Classroom (student Q&A perms, subtitle-before-audio, navigation kills audio) and add a wizard step for LLM-generated Indian agents with Azure en-IN voices and pre-generated playback audio.

**Architecture:** 5 workstreams. WS-A wires role-aware URLs across 4 frontend consumers. WS-B adds agent-profile generation + propagates persona into downstream prompts. WS-C adds a wizard step with generate/edit/preview/regen. WS-D converts publish into a Celery-driven pre-gen pipeline with an idempotent `audioId` hash. WS-E rewrites the frontend speech executor around a `generationToken` that neuters stale callbacks and fires subtitles on the `<audio>` element's `playing` event.

**Tech Stack:** Django 5.0 + DRF + Celery; React 19 + TypeScript + Vite + Zustand; Azure TTS (en-IN neural voices); PostgreSQL 15; pytest + Vitest + Playwright.

**Spec:** `docs/superpowers/specs/2026-04-16-maic-classroom-fixes-design.md`

---

## File Structure

### Created

| Path | Responsibility |
|---|---|
| `backend/apps/courses/maic_voices.py` | Azure en-IN voice roster (data-only module) |
| `backend/apps/courses/prompts/__init__.py` | Package marker for prompt templates |
| `backend/apps/courses/prompts/agent_profiles.md` | System prompt for agent-profile generation |
| `backend/apps/courses/prompts/loader.py` | Small helper to load + cache prompt files |
| `backend/apps/courses/migrations/NNNN_maic_audio_manifest.py` | Data migration: stamp `audioManifest` on existing classrooms |
| `backend/tests/courses/test_maic_permissions.py` | WS-A backend tests |
| `backend/tests/courses/test_maic_agents.py` | WS-B backend tests |
| `backend/tests/courses/test_maic_pregen.py` | WS-D backend tests |
| `frontend/src/lib/maic/endpoints.ts` | Role-aware URL helpers |
| `frontend/src/components/maic/AgentGenerationStep.tsx` | WS-C wizard step shell |
| `frontend/src/components/maic/AgentCard.tsx` | WS-C single agent card |
| `frontend/src/components/maic/AgentEditModal.tsx` | WS-C edit-one-agent modal |
| `frontend/src/components/maic/__tests__/AgentCard.test.tsx` | WS-C Vitest |
| `frontend/src/components/maic/__tests__/AgentGenerationStep.test.tsx` | WS-C Vitest |
| `frontend/src/lib/__tests__/maicActionEngine.test.ts` | WS-E Vitest |
| `frontend/src/lib/__tests__/maicPlaybackEngine.test.ts` | WS-E Vitest |
| `e2e/tests/maic-student-chat.spec.ts` | WS-A Playwright |
| `e2e/tests/maic-agent-wizard.spec.ts` | WS-C Playwright |
| `e2e/tests/maic-playback-navigation.spec.ts` | WS-E Playwright |

### Modified

| Path | What changes |
|---|---|
| `backend/apps/courses/maic_views.py` | implement `teacher_maic_generate_agent_profiles`; add `teacher_maic_regenerate_one_agent`, `teacher_maic_tts_preview`, `teacher_maic_classroom_publish`, `maic_list_voices`; gate student visibility on `audioManifest` |
| `backend/apps/courses/maic_urls.py` | wire new endpoints |
| `backend/apps/courses/maic_generation_service.py` | new `generate_agent_profiles_json`; remove agent generation from `OUTLINE_SYSTEM_PROMPT`; add `agents` input to outline + actions prompts; inject persona into `CHAT_SYSTEM_PROMPT` |
| `backend/apps/courses/maic_tasks.py` | rewrite `pre_generate_classroom_tts` with idempotent hashing, progress manifest, exponential-backoff retries |
| `backend/apps/courses/maic_models.py` | no schema change — `content` JSONField already holds everything; add helper methods |
| `backend/config/urls.py` | mount `/api/v1/maic/voices/` public-ish endpoint |
| `frontend/src/types/maic.ts` | `MAICAgent` adds `voiceId`, `voiceProvider`, `speakingStyle` |
| `frontend/src/types/maic-actions.ts` | `SpeechAction` adds `audioId`, `audioUrl`, `voiceId` |
| `frontend/src/types/maic-scenes.ts` | `MAICContent` adds `audioManifest` |
| `frontend/src/services/openmaicService.ts` | `maicApi.generateAgentProfiles`, `regenerateAgent`, `ttsPreview`, `publishClassroom`, `getClassroomDetail` (with manifest); `maicStudentApi.chat` + `tts` already exist — confirm role-aware |
| `frontend/src/lib/maicActionEngine.ts` | rewrite `executeSpeech`, add `generationToken`, `playAudioSynced`, `readingTimeFallback`; use `this.ttsEndpoint` for configured-provider path |
| `frontend/src/lib/maicPlaybackEngine.ts` | fix checkpoint `-1`; add `seekToSlide` |
| `frontend/src/hooks/usePlaybackEngine.ts` | remove 150ms setTimeout in `loadScene` |
| `frontend/src/components/maic/RoundtablePanel.tsx` | role prop + `maicChatUrl(role)` |
| `frontend/src/components/maic/ChatPanel.tsx` | use helper for consistency |
| `frontend/src/components/maic/PBLRenderer.tsx` | role prop + helper |
| `frontend/src/components/maic/SlideNavigator.tsx` | wire `seekToSlide` on thumbnail click |
| `frontend/src/lib/orchestration/director.ts` | role in constructor; pass to `streamMAIC` |
| `frontend/src/pages/teacher/MAICCreatePage.tsx` | insert `AgentGenerationStep` between Topic and Outline |
| `frontend/src/pages/student/StudentMAICCreatePage.tsx` | same |
| `frontend/src/pages/teacher/MAICPlayerPage.tsx` | pass `role="teacher"` into Stage + Panels |
| `frontend/src/pages/student/MAICPlayerPage.tsx` | pass `role="student"` |
| `frontend/src/stores/maicStageStore.ts` | agents reducer shape already present; confirm `setAgents` exists |

### Shared-touchpoint sequencing (authoritative — overrides spec §15 where they disagree)

- **Types first (Chunk 1 opening):** `types/maic.ts`, `types/maic-actions.ts`, `types/maic-scenes.ts` edits land first and are owned by Chunk 1. Chunks 3/4/5 read them.
- **maic_voices.py** is owned by Chunk 2 (Backend-Agents) since Chunk 2 consumes it first; Chunk 4 reads it.
- **maic_generation_service.py** is owned by Chunk 2 (service-layer changes). Chunk 4 only imports from it (`generate_tts_audio`, `generate_agent_profiles_json`, etc.).
- **maic_views.py** and **maic_urls.py** are owned by Chunk 4 (all handlers). Chunk 2 only modifies the service layer and does not touch views. Any outline-view caller updates that depend on Chunk 2's service signature changes move to Chunk 4 Task 4.1.5.
- **maic_models.py** — no edits in this plan. Content is in the JSONField already.

### Pre-investigation results (resolved at plan time)

- Latest migration: `0034_maicclassroom_content`. Chunk 4 Task 4.7 depends on this.
- `generate_tts_audio` signature: `(text: str, config: TenantAIConfig, voice_id: str | None = None) -> bytes | None`. Chunk 4 Task 4.2 uses this signature.
- `DirectorGraph` (not `Director`) class lives in `frontend/src/lib/orchestration/director.ts:29`. Single instantiation site: `frontend/src/hooks/useOrchestration.ts:139`.
- `MAICContent` type does not yet exist in the codebase. Chunk 1 Task 1.4 creates it in `types/maic.ts` (not `types/maic-scenes.ts`).
- `ChatPanel.tsx:189` already destructures `role` from props — no prop threading needed for Task 1.6.
- Courses URL router: `backend/apps/courses/urls.py` (used directly from `backend/config/urls.py:24`). Public voices endpoint mounts there.

---

## Chunk 1: WS-A Permission Fixes + Shared Type Additions

**Owner subagent:** `Frontend-Bugs+Engine` (continues in Chunk 5)
**Est:** 0.6d
**Depends on:** nothing — start first.

### Task 1.1: Create role-aware URL helpers

**Files:** Create `frontend/src/lib/maic/endpoints.ts`

- [ ] **Step 1: Create the file**

```ts
// frontend/src/lib/maic/endpoints.ts
export type MAICRole = 'teacher' | 'student';

export function maicChatUrl(role: MAICRole): string {
  return `/api/v1/${role}/maic/chat/`;
}

export function maicTtsUrl(role: MAICRole): string {
  return `/api/v1/${role}/maic/generate/tts/`;
}

export function maicSceneActionsUrl(role: MAICRole): string {
  return `/api/v1/${role}/maic/generate/scene-actions/`;
}

export function maicQuizGradeUrl(role: MAICRole): string {
  return `/api/v1/${role}/maic/quiz-grade/`;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/maic/endpoints.ts
git commit -m "feat(maic): role-aware URL helpers"
```

### Task 1.2: Extend MAICAgent type

**Files:** Modify `frontend/src/types/maic.ts`

- [ ] **Step 1: Open the file and find the MAICAgent interface**

- [ ] **Step 2: Add three fields**

```ts
export interface MAICAgent {
  id: string;
  name: string;
  role: 'professor' | 'teaching_assistant' | 'student' | 'moderator';
  avatar: string;
  color: string;
  personality: string;
  expertise: string;
  // NEW:
  voiceId: string;                     // e.g. "en-IN-PrabhatNeural"
  voiceProvider: 'azure';              // future-proofing
  speakingStyle: string;               // 1-2 sentences, e.g. "warm, occasionally says 'theek hai?'"
  // Backward compat: legacy `voice` field alias — read-only, populated from voiceId on load.
  voice?: string;
}
```

- [ ] **Step 3: Grep for any `role === 'student_rep'` usages**

Run: `grep -rn "student_rep" frontend/src/`
Expected: if any hits, update them to `'student'`. If none, skip.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/maic.ts
git commit -m "feat(maic): MAICAgent voiceId/voiceProvider/speakingStyle"
```

### Task 1.3: Extend SpeechAction type

**Files:** Modify `frontend/src/types/maic-actions.ts`

- [ ] **Step 1: Find the SpeechAction interface**

- [ ] **Step 2: Add three optional fields**

```ts
export interface SpeechAction {
  type: 'speech';
  agentId: string;
  text: string;
  ssml?: string;
  // NEW — stamped at publish time by pre-gen pipeline:
  audioId?: string;
  audioUrl?: string;
  voiceId?: string;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/maic-actions.ts
git commit -m "feat(maic): SpeechAction audioId/audioUrl/voiceId"
```

### Task 1.4: Extend MAICContent with audioManifest

**Files:** Modify `frontend/src/types/maic-scenes.ts`

- [ ] **Step 1: Add AudioManifest interface** (in `types/maic-scenes.ts`)

```ts
export type AudioManifestStatus = 'idle' | 'generating' | 'ready' | 'partial' | 'failed';

export interface AudioManifest {
  status: AudioManifestStatus;
  progress: number;             // 0-100
  totalActions: number;
  completedActions: number;
  failedAudioIds: string[];
  generatedAt: string | null;   // ISO
}
```

- [ ] **Step 2: Create MAICContent in `types/maic.ts`**

Pre-verified: `MAICContent` does not exist anywhere in the codebase (confirmed via grep). Add it to `types/maic.ts` (the main types module):

```ts
import type { MAICScene } from './maic-scenes';
import type { AudioManifest } from './maic-scenes';

export interface MAICContent {
  agents: MAICAgent[];
  scenes: MAICScene[];
  audioManifest?: AudioManifest;  // Optional until WS-D migration lands.
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/maic-scenes.ts frontend/src/types/maic.ts
git commit -m "feat(maic): AudioManifest + MAICContent type"
```

### Task 1.5: Fix RoundtablePanel chat URL

**Files:** Modify `frontend/src/components/maic/RoundtablePanel.tsx:305`

- [ ] **Step 1: Add `role` to the component's props interface**

Find the props interface and add:
```ts
role?: MAICRole;   // defaults to 'teacher' for backward compat
```

- [ ] **Step 2: Import helper**

At top of file:
```ts
import { maicChatUrl, type MAICRole } from '../../lib/maic/endpoints';
```

- [ ] **Step 3: Replace the hardcoded URL**

Change line 305 from:
```ts
url: '/api/v1/teacher/maic/chat/',
```
to:
```ts
url: maicChatUrl(role ?? 'teacher'),
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/maic/RoundtablePanel.tsx
git commit -m "fix(maic): RoundtablePanel uses role-aware chat URL"
```

### Task 1.6: Fix ChatPanel (and consolidate with helper)

**Files:** Modify `frontend/src/components/maic/ChatPanel.tsx:189-191`

Pre-verified: `role` is already destructured from props at line 189 (`const endpoint = role === 'teacher' ? ... : ...`). No prop threading needed.

- [ ] **Step 1: Import helper at the top of the file**

```ts
import { maicChatUrl } from '../../lib/maic/endpoints';
```

- [ ] **Step 2: Replace the existing ternary at line 189-191**

Current:
```ts
const endpoint = role === 'teacher'
  ? '/api/v1/teacher/maic/chat/'
  : '/api/v1/student/maic/chat/';
```
Replace with:
```ts
const endpoint = maicChatUrl(role);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/maic/ChatPanel.tsx
git commit -m "refactor(maic): ChatPanel uses maicChatUrl helper"
```

### Task 1.7: Fix PBLRenderer chat URL

**Files:** Modify `frontend/src/components/maic/PBLRenderer.tsx:189`

- [ ] **Step 1: Add role prop + import helper**

Same pattern as Task 1.5.

- [ ] **Step 2: Replace the hardcoded URL**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/maic/PBLRenderer.tsx
git commit -m "fix(maic): PBLRenderer uses role-aware chat URL"
```

### Task 1.8: Fix DirectorGraph chat URL

**Files:** Modify `frontend/src/lib/orchestration/director.ts:237`, `frontend/src/hooks/useOrchestration.ts:139`

Pre-verified: the class is `DirectorGraph` (not `Director`). Single instantiation site: `useOrchestration.ts:139`.

- [ ] **Step 1: Add `role: MAICRole` to DirectorGraph constructor config interface**

In `director.ts`, find the config interface (near the class definition) and add:
```ts
import { maicChatUrl, type MAICRole } from '../maic/endpoints';

interface DirectorGraphConfig {
  // ... existing fields
  role: MAICRole;
}
```

- [ ] **Step 2: Store as `this.role` in the constructor**

```ts
private role: MAICRole;
constructor(agents: ..., callbacks: ..., config: DirectorGraphConfig) {
  // ... existing
  this.role = config.role;
}
```

- [ ] **Step 3: Replace hardcoded URL at line 237**

Change:
```ts
url: '/v1/teacher/maic/chat/',
```
to:
```ts
url: maicChatUrl(this.role).replace(/^\/api/, ''),   // existing code uses /v1/... (api prefix is added by streamMAIC)
```
(Verify whether `streamMAIC` prepends `/api` — if it does, strip it; if not, use full `maicChatUrl(this.role)`.)

- [ ] **Step 4: Update the single instantiation site**

In `frontend/src/hooks/useOrchestration.ts:139`, find:
```ts
const director = new DirectorGraph(agents, callbacks, {
  // existing config
});
```
Add `role` to the config object. The `role` must be passed as a prop or hook argument up the chain from MAICPlayerPage.

If `useOrchestration` doesn't currently accept a role, add it as a parameter:
```ts
export function useOrchestration(..., role: MAICRole) {
  // ...
  const director = new DirectorGraph(agents, callbacks, { ..., role });
}
```

Then update the single caller of `useOrchestration` to pass `role`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/orchestration/director.ts frontend/src/hooks/useOrchestration.ts
git commit -m "fix(maic): DirectorGraph uses role-aware chat URL"
```

### Task 1.9: Fix actionEngine configured-TTS URL

**Files:** Modify `frontend/src/lib/maicActionEngine.ts:333`

- [ ] **Step 1: Replace hardcoded URL**

Change line 333:
```ts
const ttsProviderUrl = `${baseUrl}/api/v1/teacher/maic/generate/tts/`;
```
to:
```ts
const ttsProviderUrl = `${baseUrl}${this.ttsEndpoint}`;
```
(The constructor already receives `ttsEndpoint` and it's already role-aware in `usePlaybackEngine.ts:17-18`.)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/maicActionEngine.ts
git commit -m "fix(maic): configured-TTS path uses role-aware ttsEndpoint"
```

### Task 1.10: Thread role through MAICPlayerPage → Stage → Panels

**Files:** Modify `frontend/src/pages/teacher/MAICPlayerPage.tsx`, `frontend/src/pages/student/MAICPlayerPage.tsx`, `frontend/src/components/maic/Stage.tsx`

- [ ] **Step 1: Teacher page passes `role="teacher"` into `<Stage>`**

- [ ] **Step 2: Student page passes `role="student"` into `<Stage>`**

- [ ] **Step 3: `Stage.tsx` accepts `role` and forwards to `<RoundtablePanel role={role} />`, `<ChatPanel role={role} />`, `<PBLRenderer role={role} />`**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/{teacher,student}/MAICPlayerPage.tsx frontend/src/components/maic/Stage.tsx
git commit -m "feat(maic): thread role prop through player → panels"
```

### Task 1.11: Write backend permissions test

**Files:** Create `backend/tests/courses/test_maic_permissions.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest
from rest_framework.test import APIClient
from apps.courses.maic_models import TenantAIConfig, MAICClassroom

pytestmark = pytest.mark.django_db


@pytest.fixture
def student(user_factory, tenant):
    return user_factory(tenant=tenant, role="STUDENT")


@pytest.fixture
def teacher(user_factory, tenant):
    return user_factory(tenant=tenant, role="TEACHER")


@pytest.fixture
def ai_config(tenant):
    return TenantAIConfig.objects.create(
        tenant=tenant,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        maic_enabled=True,
    )


def test_student_chat_succeeds(client, student, ai_config, tenant):
    client.force_authenticate(student)
    r = client.post(
        "/api/v1/student/maic/chat/",
        {"message": "Hi", "classroomId": None},
        format="json",
        HTTP_HOST=f"{tenant.subdomain}.localhost",
    )
    assert r.status_code in (200, 502)  # 502 ok if sidecar down, fallback runs


def test_teacher_endpoint_rejects_student(client, student, ai_config, tenant):
    client.force_authenticate(student)
    r = client.post(
        "/api/v1/teacher/maic/chat/",
        {"message": "Hi"},
        format="json",
        HTTP_HOST=f"{tenant.subdomain}.localhost",
    )
    assert r.status_code == 403
    assert "Teacher or admin" in r.content.decode()
```

- [ ] **Step 2: Run tests**

Run: `cd backend && pytest tests/courses/test_maic_permissions.py -v`
Expected: both PASS (if fixtures exist) — else create fixtures.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/courses/test_maic_permissions.py
git commit -m "test(maic): student chat perms"
```

### Task 1.12: Write E2E permissions test

**Files:** Create `e2e/tests/maic-student-chat.spec.ts`

- [ ] **Step 1: Write Playwright test**

```typescript
import { test, expect } from '@playwright/test';

test('student can send chat in classroom player', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[name="email"]', 'student@demo.test');
  await page.fill('input[name="password"]', 'demo1234');
  await page.click('button[type="submit"]');

  await page.waitForURL('**/student/**');
  await page.goto('/student/ai-classroom');
  await page.click('[data-testid="classroom-card"]:first-child');

  await page.waitForSelector('[data-testid="maic-stage"]');

  const chatInput = page.locator('[data-testid="chat-input"]');
  await chatInput.fill('What is this topic about?');
  await chatInput.press('Enter');

  // Agent reply must appear within 15s; no 403 error toast.
  await expect(page.locator('[data-testid="chat-agent-message"]').first()).toBeVisible({ timeout: 15000 });
  await expect(page.locator('text=/Teacher or admin/i')).toHaveCount(0);
});
```

- [ ] **Step 2: Commit**

```bash
git add e2e/tests/maic-student-chat.spec.ts
git commit -m "test(maic): e2e student chat"
```

### Task 1.13: Chunk 1 checkpoint — run all tests

- [ ] **Step 1: Backend tests**

Run: `cd backend && pytest tests/courses/test_maic_permissions.py -v`
Expected: 2 PASS

- [ ] **Step 2: Frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Mark chunk complete**

```bash
git log --oneline -15
```

Should show ~12 commits for Chunk 1.

---

## Chunk 2: WS-B Backend — Agent Profiles + Prompt Propagation

**Owner subagent:** `Backend-Agents`
**Est:** 1.3d
**Depends on:** nothing — can start in parallel with Chunk 1.

### Task 2.1: Create voice roster module

**Files:** Create `backend/apps/courses/maic_voices.py`

- [ ] **Step 1: Write the module**

```python
"""Azure en-IN neural voice roster for MAIC agents.

Data-only module. No business logic. Consumed by:
- maic_generation_service.generate_agent_profiles_json (for voice assignment)
- maic_views.maic_list_voices (surfaced to frontend)
- maic_views.teacher_maic_tts_preview (voice validation)
"""

AZURE_IN_VOICES = [
    {"id": "en-IN-PrabhatNeural",   "gender": "male",   "tone": "authoritative", "age": "adult",       "suits": ["professor"]},
    {"id": "en-IN-NeerjaNeural",    "gender": "female", "tone": "warm",          "age": "adult",       "suits": ["teaching_assistant", "professor"]},
    {"id": "en-IN-AaravNeural",     "gender": "male",   "tone": "friendly",      "age": "young adult", "suits": ["student"]},
    {"id": "en-IN-AashiNeural",     "gender": "female", "tone": "youthful",      "age": "young adult", "suits": ["student"]},
    {"id": "en-IN-KavyaNeural",     "gender": "female", "tone": "energetic",     "age": "adult",       "suits": ["teaching_assistant", "moderator"]},
    {"id": "en-IN-KunalNeural",     "gender": "male",   "tone": "thoughtful",    "age": "adult",       "suits": ["moderator", "student"]},
    {"id": "en-IN-RehaanNeural",    "gender": "male",   "tone": "playful",       "age": "young adult", "suits": ["student"]},
]

VOICE_BY_ID = {v["id"]: v for v in AZURE_IN_VOICES}


def voices_for_role(role: str) -> list[dict]:
    """All voices whose `suits` list contains the given role."""
    return [v for v in AZURE_IN_VOICES if role in v["suits"]]


def is_valid_voice(voice_id: str) -> bool:
    return voice_id in VOICE_BY_ID


def voice_matches_role(voice_id: str, role: str) -> bool:
    v = VOICE_BY_ID.get(voice_id)
    return v is not None and role in v["suits"]
```

- [ ] **Step 2: Commit**

```bash
git add backend/apps/courses/maic_voices.py
git commit -m "feat(maic): Azure en-IN voice roster"
```

### Task 2.2: Create prompt loader

**Files:** Create `backend/apps/courses/prompts/__init__.py`, `backend/apps/courses/prompts/loader.py`

- [ ] **Step 1: Package marker**

Create empty `backend/apps/courses/prompts/__init__.py`.

- [ ] **Step 2: Write loader**

```python
# backend/apps/courses/prompts/loader.py
"""Load + cache prompt template files.

Templates live as .md files in this directory and are loaded once per process.
"""
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Load a prompt file by name (without extension). Cached.

    Example: load_prompt('agent_profiles') → content of agent_profiles.md
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")
```

- [ ] **Step 3: Commit**

```bash
git add backend/apps/courses/prompts/
git commit -m "feat(maic): prompt template loader"
```

### Task 2.3: Write agent_profiles system prompt

**Files:** Create `backend/apps/courses/prompts/agent_profiles.md`

- [ ] **Step 1: Write the prompt**

```markdown
You are an expert instructional designer creating a roster of AI agents for an interactive classroom. Your agents will teach Indian students (K-12 and higher-ed). The roster must feel authentic, warm, and culturally grounded without being stereotyped.

## Output

Return ONLY valid JSON with this exact shape. No markdown fences, no commentary.

```json
{
  "agents": [
    {
      "id": "agent-1",
      "name": "Dr. Aarav Sharma",
      "role": "professor",
      "avatar": "👨‍🏫",
      "color": "#4338CA",
      "voiceId": "en-IN-PrabhatNeural",
      "voiceProvider": "azure",
      "personality": "Patient and methodical. Explains with everyday analogies drawn from Indian kitchens, trains, and cricket.",
      "expertise": "Leads the lecture; connects abstract concepts to concrete examples.",
      "speakingStyle": "Warm, unhurried. Occasionally asks 'theek hai?' to check understanding."
    }
  ]
}
```

## Hard constraints

- **Names:** Indian. Mix regions — Hindi (Sharma, Verma), Tamil (Iyer, Krishnan), Telugu (Reddy, Rao), Bengali (Bose, Sen), Marathi (Desai, Patil), Punjabi (Kaur, Singh), Malayali (Nair, Menon). Gender-balanced when count ≥ 3 (at least one male AND one female).
- **Honorifics:** `professor` → "Dr." or "Prof." prefix. `teaching_assistant` → "Ms." or "Mr." prefix. `student` → first-name only (no honorific). `moderator` → "Ms." or "Mr." prefix.
- **No stereotypes.** No "aunty" or "uncle" tropes. No IT/coding clichés. No caste references.
- **`personality`:** 1–2 sentences, topic-grounded. Mention how the agent relates to the topic.
- **`speakingStyle`:** 1–2 sentences. Include ONE culturally-grounded phrase hint used SPARINGLY (e.g. "theek hai?", "bilkul", "samjhe?"). Not every line — ONE phrase per agent, to be used occasionally.
- **`voiceId`:** MUST be one from the available voice list I provide. The voice's `suits` list MUST contain the agent's role.
- **No two agents share a voiceId.**
- **`color`:** pick from this exact palette — `#4338CA` (indigo), `#0F766E` (teal), `#D97706` (saffron), `#166534` (forest), `#9F1239` (cranberry), `#334155` (slate). No two agents share a color.
- **`avatar`:** pick from this exact emoji set — 👨‍🏫 👩‍🏫 🧑‍🎓 👨‍🎓 👩‍🎓 🧕 🙋‍♀️ 🙋‍♂️. No two agents share an avatar.
- **`id`:** sequential `agent-1`, `agent-2`, …
- **Role enum:** one of `professor`, `teaching_assistant`, `student`, `moderator`.

## Input variables

- Topic: {{topic}}
- Language of instruction: {{language}}
- Role slots requested (must match exactly):
{{role_slots_json}}
- Available voices (you MUST pick from these):
{{voices_json}}

Return the agents array matching the role slot counts.
```

- [ ] **Step 2: Commit**

```bash
git add backend/apps/courses/prompts/agent_profiles.md
git commit -m "feat(maic): agent profiles system prompt"
```

### Task 2.4: Write agent-profile validator

**Files:** Modify `backend/apps/courses/maic_generation_service.py` — add new function

- [ ] **Step 1: Write failing test first**

Create `backend/tests/courses/test_maic_agents.py`:

```python
import pytest
from apps.courses.maic_generation_service import validate_agents, AgentValidationError
from apps.courses.maic_voices import AZURE_IN_VOICES

pytestmark = pytest.mark.django_db


def sample_agents():
    return [
        {"id": "agent-1", "name": "Dr. Aarav Sharma", "role": "professor",
         "avatar": "👨‍🏫", "color": "#4338CA",
         "voiceId": "en-IN-PrabhatNeural", "voiceProvider": "azure",
         "personality": "Patient.", "expertise": "Leads.", "speakingStyle": "Warm."},
        {"id": "agent-2", "name": "Ms. Priya Iyer", "role": "teaching_assistant",
         "avatar": "👩‍🏫", "color": "#0F766E",
         "voiceId": "en-IN-NeerjaNeural", "voiceProvider": "azure",
         "personality": "Kind.", "expertise": "Supports.", "speakingStyle": "Warm."},
        {"id": "agent-3", "name": "Rohan Menon", "role": "student",
         "avatar": "🙋‍♂️", "color": "#D97706",
         "voiceId": "en-IN-AaravNeural", "voiceProvider": "azure",
         "personality": "Curious.", "expertise": "Asks.", "speakingStyle": "Friendly."},
    ]


def test_valid_agents_pass():
    validate_agents(sample_agents(), role_slots=[
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 1},
    ])


def test_duplicate_voice_rejected():
    agents = sample_agents()
    agents[1]["voiceId"] = "en-IN-PrabhatNeural"  # collide with agent-1
    with pytest.raises(AgentValidationError, match="duplicate voice"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_voice_role_mismatch_rejected():
    agents = sample_agents()
    agents[2]["voiceId"] = "en-IN-PrabhatNeural"  # prof voice on student
    # also fix duplicate on agent-1 so we test voice-role mismatch cleanly
    agents[0]["voiceId"] = "en-IN-NeerjaNeural"
    agents[1]["voiceId"] = "en-IN-KavyaNeural"
    with pytest.raises(AgentValidationError, match="voice .* does not suit role"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_gender_balance_with_3plus_agents():
    # Valid: 2 males + 1 female (default sample)
    agents = sample_agents()
    validate_agents(agents, role_slots=[
        {"role": "professor", "count": 1},
        {"role": "teaching_assistant", "count": 1},
        {"role": "student", "count": 1},
    ])

    # Invalid: all male (3 agents, all male voices picked from roster where male suits each role)
    all_male = [
        {**agents[0], "voiceId": "en-IN-PrabhatNeural"},                 # male, suits professor
        {**agents[1], "role": "moderator", "voiceId": "en-IN-KunalNeural"},  # male, suits moderator
        {**agents[2], "voiceId": "en-IN-AaravNeural"},                   # male, suits student
    ]
    with pytest.raises(AgentValidationError, match="gender balance"):
        validate_agents(all_male, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "moderator", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_invalid_voice_id_rejected():
    agents = sample_agents()
    agents[0]["voiceId"] = "en-US-DavisNeural"  # not in roster
    with pytest.raises(AgentValidationError, match="not in roster"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])


def test_role_count_mismatch_rejected():
    agents = sample_agents()[:2]  # only 2 agents
    with pytest.raises(AgentValidationError, match="expected .* got"):
        validate_agents(agents, role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ])
```

- [ ] **Step 2: Run test — expect ImportError**

Run: `cd backend && pytest tests/courses/test_maic_agents.py -v`
Expected: ImportError on `validate_agents` / `AgentValidationError`.

- [ ] **Step 3: Implement validator in maic_generation_service.py**

Add near the top of the file (after existing imports):

```python
from apps.courses.maic_voices import AZURE_IN_VOICES, VOICE_BY_ID, voice_matches_role


class AgentValidationError(ValueError):
    pass


def validate_agents(agents: list[dict], role_slots: list[dict]) -> None:
    """Raise AgentValidationError if the agent list doesn't satisfy constraints.

    role_slots: [{"role": "professor", "count": 1}, ...]
    """
    # Count by role must match role_slots
    role_counts = {}
    for a in agents:
        role_counts[a["role"]] = role_counts.get(a["role"], 0) + 1
    for slot in role_slots:
        actual = role_counts.get(slot["role"], 0)
        if actual != slot["count"]:
            raise AgentValidationError(
                f"role {slot['role']}: expected {slot['count']}, got {actual}"
            )

    # Voice constraints
    seen_voices = set()
    for a in agents:
        voice_id = a.get("voiceId")
        if voice_id not in VOICE_BY_ID:
            raise AgentValidationError(f"voice {voice_id!r} not in roster")
        if voice_id in seen_voices:
            raise AgentValidationError(f"duplicate voice: {voice_id}")
        seen_voices.add(voice_id)
        if not voice_matches_role(voice_id, a["role"]):
            raise AgentValidationError(
                f"voice {voice_id} does not suit role {a['role']}"
            )

    # Gender balance when count ≥ 3
    if len(agents) >= 3:
        genders = {VOICE_BY_ID[a["voiceId"]]["gender"] for a in agents}
        if len(genders) < 2:
            raise AgentValidationError("gender balance required: need at least one male and one female")

    # Duplicate colors / avatars
    colors = [a["color"] for a in agents]
    if len(set(colors)) != len(colors):
        raise AgentValidationError("duplicate color")
    avatars = [a["avatar"] for a in agents]
    if len(set(avatars)) != len(avatars):
        raise AgentValidationError("duplicate avatar")
```

- [ ] **Step 4: Run tests — expect all PASS**

Run: `cd backend && pytest tests/courses/test_maic_agents.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/courses/maic_generation_service.py backend/tests/courses/test_maic_agents.py
git commit -m "feat(maic): agent profile validator"
```

### Task 2.5: Implement `generate_agent_profiles_json`

**Files:** Modify `backend/apps/courses/maic_generation_service.py`

- [ ] **Step 1: Write failing test**

Append to `test_maic_agents.py`:

```python
from unittest.mock import patch
from apps.courses.maic_generation_service import generate_agent_profiles_json


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_agent_profiles_returns_valid(mock_llm, ai_config):
    mock_llm.return_value = '{"agents": ' + str(sample_agents()).replace("'", '"') + '}'
    result = generate_agent_profiles_json(
        topic="Photosynthesis",
        language="en",
        role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ],
        config=ai_config,
    )
    assert "agents" in result
    assert len(result["agents"]) == 3
    assert result["agents"][0]["role"] == "professor"


@patch("apps.courses.maic_generation_service._call_llm")
def test_generate_agent_profiles_retries_on_validation_error(mock_llm, ai_config):
    bad = sample_agents()
    bad[1]["voiceId"] = bad[0]["voiceId"]  # duplicate → invalid
    good = sample_agents()
    mock_llm.side_effect = [
        '{"agents": ' + str(bad).replace("'", '"') + '}',
        '{"agents": ' + str(good).replace("'", '"') + '}',
    ]
    result = generate_agent_profiles_json(
        topic="X", language="en",
        role_slots=[
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": 1},
        ],
        config=ai_config,
    )
    assert len(result["agents"]) == 3
    assert mock_llm.call_count == 2  # retry happened
```

- [ ] **Step 2: Run tests — expect import error**

- [ ] **Step 3: Implement**

Add to `maic_generation_service.py`:

```python
import json
from apps.courses.prompts.loader import load_prompt
from apps.courses.maic_voices import AZURE_IN_VOICES


def generate_agent_profiles_json(
    topic: str,
    language: str,
    role_slots: list[dict],
    config: TenantAIConfig,
) -> dict:
    """Generate an agent roster via LLM, validated against our constraints.

    Retries once on validation failure. Raises AgentValidationError on persistent failure.
    """
    system_prompt = load_prompt("agent_profiles")

    # Build user prompt from template variables baked into the markdown.
    # The template has {{topic}}, {{language}}, {{role_slots_json}}, {{voices_json}}.
    rendered = system_prompt.replace("{{topic}}", topic)
    rendered = rendered.replace("{{language}}", language)
    rendered = rendered.replace("{{role_slots_json}}", json.dumps(role_slots, indent=2))
    rendered = rendered.replace("{{voices_json}}", json.dumps(AZURE_IN_VOICES, indent=2))

    user_prompt = f"Generate the agents for the topic \"{topic}\" in {language}."

    last_error = None
    for attempt in range(2):
        raw = _call_llm(config, rendered, user_prompt, temperature=0.9, max_tokens=2048)
        if not raw:
            last_error = "LLM returned empty"
            continue
        parsed = _parse_json_from_llm(raw)
        if not parsed or "agents" not in parsed:
            last_error = "invalid JSON"
            continue
        try:
            validate_agents(parsed["agents"], role_slots)
            return parsed
        except AgentValidationError as e:
            last_error = str(e)
            continue

    raise AgentValidationError(f"generation failed after 2 attempts: {last_error}")
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd backend && pytest tests/courses/test_maic_agents.py::test_generate_agent_profiles_returns_valid tests/courses/test_maic_agents.py::test_generate_agent_profiles_retries_on_validation_error -v`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/courses/maic_generation_service.py backend/tests/courses/test_maic_agents.py
git commit -m "feat(maic): generate_agent_profiles_json with retry"
```

### Task 2.6: Add `regenerate_one_agent` helper

**Files:** Modify `backend/apps/courses/maic_generation_service.py`

- [ ] **Step 1: Implement**

```python
def regenerate_one_agent(
    topic: str,
    language: str,
    existing_agents: list[dict],
    target_agent_id: str,
    locked_fields: list[str],
    config: TenantAIConfig,
) -> dict:
    """Regenerate a single agent distinct from the existing set.

    locked_fields: list of field names to preserve from the existing agent (e.g., ['voiceId']).
    Returns the new agent dict.
    """
    existing = next((a for a in existing_agents if a["id"] == target_agent_id), None)
    if not existing:
        raise ValueError(f"target_agent_id {target_agent_id} not in existing_agents")
    others = [a for a in existing_agents if a["id"] != target_agent_id]
    target_role = existing["role"]

    system_prompt = (
        "You are an expert instructional designer. Generate ONE replacement AI agent "
        f"for an Indian classroom teaching \"{topic}\" in {language}.\n"
        f"The new agent must fill this role slot: {target_role}.\n"
        f"The new agent must be distinct from these existing agents:\n"
        f"{json.dumps(others, indent=2)}\n"
        f"The new agent MUST preserve these locked fields from the existing agent: {locked_fields}.\n"
        f"Existing agent (for locked fields only): {json.dumps({k: existing[k] for k in locked_fields})}\n"
        "Follow the same naming/styling rules as full roster generation: Indian names, no stereotypes, "
        "1 cultural phrase in speakingStyle (used sparingly).\n"
        "Return ONLY JSON: {\"agent\": {...}}"
    )
    user_prompt = f"Generate replacement agent for id={target_agent_id}."

    raw = _call_llm(config, system_prompt, user_prompt, temperature=0.9, max_tokens=1024)
    parsed = _parse_json_from_llm(raw or "")
    if not parsed or "agent" not in parsed:
        raise AgentValidationError("regenerate returned invalid JSON")

    new_agent = parsed["agent"]
    # Force-preserve locked fields
    for field in locked_fields:
        new_agent[field] = existing[field]
    new_agent["id"] = target_agent_id  # always preserve id

    # Validate against full roster: replace target in list, re-validate
    full = [new_agent if a["id"] == target_agent_id else a for a in existing_agents]
    role_slots_from_existing = _infer_role_slots(existing_agents)
    validate_agents(full, role_slots_from_existing)

    return {"agent": new_agent}


def _infer_role_slots(agents: list[dict]) -> list[dict]:
    counts = {}
    for a in agents:
        counts[a["role"]] = counts.get(a["role"], 0) + 1
    return [{"role": r, "count": c} for r, c in counts.items()]
```

- [ ] **Step 2: Write test**

```python
@patch("apps.courses.maic_generation_service._call_llm")
def test_regenerate_one_preserves_locked_voice(mock_llm, ai_config):
    existing = sample_agents()
    new_agent = dict(existing[1])
    new_agent["name"] = "Ms. Ananya Nair"
    new_agent["voiceId"] = "en-IN-AashiNeural"  # LLM tries to change voice
    mock_llm.return_value = json.dumps({"agent": new_agent})

    result = regenerate_one_agent(
        topic="X", language="en",
        existing_agents=existing,
        target_agent_id="agent-2",
        locked_fields=["voiceId"],
        config=ai_config,
    )
    assert result["agent"]["voiceId"] == existing[1]["voiceId"]  # preserved
    assert result["agent"]["name"] == "Ms. Ananya Nair"  # new
```

- [ ] **Step 3: Run tests + commit**

```bash
cd backend && pytest tests/courses/test_maic_agents.py -v
git add backend/apps/courses/maic_generation_service.py backend/tests/courses/test_maic_agents.py
git commit -m "feat(maic): regenerate_one_agent with locked fields"
```

### Task 2.7: Update OUTLINE_SYSTEM_PROMPT to accept agents input

**Files:** Modify `backend/apps/courses/maic_generation_service.py:131` (OUTLINE_SYSTEM_PROMPT)

- [ ] **Step 1: Rewrite prompt to remove agent generation**

Replace the entire `OUTLINE_SYSTEM_PROMPT` string (lines 131–183 currently) with:

```python
OUTLINE_SYSTEM_PROMPT = """You are an expert educational content designer creating a multi-agent interactive classroom.

You will receive a pre-configured agent roster. Do NOT invent new agents. Use the exact `id`s from the roster when assigning agents to scenes.

Return a valid JSON object:
{
  "scenes": [
    {
      "id": "scene-1",
      "title": "Scene title",
      "description": "Brief description of what this scene covers",
      "type": "introduction|lecture|discussion|quiz|activity|pbl|case_study|summary",
      "estimatedMinutes": 3,
      "agentIds": ["agent-1", "agent-2"],
      "slideCount": 6,
      "questionCount": 0
    }
  ],
  "totalMinutes": 20
}

Rules:
- The FIRST scene MUST be type "introduction" — all agents introduce themselves and preview the class
- The LAST scene MUST be type "summary" — wrap up key takeaways and next steps
- Automatically insert a "quiz" scene after every 2-3 lecture/discussion scenes to reinforce learning
- Each scene should have 2-5 minutes estimated time
- Every scene MUST have at least 2 agents assigned (for dialogue) drawn from the provided roster
- Scene type distribution: introduction -> lectures -> quiz -> lectures/discussion -> quiz -> summary
- For "lecture" scenes: set "slideCount" to 5-8 (number of slides to generate)
- For "discussion" scenes: set "slideCount" to 3-5
- For "introduction" scenes: set "slideCount" to 3-4
- For "summary" scenes: set "slideCount" to 3-4
- For "quiz" scenes: set "questionCount" to 3-5, "slideCount" to 1
- For "activity" scenes: set "slideCount" to 3-5
- For "pbl" scenes: set "slideCount" to 4-6
- For "case_study" scenes: set "slideCount" to 4-6
- Use agentIds ONLY from the provided roster — never invent new ids."""
```

- [ ] **Step 2: Modify `generate_outline_sse` to accept agents + include in user prompt**

Find `generate_outline_sse(topic, language, agent_count, scene_count, pdf_text, config)` and change signature:

```python
def generate_outline_sse(topic: str, language: str, agents: list[dict],
                         scene_count: int, pdf_text: str | None,
                         config: TenantAIConfig):
    user_prompt = f"""Create a classroom outline for the following:

Topic: {topic}
Language: {language}
Number of scenes: {scene_count}

Agent roster (use these ids when assigning agents to scenes):
{json.dumps([{
    "id": a["id"], "name": a["name"], "role": a["role"],
    "personality": a.get("personality", ""),
} for a in agents], indent=2)}
"""
    if pdf_text:
        excerpt = pdf_text[:15000]
        user_prompt += f"\nReference material (excerpt):\n{excerpt}\n"
    # ... rest stays the same EXCEPT remove the agent-fixup logic below
```

Remove the block that was fixing up `agents` and return-value (lines ~224–250 currently):
```python
    # OLD: agents = parsed.get("agents", [])
    # NEW: agents come from input — just validate scene.agentIds are in the roster
    agent_ids_allowed = {a["id"] for a in agents}
    for scene in parsed.get("scenes", []):
        scene["agentIds"] = [aid for aid in scene.get("agentIds", []) if aid in agent_ids_allowed]
        if len(scene["agentIds"]) < 2:
            # Fall back: pick first 2 from roster
            scene["agentIds"] = [a["id"] for a in agents[:2]]

    outline_data = {
        "scenes": parsed.get("scenes", []),
        "agents": agents,                      # pass-through from input
        "totalMinutes": parsed.get("totalMinutes",
            sum(s.get("estimatedMinutes", 3) for s in parsed.get("scenes", []))),
    }
```

- [ ] **Step 3: Write test**

```python
from apps.courses.maic_generation_service import generate_outline_sse

@patch("apps.courses.maic_generation_service._call_llm")
def test_outline_uses_provided_agents_not_generated(mock_llm, ai_config):
    mock_llm.return_value = json.dumps({
        "scenes": [
            {"id": "scene-1", "title": "Intro", "type": "introduction",
             "estimatedMinutes": 3, "agentIds": ["agent-1", "agent-2"], "slideCount": 3},
            {"id": "scene-2", "title": "Lecture", "type": "lecture",
             "estimatedMinutes": 5, "agentIds": ["agent-1", "agent-3"], "slideCount": 5},
        ],
        "totalMinutes": 8,
    })
    agents = sample_agents()
    events = list(generate_outline_sse(
        topic="X", language="en", agents=agents, scene_count=2, pdf_text=None, config=ai_config,
    ))
    # find the outline event
    outline_event = next(e for e in events if '"outline"' in e)
    assert all(aid in {"agent-1", "agent-2", "agent-3"} for s in json.loads(outline_event.split("data: ")[1])["scenes"] for aid in s["agentIds"])
```

- [ ] **Step 4: Run tests + commit service-layer changes ONLY**

Caller updates in `maic_views.py` are owned by Chunk 4 (see Task 4.1.5) to respect file-ownership boundaries.

```bash
cd backend && pytest tests/courses/test_maic_agents.py -v
git add backend/apps/courses/maic_generation_service.py backend/tests/courses/test_maic_agents.py
git commit -m "refactor(maic): outline service accepts agents input"
```

### Task 2.8: Enrich ACTIONS_SYSTEM_PROMPT with speakingStyle

**Files:** Modify `backend/apps/courses/maic_generation_service.py` around `ACTIONS_SYSTEM_PROMPT` and `generate_scene_actions`

- [ ] **Step 1: Add speakingStyle to agent_details JSON**

Find the block in `generate_scene_actions` that builds `agent_details = json.dumps([...])`:

```python
agent_details = json.dumps([{
    "id": a["id"],
    "name": a["name"],
    "role": a.get("role", "professor"),
    "personality": a.get("personality", ""),
    "speakingStyle": a.get("speakingStyle", ""),  # NEW
} for a in assigned_agents])
```

- [ ] **Step 2: Add explicit rule in ACTIONS_SYSTEM_PROMPT**

Find the `CRITICAL RULES:` section. Add as a new rule:

```
- VOICE DISCIPLINE: You MUST write speech text that reflects each agent's `speakingStyle`, including any cultural phrases the style notes. Each agent's lines should be identifiable as that agent's voice, not generic LLM prose. Use the cultural phrases SPARINGLY — one phrase per agent across the whole scene, not every line.
```

- [ ] **Step 3: Commit**

```bash
git add backend/apps/courses/maic_generation_service.py
git commit -m "feat(maic): scene actions honor speakingStyle"
```

### Task 2.9: Enrich CHAT_SYSTEM_PROMPT with persona

**Files:** Modify `backend/apps/courses/maic_generation_service.py:832` (CHAT_SYSTEM_PROMPT + `generate_chat_sse`)

- [ ] **Step 1: Rewrite prompt**

```python
CHAT_SYSTEM_PROMPT = """You are a panel of AI teaching agents in an interactive classroom. Multiple agents should respond to the student's question, each bringing their unique perspective and their own voice.

You MUST return a valid JSON array of agent responses:
[
  {"agentId": "agent-1", "agentName": "Dr. Aarav Sharma", "content": "Your response..."},
  {"agentId": "agent-2", "agentName": "Ms. Priya Iyer", "content": "Building on that..."}
]

Rules:
- Return 2-3 agent responses (not just one)
- The lead agent (professor) answers first with the main explanation
- Supporting agents add perspective, ask follow-ups, give analogies, or provide examples
- Each response is 2-4 sentences
- EACH AGENT MUST SPEAK IN THEIR OWN VOICE per their `personality` and `speakingStyle`. Do not write generic answers — make them identifiable.
- Use each agent's cultural phrases (from speakingStyle) SPARINGLY — at most once per response
- Be conversational, warm, and encouraging
- Reference the classroom topic naturally
- If the question is off-topic, gently redirect"""
```

- [ ] **Step 2: Pass full agent dicts (with speakingStyle) into the user prompt**

In `generate_chat_sse`, change agent formatting:

```python
agents_for_prompt = json.dumps([{
    "id": a["id"],
    "name": a["name"],
    "role": a.get("role", "professor"),
    "personality": a.get("personality", ""),
    "speakingStyle": a.get("speakingStyle", ""),
} for a in agents], indent=2)

user_prompt = f"""Classroom topic: {classroom_title}
Agents (each must speak in their own voice):
{agents_for_prompt}

Student question: {message}

Generate 2-3 agent responses."""
```

- [ ] **Step 3: Commit**

```bash
git add backend/apps/courses/maic_generation_service.py
git commit -m "feat(maic): chat responses respect agent persona + speakingStyle"
```

### Task 2.10: Chunk 2 checkpoint

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && pytest tests/courses/ -v --tb=short`
Expected: green.

- [ ] **Step 2: Confirm test count**

Run: `cd backend && pytest tests/courses/test_maic_agents.py --collect-only -q | wc -l`
Expected: ≥ 6 tests.

---

## Chunk 3: WS-C Frontend Wizard — Agent Picker

**Owner subagent:** `Frontend-Wizard`
**Est:** 1.5d
**Depends on:** Chunk 1 type additions merged; Chunk 2 endpoints available (can mock until they land).

### Task 3.1: Add API methods to openmaicService

**Files:** Modify `frontend/src/services/openmaicService.ts`

- [ ] **Step 1: Add `maicApi.generateAgentProfiles`, `regenerateAgent`, `ttsPreview`, `listVoices`, `publishClassroom`**

```ts
// Around the existing maicApi object:

interface GenerateAgentProfilesRequest {
  topic: string;
  language: string;
  roleSlots: { role: string; count: number }[];
}

interface GenerateAgentProfilesResponse {
  agents: MAICAgent[];
}

export const maicApi = {
  // ... existing methods

  generateAgentProfiles: (data: GenerateAgentProfilesRequest) =>
    api.post<GenerateAgentProfilesResponse>('/v1/teacher/maic/generate/agent-profiles/', data),

  regenerateAgent: (data: {
    topic: string;
    existingAgents: MAICAgent[];
    targetAgentId: string;
    lockedFields: string[];
  }) =>
    api.post<{ agent: MAICAgent }>('/v1/teacher/maic/agents/regenerate-one/', data),

  ttsPreview: (data: { voiceId: string; text: string }) =>
    api.post('/v1/teacher/maic/tts/preview/', data, { responseType: 'blob' }),

  listVoices: () =>
    api.get<{ voices: Array<{ id: string; gender: string; tone: string; age: string; suits: string[] }> }>('/v1/maic/voices/'),

  publishClassroom: (id: string) =>
    api.post<{ audioManifest: AudioManifest }>(`/v1/teacher/maic/classrooms/${id}/publish/`, {}),
};

// Student variants
export const maicStudentApi = {
  // ... existing
  generateAgentProfiles: (data: GenerateAgentProfilesRequest) =>
    api.post<GenerateAgentProfilesResponse>('/v1/student/maic/generate/agent-profiles/', data),
  regenerateAgent: (data: {
    topic: string;
    existingAgents: MAICAgent[];
    targetAgentId: string;
    lockedFields: string[];
  }) =>
    api.post<{ agent: MAICAgent }>('/v1/student/maic/agents/regenerate-one/', data),
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/openmaicService.ts
git commit -m "feat(maic): agent profile + voice + publish API methods"
```

### Task 3.2: Create AgentCard component

**Files:** Create `frontend/src/components/maic/AgentCard.tsx`

- [ ] **Step 1: Write failing Vitest**

Create `frontend/src/components/maic/__tests__/AgentCard.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { AgentCard } from '../AgentCard';
import type { MAICAgent } from '../../../types/maic';

const agent: MAICAgent = {
  id: 'agent-1',
  name: 'Dr. Aarav Sharma',
  role: 'professor',
  avatar: '👨‍🏫',
  color: '#4338CA',
  voiceId: 'en-IN-PrabhatNeural',
  voiceProvider: 'azure',
  personality: 'Patient.',
  expertise: 'Leads.',
  speakingStyle: 'Warm.',
};

test('renders name, role, voice, avatar', () => {
  render(
    <AgentCard
      agent={agent}
      onEdit={() => {}}
      onRegenerate={() => {}}
      onPreviewVoice={() => {}}
      isPreviewing={false}
    />,
  );
  expect(screen.getByText('Dr. Aarav Sharma')).toBeInTheDocument();
  expect(screen.getByText(/professor/i)).toBeInTheDocument();
  expect(screen.getByText(/Prabhat/i)).toBeInTheDocument();
  expect(screen.getByText('👨‍🏫')).toBeInTheDocument();
});

test('fires onEdit when edit button clicked', () => {
  const onEdit = vi.fn();
  render(
    <AgentCard
      agent={agent}
      onEdit={onEdit}
      onRegenerate={() => {}}
      onPreviewVoice={() => {}}
      isPreviewing={false}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /edit/i }));
  expect(onEdit).toHaveBeenCalledWith(agent);
});

test('fires onPreviewVoice with voiceId', () => {
  const onPreviewVoice = vi.fn();
  render(
    <AgentCard
      agent={agent}
      onEdit={() => {}}
      onRegenerate={() => {}}
      onPreviewVoice={onPreviewVoice}
      isPreviewing={false}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /preview voice/i }));
  expect(onPreviewVoice).toHaveBeenCalledWith('en-IN-PrabhatNeural');
});
```

- [ ] **Step 2: Run — expect fail**

Run: `cd frontend && npx vitest run src/components/maic/__tests__/AgentCard.test.tsx`

- [ ] **Step 3: Write AgentCard**

```tsx
// frontend/src/components/maic/AgentCard.tsx
import { Play, Pause, Edit3, RotateCcw } from 'lucide-react';
import type { MAICAgent } from '../../types/maic';

interface AgentCardProps {
  agent: MAICAgent;
  onEdit: (agent: MAICAgent) => void;
  onRegenerate: (agentId: string) => void;
  onPreviewVoice: (voiceId: string) => void;
  isPreviewing: boolean;
  isRegenerating?: boolean;
}

export function AgentCard({ agent, onEdit, onRegenerate, onPreviewVoice, isPreviewing, isRegenerating }: AgentCardProps) {
  const voiceShort = agent.voiceId.replace('en-IN-', '').replace('Neural', '');

  return (
    <div
      className="relative rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md"
      style={{ borderTopColor: agent.color, borderTopWidth: 4 }}
    >
      {isRegenerating && (
        <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-white/70 backdrop-blur-sm">
          <span className="text-sm text-slate-500">Regenerating…</span>
        </div>
      )}
      <div className="mb-3 text-4xl" role="img" aria-label="avatar">{agent.avatar}</div>
      <h3 className="mb-1 text-lg font-semibold text-slate-900">{agent.name}</h3>
      <span className="inline-block rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 capitalize">
        {agent.role.replace('_', ' ')}
      </span>
      <p className="mt-3 line-clamp-2 text-sm text-slate-600" title={agent.personality}>
        {agent.personality}
      </p>
      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPreviewVoice(agent.voiceId)}
          className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-200"
          aria-label="Preview voice"
        >
          {isPreviewing ? <Pause size={14} /> : <Play size={14} />}
          {voiceShort}
        </button>
      </div>
      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => onEdit(agent)}
          className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          <Edit3 size={12} className="mr-1 inline" /> Edit
        </button>
        <button
          type="button"
          onClick={() => onRegenerate(agent.id)}
          className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          <RotateCcw size={12} className="mr-1 inline" /> Regen
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/maic/AgentCard.tsx frontend/src/components/maic/__tests__/AgentCard.test.tsx
git commit -m "feat(maic): AgentCard component"
```

### Task 3.3: Create AgentEditModal

**Files:** Create `frontend/src/components/maic/AgentEditModal.tsx`

- [ ] **Step 1: Write component**

```tsx
import { useState, useEffect } from 'react';
import type { MAICAgent } from '../../types/maic';

interface Voice {
  id: string;
  gender: string;
  tone: string;
  suits: string[];
}

interface AgentEditModalProps {
  agent: MAICAgent;
  voices: Voice[];
  onSave: (agent: MAICAgent) => void;
  onCancel: () => void;
}

export function AgentEditModal({ agent, voices, onSave, onCancel }: AgentEditModalProps) {
  const [draft, setDraft] = useState<MAICAgent>(agent);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setDraft(agent), [agent]);

  const validVoices = voices.filter(v => v.suits.includes(draft.role));

  function handleSave() {
    if (!draft.name.trim()) { setError('Name is required'); return; }
    if (draft.personality.length > 500) { setError('Personality too long (max 500 chars)'); return; }
    if (draft.speakingStyle.length > 200) { setError('Speaking style too long (max 200 chars)'); return; }
    onSave(draft);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">Edit agent</h2>

        <label className="mb-3 block">
          <span className="mb-1 block text-xs font-medium text-slate-700">Name</span>
          <input
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            value={draft.name}
            onChange={e => setDraft({ ...draft, name: e.target.value })}
          />
        </label>

        <label className="mb-3 block">
          <span className="mb-1 block text-xs font-medium text-slate-700">Personality</span>
          <textarea
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            rows={3}
            maxLength={500}
            value={draft.personality}
            onChange={e => setDraft({ ...draft, personality: e.target.value })}
          />
          <span className="text-xs text-slate-400">{draft.personality.length}/500</span>
        </label>

        <label className="mb-3 block">
          <span className="mb-1 block text-xs font-medium text-slate-700">Speaking style</span>
          <textarea
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            rows={2}
            maxLength={200}
            value={draft.speakingStyle}
            onChange={e => setDraft({ ...draft, speakingStyle: e.target.value })}
          />
          <span className="text-xs text-slate-400">{draft.speakingStyle.length}/200</span>
        </label>

        <label className="mb-3 block">
          <span className="mb-1 block text-xs font-medium text-slate-700">Voice</span>
          <select
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            value={draft.voiceId}
            onChange={e => setDraft({ ...draft, voiceId: e.target.value })}
          >
            {validVoices.map(v => (
              <option key={v.id} value={v.id}>
                {v.id.replace('en-IN-', '').replace('Neural', '')} — {v.gender}, {v.tone}
              </option>
            ))}
          </select>
        </label>

        {error && <p className="mb-3 text-xs text-red-600">{error}</p>}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/maic/AgentEditModal.tsx
git commit -m "feat(maic): AgentEditModal component"
```

### Task 3.4: Create AgentGenerationStep

**Files:** Create `frontend/src/components/maic/AgentGenerationStep.tsx`

- [ ] **Step 1: Write component**

```tsx
import { useState, useEffect, useRef } from 'react';
import { maicApi, maicStudentApi } from '../../services/openmaicService';
import { AgentCard } from './AgentCard';
import { AgentEditModal } from './AgentEditModal';
import type { MAICAgent } from '../../types/maic';

interface Voice {
  id: string;
  gender: string;
  tone: string;
  age: string;
  suits: string[];
}

interface Props {
  topic: string;
  language: string;
  role: 'teacher' | 'student';
  onComplete: (agents: MAICAgent[]) => void;
  onBack: () => void;
}

const DEFAULT_ROLE_SLOTS = [
  { role: 'professor', count: 1 },
  { role: 'teaching_assistant', count: 1 },
  { role: 'student', count: 2 },
];

const PREVIEW_SENTENCE = "Hello students, I'm excited to teach you about this topic today.";

export function AgentGenerationStep({ topic, language, role, onComplete, onBack }: Props) {
  const api = role === 'student' ? maicStudentApi : maicApi;

  const [agents, setAgents] = useState<MAICAgent[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<MAICAgent | null>(null);
  const [regenIds, setRegenIds] = useState<Set<string>>(new Set());
  const [previewingVoice, setPreviewingVoice] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Load voices once
  useEffect(() => {
    maicApi.listVoices().then(r => setVoices(r.data.voices)).catch(() => {});
  }, []);

  // Generate agents on mount
  useEffect(() => {
    generateAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function generateAll() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.generateAgentProfiles({
        topic,
        language,
        roleSlots: DEFAULT_ROLE_SLOTS,
      });
      setAgents(r.data.agents);
    } catch (e) {
      setError("Couldn't generate agents. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegenerate(agentId: string) {
    setRegenIds(prev => new Set(prev).add(agentId));
    try {
      const r = await api.regenerateAgent({
        topic,
        existingAgents: agents,
        targetAgentId: agentId,
        lockedFields: [],
      });
      setAgents(prev => prev.map(a => a.id === agentId ? r.data.agent : a));
    } catch (e) {
      // toast
    } finally {
      setRegenIds(prev => {
        const next = new Set(prev);
        next.delete(agentId);
        return next;
      });
    }
  }

  async function handlePreviewVoice(voiceId: string) {
    if (previewingVoice === voiceId) {
      audioRef.current?.pause();
      setPreviewingVoice(null);
      return;
    }
    audioRef.current?.pause();
    try {
      const blob = await maicApi.ttsPreview({ voiceId, text: PREVIEW_SENTENCE });
      const url = URL.createObjectURL(blob.data);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        setPreviewingVoice(null);
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setPreviewingVoice(null);
        URL.revokeObjectURL(url);
      };
      await audio.play();
      setPreviewingVoice(voiceId);
    } catch (e) {
      // toast: preview unavailable
    }
  }

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, []);

  if (loading) {
    return (
      <div className="py-12 text-center">
        <div className="mb-3 text-lg text-slate-700">Meeting your agents…</div>
        <div className="text-sm text-slate-500">This takes about 10 seconds.</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-12 text-center">
        <p className="mb-4 text-sm text-red-600">{error}</p>
        <button type="button" onClick={generateAll} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <h2 className="mb-1 text-xl font-semibold text-slate-900">Meet your classroom</h2>
      <p className="mb-6 text-sm text-slate-600">
        Your AI classroom has {agents.length} agents. Preview their voices, tweak personas, or regenerate.
      </p>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {agents.map(a => (
          <AgentCard
            key={a.id}
            agent={a}
            onEdit={setEditing}
            onRegenerate={handleRegenerate}
            onPreviewVoice={handlePreviewVoice}
            isPreviewing={previewingVoice === a.voiceId}
            isRegenerating={regenIds.has(a.id)}
          />
        ))}
      </div>

      <div className="mt-6 flex items-center justify-between">
        <button
          type="button"
          onClick={() => {
            if (confirm('Regenerate all agents? This will discard your edits.')) generateAll();
          }}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          ↻ Regenerate all
        </button>
        <div className="flex gap-2">
          <button type="button" onClick={onBack} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
            ← Back
          </button>
          <button type="button" onClick={() => onComplete(agents)} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700">
            Looks good →
          </button>
        </div>
      </div>

      {editing && (
        <AgentEditModal
          agent={editing}
          voices={voices}
          onSave={(updated) => {
            setAgents(prev => prev.map(a => a.id === updated.id ? updated : a));
            setEditing(null);
          }}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/maic/AgentGenerationStep.tsx
git commit -m "feat(maic): AgentGenerationStep wizard step"
```

### Task 3.5: Write Vitest for AgentGenerationStep

**Files:** Create `frontend/src/components/maic/__tests__/AgentGenerationStep.test.tsx`

- [ ] **Step 1: Write test**

```tsx
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { AgentGenerationStep } from '../AgentGenerationStep';
import * as svc from '../../../services/openmaicService';

vi.mock('../../../services/openmaicService');

const mockAgents = [
  { id: 'agent-1', name: 'Dr. Aarav Sharma', role: 'professor', avatar: '👨‍🏫', color: '#4338CA',
    voiceId: 'en-IN-PrabhatNeural', voiceProvider: 'azure' as const,
    personality: 'Patient.', expertise: 'Leads.', speakingStyle: 'Warm.' },
];

test('loads agents on mount and shows them', async () => {
  (svc.maicApi.generateAgentProfiles as any).mockResolvedValue({ data: { agents: mockAgents } });
  (svc.maicApi.listVoices as any).mockResolvedValue({ data: { voices: [] } });

  render(<AgentGenerationStep topic="X" language="en" role="teacher" onComplete={vi.fn()} onBack={vi.fn()} />);

  await waitFor(() => expect(screen.getByText('Dr. Aarav Sharma')).toBeInTheDocument());
});

test('Looks good → calls onComplete with current agents', async () => {
  (svc.maicApi.generateAgentProfiles as any).mockResolvedValue({ data: { agents: mockAgents } });
  (svc.maicApi.listVoices as any).mockResolvedValue({ data: { voices: [] } });

  const onComplete = vi.fn();
  render(<AgentGenerationStep topic="X" language="en" role="teacher" onComplete={onComplete} onBack={vi.fn()} />);

  await waitFor(() => screen.getByText('Dr. Aarav Sharma'));
  fireEvent.click(screen.getByRole('button', { name: /Looks good/i }));
  expect(onComplete).toHaveBeenCalledWith(mockAgents);
});

test('Regenerate all asks for confirm', async () => {
  (svc.maicApi.generateAgentProfiles as any).mockResolvedValue({ data: { agents: mockAgents } });
  (svc.maicApi.listVoices as any).mockResolvedValue({ data: { voices: [] } });

  const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<AgentGenerationStep topic="X" language="en" role="teacher" onComplete={vi.fn()} onBack={vi.fn()} />);

  await waitFor(() => screen.getByText('Dr. Aarav Sharma'));
  fireEvent.click(screen.getByRole('button', { name: /Regenerate all/i }));
  expect(confirmSpy).toHaveBeenCalled();
});
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/maic/__tests__/AgentGenerationStep.test.tsx
git commit -m "test(maic): AgentGenerationStep"
```

### Task 3.6: Wire into MAICCreatePage

**Files:** Modify `frontend/src/pages/teacher/MAICCreatePage.tsx`

- [ ] **Step 1: Add wizard step state**

At top, in the wizard's step enum / state:
```ts
type Step = 'topic' | 'config' | 'agents' | 'outline' | 'content' | 'publish';
```

- [ ] **Step 2: Insert `<AgentGenerationStep>` between 'config' and 'outline'**

```tsx
{step === 'agents' && (
  <AgentGenerationStep
    topic={topic}
    language={language}
    role="teacher"
    onBack={() => setStep('config')}
    onComplete={(agents) => {
      setAgents(agents);                     // store in wizard state / maicStageStore
      setStep('outline');
    }}
  />
)}
```

- [ ] **Step 3: Pass `agents` into outline generation request body**

Find the outline-generation hook call (`useMAICGeneration`), ensure it sends `agents` in the body.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/teacher/MAICCreatePage.tsx
git commit -m "feat(maic): wizard adds agent step"
```

### Task 3.7: Wire into StudentMAICCreatePage

**Files:** Modify `frontend/src/pages/student/StudentMAICCreatePage.tsx`

- [ ] **Step 1: Mirror Task 3.6 with `role="student"`**

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/student/StudentMAICCreatePage.tsx
git commit -m "feat(maic): student wizard adds agent step"
```

### Task 3.8: E2E wizard test

**Files:** Create `e2e/tests/maic-agent-wizard.spec.ts`

- [ ] **Step 1: Write Playwright test**

```ts
import { test, expect } from '@playwright/test';

test('teacher wizard generates and edits agents', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[name="email"]', 'teacher@demo.test');
  await page.fill('input[name="password"]', 'demo1234');
  await page.click('button[type="submit"]');

  await page.goto('/teacher/ai-classroom/new');
  await page.fill('input[name="topic"]', 'Photosynthesis');
  await page.click('text=/Next/i');   // to config
  await page.click('text=/Next/i');   // to agents

  // 4 cards appear within 30s
  await expect(page.locator('[data-testid="agent-card"]')).toHaveCount(4, { timeout: 30000 });

  // Every name starts with Dr./Prof./Ms./Mr. or is a first-name (students)
  const names = await page.locator('[data-testid="agent-card"] h3').allTextContents();
  expect(names.filter(n => /^(Dr\.|Prof\.|Ms\.|Mr\.)/.test(n)).length).toBeGreaterThanOrEqual(2);

  // Voice preview
  await page.locator('[data-testid="agent-card"]:first-child button[aria-label="Preview voice"]').click();
  // Audio element should have been created — allow 5s of playback
  await page.waitForTimeout(3000);

  // Edit first card
  await page.locator('[data-testid="agent-card"]:first-child button:has-text("Edit")').click();
  await page.fill('input[value*="Dr."]', 'Dr. Test Agent');
  await page.click('button:has-text("Save")');
  await expect(page.locator('text=Dr. Test Agent')).toBeVisible();

  // Proceed
  await page.click('button:has-text("Looks good")');
  await page.waitForURL(/outline|review/i);
});
```

- [ ] **Step 2: Commit**

```bash
git add e2e/tests/maic-agent-wizard.spec.ts
git commit -m "test(maic): e2e wizard agent step"
```

### Task 3.9: Chunk 3 checkpoint

- [ ] **Step 1: Run Vitests**

Run: `cd frontend && npx vitest run src/components/maic/__tests__/`
Expected: green.

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

---

## Chunk 4: WS-D Pre-gen Audio Pipeline + maic_views ownership

**Owner subagent:** `Backend-Bugs`
**Est:** 1.3d + 0.2d for the moved tasks = 1.5d
**Depends on:** Chunks 1 + 2 merged (for MAICAgent voiceId, AgentValidationError imports, generate_outline_sse new signature).

### Task 4.0: Backend audit — verify student decorators

Moved from Chunk 1 Task 1.11 (file-ownership: Chunk 4 owns maic_views.py).

**Files:** Read + possibly modify `backend/apps/courses/maic_views.py`

- [ ] **Step 1: Grep for decorator assignment on student views**

Run: `grep -n "@teacher_or_admin\|@student_or_admin\|def student_maic" backend/apps/courses/maic_views.py`

- [ ] **Step 2: Confirm these four all use `@student_or_admin`**

- `student_maic_chat`
- `student_maic_generate_tts`
- `student_maic_generate_scene_actions`
- `student_maic_quiz_grade`

- [ ] **Step 3: If any use `@teacher_or_admin`, fix + commit**

```bash
git add backend/apps/courses/maic_views.py
git commit -m "fix(maic): student views use @student_or_admin decorator"
```

### Task 4.1: Update outline views to require agents input

Moved from Chunk 2 Task 2.7 Step 4 (file-ownership: Chunk 4 owns maic_views.py).

**Files:** Modify `backend/apps/courses/maic_views.py` — teacher + student outline view functions

- [ ] **Step 1: Find `teacher_maic_generate_outlines` and `student_maic_generate_outlines`**

Each function currently calls `generate_outline_sse(topic, language, agent_count, scene_count, pdf_text, config)` after parsing the body.

- [ ] **Step 2: Change the signature callers use**

Replace the call with:

```python
body = json.loads(request.body or b"{}")
agents_input = body.get("agents") or []
if not agents_input:
    return HttpResponse(
        json.dumps({"error": "No agents provided. Generate agents first."}),
        status=400, content_type="application/json",
    )
# ... existing topic, language, scene_count extraction
return StreamingHttpResponse(
    generate_outline_sse(
        topic=topic,
        language=language,
        agents=agents_input,
        scene_count=scene_count,
        pdf_text=pdf_text,
        config=config,
    ),
    content_type="text/event-stream",
)
```

- [ ] **Step 3: Commit**

```bash
git add backend/apps/courses/maic_views.py
git commit -m "feat(maic): outline views require agents input"
```

### Task 4.2: Add publish endpoint skeleton

**Files:** Modify `backend/apps/courses/maic_views.py`, `backend/apps/courses/maic_urls.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/courses/test_maic_pregen.py`:

```python
import hashlib
import pytest
from unittest.mock import patch
from apps.courses.maic_models import MAICClassroom, TenantAIConfig

pytestmark = pytest.mark.django_db


@pytest.fixture
def classroom_with_content(tenant, user_factory):
    teacher = user_factory(tenant=tenant, role="TEACHER")
    ai = TenantAIConfig.objects.create(tenant=tenant, llm_provider="openrouter",
                                       llm_model="openai/gpt-4o-mini", maic_enabled=True)
    return MAICClassroom.objects.create(
        tenant=tenant, creator=teacher,
        title="Test", topic="Test topic", status="DRAFT",
        content={
            "agents": [
                {"id": "agent-1", "name": "Dr. X", "role": "professor",
                 "voiceId": "en-IN-PrabhatNeural", "voiceProvider": "azure",
                 "avatar": "👨‍🏫", "color": "#4338CA",
                 "personality": "P", "expertise": "E", "speakingStyle": "S"},
            ],
            "scenes": [
                {"id": "scene-1", "title": "Intro", "type": "introduction",
                 "actions": [
                     {"type": "speech", "agentId": "agent-1", "text": "Hello"},
                     {"type": "speech", "agentId": "agent-1", "text": "Welcome"},
                 ]},
            ],
        },
    ), teacher


def test_publish_transitions_status_and_enqueues(client, classroom_with_content, tenant):
    classroom, teacher = classroom_with_content
    client.force_authenticate(teacher)
    with patch("apps.courses.maic_tasks.pre_generate_classroom_tts.delay") as mock_delay:
        r = client.post(
            f"/api/v1/teacher/maic/classrooms/{classroom.id}/publish/",
            HTTP_HOST=f"{tenant.subdomain}.localhost",
        )
    assert r.status_code == 202
    mock_delay.assert_called_once_with(str(classroom.id))
    classroom.refresh_from_db()
    assert classroom.status == "GENERATING"
    assert classroom.content["audioManifest"]["status"] == "generating"
    assert classroom.content["audioManifest"]["totalActions"] == 2
    # Each speech action gets audioId + voiceId stamped
    for action in classroom.content["scenes"][0]["actions"]:
        assert "audioId" in action
        assert len(action["audioId"]) == 12
        assert action["voiceId"] == "en-IN-PrabhatNeural"


def test_publish_rejects_while_generating(client, classroom_with_content, tenant):
    classroom, teacher = classroom_with_content
    classroom.status = "GENERATING"
    classroom.save()
    client.force_authenticate(teacher)
    r = client.post(
        f"/api/v1/teacher/maic/classrooms/{classroom.id}/publish/",
        HTTP_HOST=f"{tenant.subdomain}.localhost",
    )
    assert r.status_code == 409
```

- [ ] **Step 2: Add handler in maic_views.py**

```python
import hashlib
from django.db import transaction

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_classroom_publish(request, classroom_id):
    """Trigger pre-gen audio pipeline; transitions DRAFT/READY → GENERATING → READY."""
    with transaction.atomic():
        try:
            classroom = MAICClassroom.objects.select_for_update().get(
                pk=classroom_id, tenant=request.tenant, creator=request.user,
            )
        except MAICClassroom.DoesNotExist:
            return Response({"error": "Classroom not found."}, status=404)

        if classroom.status == "GENERATING":
            return Response({"error": "Publish already in progress."}, status=409)

        content = classroom.content or {}
        scenes = content.get("scenes", [])
        agents_by_id = {a["id"]: a for a in content.get("agents", [])}

        # Walk speech actions, stamp audioId + voiceId
        total = 0
        for scene_idx, scene in enumerate(scenes):
            actions = scene.get("actions", [])
            for action_idx, action in enumerate(actions):
                if action.get("type") != "speech":
                    continue
                agent_id = action.get("agentId")
                agent = agents_by_id.get(agent_id, {})
                voice_id = agent.get("voiceId") or "en-IN-NeerjaNeural"
                action["voiceId"] = voice_id
                payload = f"{scene.get('id', scene_idx)}|{action_idx}|{action.get('text', '')}|{voice_id}"
                action["audioId"] = hashlib.sha256(payload.encode()).hexdigest()[:12]
                total += 1

        content["audioManifest"] = {
            "status": "generating",
            "progress": 0,
            "totalActions": total,
            "completedActions": 0,
            "failedAudioIds": [],
            "generatedAt": None,
        }
        classroom.content = content
        classroom.status = "GENERATING"
        classroom.save(update_fields=["content", "status", "updated_at"])

    # Enqueue after the transaction commits
    from apps.courses.maic_tasks import pre_generate_classroom_tts
    pre_generate_classroom_tts.delay(str(classroom.id))

    return Response({"audioManifest": content["audioManifest"]}, status=202)
```

- [ ] **Step 3: Wire URL**

In `maic_urls.py` teacher_urlpatterns, add:
```python
path("classrooms/<uuid:classroom_id>/publish/", maic_views.teacher_maic_classroom_publish, name="teacher_maic_classroom_publish"),
```

- [ ] **Step 4: Run test — expect PASS**

Run: `cd backend && pytest tests/courses/test_maic_pregen.py -v -k "test_publish_transitions_status_and_enqueues or test_publish_rejects_while_generating"`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/courses/maic_views.py backend/apps/courses/maic_urls.py backend/tests/courses/test_maic_pregen.py
git commit -m "feat(maic): classroom publish endpoint"
```

### Task 4.3: Rewrite pre_generate_classroom_tts

**Files:** Modify `backend/apps/courses/maic_tasks.py`

- [ ] **Step 1: Write failing test**

Append to `test_maic_pregen.py`:

```python
from apps.courses.maic_tasks import pre_generate_classroom_tts


def test_pregen_stamps_audio_urls_and_marks_ready(classroom_with_content, settings):
    classroom, _ = classroom_with_content
    classroom.status = "GENERATING"
    classroom.content["audioManifest"] = {
        "status": "generating", "progress": 0,
        "totalActions": 2, "completedActions": 0, "failedAudioIds": [], "generatedAt": None,
    }
    for i, action in enumerate(classroom.content["scenes"][0]["actions"]):
        action["audioId"] = f"hash{i:08x}"
        action["voiceId"] = "en-IN-PrabhatNeural"
    classroom.save()

    with patch("apps.courses.maic_tasks.generate_tts_audio", return_value=b"fake-mp3-bytes") as mock_tts, \
         patch("apps.courses.maic_tasks.storage_upload", return_value="/media/foo.mp3") as mock_upload:
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()
    assert classroom.status == "READY"
    assert classroom.content["audioManifest"]["status"] == "ready"
    assert classroom.content["audioManifest"]["completedActions"] == 2
    for action in classroom.content["scenes"][0]["actions"]:
        assert action["audioUrl"] == "/media/foo.mp3"


def test_pregen_retries_transient_failure(classroom_with_content):
    classroom, _ = classroom_with_content
    classroom.status = "GENERATING"
    classroom.content["audioManifest"] = {
        "status": "generating", "progress": 0,
        "totalActions": 1, "completedActions": 0, "failedAudioIds": [], "generatedAt": None,
    }
    classroom.content["scenes"][0]["actions"] = [classroom.content["scenes"][0]["actions"][0]]
    classroom.content["scenes"][0]["actions"][0]["audioId"] = "abc"
    classroom.content["scenes"][0]["actions"][0]["voiceId"] = "en-IN-PrabhatNeural"
    classroom.save()

    calls = [0]
    def flaky(*args, **kwargs):
        calls[0] += 1
        if calls[0] < 2:
            raise RuntimeError("transient")
        return b"mp3-bytes"

    with patch("apps.courses.maic_tasks.generate_tts_audio", side_effect=flaky), \
         patch("apps.courses.maic_tasks.storage_upload", return_value="/media/x.mp3"), \
         patch("apps.courses.maic_tasks.time.sleep"):
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()
    assert classroom.content["scenes"][0]["actions"][0]["audioUrl"] == "/media/x.mp3"
    assert calls[0] == 2  # first attempt failed, second succeeded


def test_pregen_partial_status_on_some_failures(classroom_with_content):
    classroom, _ = classroom_with_content
    classroom.status = "GENERATING"
    classroom.content["audioManifest"] = {
        "status": "generating", "progress": 0,
        "totalActions": 2, "completedActions": 0, "failedAudioIds": [], "generatedAt": None,
    }
    for i, action in enumerate(classroom.content["scenes"][0]["actions"]):
        action["audioId"] = f"hash{i}"
        action["voiceId"] = "en-IN-PrabhatNeural"
    classroom.save()

    results = [b"ok", None]  # second returns empty → failure
    def tts(*a, **kw):
        return results.pop(0)

    with patch("apps.courses.maic_tasks.generate_tts_audio", side_effect=tts), \
         patch("apps.courses.maic_tasks.storage_upload", return_value="/media/ok.mp3"), \
         patch("apps.courses.maic_tasks.time.sleep"):
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()
    assert classroom.status == "READY"  # still playable
    assert classroom.content["audioManifest"]["status"] == "partial"
    assert len(classroom.content["audioManifest"]["failedAudioIds"]) == 1
```

- [ ] **Step 2: Rewrite the Celery task**

Replace `pre_generate_classroom_tts` in `maic_tasks.py`:

```python
import time
import logging
from datetime import datetime, timezone

from celery import shared_task
from apps.courses.maic_models import MAICClassroom, TenantAIConfig
from apps.courses.maic_generation_service import generate_tts_audio
from apps.courses.maic_storage import storage_upload  # see helper below

logger = logging.getLogger(__name__)


@shared_task(name="apps.courses.maic_tasks.pre_generate_classroom_tts")
def pre_generate_classroom_tts(classroom_id: str):
    """Pre-generate TTS audio for every speech action. Idempotent on re-run.

    Writes progress to classroom.content.audioManifest every 5 actions so the UI can poll.
    """
    classroom = MAICClassroom.objects.get(id=classroom_id)
    content = classroom.content or {}
    scenes = content.get("scenes", [])
    manifest = content.setdefault("audioManifest", {
        "status": "generating", "progress": 0,
        "totalActions": 0, "completedActions": 0, "failedAudioIds": [], "generatedAt": None,
    })
    config = TenantAIConfig.objects.get(tenant=classroom.tenant)

    speech_actions = [
        (scene_idx, action_idx, action)
        for scene_idx, scene in enumerate(scenes)
        for action_idx, action in enumerate(scene.get("actions", []))
        if action.get("type") == "speech"
    ]
    total = len(speech_actions)
    manifest["totalActions"] = total

    completed = 0
    failed = []

    for scene_idx, action_idx, action in speech_actions:
        audio_id = action["audioId"]
        voice_id = action["voiceId"]
        storage_key = f"tenant/{classroom.tenant_id}/maic/tts/{classroom_id}/{audio_id}.mp3"

        # Skip if already generated (idempotent re-publish)
        if action.get("audioUrl"):
            completed += 1
            continue

        audio_bytes = None
        for attempt in range(3):
            try:
                audio_bytes = generate_tts_audio(action["text"], config, voice_id=voice_id)
                if audio_bytes:
                    break
            except Exception as e:
                logger.warning("TTS attempt %d failed for %s: %s", attempt + 1, audio_id, e)
                if attempt < 2:
                    time.sleep(2 ** attempt)

        if audio_bytes:
            try:
                url = storage_upload(storage_key, audio_bytes, "audio/mpeg")
                content["scenes"][scene_idx]["actions"][action_idx]["audioUrl"] = url
            except Exception as e:
                logger.error("Storage upload failed for %s: %s", audio_id, e)
                failed.append(audio_id)
        else:
            failed.append(audio_id)

        completed += 1

        # Checkpoint every 5 actions
        if completed % 5 == 0 or completed == total:
            manifest["progress"] = int(completed / total * 100) if total else 100
            manifest["completedActions"] = completed
            manifest["failedAudioIds"] = list(failed)
            classroom.content = content
            classroom.save(update_fields=["content", "updated_at"])

    # Finalize
    if not failed:
        manifest["status"] = "ready"
        classroom.status = "READY"
    elif len(failed) < total:
        manifest["status"] = "partial"
        classroom.status = "READY"
    else:
        manifest["status"] = "failed"
        classroom.status = "FAILED"

    manifest["generatedAt"] = datetime.now(timezone.utc).isoformat()
    manifest["completedActions"] = completed
    manifest["failedAudioIds"] = list(failed)
    classroom.content = content
    classroom.save(update_fields=["content", "status", "updated_at"])
```

- [ ] **Step 3: Create storage helper**

Create `backend/apps/courses/maic_storage.py`:

```python
"""Storage abstraction for MAIC TTS files.

Uses Django's default_storage. Swaps local vs S3 based on settings.
"""
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def storage_upload(key: str, data: bytes, content_type: str = "audio/mpeg") -> str:
    """Upload bytes to storage; return public URL."""
    if default_storage.exists(key):
        default_storage.delete(key)
    default_storage.save(key, ContentFile(data))
    return default_storage.url(key)


def storage_exists(key: str) -> bool:
    return default_storage.exists(key)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd backend && pytest tests/courses/test_maic_pregen.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/courses/maic_tasks.py backend/apps/courses/maic_storage.py backend/tests/courses/test_maic_pregen.py
git commit -m "feat(maic): pre-gen TTS pipeline with retries + manifest"
```

### Task 4.4: Gate student visibility on audioManifest

**Files:** Modify `backend/apps/courses/maic_views.py:800` (`student_maic_classroom_list`) and `:853` (`student_maic_classroom_detail`)

- [ ] **Step 1: Add filter**

In both functions, add after the existing `status=READY` filter:

```python
# Postgres 15 JSONB filter (project uses Postgres 15 per CLAUDE.md).
from django.db.models import Q
qs = qs.filter(
    status="READY",
).filter(
    Q(content__audioManifest__status="ready") |
    Q(content__audioManifest__status="partial"),
)
```

- [ ] **Step 2: Write test**

Append to `test_maic_pregen.py`:

```python
def test_student_cannot_see_classroom_mid_generation(client, classroom_with_content, tenant, user_factory):
    classroom, _ = classroom_with_content
    classroom.status = "READY"
    classroom.is_public = True
    classroom.content["audioManifest"] = {
        "status": "generating", "progress": 50,
        "totalActions": 2, "completedActions": 1, "failedAudioIds": [], "generatedAt": None,
    }
    classroom.save()

    student = user_factory(tenant=tenant, role="STUDENT")
    client.force_authenticate(student)
    r = client.get(
        "/api/v1/student/maic/classrooms/",
        HTTP_HOST=f"{tenant.subdomain}.localhost",
    )
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert str(classroom.id) not in ids

    # Flip to ready → now visible
    classroom.content["audioManifest"]["status"] = "ready"
    classroom.save()
    r = client.get(
        "/api/v1/student/maic/classrooms/",
        HTTP_HOST=f"{tenant.subdomain}.localhost",
    )
    ids = [c["id"] for c in r.json()]
    assert str(classroom.id) in ids
```

- [ ] **Step 3: Run + commit**

```bash
cd backend && pytest tests/courses/test_maic_pregen.py::test_student_cannot_see_classroom_mid_generation -v
git add backend/apps/courses/maic_views.py backend/tests/courses/test_maic_pregen.py
git commit -m "feat(maic): gate student visibility on audioManifest ready/partial"
```

### Task 4.5: Expose manifest in teacher detail endpoint

**Files:** Modify `backend/apps/courses/maic_views.py:556` (`teacher_maic_classroom_detail`)

- [ ] **Step 1: Include `audioManifest` in response**

Find the Response(...) call and add:
```python
"audioManifest": (classroom.content or {}).get("audioManifest"),
```

- [ ] **Step 2: Commit**

```bash
git add backend/apps/courses/maic_views.py
git commit -m "feat(maic): teacher detail surfaces audioManifest"
```

### Task 4.6: Add voices endpoint

**Files:** Modify `backend/apps/courses/maic_views.py`, `backend/apps/courses/maic_urls.py`, `backend/config/urls.py`

- [ ] **Step 1: Handler**

In `maic_views.py`:

```python
from apps.courses.maic_voices import AZURE_IN_VOICES

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def maic_list_voices(request):
    return Response({"voices": AZURE_IN_VOICES})
```

- [ ] **Step 2: URL — wire into `backend/apps/courses/urls.py` (confirmed pattern)**

`backend/apps/courses/urls.py` is the root courses router already mounted at `courses/` in `backend/config/urls.py:24`. Add to the `urlpatterns` list:

```python
from . import maic_views

urlpatterns = [
    # ... existing
    # MAIC public endpoints (logged-in users, any role)
    path('maic/voices/', maic_views.maic_list_voices, name='maic_list_voices'),
]
```

This exposes the endpoint at `/api/courses/maic/voices/`. Frontend's `openmaicService.ts` must call this path. If a cleaner `/api/v1/maic/voices/` is preferred, update `backend/config/urls.py:24` to add:

```python
path('api/v1/maic/', include('apps.courses.maic_public_urls')),
```

— and create `maic_public_urls.py` as a one-line `urlpatterns = [path('voices/', maic_views.maic_list_voices)]`. Pick one approach and commit.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/courses/maic_views.py backend/apps/courses/maic_urls.py backend/config/urls.py
git commit -m "feat(maic): public voices list endpoint"
```

### Task 4.7: Agent-profile & regenerate-one & TTS-preview endpoints

**Files:** Modify `backend/apps/courses/maic_views.py`, `backend/apps/courses/maic_urls.py`

- [ ] **Step 1: Handlers**

```python
from apps.courses.maic_generation_service import (
    generate_agent_profiles_json, regenerate_one_agent, AgentValidationError, generate_tts_audio,
)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_generate_agent_profiles(request):
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    body = request.data
    try:
        result = generate_agent_profiles_json(
            topic=body.get("topic", ""),
            language=body.get("language", "en"),
            role_slots=body.get("roleSlots", []),
            config=config,
        )
        return Response(result, status=200)
    except AgentValidationError as e:
        return Response({"error": str(e)}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_regenerate_one_agent(request):
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    body = request.data
    try:
        result = regenerate_one_agent(
            topic=body.get("topic", ""),
            language=body.get("language", "en"),
            existing_agents=body.get("existingAgents", []),
            target_agent_id=body.get("targetAgentId", ""),
            locked_fields=body.get("lockedFields", []),
            config=config,
        )
        return Response(result, status=200)
    except AgentValidationError as e:
        return Response({"error": str(e)}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_tts_preview(request):
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    body = request.data
    voice_id = body.get("voiceId")
    text = body.get("text", "")[:200]  # cap length
    audio_bytes = generate_tts_audio(text, config, voice_id=voice_id)
    if not audio_bytes:
        return HttpResponse(status=204)
    return HttpResponse(audio_bytes, content_type="audio/mpeg")
```

- [ ] **Step 2: Student variants — extract shared helpers to avoid double-decoration**

Refactor: move the logic of `teacher_maic_generate_agent_profiles` / `teacher_maic_regenerate_one_agent` into plain (non-decorated) helper functions; have both the teacher and student view functions call the helper. This prevents decorators from firing twice when the student variant calls the teacher view.

```python
def _generate_agent_profiles_impl(request, config):
    """Shared logic — NO decorators. Called from teacher + student views."""
    body = request.data
    try:
        result = generate_agent_profiles_json(
            topic=body.get("topic", ""),
            language=body.get("language", "en"),
            role_slots=body.get("roleSlots", []),
            config=config,
        )
        return Response(result, status=200)
    except AgentValidationError as e:
        return Response({"error": str(e)}, status=500)


def _regenerate_one_agent_impl(request, config):
    body = request.data
    try:
        result = regenerate_one_agent(
            topic=body.get("topic", ""),
            language=body.get("language", "en"),
            existing_agents=body.get("existingAgents", []),
            target_agent_id=body.get("targetAgentId", ""),
            locked_fields=body.get("lockedFields", []),
            config=config,
        )
        return Response(result, status=200)
    except AgentValidationError as e:
        return Response({"error": str(e)}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_generate_agent_profiles(request):
    config, err = _get_ai_config(request.tenant)
    if err: return err
    return _generate_agent_profiles_impl(request, config)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_generate_agent_profiles(request):
    config, err = _get_ai_config(request.tenant)
    if err: return err
    return _generate_agent_profiles_impl(request, config)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_regenerate_one_agent(request):
    config, err = _get_ai_config(request.tenant)
    if err: return err
    return _regenerate_one_agent_impl(request, config)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_regenerate_one_agent(request):
    config, err = _get_ai_config(request.tenant)
    if err: return err
    return _regenerate_one_agent_impl(request, config)
```

- [ ] **Step 3: Wire URLs**

Teacher:
```python
path("agents/regenerate-one/", maic_views.teacher_maic_regenerate_one_agent, name="teacher_maic_regenerate_one_agent"),
path("tts/preview/", maic_views.teacher_maic_tts_preview, name="teacher_maic_tts_preview"),
```
(`generate/agent-profiles/` is already in the file; just implement the view.)

Student:
```python
path("generate/agent-profiles/", maic_views.student_maic_generate_agent_profiles, name="student_maic_generate_agent_profiles"),
path("agents/regenerate-one/", maic_views.student_maic_regenerate_one_agent, name="student_maic_regenerate_one_agent"),
```

- [ ] **Step 4: Commit**

```bash
git add backend/apps/courses/maic_views.py backend/apps/courses/maic_urls.py
git commit -m "feat(maic): agent-profile + regenerate-one + tts-preview endpoints"
```

### Task 4.8: Data migration for existing classrooms

**Files:** Create `backend/apps/courses/migrations/NNNN_maic_audio_manifest.py` (replace NNNN with the next number)

- [ ] **Step 1: Generate empty migration**

Run: `cd backend && python manage.py makemigrations courses --empty --name maic_audio_manifest`

- [ ] **Step 2: Write data migration**

```python
from django.db import migrations


def stamp_manifest(apps, schema_editor):
    MAICClassroom = apps.get_model("courses", "MAICClassroom")
    for c in MAICClassroom.objects.iterator():
        content = c.content or {}
        if "audioManifest" not in content:
            content["audioManifest"] = {
                "status": "idle", "progress": 0,
                "totalActions": 0, "completedActions": 0,
                "failedAudioIds": [], "generatedAt": None,
            }
            c.content = content
            c.save(update_fields=["content"])


def unstamp_manifest(apps, schema_editor):
    MAICClassroom = apps.get_model("courses", "MAICClassroom")
    for c in MAICClassroom.objects.iterator():
        if c.content and "audioManifest" in c.content:
            del c.content["audioManifest"]
            c.save(update_fields=["content"])


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0034_maicclassroom_content"),   # Latest at plan time (2026-04-16).
                                                      # If later migrations exist, update to the latest.
    ]
    operations = [
        migrations.RunPython(stamp_manifest, unstamp_manifest),
    ]
```

- [ ] **Step 3: Run migration**

Run: `cd backend && python manage.py migrate courses`
Expected: applied.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/courses/migrations/
git commit -m "migrate(maic): stamp audioManifest on existing classrooms"
```

### Task 4.9: Chunk 4 checkpoint

- [ ] **Step 1: Full Chunk 4 test run**

Run: `cd backend && pytest tests/courses/test_maic_pregen.py tests/courses/test_maic_agents.py -v`
Expected: all green.

---

## Chunk 5: WS-E Frontend Speech Rewrite

**Owner subagent:** `Frontend-Bugs+Engine` (continuation of Chunk 1's subagent)
**Est:** 1.2d
**Depends on:** Chunks 1 + 4 (for audioUrl field + publish endpoint available in test fixtures).

### Task 5.1: Add generationToken to MAICActionEngine

**Files:** Modify `frontend/src/lib/maicActionEngine.ts`

- [ ] **Step 1: Write failing unit test**

Create `frontend/src/lib/__tests__/maicActionEngine.test.ts`:

```ts
import { describe, test, expect, vi, beforeEach } from 'vitest';
import { MAICActionEngine } from '../maicActionEngine';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';

// Mock HTMLAudioElement with test-controllable end trigger
const mockAudios: MockAudio[] = [];
class MockAudio {
  src = ''; volume = 1; playbackRate = 1;
  onplaying: (() => void) | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  play = vi.fn().mockImplementation(() => {
    setTimeout(() => this.onplaying?.(), 10);
    return Promise.resolve();
  });
  pause = vi.fn();
  /** Test helper — lets tests explicitly trigger audio end. */
  endNow() { this.onended?.(); }
  constructor() { mockAudios.push(this); }
}
// @ts-expect-error
global.Audio = MockAudio;
beforeEach(() => { mockAudios.length = 0; });

describe('MAICActionEngine speech', () => {
  beforeEach(() => {
    useMAICStageStore.setState({ agents: [{ id: 'a1', name: 'X', role: 'professor', voiceId: 'en-IN-PrabhatNeural' } as any] });
    useMAICSettingsStore.setState({ audioVolume: 1, playbackSpeed: 1 });
  });

  test('subtitle fires on audio playing event, not before', async () => {
    const onStart = vi.fn();
    const engine = new MAICActionEngine({
      ttsEndpoint: '/tts',
      token: 't',
      onSpeechStart: onStart,
    });
    const promise = engine.execute({
      type: 'speech', agentId: 'a1', text: 'hi',
      audioUrl: 'https://example.com/a.mp3',
      audioId: 'abc', voiceId: 'en-IN-PrabhatNeural',
    } as any);

    // Before the mock's `playing` event fires (10ms timer), onStart should NOT have been called.
    await new Promise(r => setTimeout(r, 5));
    expect(onStart).not.toHaveBeenCalled();

    // After 15ms, `playing` fires → subtitle appears
    await new Promise(r => setTimeout(r, 15));
    expect(onStart).toHaveBeenCalledWith('a1', 'hi');

    // Trigger end → promise resolves
    mockAudios[0].endNow();
    await promise;
  });

  test('abortCurrentAction after speech starts prevents onended firing', async () => {
    const onEnd = vi.fn();
    const engine = new MAICActionEngine({
      ttsEndpoint: '/tts',
      token: 't',
      onSpeechEnd: onEnd,
    });
    engine.execute({
      type: 'speech', agentId: 'a1', text: 'hi',
      audioUrl: 'https://example.com/a.mp3',
    } as any);
    await new Promise(r => setTimeout(r, 15)); // let playing fire
    engine.abortCurrentAction();               // simulate scene change — nulls onended on audio
    // Attempt to fire end — handler was nulled, so no-op.
    // Direct call on the mock still works because endNow invokes onended which is null now.
    // Either way, onEnd should not have been called.
    expect(onEnd).not.toHaveBeenCalled();
  });

  test('rapid execute × 10 leaves one audioElement ref', async () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    for (let i = 0; i < 10; i++) {
      engine.execute({ type: 'speech', agentId: 'a1', text: `${i}`, audioUrl: `https://x/${i}.mp3` } as any);
      engine.abortCurrentAction();
    }
    // @ts-expect-error testing internal
    expect(engine.audioElement).toBeNull();
  });
});
```

- [ ] **Step 2: Run — expect fail**

Run: `cd frontend && npx vitest run src/lib/__tests__/maicActionEngine.test.ts`

- [ ] **Step 3: Modify actionEngine**

In `maicActionEngine.ts`, add private field:

```ts
private generationToken = 0;
```

Rewrite `abortCurrentAction`:

```ts
abortCurrentAction(): void {
  this.generationToken++;
  this.currentFetchController?.abort();
  if (this.audioElement) {
    this.audioElement.onplaying = null;
    this.audioElement.onended = null;
    this.audioElement.onerror = null;
    try { this.audioElement.pause(); } catch {}
    this.audioElement.src = '';
    this.audioElement = null;
  }
  this.currentFetchController = null;
  this.audioResolve = null;
  if (this.readingTimer) { clearTimeout(this.readingTimer); this.readingTimer = null; }
}
```

Add private field:
```ts
private readingTimer: ReturnType<typeof setTimeout> | null = null;
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/maicActionEngine.ts frontend/src/lib/__tests__/maicActionEngine.test.ts
git commit -m "feat(maic): generationToken + hardened abortCurrentAction"
```

### Task 5.2: Rewrite executeSpeech

**Files:** Modify `frontend/src/lib/maicActionEngine.ts`

- [ ] **Step 1: Replace `executeSpeech`**

```ts
private async executeSpeech(action: SpeechAction): Promise<void> {
  // Per-action token increment — each speech owns a unique token window.
  // stop() and loadScene() also call abortCurrentAction() which increments the same counter,
  // so any in-flight fetch/audio from a prior action or scene is neutered at the source.
  const myToken = ++this.generationToken;
  const { agentId, text, ssml } = action;

  const agents = this.stageStore.getState().agents;
  const agent = agents.find(a => a.id === agentId);
  const voiceId =
    (action as any).voiceId ||
    agent?.voiceId ||
    agent?.voice ||
    (agent?.role ? ROLE_VOICE_MAP[agent.role as keyof typeof ROLE_VOICE_MAP] : undefined) ||
    'en-IN-NeerjaNeural';

  const volume = this.settingsStore.getState().audioVolume;
  const playbackSpeed = this.settingsStore.getState().playbackSpeed;

  // 1. Preferred: pre-generated audio URL
  if (action.audioUrl) {
    return this.playAudioSynced(action.audioUrl, text, agentId, volume, playbackSpeed, myToken);
  }

  // 2. Fallback: live TTS fetch (chat/discussion, or pre-gen gap)
  const blobUrl = await this.fetchTtsBlob(ssml || text, voiceId, myToken);
  if (myToken !== this.generationToken) return;   // stale
  if (!blobUrl) {
    return this.readingTimeFallback(text, agentId, myToken);
  }
  try {
    await this.playAudioSynced(blobUrl, text, agentId, volume, playbackSpeed, myToken);
  } finally {
    URL.revokeObjectURL(blobUrl);
  }
}
```

- [ ] **Step 2: Add `fetchTtsBlob` helper extracted from existing code**

```ts
private async fetchTtsBlob(text: string, voiceId: string, token: number): Promise<string | null> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
  const url = `${baseUrl}${this.ttsEndpoint}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${this.token}`,
  };
  // (tenant subdomain injection preserved from original — keep the existing block here)

  this.currentFetchController = new AbortController();
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({ text, voiceId }),
      signal: this.currentFetchController.signal,
    });
    if (token !== this.generationToken) return null;
    if (res.status === 204 || !res.ok) return null;
    const blob = await res.blob();
    if (token !== this.generationToken) return null;
    if (blob.size === 0) return null;
    return URL.createObjectURL(blob);
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return null;
    return null;
  } finally {
    this.currentFetchController = null;
  }
}
```

- [ ] **Step 3: Add `playAudioSynced`**

```ts
private playAudioSynced(
  src: string, text: string, agentId: string,
  volume: number, playbackRate: number, token: number,
): Promise<void> {
  return new Promise((resolve) => {
    if (token !== this.generationToken) { resolve(); return; }

    const audio = new Audio();
    this.audioElement = audio;
    audio.src = src;
    audio.volume = volume;
    audio.playbackRate = playbackRate;

    audio.onplaying = () => {
      if (token !== this.generationToken) { audio.pause(); return; }
      this.onSpeechStart?.(agentId, text);
      this.stageStore.getState().setSpeakingAgent(agentId);
      this.stageStore.getState().setSpeechText(text);
    };
    audio.onended = () => {
      if (token !== this.generationToken) return;
      this.onSpeechEnd?.();
      this.stageStore.getState().setSpeakingAgent(null);
      this.stageStore.getState().setSpeechText(null);
      resolve();
    };
    audio.onerror = () => {
      if (token !== this.generationToken) return;
      this.onSpeechEnd?.();
      resolve();
    };
    audio.play().catch(() => {
      if (token !== this.generationToken) return;
      resolve();
    });
  });
}
```

- [ ] **Step 4: Add `readingTimeFallback`**

```ts
private readingTimeFallback(text: string, agentId: string, token: number): Promise<void> {
  return new Promise((resolve) => {
    if (token !== this.generationToken) { resolve(); return; }
    this.onSpeechStart?.(agentId, text);
    this.stageStore.getState().setSpeakingAgent(agentId);
    this.stageStore.getState().setSpeechText(text);
    const ms = Math.max(2000, text.length * 60);
    this.readingTimer = setTimeout(() => {
      if (token !== this.generationToken) return;
      this.onSpeechEnd?.();
      this.stageStore.getState().setSpeakingAgent(null);
      this.stageStore.getState().setSpeechText(null);
      resolve();
    }, ms);
  });
}
```

- [ ] **Step 5: Run Vitest**

Run: `cd frontend && npx vitest run src/lib/__tests__/maicActionEngine.test.ts`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/maicActionEngine.ts
git commit -m "feat(maic): rewrite executeSpeech with generationToken + subtitle-on-playing"
```

### Task 5.3: Fix checkpoint in playbackEngine + add seekToSlide

**Files:** Modify `frontend/src/lib/maicPlaybackEngine.ts`

- [ ] **Step 1: Fix checkpoint**

Change line 290 from:
```ts
this.checkpoint = { actionIndex: this.currentActionIndex };
```
to:
```ts
// Rewind -1 so the interrupted sentence replays on resume (matches OpenMAIC).
this.checkpoint = { actionIndex: Math.max(0, this.currentActionIndex - 1) };
```

- [ ] **Step 2: Add `seekToSlide`**

```ts
seekToSlide(slideIndex: number): void {
  const target = this.actions.findIndex(
    a => a.type === 'transition' && (a as { slideIndex: number }).slideIndex === slideIndex,
  );
  if (target === -1) return;
  this.stop();                   // token++, clean teardown
  this.currentActionIndex = target;
  this.setMode('playing');
  void this.processNext();
}
```

- [ ] **Step 3: Write test**

Create `frontend/src/lib/__tests__/maicPlaybackEngine.test.ts`:

```ts
import { describe, test, expect, vi } from 'vitest';
import { MAICPlaybackEngine } from '../maicPlaybackEngine';
import { MAICActionEngine } from '../maicActionEngine';

describe('MAICPlaybackEngine checkpoint', () => {
  test('checkpoint rewinds -1 to replay interrupted sentence', async () => {
    const ae = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    const pe = new MAICPlaybackEngine(ae);
    pe.loadScene({ id: 's1', title: 's', type: 'lecture', actions: [
      { type: 'speech', agentId: 'a1', text: 'one' },
      { type: 'speech', agentId: 'a1', text: 'two' },
      { type: 'discussion', sessionType: 'qa', topic: 't', agentIds: ['a1'] },
      { type: 'speech', agentId: 'a1', text: 'three' },
    ] } as any);

    // Place cursor at the discussion action (index 2); call processNext to trigger the checkpoint write.
    // @ts-expect-error private
    pe.currentActionIndex = 2;
    // @ts-expect-error private
    pe.mode = 'playing';
    // @ts-expect-error private
    await pe.processNext();

    // After processNext, currentActionIndex was incremented to 3 (post-increment).
    // Checkpoint is (post-increment index) - 1 = 2. This is the "replay the interrupted action" behaviour.
    // @ts-expect-error private
    expect(pe.checkpoint?.actionIndex).toBe(2);
  });

  test('seekToSlide jumps to transition action for that slide', () => {
    const ae = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    const pe = new MAICPlaybackEngine(ae);
    pe.loadScene({ id: 's1', title: 's', type: 'lecture', actions: [
      { type: 'speech', agentId: 'a1', text: 'intro' },
      { type: 'transition', slideIndex: 1 },
      { type: 'speech', agentId: 'a1', text: 'slide 2' },
      { type: 'transition', slideIndex: 2 },
      { type: 'speech', agentId: 'a1', text: 'slide 3' },
    ] } as any);

    pe.seekToSlide(2);
    expect(pe.getCurrentActionIndex()).toBe(3);
  });
});
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/maicPlaybackEngine.ts frontend/src/lib/__tests__/maicPlaybackEngine.test.ts
git commit -m "feat(maic): checkpoint -1 fix + seekToSlide"
```

### Task 5.4: Remove setTimeout from usePlaybackEngine.loadScene

**Files:** Modify `frontend/src/hooks/usePlaybackEngine.ts:142-157`

- [ ] **Step 1: Simplify loadScene**

```ts
const loadScene = useCallback((scene: MAICScene) => {
  engineRef.current?.loadScene(scene);
  setActionCount(scene.actions?.length ?? 0);
  setCurrentActionIndex(0);
  setPlaybackState('idle');

  if (autoAdvanceRef.current && !classStoppedRef.current) {
    engineRef.current?.play();    // no setTimeout — token guarantees clean start
  }
}, []);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/usePlaybackEngine.ts
git commit -m "fix(maic): remove 150ms setTimeout in loadScene (token handles teardown)"
```

### Task 5.5: Wire seekToSlide into SlideNavigator

**Files:** Modify `frontend/src/components/maic/SlideNavigator.tsx`

- [ ] **Step 1: Add `onSlideClick` prop + wire thumbnail**

Find the thumbnail click handler. Call `playbackEngine.seekToSlide(index)`.

- [ ] **Step 2: Expose `seekToSlide` from `usePlaybackEngine`**

```ts
const seekToSlide = useCallback((slideIndex: number) => {
  engineRef.current?.seekToSlide(slideIndex);
}, []);

return {
  // ... existing
  seekToSlide,
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/usePlaybackEngine.ts frontend/src/components/maic/SlideNavigator.tsx
git commit -m "feat(maic): slide thumbnail click seeks cleanly via seekToSlide"
```

### Task 5.6: Expose test-mode engine handle

**Files:** Modify `frontend/src/hooks/usePlaybackEngine.ts`

- [ ] **Step 1: Expose engine under `window.__maicEngine` when NODE_ENV=test**

```ts
useEffect(() => {
  if (import.meta.env.MODE === 'test' || import.meta.env.DEV) {
    (window as any).__maicEngine = { actionEngine: actionEngineRef.current, playbackEngine: engineRef.current };
  }
}, [accessToken]);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/usePlaybackEngine.ts
git commit -m "test(maic): expose engine under window.__maicEngine for e2e probes"
```

### Task 5.7: E2E playback navigation test

**Files:** Create `e2e/tests/maic-playback-navigation.spec.ts`

- [ ] **Step 1: Write test**

```ts
import { test, expect } from '@playwright/test';

test('navigating between slides does not break audio', async ({ page }) => {
  // Precondition: a published classroom exists with >3 slides and pre-gen audio.
  // Seeded by test fixture.

  await page.goto('/login');
  await page.fill('input[name="email"]', 'student@demo.test');
  await page.fill('input[name="password"]', 'demo1234');
  await page.click('button[type="submit"]');
  await page.goto('/student/ai-classroom');
  await page.click('[data-testid="classroom-card"]:first-child');
  await page.waitForSelector('[data-testid="maic-stage"]');
  await page.click('[data-testid="play-button"]');

  // Wait for first audio to actually start
  await page.waitForFunction(() => {
    const engine = (window as any).__maicEngine?.actionEngine;
    return engine?.audioElement && !engine.audioElement.paused;
  }, { timeout: 15000 });

  // Click slide 3
  await page.click('[data-testid="slide-thumbnail"]:nth-child(3)');

  // Within 1s, new audio should start (subtitle updates)
  await page.waitForFunction(() => {
    const engine = (window as any).__maicEngine?.actionEngine;
    const text = engine?.stageStore?.getState?.().speechText;
    return text !== null && text !== undefined;
  }, { timeout: 3000 });

  // Only one audio element exists
  const audioCount = await page.evaluate(() => {
    const engine = (window as any).__maicEngine?.actionEngine;
    return engine?.audioElement ? 1 : 0;
  });
  expect(audioCount).toBe(1);

  // Click slide 5 — same
  await page.click('[data-testid="slide-thumbnail"]:nth-child(5)');
  await page.waitForTimeout(1000);
  const stillOne = await page.evaluate(() => {
    const engine = (window as any).__maicEngine?.actionEngine;
    return engine?.audioElement ? 1 : 0;
  });
  expect(stillOne).toBe(1);
});
```

- [ ] **Step 2: Commit**

```bash
git add e2e/tests/maic-playback-navigation.spec.ts
git commit -m "test(maic): e2e slide navigation mid-playback"
```

### Task 5.8: Chunk 5 checkpoint

- [ ] **Step 1: Full frontend unit test run**

Run: `cd frontend && npx vitest run`
Expected: green.

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

---

## Chunk 6: End-to-End Validation

**Owner subagent:** `Test-Harness`
**Est:** 0.5d (cleanup + full green run)
**Depends on:** Chunks 1–5 merged.

### Task 6.1: Seed a complete classroom via management command

**Files:** Create `backend/apps/courses/management/commands/seed_maic_test_classroom.py`

- [ ] **Step 1: Write command**

```python
"""Seed a test MAIC classroom for e2e test fixtures."""
from django.core.management.base import BaseCommand
from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.maic_models import MAICClassroom, TenantAIConfig


class Command(BaseCommand):
    help = "Seed MAIC classroom for e2e"

    def handle(self, *args, **kwargs):
        tenant, _ = Tenant.objects.get_or_create(subdomain="demo")
        teacher, _ = User.objects.get_or_create(
            email="teacher@demo.test",
            defaults={"tenant": tenant, "role": "TEACHER"},
        )
        teacher.set_password("demo1234"); teacher.save()

        student, _ = User.objects.get_or_create(
            email="student@demo.test",
            defaults={"tenant": tenant, "role": "STUDENT"},
        )
        student.set_password("demo1234"); student.save()

        TenantAIConfig.objects.update_or_create(
            tenant=tenant,
            defaults={"llm_provider": "openrouter", "llm_model": "openai/gpt-4o-mini",
                      "maic_enabled": True, "tts_provider": "azure"},
        )

        classroom = MAICClassroom.objects.create(
            tenant=tenant, creator=teacher,
            title="E2E Demo Classroom", topic="Photosynthesis",
            is_public=True, status="READY",
            content={
                "agents": [
                    {"id": "agent-1", "name": "Dr. Aarav Sharma", "role": "professor",
                     "avatar": "👨‍🏫", "color": "#4338CA",
                     "voiceId": "en-IN-PrabhatNeural", "voiceProvider": "azure",
                     "personality": "Patient.", "expertise": "Leads.", "speakingStyle": "Warm."},
                ],
                "scenes": [
                    {"id": "scene-1", "title": "Intro", "type": "introduction",
                     "actions": [
                         {"type": "speech", "agentId": "agent-1", "text": f"Slide {i+1} content",
                          "audioId": f"fixt{i:08x}", "audioUrl": f"/media/fixt{i}.mp3",
                          "voiceId": "en-IN-PrabhatNeural"} for i in range(5)
                     ] + [
                         {"type": "transition", "slideIndex": i} for i in range(1, 5)
                     ]},
                ],
                "audioManifest": {
                    "status": "ready", "progress": 100,
                    "totalActions": 5, "completedActions": 5, "failedAudioIds": [],
                    "generatedAt": "2026-04-16T00:00:00Z",
                },
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Created classroom {classroom.id}"))
```

- [ ] **Step 2: Commit**

```bash
git add backend/apps/courses/management/commands/seed_maic_test_classroom.py
git commit -m "test(maic): seed command for e2e fixtures"
```

### Task 6.2: Run full backend test suite

- [ ] **Step 1: Run**

Run: `cd backend && pytest tests/courses/ -v --tb=short`
Expected: all green, ≥ 15 tests.

### Task 6.3: Run full frontend test suite

- [ ] **Step 1: Vitest**

Run: `cd frontend && npx vitest run`
Expected: green.

- [ ] **Step 2: tsc**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

### Task 6.4: Run full E2E suite

- [ ] **Step 1: Seed**

Run: `cd backend && python manage.py seed_maic_test_classroom`

- [ ] **Step 2: Run**

Run: `cd e2e && npx playwright test maic-*.spec.ts`
Expected: all green.

### Task 6.5: Manual smoke test

- [ ] **Step 1: Start dev stack**

Run: `docker compose up -d`

- [ ] **Step 2: Teacher flow**

Log in as teacher@demo.test → create new classroom → fill topic → advance → see agent wizard step → preview a voice → edit one agent → regenerate one → "Looks good" → outline generates → scenes generate → click Publish → see progress bar → wait for "Ready".

- [ ] **Step 3: Student flow**

Log out → log in as student@demo.test → open the published classroom → click Play → audio plays, subtitles match → click slide 3 → audio for slide 3 starts cleanly → use chat, send "what's photosynthesis?" → agent responds (no 403).

- [ ] **Step 4: Record observations**

Note any lag, audio overlap, subtitle mismatches. File as follow-up issues.

### Task 6.6: Final commit tag

- [ ] **Step 1: Tag release candidate**

```bash
git tag -a v-maic-fixes-2026-04-16 -m "MAIC classroom fixes + Indian agent selection — RC"
git log --oneline -30
```

- [ ] **Step 2: Push (pending user approval)**

Don't auto-push to remote — user decides.

---

## Appendix: Subagent Dispatch Matrix

| Chunk | Subagent name | Worktree (optional) | Branch |
|---|---|---|---|
| 1 | Frontend-Bugs+Engine | `.claude/worktrees/maic-ws-a-e` | `maic/ws-ae-bugs-engine` |
| 2 | Backend-Agents | `.claude/worktrees/maic-ws-b` | `maic/ws-b-agents` |
| 3 | Frontend-Wizard | `.claude/worktrees/maic-ws-c` | `maic/ws-c-wizard` |
| 4 | Backend-Bugs | `.claude/worktrees/maic-ws-d` | `maic/ws-d-pregen` |
| 5 | Frontend-Bugs+Engine (continues) | same as Chunk 1 | same |
| 6 | Test-Harness | `main` (after merges) | `main` |

Run Chunks 1 + 2 + 3 in parallel (different files). Chunk 4 after. Chunk 5 after Chunk 4 (needs audioUrl type). Chunk 6 last.

Every chunk commits frequently; final PR merges each chunk independently.
