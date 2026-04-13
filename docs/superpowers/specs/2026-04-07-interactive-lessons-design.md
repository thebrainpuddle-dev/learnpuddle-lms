# S1: Enhanced Interactive Lessons — Design Specification

**Date:** 2026-04-07
**Status:** Approved
**Scope:** Admin/tenant portal end-to-end (teacher consumption uses existing player with upgrades)
**Subsystem:** S1 of 6 in the AI Content Generation redesign

---

## 1. Overview

Upgrade LearnPuddle's interactive lesson system from flat text scenes to visually-typed slides with curated/AI-generated images, embedded quizzes, activity prompts, and narration. The admin creates lessons through an enhanced AI Generator tab; teachers consume them through the existing InteractiveLessonPlayer (upgraded to render the new scene types).

### What changes

| Before | After |
|--------|-------|
| All scenes are identical: title + narrative + key_points | 7 distinct scene types with purpose-specific layouts |
| No images | Curated SVG icons (default) + AI-generated images (opt-in) |
| Flat text rendering | Visual slide layouts (title, content, definition, comparison, quiz, activity, summary) |
| Edge TTS only | Edge TTS (free) + ElevenLabs (premium) |
| No quizzes in lessons | Quiz scenes embedded in lesson flow |
| No activities in lessons | Reflection/activity scenes embedded in lesson flow |

### What does NOT change

- `InteractiveLesson` model stays (JSONField `scenes` evolves, no new tables)
- Existing lessons continue to work (schema_version migration)
- Teacher progress tracking, reflection submission, XP system unchanged
- Multi-tenant isolation, JWT auth, rate limiting patterns unchanged
- Course → Module → Content hierarchy unchanged

---

## 2. Scene Schema v2

### 2.1 Document Structure

```json
{
  "schema_version": 2,
  "scenes": [
    { "slide_type": "title", ... },
    { "slide_type": "content", ... },
    ...
  ]
}
```

`schema_version` is at the **document level**, not per-scene. Migration strategy: if absent, check first scene for version; if absent, assume v1 (legacy text format).

### 2.2 Common Fields (all scene types)

| Field | Type | Source | Required | Notes |
|-------|------|--------|----------|-------|
| `id` | string (UUID) | Backend | Yes | Auto-generated, used as React key + edit target |
| `slide_type` | enum string | LLM + normalization | Yes | One of 7 types (see §2.3) |
| `order` | integer | Backend | Yes | Assigned from array index, never from LLM |
| `title` | string | LLM | Per-type | Max 200 chars |
| `image_keyword` | string | LLM | No | Keyword for icon/image lookup |
| `image_url` | string \| null | Backend | No | Resolved URL (set by image pipeline) |
| `image_status` | enum string | Backend | Yes | `pending`, `generating`, `ready`, `failed`, `skipped` |
| `alt_text` | string | LLM/Backend | No | Accessibility text for image |
| `speaker_notes` | string | LLM | No | Max 2000 chars, used for TTS narration |
| `key_points` | string[] | LLM | No | Max 20 items, each max 300 chars |
| `audio_url` | string \| null | Backend | No | Set by audio generation pipeline |
| `duration_seconds` | number \| null | Backend | No | Audio duration, set after TTS |

### 2.3 Scene Types and Type-Specific Fields

#### `title`
| Field | Type | Required | Max Length |
|-------|------|----------|-----------|
| `title` | string | **Yes** | 200 |
| `subtitle` | string | No | 300 |

#### `content`
| Field | Type | Required | Max Length | Notes |
|-------|------|----------|-----------|-------|
| `title` | string | **Yes** | 200 | |
| `body` | string | No | 3000 | At least one of `body` or `bullets` required |
| `bullets` | string[] | No | 20 items × 300 chars | |

#### `definition`
| Field | Type | Required | Max Length |
|-------|------|----------|-----------|
| `term` | string | **Yes** | 200 |
| `definition` | string | **Yes** | 1000 |
| `example` | string | No | 500 |
| `title` | string | No | 200 (auto-generated from `term` if missing) |

