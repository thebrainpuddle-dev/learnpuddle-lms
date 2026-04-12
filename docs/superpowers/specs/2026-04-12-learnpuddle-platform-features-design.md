# LearnPuddle Platform Feature Design

**Date:** 2026-04-12
**Status:** Approved
**Scope:** Teacher, Student, and Admin portals — core feature set, AI Chatbot Builder, cleanup of deprecated features

---

## 1. Vision

LearnPuddle is a dual-purpose school LMS where schools use the platform for both **teacher professional development** and **student-facing academics**. The MAIC AI Classroom is the centerpiece for both audiences. Teachers also create AI Chatbots — RAG-powered assistants trained on uploaded knowledge with configurable guardrails — that students interact with 24/7.

**Three portals, one AI-powered core:**
- **Teacher Portal** — Consume PD courses, create AI Classrooms & Chatbots
- **Student Portal** — Consume academic courses, interact with AI Classrooms & Chatbots
- **Admin Portal** — Manage school, create & assign PD courses/classrooms, analytics

---

## 2. Portal Feature Sets

### 2.1 Teacher Portal (8 modules)

| Module | Description |
|--------|-------------|
| **Dashboard** | Overview: my courses, recent AI Classrooms, chatbot activity, upcoming deadlines |
| **My Courses** | Browse & consume PD courses assigned by admin (videos, documents, quizzes, AI Classrooms embedded as content) |
| **AI Classroom — Create** | Generate multi-agent interactive classrooms from topic or PDF. Outline review → scene generation → publish. Add to course modules as content type |
| **AI Classroom — Library** | Manage created classrooms (DRAFT/READY/ARCHIVED), preview, edit |
| **AI Classroom — Player** | Full playback: slides, whiteboard, multi-agent dialogue, TTS, chat, quizzes |
| **AI Chatbot Builder** | Create chatbots: name, avatar, persona preset (Tutor/Reference/Open) + custom rules. Upload knowledge (PDFs, text). Guardrail config. Auto-scoped to teacher's assigned courses/classes |
| **Assignments** | View & complete quizzes/homework from assigned PD courses |
| **Certificates** | View earned PD certificates |

**Removed:** Scenarios, Strategy Lab, Action Plans, Podcasts, AI Personas (old), Classroom Collaboration (old)

### 2.2 Student Portal (8 modules)

| Module | Description |
|--------|-------------|
| **Dashboard** | Overview: assigned courses, progress stats, upcoming assignments, recent activity |
| **My Courses** | Browse & consume assigned courses — videos, documents, AI Classrooms (embedded), quizzes |
| **AI Classroom — Browse** | Discover public AI Classrooms (filterable by subject, teacher, topic) |
| **AI Classroom — Player** | Full playback in student mode — no edit controls, full chat interaction |
| **AI Chatbots** | List of chatbots from assigned teachers. Chat 24/7 — ask questions, get explanations, study help. Guardrails enforced |
| **Study Notes** | Subject-wise filtered view of all documents, presentations, HTMLs from assigned courses. Browse by subject/course/module. No separate upload — this is a read-only view of course content |
| **Assignments** | View, attempt, submit quizzes/homework. See grades and feedback |
| **Certificates** | View and download earned certificates |

### 2.3 Admin Portal (9 modules)

| Module | Description |
|--------|-------------|
| **Dashboard** | School-wide stats: teachers/students, course completion rates, AI Classroom usage, chatbot activity, storage |
| **Course Management** | Create/edit courses with modules and content (video, document, text, AI Classroom, chatbot). Assign to teachers and/or students. Set mandatory/optional, deadlines |
| **AI Classroom — Create & Assign** | Create AI Classrooms for teacher PD. Assign to specific teachers or all teachers. Same generation wizard as teacher portal |
| **Teacher Management** | Add/bulk-import/edit/deactivate teachers. View individual progress. Assign to courses |
| **Student Management** | Add/bulk-import/edit/deactivate students. Assign to courses, grades, sections |
| **Groups** | Organize teachers into groups (by department, subject, grade). Assign courses to groups |
| **Certificates** | Design certificate templates. Assign to courses. Issue manually or auto-issue on completion |
| **Reports & Analytics** | Progress reports by course/teacher/student. Export CSV/PDF. AI Classroom engagement. Chatbot usage stats |
| **Settings** | School branding (logo, colors, fonts), feature toggles, AI provider config (LLM, TTS, API keys), tenant limits |

---

## 3. Database Schema

### 3.1 Models to REMOVE

These models and their admin registrations, views, URLs, serializers, services, and frontend pages are deleted:

| Model | File | Reason |
|-------|------|--------|
| `ScenarioTemplate` | `ai_studio_models.py` | Scenarios feature removed |
| `ScenarioAttempt` | `ai_studio_models.py` | Scenarios feature removed |
| `TeachingStrategy` | `ai_studio_models.py` | Strategy Lab removed |
| `ActionPlan` | `ai_studio_models.py` | Action Plans removed |
| `StudyNotes` | `ai_studio_models.py` | Replaced by course content filtered view |
| `CourseEmbedding` | `ai_models.py` | Replaced by AIChatbotChunk with pgvector |
| `ChatSession` | `ai_models.py` | Replaced by AIChatbotConversation |
| `ChatMessage` | `ai_models.py` | Messages now stored as JSONField in AIChatbotConversation |

