# Course Editor Redesign — Design Spec

**Date:** 2026-04-06
**Context:** Redesign the course editor tabs to simplify the admin experience, merge AI Tools + Assignment Builder into a single "AI Generator" tab with OpenMAIC-style pedagogical pipeline, remove Activity tab.

---

## Tab Structure

| Tab | Purpose |
|-----|---------|
| **Details** | Title, description, estimated hours, deadline, thumbnail, mandatory toggle (unchanged) |
| **Content** | Module list with manual add/edit/reorder of content items (unchanged) |
| **AI Generator** | Unified AI content generation — from material or prompt → preview → one-click add to module |
| **Course Audience** | Assign teachers and groups to the course (unchanged) |

**Removed:** Activity tab, standalone Assignment Builder tab.

---

## AI Generator Tab — Detailed Design

### Layout (Top to Bottom)

```
┌──────────────────────────────────────────────────────────┐
│  Module Selector (dropdown)                               │
│  "Select a module to generate content for"               │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Unified Input Area (glassmorphism card)           │  │
│  │                                                    │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  Drop files here or type a topic...          │  │  │
│  │  │                                              │  │  │
│  │  │  (auto-expanding textarea + drop zone)       │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  │                                                    │  │
│  │  ┌─────────────────────────────────────────────┐   │  │
│  │  │ [📎 Upload] [📄 PDF] [🎬 Video] [📝 DOCX] │   │  │
│  │  │                          [Generate ➜]       │   │  │
│  │  └─────────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Uploaded File Preview (conditional)               │  │
│  │  [icon] filename.pdf  12.3 MB  ✕ remove           │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  STAGE 1: Outline Review (after generation starts)       │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Section 1: "Understanding Digital Citizenship"    │  │
│  │  Objectives: [editable tags]                       │  │
│  │  Content: Lesson text, Quiz (3 MCQ)                │  │
│  │  [Edit] [Remove]                                   │  │
│  ├────────────────────────────────────────────────────┤  │
│  │  Section 2: "Online Safety Practices"              │  │
│  │  ...                                               │  │
│  ├────────────────────────────────────────────────────┤  │
│  │  [+ Add Section]                                   │  │
│  │  [← Back] [Generate Content ➜]                    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  STAGE 2: Generated Content Preview (inline cards)       │
│  ┌────────────────────────────────────────────────────┐  │
│  │  ✅ Lesson: "Understanding Digital Citizenship"    │  │
│  │  [Preview ▾]  [Add to Module ➜]                   │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  <h2>What is Digital Citizenship?</h2>       │  │  │
│  │  │  <p>Digital citizenship refers to...</p>     │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  ├────────────────────────────────────────────────────┤  │
│  │  ✅ Quiz: "Digital Citizenship Assessment"         │  │
│  │  [Preview ▾]  [Add to Module ➜]                   │  │
│  │  3 questions • MCQ • Medium difficulty             │  │
│  ├────────────────────────────────────────────────────┤  │
│  │  ✅ Assignment: "Online Safety Action Plan"        │  │
│  │  [Preview ▾]  [Add to Module ➜]                   │  │
│  │  Open-ended • Rubric included                      │  │
│  ├────────────────────────────────────────────────────┤  │
│  │  ✅ Summary: "Key Takeaways"                       │  │
│  │  [Preview ▾]  [Add to Module ➜]                   │  │
│  ├────────────────────────────────────────────────────┤  │
│  │  [Add All to Module ➜]                            │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 1. Module Selector

- Dropdown at the top of the AI Generator tab
- Lists all modules in the current course
- Required before generation — disabled state on Generate button if no module selected
- Shows module order number and title: "1. Introduction to AI in Education"

### 2. Unified Input Area

**Smart detection behavior:**

| Input | Detection | Behavior |
|-------|-----------|----------|
| User types text | Prompt mode | Topic/description sent to outline generation |
| User drops/uploads PDF | Material mode | PDF parsed → text extracted → sent to outline generation with material context |
| User drops/uploads video | Material mode | Video transcribed (existing Whisper pipeline) → transcript sent to outline generation |
| User drops/uploads DOCX/PPTX | Material mode | Document text extracted → sent to outline generation |
| User types text + uploads file | Combined mode | Both prompt and extracted material sent to outline generation |

**Input area design (OpenMAIC-inspired):**
- Single card with subtle border, rounded-2xl
- Textarea: borderless, transparent background, placeholder "Describe what you want to generate, or drop a file..."
- Auto-expanding height (min 120px, max 300px)
- Bottom toolbar row:
  - Left: file type pills (Upload, PDF, Video, DOCX) — clicking opens file picker filtered to that type
  - Right: Generate button (primary, disabled until input provided + module selected)
- Drag-and-drop: entire card is a drop zone, shows dashed border on dragover
- File preview: appears below input when file attached, shows icon + name + size + remove button

**Content type selection:**
- After the input area, before generating: a row of toggleable pills for what to generate
- Options: **Lesson** | **Quiz** | **Assignment** | **Summary**
- Multiple can be selected (default: all selected)
- These map to our generation types:
  - Lesson → `ai/generate-content/` (TEXT type)
  - Quiz → `assignments/ai-generate/` (quiz with questions)
  - Assignment → `ai/generate-content/` (assignment prompt with rubric)
  - Summary → `ai/summarize/`

### 3. Stage 1: Outline Review (OpenMAIC Pipeline)

**Triggered when:** User clicks Generate.

**Pipeline:**
1. If file uploaded: parse file → extract text (and images for PDF)
2. Send to `ai/generate-outline/` with: topic/text + extracted material + content types + target module context
3. Stream results as they arrive (SSE if possible, or show loading then results)

**Outline display:**
- Collapsible section cards (OpenMAIC `OutlinesEditor` style)
- Each section shows:
  - **Number badge** (circle with index)
  - **Title** (editable inline)
  - **Learning objectives** (editable, as tags or comma-separated)
  - **Key points** (3-5 bullet points, editable)
  - **Content types** to generate for this section (pill toggles: Lesson / Quiz / Assignment / Summary)
  - **Reorder** buttons (up/down arrows)
  - **Delete** button
- **Add Section** button at bottom
- **Action buttons:** "← Back to Input" | "Generate Content →"

**The admin can:**
- Edit section titles and descriptions
- Remove sections they don't want
- Add new sections
- Toggle which content types to generate per section
- Reorder sections

### 4. Stage 2: Content Generation + Preview

**Triggered when:** Admin clicks "Generate Content →" from outline review.

**Generation flow:**
- For each section in the outline, generate requested content types in parallel
- Show per-section progress: pending → generating → done / failed
- Overall progress bar at top

**Generated content preview (inline cards):**
- Each generated item is a card with:
  - **Status icon** (✅ done, ⏳ generating, ❌ failed)
  - **Type badge** (Lesson / Quiz / Assignment / Summary)
  - **Title**
  - **Collapsible preview** — click "Preview ▾" to expand:
    - Lesson: rendered HTML content
    - Quiz: list of questions with options (correct answer highlighted)
    - Assignment: prompt text + rubric table
    - Summary: condensed text
  - **"Add to Module →" button** — one-click adds this item to the selected module via API
  - **"Regenerate" button** — re-generate just this item
- **"Add All to Module →" button** at bottom — bulk add everything

**API calls on "Add to Module":**
- Lesson → `POST /courses/{id}/modules/{mid}/contents/` with `content_type: TEXT`
- Quiz → `POST /courses/{id}/assignments/` with generated questions
- Assignment → `POST /courses/{id}/assignments/` with type WRITTEN
- Summary → `POST /courses/{id}/modules/{mid}/contents/` with `content_type: TEXT`

After adding, the card shows "✓ Added" state (green, disabled button). Admin can switch to Content tab to see it.

---

## OpenMAIC Pipeline Integration

### Pedagogical Prompt Structure

Replace current flat "generate text about topic" prompts with OpenMAIC's structured approach:

**Stage 1 prompt (outline generation):**
```
You are an instructional designer creating a structured learning module.