#### `comparison`
| Field | Type | Required | Max Length |
|-------|------|----------|-----------|
| `title` | string | **Yes** | 200 |
| `left_label` | string | **Yes** | 100 |
| `left_points` | string[] | **Yes** | 10 items × 300 chars |
| `right_label` | string | **Yes** | 100 |
| `right_points` | string[] | **Yes** | 10 items × 300 chars |

#### `quiz`
| Field | Type | Required | Max Length | Notes |
|-------|------|----------|-----------|-------|
| `title` | string | **Yes** | 200 | |
| `question` | string | **Yes** | 500 | |
| `options` | string[] (from LLM) | **Yes** | 2–6 items, each max 200 chars | LLM produces simple string array |
| `correct_answer` | string (from LLM) | **Yes** | 200 | Must match one option (case-insensitive) |
| `explanation` | string | No | 1000 | |

**Backend normalization** converts LLM output to:
```json
{
  "options": [
    {"id": "opt-uuid", "text": "Remember", "is_correct": false},
    {"id": "opt-uuid", "text": "Create", "is_correct": true}
  ]
}
```
The `correct_answer` field is removed after normalization. Matching is case-insensitive, whitespace-trimmed.

#### `activity`
| Field | Type | Required | Max Length | Notes |
|-------|------|----------|-----------|-------|
| `title` | string | **Yes** | 200 | |
| `instructions` | string | **Yes** | 1000 | |
| `activity_type` | enum | **Yes** | — | `reflection` only for v2; extensible later |
| `reflection_prompt` | string | **Yes** (if reflection) | 500 | Flat field, NOT nested object |
| `reflection_min_length` | integer | No | — | Default 50 |

#### `summary`
| Field | Type | Required | Max Length |
|-------|------|----------|-----------|
| `title` | string | **Yes** | 200 |
| `recap_points` | string[] | **Yes** | 10 items × 300 chars |
| `next_steps` | string | No | 500 |

### 2.4 What the LLM Generates vs What Backend Adds

**LLM generates:**
```json
{
  "scenes": [
    {
      "slide_type": "quiz",
      "title": "Check Your Understanding",
      "question": "Which level involves creating new work?",
      "options": ["Remember", "Create", "Understand", "Apply"],
      "correct_answer": "Create",
      "explanation": "Create is the highest level...",
      "image_keyword": "quiz",
      "speaker_notes": "Let's test your understanding...",
      "key_points": []
    }
  ]
}
```

**Backend adds/transforms:**
- `id`: UUID per scene
- `order`: from array index (LLM-provided `order` ignored)
- `schema_version`: moved to document level
- `image_url`: null (set later by image pipeline)
- `image_status`: `pending` if `image_keyword` present, `skipped` if not
- `alt_text`: generated from title + image_keyword if missing
- `audio_url`: null (set later by audio pipeline)
- `duration_seconds`: null
- Quiz `options` string[] → `[{id, text, is_correct}]` (matched via `correct_answer`)
- `correct_answer` field removed from stored schema
- All text fields sanitized via `bleach.clean()` (prevents stored XSS)
- Field length enforcement (truncation, not rejection)
- `slide_type` normalized via alias map (case-insensitive)

### 2.5 Slide Type Alias Map

```python
SLIDE_TYPE_ALIASES = {
    "intro": "title", "introduction": "title",
    "multiple_choice": "quiz", "mcq": "quiz", "question": "quiz",
    "recap": "summary", "conclusion": "summary", "review": "summary",
    "define": "definition", "vocab": "definition", "vocabulary": "definition",
    "compare": "comparison", "versus": "comparison", "vs": "comparison",
    "exercise": "activity", "task": "activity", "practice": "activity",
}
```

### 2.6 Required Fields Validation

```python
REQUIRED_FIELDS = {
    "title": ["title"],
    "content": ["title"],  # + custom: at least one of body|bullets
    "definition": ["term", "definition"],
    "comparison": ["title", "left_label", "left_points", "right_label", "right_points"],
    "quiz": ["title", "question", "options", "correct_answer"],
    "activity": ["title", "instructions", "activity_type"],
    "summary": ["title", "recap_points"],
}
```