After removal, `ai_studio_models.py` and `ai_models.py` are both deleted entirely.

### 3.2 Models to ADD

#### AIChatbot

Teacher-created AI chatbot with persona, knowledge base, and guardrails.

```
AIChatbot
├── id              UUID PK
├── tenant          FK → Tenant (CASCADE)
├── creator         FK → User (CASCADE) [teacher who created it]
├── name            CharField(200)
├── avatar_url      CharField(500, blank) [URL to avatar image]
├── persona_preset  CharField(20) choices: tutor | reference | open
├── persona_description  TextField(blank) [personality description for LLM]
├── custom_rules    TextField(blank) [additional guardrail instructions]
├── block_off_topic BooleanField(default=True)
├── welcome_message TextField(blank) [first message shown to students]
├── is_active       BooleanField(default=True)
├── created_at      DateTimeField(auto_now_add)
├── updated_at      DateTimeField(auto_now)
│
├── Meta:
│   indexes: (tenant, creator), (tenant, is_active)
│   TenantManager for auto-filtering
```

**Persona presets** map to system prompt templates:
- **tutor**: Socratic — never gives direct answers, asks guiding questions, hints progressively
- **reference**: Answers only from uploaded knowledge base, cites sources, says "I don't have that information" when not found
- **open**: Helpful study companion, stays on-topic but more flexible

#### AIChatbotKnowledge

Knowledge source uploaded to a chatbot (PDF, text, URL).

```
AIChatbotKnowledge
├── id              UUID PK
├── chatbot         FK → AIChatbot (CASCADE)
├── source_type     CharField(20) choices: pdf | text | url | document
├── title           CharField(300)
├── filename        CharField(500, blank) [original filename for uploads]
├── file_url        CharField(500, blank) [stored file path]
├── raw_text        TextField(blank) [for text source_type]
├── content_hash    CharField(64) [SHA-256 for dedup]
├── chunk_count     PositiveIntegerField(default=0)
├── total_token_count PositiveIntegerField(default=0) [total tokens across all chunks]
├── embedding_status CharField(20) choices: pending | processing | ready | failed
├── error_message   TextField(blank)
├── created_at      DateTimeField(auto_now_add)
├── updated_at      DateTimeField(auto_now)
│
├── Meta:
│   indexes: (chatbot, embedding_status)
```

#### AIChatbotChunk

Individual text chunk with pgvector embedding for RAG retrieval.

```
AIChatbotChunk
├── id              BigAutoField PK
├── knowledge       FK → AIChatbotKnowledge (CASCADE)
├── tenant          FK → Tenant (CASCADE) [denormalized for fast filtered search]
├── chatbot         FK → AIChatbot (CASCADE) [denormalized for fast filtered search]
├── chunk_index     PositiveIntegerField
├── content         TextField [the chunk text]
├── token_count     PositiveIntegerField(default=0)
├── heading         CharField(512, blank) [section heading if available]
├── page_number     PositiveIntegerField(null=True) [for PDFs]
├── embedding       VectorField(dimensions=1536) [text-embedding-3-small]
├── metadata        JSONField(default=dict)
├── created_at      DateTimeField(auto_now_add)
│
├── Meta:
│   ordering: [knowledge, chunk_index]
│   unique_together: (knowledge, chunk_index)
│   indexes:
│     HnswIndex(embedding, m=16, ef_construction=64, vector_cosine_ops)
│     (tenant, chatbot)
```

#### AIChatbotConversation

Student conversation session with a chatbot.

```
AIChatbotConversation
├── id              UUID PK
├── tenant          FK → Tenant (CASCADE)
├── chatbot         FK → AIChatbot (CASCADE)
├── student         FK → User (CASCADE)
├── title           CharField(300) [auto-generated from first message]
├── messages        JSONField(default=list)
│   └── [{role: "user"|"assistant", content: str, timestamp: int, sources?: [{title, page}]}]
├── message_count   PositiveIntegerField(default=0)
├── is_flagged      BooleanField(default=False) [guardrail violation detected]
├── flag_reason     TextField(blank)
├── started_at      DateTimeField(auto_now_add)
├── last_message_at DateTimeField(auto_now)
│
├── Meta:
│   indexes: (tenant, student), (chatbot, student), (tenant, is_flagged)
│   TenantManager
```

### 3.3 Models to MODIFY

#### Content — New content types

Update `CONTENT_TYPE_CHOICES` — remove deprecated types, add new ones:
```python
# REMOVE:
('INTERACTIVE_LESSON', 'Interactive Lesson'),  # deleted in migration 0022
('SCENARIO', 'Scenario Simulation'),           # being removed now

# ADD:
('AI_CLASSROOM', 'AI Classroom'),
('CHATBOT', 'AI Chatbot'),

# FINAL choices:
CONTENT_TYPE_CHOICES = [
    ('VIDEO', 'Video'),
    ('DOCUMENT', 'Document'),
    ('LINK', 'External Link'),
    ('TEXT', 'Text Content'),
    ('AI_CLASSROOM', 'AI Classroom'),
    ('CHATBOT', 'AI Chatbot'),
]
```