Given the topic/material below, create a pedagogically sound outline that follows:
1. Learning Objectives (what the learner will be able to do)
2. Content Sections (logical progression from foundational → applied)
3. Assessment Points (where to check understanding)
4. Key Takeaways (summary points)

For each section, identify:
- Title and description
- 3-5 key teaching points
- Suggested content type (lesson text, quiz, assignment, summary)
- Bloom's taxonomy level (Remember → Understand → Apply → Analyze → Evaluate → Create)

Topic/Material: {{input}}
Target audience: {{course_description}}
Number of sections: {{num_sections}}
```

**Stage 2 prompts (per content type):**

- **Lesson text:** Generate structured HTML with headings, key concepts highlighted, examples, analogies. Not a wall of text — scannable, visual, with embedded callouts.
- **Quiz:** Generate Bloom's-aligned questions at appropriate difficulty. MCQ with plausible distractors, short answer with expected responses. Include answer explanations.
- **Assignment:** Generate open-ended prompt with clear success criteria, rubric (4-level), and example submission guidance.
- **Summary:** Generate concise key takeaways with 5-7 bullet points and a one-paragraph synthesis.

### Material Processing Pipeline

| Material Type | Processing | What AI Receives |
|---------------|-----------|------------------|
| **PDF** | Extract text (first 100k chars) + images | Full text context + image descriptions |
| **Video** | Transcribe via Whisper (existing pipeline) | Transcript text |
| **DOCX** | Extract text via python-docx | Full text content |
| **PPTX** | Extract slide text + notes via python-pptx | Slide-by-slide text |
| **Text prompt** | Direct pass-through | User's topic description |

New backend endpoint needed: `POST /api/v1/courses/ai/parse-material/`
- Accepts multipart file upload
- Returns: `{ text: string, images?: { id: string, description: string }[], metadata: { pages, file_type, file_size } }`
- Handles PDF, DOCX, PPTX, video (via existing transcription)

---

## UI/UX Principles (OpenMAIC-Inspired)

### Visual Design
- **Clean cards** with subtle borders (border-border/60), rounded-xl
- **Minimal chrome** — no heavy headers, no wizard step indicators
- **Progressive disclosure** — outline and preview sections appear only after generation
- **Inline editing** — edit outlines in place, no modals
- **Pill-based controls** — content type toggles, file type selectors

### Interaction Design
- **Single-page flow** — no multi-step wizard, no modal dialogs
- **Smart defaults** — all content types selected by default, outline auto-populated
- **One-click actions** — "Add to Module" is a single button press
- **Non-destructive** — generated content is previewed before adding, nothing auto-saves
- **Recoverable** — "Back" buttons at every stage, regenerate individual items

### States
- **Empty:** Module selector + input area, nothing else visible
- **File attached:** Input area + file preview card
- **Generating outline:** Input area + loading spinner with "Analyzing content..."
- **Outline ready:** Input area + outline editor cards + action buttons
- **Generating content:** Outline (collapsed) + progress indicators per section
- **Content ready:** Preview cards with "Add to Module" buttons
- **Added:** Cards show "✓ Added to [Module Name]" green state

---

## Files to Change

### Remove
- `components/courses/CourseActivity.tsx` — Activity tab component
- `components/courses/LessonPlanner.tsx` — Re-export file (no longer needed)

### Rewrite
- `components/courses/AIGenerationPanel.tsx` — Complete rewrite as single-page AI Generator with OpenMAIC pipeline

### Modify
- `pages/admin/CourseEditorPage.tsx` — Remove Activity tab, remove Assignment Builder tab, rename "AI Tools" to "AI Generator"
- `pages/admin/course-editor/types.ts` — Remove `'activity'` from EditorTab, remove `'assignments'` from EditorTab, keep `'ai'` (rename display label only)

### New (Backend)
- `apps/courses/ai_views.py` — Add `parse_material` endpoint for PDF/DOCX/PPTX/video text extraction
- Upgrade generation prompts in `apps/courses/ai_service.py` to use pedagogical structure

### Dependencies
- `python-docx` — DOCX text extraction
- `python-pptx` — PPTX text extraction
- PDF extraction already exists (uploads pipeline)
- Video transcription already exists (Whisper pipeline)

---

## What This Does NOT Change

- **Details tab** — unchanged
- **Content tab** — unchanged (it's the manual workbench)
- **Course Audience tab** — unchanged (teacher/group assignment)
- **Backend course/module/content CRUD** — unchanged
- **Teacher-facing Interactive Lessons & Scenarios** — stays on teacher side, not in admin editor