### 2.7 Image Status State Machine

```
pending ──→ generating ──→ ready
  │              │
  │              └──→ failed ──→ pending (retry)
  │
  └──→ skipped (no image_keyword)

ready ──→ pending (regenerate)
```

Invariant: if `image_keyword` is empty/null, `image_status` must be `skipped`.

### 2.8 Backward Compatibility

- Existing v1 lessons (no `slide_type`) continue to render in the player
- `InteractiveLessonPlayer` is updated to embed `SceneRenderer` for v2 scenes:
  - Check `lesson.scene_schema_version` (model field) or document-level `schema_version`
  - v1 or missing: render using existing code path (`scene.narrative`, `scene.reflection.prompt`)
  - v2: delegate each scene to `SceneRenderer` which dispatches by `slide_type`
- Backend lazy migration: when a v1 lesson is loaded, optionally convert to v2 format on write-back
- New `lesson_format` field on `InteractiveLesson` model: `text` (v1) | `visual` (v2, default for new)
  - Named `lesson_format` (not `format`) to avoid shadowing Python's builtin `format()`

---

## 3. Backend Changes

### 3.1 Model Changes (`ai_studio_models.py`)

```python
class InteractiveLesson(models.Model):
    # Existing fields unchanged
    # New fields:
    scene_schema_version = models.PositiveSmallIntegerField(default=2)
    image_generation_status = models.CharField(
        max_length=20,
        choices=[
            ("none", "None"),
            ("pending", "Pending"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("partial_failure", "Partial Failure"),
        ],
        default="none",
    )
    lesson_format = models.CharField(
        max_length=10,
        choices=[("text", "Text"), ("visual", "Visual")],
        default="visual",
    )
    has_audio = models.BooleanField(default=False)  # Denormalized for query perf
    generation_error = models.TextField(blank=True, default="")  # Human-readable error on failure
```

Total: **5 new fields** (`scene_schema_version`, `image_generation_status`, `lesson_format`, `has_audio`, `generation_error`). No new tables. No database migration for scenes (JSONField is schemaless).

### 3.1.1 Reflection Tracking: `scene_index` vs Scene UUID

The existing `LessonReflectionResponse` model tracks reflections by `scene_index` (positional integer). The v2 schema introduces stable scene UUIDs. Strategy:

- **V1 lessons**: Continue using `scene_index` (unchanged behavior).
- **V2 lessons**: `LessonReflectionResponse.scene_index` is set to the scene's `order` value (which equals the array index). Since v2 scenes also have a UUID `id`, add a new nullable field `scene_id` (CharField) to `LessonReflectionResponse` for v2 lessons. Lookups use `scene_id` when present, fall back to `scene_index`.
- **Admin scene reorder**: Not exposed in v1 of this feature. When added later, reflection records must be re-mapped by `scene_id` (not positional index). The UUID ensures stability across reorders.

```python
# New field on LessonReflectionResponse
scene_id = models.CharField(max_length=36, blank=True, null=True, db_index=True)
```

### 3.2 New Module: `scene_validation.py`

Responsibilities:
- `normalize_scenes(raw_scenes: list) -> list`: Full normalization pipeline
- `normalize_slide_type(raw: str) -> str`: Alias resolution + case normalization
- `validate_required_fields(scene: dict, slide_type: str) -> list[str]`: Returns missing fields
- `normalize_quiz_options(scene: dict) -> dict`: `correct_answer` → `{id, text, is_correct}`
- `sanitize_scene_fields(scene: dict) -> dict`: bleach.clean() on all text fields
- `enforce_field_lengths(scene: dict) -> dict`: Truncation per field
- `coerce_field_types(scene: dict) -> dict`: string → array for bullets/key_points

### 3.3 AI Service Prompt Changes

- LLM prompt requests flat JSON with `slide_type` discriminator
- Temperature: 0.4 (down from 0.7 for more reliable structure)
- JSON mode enabled when provider supports it
- `json-repair` applied to raw LLM output before parsing
- Explicit instruction: "Do NOT include `order` or `id` fields"
- Quiz prompt: "Set `correct_answer` to the exact text of the correct option"
- Activity prompt: "Use flat fields `reflection_prompt` and `reflection_min_length`, NOT nested objects"
- Max scenes per generation: 12 (free-tier LLM output token limit protection)