Add optional FK fields:
```python
maic_classroom = FK → MAICClassroom (SET_NULL, null=True, blank=True)
ai_chatbot     = FK → AIChatbot (SET_NULL, null=True, blank=True)
```

Note: `scenario_template` and `interactive_lesson` are reverse OneToOneField relations from `ScenarioTemplate` and `InteractiveLesson` (already deleted in 0022) — not FK columns on Content. Deleting the parent models automatically removes these reverse relations. No Content schema changes needed for removal.

When `content_type='AI_CLASSROOM'`, `maic_classroom` points to the linked classroom.
When `content_type='CHATBOT'`, `ai_chatbot` points to the linked chatbot.

**Data migration required:** Any existing Content rows with `content_type='INTERACTIVE_LESSON'` or `content_type='SCENARIO'` must be migrated to `content_type='TEXT'` (preserving title/description) or deleted, before the choices are removed. This is a separate data migration that runs before the schema migration.

### 3.4 Models to MODIFY (TenantAIConfig)

Add chatbot limit to `TenantAIConfig`:
```python
max_chatbots_per_teacher = PositiveIntegerField(default=10)  # per-tenant limit
```

### 3.5 Models that STAY (no changes)

- `Tenant` (with `feature_maic`)
- `User` (all roles)
- `Course`, `Module` (course structure)
- `TeacherGroup` (teacher organization)
- `TeacherProgress` (progress tracking)
- `MAICClassroom` (AI Classroom metadata)
- `VideoAsset`, `VideoTranscript` (video pipeline)
- All notification, reminder, certificate models

---

## 4. API Design

### 4.1 Teacher Chatbot APIs

All chatbot endpoints require `@check_feature("feature_maic")` decorator (same feature flag as AI Classroom — one toggle controls both MAIC features).

```
POST   /api/v1/teacher/chatbots/                         → Create chatbot
GET    /api/v1/teacher/chatbots/                         → List my chatbots
GET    /api/v1/teacher/chatbots/<id>/                    → Chatbot detail
PATCH  /api/v1/teacher/chatbots/<id>/                    → Update chatbot config
DELETE /api/v1/teacher/chatbots/<id>/                    → Deactivate chatbot

POST   /api/v1/teacher/chatbots/<id>/knowledge/          → Upload knowledge source
GET    /api/v1/teacher/chatbots/<id>/knowledge/          → List knowledge sources
DELETE /api/v1/teacher/chatbots/<id>/knowledge/<kid>/    → Remove knowledge source

GET    /api/v1/teacher/chatbots/<id>/conversations/      → List student conversations
GET    /api/v1/teacher/chatbots/<id>/conversations/<cid>/ → Conversation detail
GET    /api/v1/teacher/chatbots/<id>/analytics/          → Usage stats (message count, unique students, flagged count, common questions)
```

### 4.2 Student Chatbot APIs

```
GET    /api/v1/student/chatbots/                         → List available chatbots (from assigned teachers)
POST   /api/v1/student/chatbots/<id>/chat/               → Send message → SSE response (RAG + LLM)
GET    /api/v1/student/chatbots/<id>/conversations/      → My conversation history (paginated, 20/page)
GET    /api/v1/student/chatbots/<id>/conversations/<cid>/ → Conversation detail
POST   /api/v1/student/chatbots/<id>/conversations/      → Start new conversation
```

Conversation list endpoints use cursor-based pagination (ordered by `last_message_at` desc) to handle students with many conversations.

### 4.3 Existing APIs — Changes

| API | Change |
|-----|--------|
| Teacher course content endpoints | Accept `content_type=AI_CLASSROOM` and `content_type=CHATBOT` with corresponding FK |
| Student course content endpoints | Return AI Classroom and Chatbot content types with embedded metadata |
| Admin AI config | No changes (already supports LLM + TTS config) |

### 4.4 APIs to REMOVE

| Endpoint Pattern | Reason |
|------------------|--------|
| `/api/v1/teacher/scenarios/*` | Scenarios removed |
| `/api/v1/teacher/strategies/*` | Strategy Lab removed |
| `/api/v1/teacher/action-plans/*` | Action Plans removed |
| `/api/v1/teacher/notes/*` | Study Notes generation removed (view stays as course content filter) |
| `/api/v1/student/scenarios/*` | Scenarios removed |
| `/api/v1/student/notes/*` | Notes generation removed |

---

## 5. AI Chatbot Architecture

### 5.1 Knowledge Ingestion Pipeline

