# Course Editor Redesign — Implementation Plan

**Date:** 2026-04-06
**Spec:** `2026-04-06-course-editor-redesign-design.md`

---

## Phase 1: Backend — Material Parsing + Prompt Upgrades

### Step 1.1: Material Parsing Endpoint

**New file:** `backend/apps/courses/material_views.py`

Create `POST /api/v1/courses/ai/parse-material/` endpoint:
- Accepts multipart file upload (PDF, DOCX, PPTX, video)
- Returns `{ text, images?, metadata: { pages, file_type, file_size } }`

**PDF parsing:**
- Use existing PDF text extraction (PyPDF2 or pdfplumber — check what's already installed)
- Extract first 100k chars of text
- Extract embedded images with descriptions (optional, phase 2)

**DOCX parsing:**
- Install `python-docx` (`pip install python-docx`)
- Extract paragraph text, table text, heading structure
- Return concatenated text

**PPTX parsing:**
- Install `python-pptx` (`pip install python-pptx`)
- Extract slide text + notes per slide
- Return slide-by-slide text with slide numbers

**Video parsing:**
- Trigger existing Whisper transcription pipeline
- Return transcript text
- If async (Celery task), return `{ task_id, status: "PROCESSING" }` and add a polling endpoint

**Validation:**
- Max file size: 50MB
- Allowed MIME types: `application/pdf`, `application/vnd.openxmlformats-officedocument.*`, `video/*`
- Return 400 for unsupported types

### Step 1.2: Register URL

**Modify:** `backend/apps/courses/urls.py`
- Add: `path('ai/parse-material/', material_views.parse_material, name='ai_parse_material')`

### Step 1.3: Upgrade Generation Prompts

**Modify:** `backend/apps/courses/ai_service.py`

Replace flat prompts with OpenMAIC-style pedagogical prompts:

**Outline generation prompt:**
- Input: topic + extracted material text + target audience + num_sections
- Output: structured sections with learning objectives, key points, Bloom's level, suggested content types
- JSON schema for output validation

**Content generation prompt (per type):**
- **Lesson text:** Structured HTML with headings, callouts, examples, analogies. Scannable, not wall-of-text.
- **Quiz:** Bloom's-aligned MCQ with plausible distractors + answer explanations. Difficulty: easy/medium/hard.
- **Assignment:** Open-ended prompt + 4-level rubric + success criteria.
- **Summary:** 5-7 bullet key takeaways + one-paragraph synthesis.

### Step 1.4: New Generation Endpoints (if needed)

**Check existing endpoints and add missing ones:**
- `POST /api/v1/courses/ai/generate-assignment/` — Generate assignment prompt with rubric from topic/material
- `POST /api/v1/courses/ai/generate-summary/` — Generate summary from topic/material (may reuse existing `ai/summarize/`)

**Verify:** All 4 generation types (lesson, quiz, assignment, summary) have working endpoints.

---

## Phase 2: Frontend — Tab Cleanup

### Step 2.1: Update Tab Types

**Modify:** `frontend/src/pages/admin/course-editor/types.ts`
- Remove `'activity'` from `EditorTab` union
- Remove `'assignments'` from `EditorTab` union (if present)
- Keep: `'details' | 'content' | 'ai' | 'audience'`

### Step 2.2: Update CourseEditorPage

**Modify:** `frontend/src/pages/admin/CourseEditorPage.tsx`

Changes:
- Remove Activity tab button and rendering
- Remove Assignment Builder tab button and rendering
- Rename "AI Tools" tab label to "AI Generator"
- Remove imports: `CourseActivity`, assignment-related components
- Remove assignment-related state/mutations
- Clean up unused imports (LessonPlanner, AcademicCapIcon, etc.)

Tab bar should render exactly 4 tabs: Details | Content | AI Generator | Course Audience

### Step 2.3: Remove Unused Files

**Delete:**
- `frontend/src/components/courses/CourseActivity.tsx`
- `frontend/src/components/courses/LessonPlanner.tsx`

---

## Phase 3: Frontend — AI Generator Component (Rewrite)

### Step 3.1: Create AI Service Extensions

**Modify:** `frontend/src/services/aiService.ts`

Add new functions:
```typescript
parseMaterial: (file: File) => FormData POST to /courses/ai/parse-material/
generateAssignment: (data) => POST to /courses/ai/generate-assignment/
generateSummary: (data) => POST to /courses/ai/generate-summary/ (or reuse summarize)
```

### Step 3.2: Rewrite AIGenerationPanel

**Rewrite:** `frontend/src/components/courses/AIGenerationPanel.tsx`

Replace the 4-step wizard with a single-page progressive flow.

**Component structure:**

```
AIGenerationPanel (main component)
├── ModuleSelector          — dropdown to pick target module
├── UnifiedInput            — textarea + drop zone + file toolbar + generate button
│   ├── FilePreview         — shows attached file (name, size, remove)
│   └── ContentTypePills    — toggles: Lesson | Quiz | Assignment | Summary
├── OutlineReview           — editable section cards (appears after Stage 1)
│   ├── OutlineCard         — single section: title, objectives, key points, type toggles
│   └── AddSectionButton
├── GenerationProgress      — per-section progress indicators (appears during Stage 2)
└── ContentPreview          — generated content cards with "Add to Module" buttons
    ├── LessonPreviewCard   — rendered HTML preview
    ├── QuizPreviewCard     — questions list with options
    ├── AssignmentPreviewCard — prompt + rubric preview
    └── SummaryPreviewCard  — condensed text preview
```

**State management (local useState, no Zustand needed):**

```typescript
type GeneratorState = 'idle' | 'parsing' | 'generating-outline' | 'outline-ready' | 'generating-content' | 'content-ready';

// Key state:
selectedModuleId: string | null
inputText: string
attachedFile: File | null
parsedMaterial: { text: string; metadata: any } | null
selectedTypes: Set<'lesson' | 'quiz' | 'assignment' | 'summary'>
outline: OutlineSection[]
generatedItems: GeneratedItem[]
generatorState: GeneratorState
```

**Flow implementation:**

1. **Idle state:** Show ModuleSelector + UnifiedInput only
2. **User provides input:** Enable Generate button when (module selected) AND (text entered OR file attached)
3. **Click Generate:**
   - If file attached → call `parseMaterial(file)` → set state to `'parsing'`
   - Then call `generateOutline({ topic, material_text, num_sections })` → set state to `'generating-outline'`
   - On success → set `outline` state, set state to `'outline-ready'`, show OutlineReview
4. **Outline Review:** Admin edits inline, clicks "Generate Content →"
   - Set state to `'generating-content'`
   - For each section × selected content types, call appropriate generation endpoint
   - Show GenerationProgress with per-item status
   - On completion → set state to `'content-ready'`, show ContentPreview
5. **Content Preview:** Each card has "Add to Module →" button
   - Lesson/Summary → `POST /courses/{id}/modules/{mid}/contents/` with TEXT type
   - Quiz → `POST /courses/{id}/assignments/` with questions
   - Assignment → `POST /courses/{id}/assignments/` with WRITTEN type
   - On success → card shows "✓ Added" green state
   - "Add All to Module →" button does all at once

**UI design (OpenMAIC-inspired):**

- Input card: `rounded-2xl border border-gray-200 bg-white shadow-sm`
- Textarea: borderless, `bg-transparent`, placeholder "Describe what you want to generate, or drop a file..."
- File type pills: `rounded-full px-3 py-1.5 text-xs font-medium border` with active state (primary color bg)
- Outline cards: `rounded-xl border p-4` with number badge (circle), inline edit inputs
- Preview cards: `rounded-xl border p-4` with status icon, type badge, collapsible content
- Generate button: primary solid button, full-width below input
- "Add to Module" buttons: outline style, becomes solid green "✓ Added" on success
- Progress: simple dots/spinner per section, no heavy progress bars

### Step 3.3: Props Interface

```typescript
interface AIGenerationPanelProps {
  courseId: string;
  modules: Module[];  // list of modules for the selector
  onContentAdded: () => void;  // callback to refresh course data (invalidate query)
}
```

No more `onApplyComplete`, `onSwitchTab` — simpler interface.

---

## Phase 4: Integration & Verification

### Step 4.1: Wire Up

- CourseEditorPage passes `modules` list and `courseId` to AIGenerationPanel
- `onContentAdded` callback calls `queryClient.invalidateQueries(['course', courseId])`
- Verify Content tab updates when items are added via AI Generator

### Step 4.2: TypeScript Check

```bash
cd frontend && npx tsc --noEmit
```

Must pass with zero errors.

### Step 4.3: Functional Testing

Test on april5 tenant (`april5.localhost:3000`):

1. **Prompt-only flow:**
   - Select a module → type "Teaching climate change to middle schoolers" → Generate
   - Review outline → edit a section title → Generate Content
   - Preview lesson → click "Add to Module" → verify in Content tab

2. **PDF upload flow:**
   - Select a module → drop a PDF → Generate
   - Verify parsed content appears in outline
   - Generate content → add quiz to module → verify assignment created

3. **Video flow:**
   - Select a module → upload a short video → Generate
   - Verify transcript extracted and used for outline

4. **Combined flow:**
   - Type a topic + attach a PDF → Generate
   - Verify both prompt and material are used

5. **Edge cases:**
   - No module selected → Generate button disabled
   - No input → Generate button disabled
   - Generation fails → error shown inline, retry available
   - File too large → validation error
   - Unsupported file type → validation error

---

## Execution Strategy

| Phase | Scope | Estimated Complexity |
|-------|-------|---------------------|
| 1 | Backend: parse-material endpoint + prompt upgrades | Medium — new endpoint, prompt engineering |
| 2 | Frontend: tab cleanup (remove Activity, Assignment Builder) | Small — delete/modify a few files |
| 3 | Frontend: AIGenerationPanel rewrite | Large — new component, ~600-800 lines |
| 4 | Integration + testing | Small — wiring + verification |

**Recommended approach:** Phase 1 + 2 in parallel (backend + frontend cleanup), then Phase 3 (the main rewrite), then Phase 4 (testing).

**Single agent** — all changes are interconnected (removing tabs affects the editor page which affects the AI panel). No file ownership conflicts. One agent, sequential execution.

---

## File Impact Summary

| Action | File |
|--------|------|
| **New** | `backend/apps/courses/material_views.py` |
| **Modify** | `backend/apps/courses/urls.py` — add parse-material route |
| **Modify** | `backend/apps/courses/ai_service.py` — upgrade prompts |
| **Modify** | `frontend/src/pages/admin/course-editor/types.ts` — remove activity/assignments from EditorTab |
| **Modify** | `frontend/src/pages/admin/CourseEditorPage.tsx` — 4 tabs, clean imports |
| **Rewrite** | `frontend/src/components/courses/AIGenerationPanel.tsx` — full rewrite |
| **Modify** | `frontend/src/services/aiService.ts` — add parseMaterial, generateAssignment |
| **Delete** | `frontend/src/components/courses/CourseActivity.tsx` |
| **Delete** | `frontend/src/components/courses/LessonPlanner.tsx` |