### 3.4 New Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `POST /api/v1/ai-studio/lessons/{id}/generate-images/` | POST | admin_only | Trigger image generation (Celery) |
| `PATCH /api/v1/ai-studio/lessons/{id}/scenes/{scene_id}/` | PATCH | admin_only | Edit individual scene fields |
| `POST /api/v1/ai-studio/lessons/{id}/scenes/{scene_id}/regenerate/` | POST | admin_only | Regenerate single scene via LLM |

### 3.5 Modified Endpoints

| Endpoint | Change |
|----------|--------|
| `POST /generate/` | Now produces visual slides (schema v2). Existing `num_scenes` param kept (not renamed). New params: `include_quiz` (bool), `include_activity` (bool). Returns `status_url` in response. |
| `GET /status/` | Enhanced response (see §3.5.1 below). |
| `POST /generate-audio/` | NEW behavior: rate limited (10/hr/tenant). Checks for existing audio — if scenes already have `audio_url`, requires `regenerate=true` query param to overwrite. Without it, returns 409 Conflict. |

#### 3.5.1 Enhanced Status Response Contract

```json
{
  "type": "lesson",
  "id": "uuid",
  "title": "Lesson Title",
  "status": "GENERATING",
  "phase": "content_generation",
  "progress": {
    "current_scene": 3,
    "total_scenes": 10,
    "percentage": 30
  },
  "phases_completed": ["content_generation"],
  "phases_remaining": ["image_generation", "audio_generation"],
  "scene_count": 10,
  "has_audio": false,
  "error": null,
  "created_at": "2026-04-07T10:00:00Z",
  "updated_at": "2026-04-07T10:02:15Z"
}
```

Status enum values (uppercase, matching existing convention): `PENDING`, `GENERATING`, `IMAGES`, `NARRATING`, `READY`, `FAILED`, `PARTIAL_FAILURE`.

Phase enum values (lowercase): `content_generation`, `image_generation`, `audio_generation`.

The response includes existing fields (`type`, `id`, `title`, `status`, `scene_count`, `has_audio`) for backward compatibility, plus new fields (`phase`, `progress`, `phases_completed`, `phases_remaining`, `error`). Existing frontend code that only reads `status` continues to work.

### 3.6 Idempotency Guard

Before creating a new generation:
```python
existing = InteractiveLesson.objects.filter(
    content_id=content_id,
    status__in=["pending", "generating"],
).first()
if existing:
    return Response(
        {"error": {"code": "GENERATION_IN_PROGRESS", ...}},
        status=409,
    )
```

### 3.7 Security Mitigations (from review)

1. **Sanitize LLM output**: Apply `bleach.clean()` to all scene text fields during normalization
2. **Prompt injection defense**: User inputs (topic, description) placed in `<user_input>` delimited blocks in the prompt
3. **Celery tenant isolation**: Add `set_current_tenant(lesson.tenant)` to `generate_lesson_audio` task
4. **Clamp `num_scenes`**: `max(3, min(12, num_scenes))` at the API layer, not just in the generator
5. **Scenes array size limit**: `len(scenes) <= 20` enforced in create-lesson
6. **Rate limit fix**: Rewrite `_check_studio_rate_limit()` to use atomic `cache.incr()` with `ValueError` fallback + `cache.set()`, matching the existing pattern in `teacher_generate_strategy` (lines 1019-1025 of `ai_studio_views.py`). The current `cache.add()` + `cache.incr()` pattern has a TOCTOU race.
7. **Quiz answer protection**: Strip `is_correct` from quiz options in teacher-facing serialization; reveal only after answer submission

### 3.8 Generation Flow (6 steps)