```
Teacher uploads PDF/text
        │
        ▼
  Save to AIChatbotKnowledge (status=pending)
        │
        ▼
  Celery task: ingest_chatbot_knowledge
        │
        ├── PDF → PyMuPDF text extraction
        ├── Text → direct use
        ├── URL → fetch + extract
        │
        ▼
  Chunk (512 tokens, 50-token overlap)
        │
        ▼
  Batch embed (text-embedding-3-small, 1536 dims)
        │
        ▼
  Bulk insert AIChatbotChunk rows
        │
        ▼
  Update AIChatbotKnowledge (status=ready, chunk_count=N)
```

### 5.2 Chat Pipeline (Student → Chatbot)

```
Student sends message
        │
        ▼
  Build query embedding (text-embedding-3-small)
        │
        ▼
  pgvector similarity search
  (filter: tenant_id + chatbot_id, cosine distance < 0.4, top 5)
        │
        ▼
  Assemble system prompt:
    1. Base guardrail (always-on safety rules)
    2. Persona preset template (tutor/reference/open)
    3. Persona description (teacher-written personality)
    4. Custom rules (teacher-written instructions)
    5. Block off-topic instruction (if enabled)
    6. Retrieved context chunks with source citations
        │
        ▼
  LLM call (via TenantAIConfig — OpenRouter/OpenAI/etc.)
  Stream response via SSE
        │
        ▼
  Append to AIChatbotConversation.messages
  Check for guardrail violations → flag if detected
```

### 5.3 Guardrail System

**Three layers:**

1. **Always-on safety rules** (cannot be overridden by teacher):
   - No harmful, violent, sexual, or illegal content
   - No personal advice (medical, legal, financial)
   - No generating content that could be used for cheating on external exams
   - Redirect to human teacher for sensitive topics

2. **Persona preset** (teacher selects one):
   - **Tutor**: "You are a Socratic tutor. Never give direct answers to questions that test understanding. Instead, ask guiding questions that lead the student to discover the answer themselves. Use progressive hints — start vague, get more specific only if the student is stuck."
   - **Reference**: "You are a reference assistant. Answer questions ONLY using information from the provided knowledge base. Always cite the source document and page number. If the answer is not in the knowledge base, say: 'I don't have that information in my materials. Please ask your teacher.'"
   - **Open Discussion**: "You are a helpful study companion. Explain concepts clearly, provide examples, and encourage deeper thinking. Stay focused on the subject matter."

3. **Teacher custom rules** (appended to system prompt):
   - Free-text instructions like "Never give homework answers directly", "Always respond in formal English", "Encourage students to show their work before helping"
   - **Block off-topic toggle**: Adds "If the student's question is unrelated to the subject matter of the uploaded materials, politely redirect them back to the topic."

### 5.4 Chatbot Scoping (Access Control)

No explicit sharing mechanism. Access flows through existing relationships:

```
Teacher creates Chatbot
        │
Teacher is assigned to Course(s)
        │
Students are assigned to those same Course(s)
        │
Student chatbot list API:
  SELECT DISTINCT chatbot.*
  FROM ai_chatbot chatbot
  JOIN users teacher ON chatbot.creator_id = teacher.id
  JOIN course_assigned_teachers cat ON cat.user_id = teacher.id
  JOIN course_assigned_students cas ON cas.course_id = cat.course_id
  WHERE cas.user_id = <student_id>
    AND chatbot.is_active = TRUE
    AND chatbot.tenant_id = <tenant_id>
```

No new models needed for scoping — it derives from `Course.assigned_teachers` and `Course.assigned_students` M2M relationships.

**Important:** The implementation must also filter by `course.is_active = TRUE` and `course.is_published = TRUE` to prevent exposing chatbots from unpublished or deactivated courses.

### 5.5 Technical Stack for RAG

| Component | Technology |
|-----------|------------|
| Vector storage | pgvector 0.7+ (PostgreSQL extension) |
| Django integration | `pgvector` package (`pgvector.django`) — VectorField, CosineDistance, HnswIndex |
| Embedding model | `text-embedding-3-small` (1536 dims, $0.02/1M tokens) |
| Chunking | Token-based (512 tokens, 50 overlap) via `tiktoken` |
| PDF parsing | PyMuPDF (`fitz`) |
| Index type | HNSW (m=16, ef_construction=64, vector_cosine_ops) |
| Tenant isolation | Row-level `tenant_id` filter on chunk table |
| Background ingestion | Celery task with batch embedding (2048 per API call) |
| Search | Cosine similarity with threshold (< 0.4), top 5 chunks |

---

## 6. Frontend Architecture

### 6.1 New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `ChatbotBuilderPage.tsx` | `pages/teacher/` | Full chatbot creation/edit form |
| `ChatbotListPage.tsx` | `pages/teacher/` | List teacher's chatbots with status |
| `ChatbotChat.tsx` | `components/maic/` | Chat interface for student interaction (SSE streaming) |
| `ChatbotCard.tsx` | `components/maic/` | Card for chatbot grid/list views |
| `KnowledgeUploader.tsx` | `components/maic/` | Drag-and-drop PDF/text upload with progress |
| `GuardrailConfig.tsx` | `components/maic/` | Preset selector + custom rules editor |
| `StudentChatbotsPage.tsx` | `pages/student/` | Browse available chatbots from assigned teachers |
| `StudentChatPage.tsx` | `pages/student/` | Full chat interface with conversation history |
| `StudyNotesPage.tsx` (rewrite) | `pages/student/` | Filtered course content browser by subject |