```
1. Admin submits config           → API validates, creates InteractiveLesson(status="pending")
2. Celery: generate scenes        → LLM call, normalize, sanitize, store in JSONField
3. Celery: generate images        → Per-scene, parallel via chord (if enabled)
4. Celery: generate audio         → Per-scene, parallel via chord (if enabled)
5. Finalize                       → Set status="ready", push WebSocket notification
6. Admin previews and edits       → PATCH individual scenes, then "Add to Module"
```

---

## 4. Celery Architecture

### 4.1 Queue Separation

```python
CELERY_TASK_ROUTES = {
    "apps.courses.ai_studio_tasks.*": {"queue": "ai_generation"},
    "apps.courses.tasks.process_video_upload": {"queue": "video"},
    "apps.ops.tasks.*": {"queue": "ops"},
}
```

### 4.2 Parallel Audio Generation

Refactor the existing `generate_lesson_audio` task into an **orchestrator** that fans out to per-scene sub-tasks:

```python
from celery import group, chord

# generate_lesson_audio (orchestrator) — called by the view, same signature as today
@shared_task(bind=True)
def generate_lesson_audio(self, lesson_id, voice=""):
    # ... setup, set_current_tenant ...
    scenes = lesson.scenes
    sub_tasks = [
        _generate_scene_audio.s(lesson_id, idx, voice)  # NEW leaf task (private)
        for idx, scene in enumerate(scenes)
        if _has_narrable_text(scene)
    ]
    chord(group(sub_tasks))(_finalize_lesson_audio.s(lesson_id))

# _generate_scene_audio — NEW leaf task, generates audio for one scene
# _finalize_lesson_audio — NEW callback, updates lesson.has_audio, status
```

15-slide lesson: ~90s serial → ~8s parallel.

### 4.3 Parallel Image + Audio

When both are enabled, image and audio generation run concurrently:
```python
chain(
    generate_lesson_scenes.s(lesson_id),
    group(
        generate_lesson_images.s(lesson_id),
        generate_lesson_audio.s(lesson_id),
    ),
    finalize_lesson.s(lesson_id),
)
```

---

## 5. Frontend Architecture

### 5.1 Terminology

**"Scene"** everywhere on the frontend, matching the backend `scenes` JSONField and existing `InteractiveLessonPlayer`. Layout components are named by visual purpose (e.g., `TitleLayout`, `ContentLayout`) but the data model is always "scene."

### 5.2 Component Structure

```
src/components/lessons/
├── SceneRenderer.tsx              — Dispatches to layout by slide_type (shared)
├── layouts/
│   ├── TitleLayout.tsx            — Title + subtitle + hero image
│   ├── ContentLayout.tsx          — Body text + bullets + image
│   ├── DefinitionLayout.tsx       — Term + definition + example
│   ├── ComparisonLayout.tsx       — Two-column comparison
│   ├── QuizLayout.tsx             — Question + options + explanation
│   ├── ActivityLayout.tsx         — Instructions + reflection prompt
│   ├── SummaryLayout.tsx          — Recap points + next steps
│   └── FallbackLayout.tsx         — Unknown slide_type graceful degradation
├── ScenePreview.tsx               — Admin: navigation + edit controls
├── SceneEditor.tsx                — Admin: inline field editing
├── GenerationProgress.tsx         — Multi-phase progress indicator
├── schemas.ts                     — Zod schemas + z.infer types
├── types.ts                       — Additional TypeScript types
└── iconMap.ts                     — image_keyword → Heroicon mapping
```

### 5.3 AIGenerationPanel Split

The existing 1,329-line file is split into:

```
src/components/courses/
├── AIGenerationPanel.tsx           — Orchestrator (~300 lines), useReducer state machine
├── ai-generation/
│   ├── InputStep.tsx               — Topic input + content type toggle
│   ├── OutlineStep.tsx             — Outline review (text content)
│   ├── GenerationStep.tsx          — Text content generation progress
│   ├── PreviewStep.tsx             — Text content preview + add-to-module
│   ├── LessonConfigStep.tsx        — NEW: Lesson config (slide count, quiz/activity toggles)
│   ├── LessonGenerationStep.tsx    — NEW: Multi-phase generation progress
│   ├── LessonPreviewStep.tsx       — NEW: Scene preview with SceneRenderer
│   ├── types.ts                    — Shared types
│   └── helpers.ts                  — extractErrorMessage, genId, formatFileSize
```