### 6.2 Sidebar Updates

**Teacher Sidebar (updated):**
```
Main
  ├── Dashboard
  ├── My Courses
  └── My Classes

AI Learning
  ├── AI Classroom        → /teacher/ai-classroom
  ├── AI Chatbots         → /teacher/chatbots        [NEW]
  └── Discussions

Tools
  ├── Announcements
  ├── Assessments
  ├── Competency
  └── Reports

[Removed: Strategy Lab, Action Plans]
[Study Notes stays under AI Learning or removed from teacher — teachers access notes through courses]
```

**Student Sidebar (updated):**
```
Main
  ├── Dashboard
  └── My Courses

Learning
  ├── Assignments
  └── Achievements

Learning Tools
  ├── AI Classroom        → /student/ai-classroom
  ├── AI Chatbots         → /student/chatbots        [NEW]
  └── Study Notes         → /student/study-notes

[Bottom: Profile, Settings, Support, Logout]
```

### 6.3 New Zustand Store

```typescript
// stores/chatbotStore.ts
interface ChatbotStore {
  // Teacher
  chatbots: AIChatbot[];
  selectedChatbot: AIChatbot | null;
  loadChatbots: () => Promise<void>;
  createChatbot: (data: CreateChatbotRequest) => Promise<AIChatbot>;
  updateChatbot: (id: string, data: Partial<AIChatbot>) => Promise<void>;
  deleteChatbot: (id: string) => Promise<void>;

  // Student
  availableChatbots: AIChatbot[];
  loadAvailableChatbots: () => Promise<void>;

  // Chat
  activeConversation: Conversation | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  sendMessage: (chatbotId: string, message: string) => Promise<void>;
  loadConversation: (conversationId: string) => Promise<void>;
  startNewConversation: (chatbotId: string) => Promise<void>;
}
```

### 6.4 New TypeScript Types

```typescript
// types/chatbot.ts
interface AIChatbot {
  id: string;
  name: string;
  avatar_url: string;
  persona_preset: 'tutor' | 'reference' | 'open';
  persona_description: string;
  custom_rules: string;
  block_off_topic: boolean;
  welcome_message: string;
  is_active: boolean;
  knowledge_count: number;
  conversation_count: number;
  created_at: string;
  updated_at: string;
}

interface AIChatbotKnowledge {
  id: string;
  source_type: 'pdf' | 'text' | 'url' | 'document';
  title: string;
  filename: string;
  chunk_count: number;
  embedding_status: 'pending' | 'processing' | 'ready' | 'failed';
  error_message: string;
  created_at: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  sources?: { title: string; page?: number }[];
}

interface Conversation {
  id: string;
  chatbot_id: string;
  title: string;
  messages: ChatMessage[];
  message_count: number;
  is_flagged: boolean;
  started_at: string;
  last_message_at: string;
}
```

---

## 7. Cleanup Plan

### 7.1 Backend Files to DELETE

| File | Contains |
|------|----------|
| `apps/courses/ai_studio_models.py` | ScenarioTemplate, ScenarioAttempt, TeachingStrategy, ActionPlan, StudyNotes |
| `apps/courses/ai_studio_views.py` | Views for all removed features (scenarios, strategies, action plans) — 843 lines |
| `apps/courses/ai_studio_tasks.py` | Celery tasks: generate_scenario_from_content_async |
| `apps/courses/ai_models.py` | CourseEmbedding (JSON embeddings), ChatSession, ChatMessage — all replaced by AIChatbot* models |
| `apps/courses/ai_chat_views.py` | Chat session CRUD endpoints — imports ChatSession/ChatMessage from ai_models.py which is deleted |
| `apps/courses/ai_rag_service.py` | RAG service using CourseEmbedding/ChatSession — replaced by chatbot_rag_service.py |
| `apps/courses/notes_service.py` | Study notes generation logic (638 lines) |
| `apps/courses/openmaic_views.py` | Teacher study notes API endpoints (list, detail, status, export, generate, delete) |
| `apps/courses/consumers.py` | WebSocket consumer for AI Studio generation status — references deleted models |
| `apps/courses/routing.py` | WebSocket URL routing for AiStudioConsumer |

### 7.2 Frontend Files to DELETE

| File | Contains |
|------|----------|
| `pages/teacher/StrategyLabPage.tsx` | Strategy Lab page |
| `pages/teacher/ActionPlanPage.tsx` | Action Plans page |
| `pages/teacher/StudyNotesPage.tsx` | Old Study Notes generation page (uses notesApi) |
| `components/teacher/ScenarioSimulator.tsx` | Branching decision-tree scenario simulator |
| `components/lessons/SceneRenderer.tsx` | Interactive lesson scene renderer |
| `components/lessons/DragDropLayout.tsx` | Lesson layout component |
| `components/lessons/MatchingLayout.tsx` | Lesson layout component |
| `components/lessons/SequencingLayout.tsx` | Lesson layout component |
| `components/lessons/AddToCourseModal.tsx` | Add interactive lesson to course modal |
| `components/lessons/layouts/*.tsx` | All remaining lesson layout variants |
| `components/teacher/StudyNotesPanel.tsx` | Study notes panel component — orphaned after feature removal |

### 7.3 Backend Files to MODIFY

| File | Changes |
|------|---------|
| `admin.py` | Remove ScenarioTemplate, ScenarioAttempt, TeachingStrategy, ActionPlan admin registrations. Add AIChatbot, AIChatbotKnowledge, AIChatbotConversation admin |
| `models.py` | Update Content.CONTENT_TYPE_CHOICES (remove INTERACTIVE_LESSON, SCENARIO; add AI_CLASSROOM, CHATBOT). Add maic_classroom, ai_chatbot FK fields |
| `urls.py` | Remove `ai_studio_views` import and admin-level ai-studio URL patterns (lines 29-33: generate-scenario, generate-scenario-async, create-scenario, status). Remove `ai_chat_views` import and all `/chat/sessions/` URL patterns (lines 99-114) |
| `ai_service.py` | MODIFY not delete: Remove `generate_scenario`, `generate_interactive_lesson`, `generate_teaching_strategies`, `generate_action_plan` methods from `AICourseGenerator`. Keep the class and remaining active methods (`generate_course_outline`, `generate_module_content`, `summarize_content`, `generate_assignment`) — still imported by `ai_views.py` |
| `teacher_urls.py` | Remove scenario/strategy/action-plan/notes URL patterns. Add chatbot URL patterns. Remove openmaic_views study notes routes |
| `student_urls.py` | Remove scenario/notes URL patterns. Add chatbot URL patterns |
| `student_views.py` | Remove student_get_scenario, student_submit_scenario_attempt, student_notes_list, student_notes_detail and related imports |
| `student_serializers.py` | Remove `scenario_id` and `interactive_lesson_id` fields from StudentContentProgressSerializer. Add `maic_classroom_id` and `ai_chatbot_id` |
| `serializers.py` | Remove `scenario_template_id` getter from ContentSerializer. Add `maic_classroom` and `ai_chatbot` FK serialization |
| `config/settings.py` | Add `'pgvector.django'` to INSTALLED_APPS. Remove `ai_studio_tasks` entries from `CELERY_TASK_ROUTES` (lines 600-603) |
| `maic_models.py` | Add `max_chatbots_per_teacher` field to TenantAIConfig |
| `teacher_serializers.py` | Remove `interactive_lesson_id` and `scenario_id` fields. Remove `select_related('interactive_lesson', 'scenario_template')`. Add `maic_classroom_id` and `ai_chatbot_id` |
| `apps/notifications/routing.py` | Remove import of `apps.courses.routing.websocket_urlpatterns` and remove `+ courses_ws_patterns` from combined URL list (prevents ASGI startup crash) |
| `tests_scene_validation.py` | Remove `TestStripQuizAnswers` class and `_strip_quiz_answers` import from `ai_studio_views` (lines 883-990) |

### 7.3.1 Backend Files to CREATE

| File | Purpose |
|------|---------|
| `apps/courses/chatbot_models.py` | AIChatbot, AIChatbotKnowledge, AIChatbotChunk, AIChatbotConversation models |
| `apps/courses/chatbot_views.py` | Teacher chatbot CRUD + student chatbot chat endpoints (SSE) |
| `apps/courses/chatbot_tasks.py` | Celery tasks: `ingest_chatbot_knowledge` (PDF parse → chunk → embed → pgvector insert) |
| `apps/courses/chatbot_serializers.py` | Serializers for chatbot CRUD, knowledge sources, conversations |
| `apps/courses/chatbot_urls.py` | URL patterns for all chatbot endpoints (teacher + student) |
| `apps/courses/chatbot_rag_service.py` | RAG pipeline: query embedding → pgvector similarity search → context assembly → LLM call |
| `apps/courses/chatbot_guardrails.py` | System prompt builder: base safety + persona preset + custom rules |

### 7.4 Frontend Files to MODIFY