### 5.4 State Management

**Generation flow**: `useReducer` with discriminated union step type:

```typescript
type GenerationStep =
  | { kind: 'input' }
  | { kind: 'parsing' }
  | { kind: 'outline-review'; outline: OutlineSection[] }
  | { kind: 'generating'; progress: SectionProgress[] }
  | { kind: 'content-ready'; items: GeneratedItem[] }
  | { kind: 'lesson-config' }
  | { kind: 'lesson-generating'; phase: 'scenes' | 'images' | 'narration'; lessonId: string }
  | { kind: 'lesson-preview'; lesson: InteractiveLessonData; currentScene: number };
```

**Player state**: `useReducer` in existing InteractiveLessonPlayer (upgrade).

**Polling**: `useGenerationStatus` custom hook using react-query `refetchInterval`:

```typescript
export function useGenerationStatus(lessonId: string | null) {
  return useQuery({
    queryKey: ['generationStatus', lessonId],
    queryFn: () => aiService.studio.getStatus(lessonId!),
    enabled: Boolean(lessonId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'READY' || status === 'FAILED') return false;
      return 3000;
    },
    refetchIntervalInBackground: false,
  });
}
```

### 5.5 TypeScript Types (discriminated unions)

```typescript
interface BaseScene {
  id: string;
  slide_type: string;
  order: number;
  title: string;
  image_keyword: string;
  image_url: string | null;
  image_status: 'pending' | 'generating' | 'ready' | 'failed' | 'skipped';
  alt_text: string;
  speaker_notes: string;
  key_points: string[];
  audio_url: string | null;
  duration_seconds: number | null;
}

interface TitleScene extends BaseScene { slide_type: 'title'; subtitle: string; }
interface ContentScene extends BaseScene { slide_type: 'content'; body: string; bullets: string[]; }
interface DefinitionScene extends BaseScene { slide_type: 'definition'; term: string; definition: string; example: string; }
interface ComparisonScene extends BaseScene { slide_type: 'comparison'; left_label: string; left_points: string[]; right_label: string; right_points: string[]; }
interface QuizScene extends BaseScene { slide_type: 'quiz'; question: string; options: QuizOption[]; explanation: string; }
interface ActivityScene extends BaseScene { slide_type: 'activity'; instructions: string; activity_type: string; reflection_prompt: string; reflection_min_length: number; }
interface SummaryScene extends BaseScene { slide_type: 'summary'; recap_points: string[]; next_steps: string; }

type Scene = TitleScene | ContentScene | DefinitionScene | ComparisonScene | QuizScene | ActivityScene | SummaryScene;
```

Zod schemas in `schemas.ts` with `z.infer` for type derivation. Validation at fetch boundary (when API response is received).

### 5.6 SceneRenderer Architecture

```typescript
// Shared by admin ScenePreview and teacher InteractiveLessonPlayer
const LAYOUT_REGISTRY: Record<string, React.FC<LayoutProps>> = {
  title: TitleLayout,
  content: ContentLayout,
  definition: DefinitionLayout,
  comparison: ComparisonLayout,
  quiz: QuizLayout,
  activity: ActivityLayout,
  summary: SummaryLayout,
};

function SceneRenderer({ scene, onAction }: Props) {
  const Layout = LAYOUT_REGISTRY[scene.slide_type] || FallbackLayout;
  return (
    <ErrorBoundary fallback={<FallbackLayout scene={scene} />}>
      <Layout scene={scene} onAction={onAction} />
    </ErrorBoundary>
  );
}
```

Per-scene ErrorBoundary: one bad scene doesn't crash the whole lesson.

### 5.7 Admin Preview UX

Embedded in AI Generator tab (not a modal):

```
┌─────────────────────────────────────────────┐
│  Interactive Lesson Preview          [Edit] │
│  ┌───────────────────────────────────────┐  │
│  │         [Scene Visual Preview]       │  │
│  │         Layout rendered by type      │  │
│  └───────────────────────────────────────┘  │
│  ◀  ● ● ○ ○ ○ ○ ○ ○ ○ ○  ▶   1/10        │
│  Speaker Notes: "Welcome to..."             │
│  ┌──────────┐  ┌──────────────┐             │
│  │ Regenerate│  │ Add to Module│             │
│  └──────────┘  └──────────────┘             │
└─────────────────────────────────────────────┘
```

- Arrow key navigation between scenes
- Per-scene "Regenerate" button (re-prompts LLM for that scene only)
- Inline edit mode for title, body, key_points, speaker_notes
- Image shows Heroicon placeholder until AI image loads (if enabled)
- Audio preview play button on scenes with narration

### 5.8 Accessibility (WCAG 2.1 AA)

- ARIA roles: `region`, `navigation`, `button`, `radiogroup` (quiz options)
- Keyboard: Arrow keys for navigation, Tab for interactive elements, Enter for quiz submit
- `alt_text` on all images (auto-generated if not provided)
- `prefers-reduced-motion`: disable CSS transitions
- Focus management: focus moves to scene content on navigation
- Color contrast: all layouts meet 4.5:1 contrast ratio

### 5.9 Responsive Design

- **Mobile (<640px)**: Single column, comparison stacks vertically, "2 of 8" text counter (dots hidden)
- **Tablet (640–1024px)**: Two-column layouts work, images at 40% width
- **Desktop (>1024px)**: Full layout, `max-w-3xl`, side-by-side comparisons

### 5.10 Icons (image_keyword mapping)

Map `image_keyword` to a subset of ~25 Heroicons already in the bundle. No custom SVG library needed for v1.

```typescript
const ICON_MAP: Record<string, HeroIcon> = {
  classroom: AcademicCapIcon,
  quiz: ClipboardDocumentCheckIcon,
  summary: DocumentTextIcon,
  comparison: ScaleIcon,
  // ... ~25 mappings covering common education keywords
};

function getSceneIcon(keyword: string): HeroIcon {
  return ICON_MAP[keyword.toLowerCase()] || LightBulbIcon; // fallback
}
```

Custom illustration library deferred to a later phase when the need is proven.

---

## 6. Image Pipeline

### 6.1 Tier 1: Heroicon Mapping (default, instant, zero cost)

- Maps `image_keyword` → Heroicon from existing bundle
- Fuzzy fallback: `LightBulbIcon` for unknown keywords
- No API calls, no storage, no latency

### 6.2 Tier 2: AI Image Generation (opt-in, async)

Gated by `Tenant.features["ai_images"]`.

Pipeline:
1. Admin clicks "Generate Images" (or auto-triggered if feature enabled)
2. Celery task iterates scenes, builds image prompt from `title + image_keyword`
3. Calls image API (Stable Diffusion via OpenRouter, or local ComfyUI)
4. Stores result: `media/tenant/{tenant_id}/lessons/{lesson_id}/scene_{scene_id}.webp`
5. Updates scene `image_url` and `image_status: "ready"`
6. WebSocket push notifies frontend

Constraints:
- Max 1024×576 (16:9), WebP, <200KB per image
- Rate: 15 images per lesson, 50 per hour per tenant
- Timeout: 30s per image, skip on failure (keeps icon fallback)
- Parallel via Celery `group` (all images generated concurrently)

---

## 7. Performance Architecture

### 7.1 Generation Status

**Primary**: WebSocket push via existing Django Channels infrastructure.
- Create `AiStudioConsumer` joining user-specific group
- Celery tasks send `channel_layer.group_send()` after each phase
- Frontend `useGenerationStatus` listens to WebSocket, falls back to polling

**Fallback**: Redis-cached status (avoids DB hit on every poll).
```python
cache.set(f"ai_studio_status:{lesson_id}", {"status": "GENERATING", "progress": 0.3}, timeout=600)
```

### 7.2 Asset Serving

- Audio/images served through `protected-media` nginx location
- Fingerprinted filenames: `scene_{id}_{hash8}.webp`
- Cache headers: `Cache-Control: public, max-age=31536000, immutable`
- S3/DO Spaces: pre-signed URLs with 7-day expiry returned directly to client