| File | Changes |
|------|---------|
| `TeacherSidebar.tsx` | Remove Strategy Lab (Lightbulb icon, line 53), Action Plans (Target icon, line 54), Study Notes (FileText icon, line 45) nav items. Add AI Chatbots nav item |
| `StudentSidebar.tsx` | Remove Study Notes (StickyNote icon, line 44) — will be re-added as course content view. Add AI Chatbots nav item |
| `App.tsx` | Remove lazy imports + routes: StrategyLabPage (line 141-142), ActionPlanPage (line 144-145), teacher StudyNotesPage (line 155-156), student StudyNotesPage (line 207-208). Add chatbot page routes |
| `services/openmaicService.ts` | Remove `notesApi` object (lines 41-68). Add `chatbotApi` and `chatbotStudentApi` |
| `services/aiService.ts` | Remove `strategyLab` API object (lines 437-450), `actionPlans` API object (lines 451-482), all scenario/lesson types + methods (lines 75-159), `teacherStudio.getScenario`, `teacherStudio.submitAttempt`, `teacherStudio.getLesson`, `teacherStudio.submitReflection`, etc. |
| `services/studentService.ts` | Remove `INTERACTIVE_LESSON` and `SCENARIO` from content type union (line 80). Add `AI_CLASSROOM` and `CHATBOT` |
| `pages/student/CourseViewPage.tsx` | Remove scenario content type handling. Add AI_CLASSROOM and CHATBOT content type rendering |
| `pages/teacher/CourseViewPage.tsx` | Remove scenario/lesson content type handling. Add AI_CLASSROOM and CHATBOT content type rendering |
| `pages/admin/CourseEditorPage.tsx` | Remove InteractiveLessonPreview comment. Add AI_CLASSROOM and CHATBOT as content type options in editor |
| `pages/admin/course-editor/types.ts` | Remove `INTERACTIVE_LESSON` and `SCENARIO` from content_type union (line 30) |
| `pages/admin/course-editor/ModuleContentEditor.tsx` | Remove switch cases and `<option>` elements for INTERACTIVE_LESSON and SCENARIO (lines 43-45, 390-391) |
| `components/teacher/index.ts` | Remove `ScenarioSimulator`, `ScenarioNodeContext`, and `StudyNotesPanel` exports |
| `pages/teacher/index.ts` | Remove `StrategyLabPage`, `ActionPlanPage`, `StudyNotesPage` exports |

### 7.5 Migrations (3 separate, ordered)

**Migration 0023: Data migration for deprecated content types**
- Convert any Content rows with `content_type='INTERACTIVE_LESSON'` to `content_type='TEXT'` (preserve title, description)
- Convert any Content rows with `content_type='SCENARIO'` to `content_type='TEXT'`
- This is a `RunPython` data migration — must run before schema changes

**Migration 0024: Drop deprecated models + update Content**
- Drop tables: ScenarioTemplate, ScenarioAttempt, TeachingStrategy, ActionPlan, StudyNotes, CourseEmbedding, ChatSession, ChatMessage (deleting ScenarioTemplate auto-removes its OneToOne reverse relation on Content)
- Remove `INTERACTIVE_LESSON`, `SCENARIO` from Content.content_type choices
- Add `AI_CLASSROOM`, `CHATBOT` to Content.content_type choices
- Add `maic_classroom` FK (nullable) and `ai_chatbot` FK (nullable) to Content
- Add `max_chatbots_per_teacher` to TenantAIConfig

**Migration 0025: Create chatbot models + enable pgvector**
- `CREATE EXTENSION IF NOT EXISTS vector` (RunSQL)
- Create AIChatbot table
- Create AIChatbotKnowledge table
- Create AIChatbotChunk table with VectorField(1536)
- Create AIChatbotConversation table
- Create HNSW index on AIChatbotChunk.embedding (m=16, ef_construction=64, vector_cosine_ops)

Separating migrations ensures: (a) data is preserved before schema drops, (b) pgvector extension is enabled before vector columns are created, (c) each migration can be rolled back independently.

---

## 8. Implementation Phases

### Phase 1: Cleanup
**Backend DELETE** (10 files): `ai_studio_models.py`, `ai_studio_views.py`, `ai_studio_tasks.py`, `ai_models.py`, `ai_chat_views.py`, `ai_rag_service.py`, `notes_service.py`, `openmaic_views.py`, `consumers.py`, `routing.py`. **Backend MODIFY** (11 files): `admin.py`, `models.py`, `urls.py`, `teacher_urls.py`, `student_urls.py`, `student_views.py`, `serializers.py`, `student_serializers.py`, `teacher_serializers.py`, `ai_service.py` (remove deprecated methods, keep active ones), `config/settings.py` (remove CELERY_TASK_ROUTES entries), `apps/notifications/routing.py` (remove courses WS import), `tests_scene_validation.py`. **Frontend DELETE** (8+ files): `StrategyLabPage.tsx`, `ActionPlanPage.tsx`, teacher `StudyNotesPage.tsx`, `ScenarioSimulator.tsx`, `StudyNotesPanel.tsx`, all `components/lessons/` files. **Frontend MODIFY** (11 files): `App.tsx`, `TeacherSidebar.tsx`, `StudentSidebar.tsx`, `aiService.ts`, `openmaicService.ts`, `studentService.ts`, `CourseViewPage.tsx` (teacher+student), `CourseEditorPage.tsx`, `course-editor/types.ts`, `ModuleContentEditor.tsx`, `components/teacher/index.ts`, `pages/teacher/index.ts`. Create data migration 0023 + schema migration 0024. Verify builds pass.