### 7.3 Bundle Size

Estimated increase: ~25 KB gzipped (main bundle). Admin-only components code-split via lazy route.

---

## 8. Error Handling

### 8.1 Backend

- `json-repair` on raw LLM output before JSON parsing
- Per-scene validation: invalid scenes logged and skipped (not fatal)
- Generation failure: `status="failed"`, error message stored in `generation_error` model field (§3.1)
- Partial success: if 8/10 scenes valid, store the 8 valid ones + set `partial_failure` status

### 8.2 Frontend

- Zod validation at fetch boundary (graceful degradation for invalid scenes)
- Per-scene `ErrorBoundary` → `FallbackLayout` component
- Unknown `slide_type` → `FallbackLayout` (renders title + raw JSON)
- Network errors → `extractErrorMessage()` → toast notification
- Generation timeout (>5 min) → auto-cancel with retry option

### 8.3 Error Response Format (new endpoints)

```json
{
  "error": {
    "code": "SCENE_GENERATION_FAILED",
    "message": "Image generation failed for scene 3: provider timeout",
    "details": { "scene_id": "uuid", "retry_after": 30 }
  }
}
```

---

## 9. Rate Limiting

| Resource | Limit | Scope | Window |
|----------|-------|-------|--------|
| Lesson generation | 10 | per tenant | 1 hour |
| Image generation | 50 images | per tenant | 1 hour |
| Audio generation | 10 | per tenant | 1 hour |
| Scene regeneration | 30 | per tenant | 1 hour |

Rate limit headers on all generation endpoints:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1712505600
```

---

## 10. Testing Strategy

### Backend
- Unit: `scene_validation.py` — normalization, alias mapping, required fields, quiz conversion, sanitization
- Unit: `ai_service.py` — prompt construction, response parsing
- Integration: Full generation flow with mocked LLM response
- Security: XSS payloads in scene fields, tenant isolation in Celery tasks

### Frontend
- Unit: Zod schemas with known-good and known-bad payloads
- Unit: `useGenerationReducer` — state machine transitions
- Component: Each layout renders correctly with typed props
- Component: `SceneRenderer` dispatches correctly, FallbackLayout for unknowns
- Integration: Full admin flow (input → generate → preview → edit → add to module)

---

## 11. Dependencies

### Backend (existing, no new packages)
- `bleach` — already in requirements (HTML sanitization)
- `celery` — already in requirements (task queue)
- `channels` — already in requirements (WebSocket)

### Backend (new)
- `json-repair` — LLM output recovery (~5KB package)

### Frontend (existing, no new packages)
- `zod` — already in package.json
- `@tanstack/react-query` — already in package.json
- `@heroicons/react` — already in package.json
- `dompurify` — already in package.json

### Frontend (no new packages needed)

---

## 12. Out of Scope (deferred to later subsystems)

- S2: AI Narration & TTS (ElevenLabs voices, voice selection UI)
- S3: AI Classroom Personas (Teacher, TA, Student agents)
- S4: NotebookLM Audio (podcast-style generation from course content)
- S5: Interactive Exercises (code playground, drag-drop, matching)
- S6: Export Pipeline (PPTX, interactive HTML)
- Custom SVG illustration library (deferred from S1 until demand proven)
- Multi-language lesson generation
- Student portal consumption

---

## 13. Migration Path

1. **Database**: Add 5 fields to `InteractiveLesson` model (`scene_schema_version`, `image_generation_status`, `lesson_format`, `has_audio`, `generation_error`) + 1 field to `LessonReflectionResponse` (`scene_id`). Standard Django migration.
2. **Existing lessons**: Continue to work. `lesson_format="text"` for existing, `lesson_format="visual"` for new.
3. **Frontend**: `SceneRenderer` checks `schema_version` — v1 renders as legacy, v2 dispatches by `slide_type`.
4. **API**: Generate endpoint produces v2 by default. Existing v1 lessons served unchanged. The only consumer is our own frontend, so no external API versioning needed — frontend and backend deploy together.
5. **No data migration needed**: Old and new formats coexist indefinitely.