### Phase 2: Schema & Infrastructure
Install dependencies: `pgvector`, `tiktoken`, `PyMuPDF`. Add `'pgvector.django'` to INSTALLED_APPS. Create `chatbot_models.py` with AIChatbot, AIChatbotKnowledge, AIChatbotChunk, AIChatbotConversation. Add `max_chatbots_per_teacher` to TenantAIConfig. Create migration 0025 (enable pgvector extension + create chatbot tables + HNSW index). Verify migration applies cleanly.

### Phase 3: Chatbot Backend
Create `chatbot_views.py` (teacher CRUD + student chat), `chatbot_serializers.py`, `chatbot_urls.py`. Create `chatbot_tasks.py` with `ingest_chatbot_knowledge` Celery task (PDF parsing → chunking → embedding → pgvector bulk insert). Create `chatbot_rag_service.py` (query embedding → pgvector similarity search → context assembly). Create `chatbot_guardrails.py` (system prompt builder: base safety + persona preset + custom rules). Wire SSE streaming for chat endpoint. All views decorated with `@check_feature("feature_maic")`. Chatbot scoping query: teacher→course→student.

### Phase 4: Chatbot Frontend
Create: `ChatbotBuilderPage.tsx`, `ChatbotListPage.tsx` (teacher), `GuardrailConfig.tsx`, `KnowledgeUploader.tsx` (components), `StudentChatbotsPage.tsx`, `StudentChatPage.tsx` (student), `ChatbotChat.tsx`, `ChatbotCard.tsx` (shared components). Create `chatbotStore.ts` (Zustand). Create `types/chatbot.ts`. Add `chatbotApi` and `chatbotStudentApi` to `openmaicService.ts`. Update sidebars with AI Chatbots nav item. Register routes in `App.tsx`.

### Phase 5: Content Type Integration
Wire AI_CLASSROOM and CHATBOT as embeddable content types in Course → Module → Content. Update `serializers.py` and `student_serializers.py` with new FK fields. Update `CourseEditorPage.tsx` content type selector (admin). Update `CourseViewPage.tsx` (teacher + student) to render AI Classroom player and chatbot inline.

### Phase 6: Study Notes Rewrite
Rewrite student `StudyNotesPage.tsx` as a filtered course content browser. Group by subject/course. Filter by content type (DOCUMENT, TEXT). No AI generation — pure content aggregation view of assigned course materials.

### Phase 7: Analytics & Polish
Teacher chatbot analytics dashboard (message count, unique students, flagged conversations, common questions). Admin reports integration. Conversation flagging review UI. Testing across all three portals. Seed data updates for chatbot demo data.

---

## 9. Dependencies

### Backend (new packages to add to requirements.txt)

```
pgvector>=0.3.0          # Django VectorField + HnswIndex + CosineDistance
tiktoken>=0.7.0          # Token counting for accurate chunk sizing
PyMuPDF>=1.24.0          # PDF text extraction (replaces PyPDF2 for better quality)
```

Note: PyPDF2 (currently in requirements.txt) can be removed after PyMuPDF is added, as PyMuPDF provides superior text extraction. Existing `python-docx` and `python-pptx` are kept for Word/PowerPoint support.

### Backend (settings.py change)

Add `'pgvector.django'` to `INSTALLED_APPS` — required for VectorField, HnswIndex, and CosineDistance to work with Django's migration framework.

### Frontend (no new packages)

All chatbot UI uses existing stack: React 18, Zustand, Tailwind, Lucide icons, fetch API for SSE.

---

## 10. Security & Multi-tenancy

| Concern | Approach |
|---------|----------|
| Tenant isolation | All chatbot models use TenantManager. Chunk table has denormalized tenant_id for filtered vector search. All API views use @tenant_required decorator |
| API key security | Tenant LLM/embedding API keys encrypted via Fernet (TenantAIConfig). Never sent to frontend |
| Chatbot access control | Students see only chatbots from teachers assigned to their courses. No direct sharing |
| Conversation privacy | Students see only their own conversations. Teachers see conversations for their chatbots only. Admins see aggregate analytics |
| Guardrail enforcement | Always-on safety layer cannot be overridden. Custom rules appended, never replace base safety |
| Knowledge isolation | Each chatbot's chunks are scoped by chatbot_id + tenant_id. No cross-tenant or cross-chatbot leakage in vector search |
| File upload limits | Max 10MB per file. PDF/TXT/DOCX/MD only. Validated server-side before ingestion |

---

## 11. Success Criteria

- [ ] Teacher can create a chatbot, upload a PDF, and have a student chat with it within 5 minutes
- [ ] Chatbot answers are grounded in uploaded knowledge (RAG retrieval, not hallucination)
- [ ] Tutor mode never gives direct answers — always asks guiding questions
- [ ] Students only see chatbots from their assigned teachers
- [ ] AI Classroom can be embedded as content in a course module
- [ ] Study Notes page shows course materials organized by subject
- [ ] All deprecated features (Scenarios, Strategy Lab, Action Plans) are cleanly removed
- [ ] No cross-tenant data leakage in chatbot conversations or vector search
- [ ] All three portals (Teacher, Student, Admin) render correctly with updated navigation
- [ ] Build passes: `npx tsc --noEmit` and `npm run build` succeed with zero errors
