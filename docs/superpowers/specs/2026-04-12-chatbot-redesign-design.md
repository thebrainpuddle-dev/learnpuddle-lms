# AI Chatbot Redesign — Section-Scoped, NotebookLM-style Builder

## Problem

Current chatbot flow lacks section scoping (teachers can't target specific classes) and the builder UX is a generic form. Students see all chatbots regardless of class assignment.

## Design Decisions

### Section Scoping
- AIChatbot gains a `sections` ManyToManyField → `academics.Section`
- Teachers pick sections from their TeachingAssignments when creating/editing
- Students only see chatbots linked to their enrolled sections
- Teachers see flat grid with section badge tags and optional section filter

### Persona Templates (6 education-specific)
Replace generic `tutor/reference/open` with:

| Key | Name | Behavior |
|-----|------|----------|
| `study_buddy` | Study Buddy | Friendly peer, breaks concepts down, encourages |
| `quiz_master` | Quiz Master | Generates practice questions, gives feedback |
| `concept_explainer` | Concept Explainer | Deep explanations with analogies, visual language |
| `homework_helper` | Homework Helper | Guides through problems step-by-step, never gives direct answers |
| `revision_coach` | Revision Coach | Summarizes topics, creates flashcard-style Q&A |
| `custom` | Custom | Teacher writes full persona description |

### NotebookLM-style Builder (Single Page)
1. **Top**: Name + section multi-select
2. **Left column**: Knowledge sources (drag-drop files, URL input, paste text) — always visible
3. **Right column**: Persona card grid (6 visual cards) + optional custom rules
4. **Bottom**: Welcome message + save/publish

### Student Flow
- Flat list of chatbots from enrolled sections
- Click → direct chat (sessionStorage messages, SSE streaming)
- No conversation sidebar, no history persistence

### Clone Support
- Teacher endpoint to clone a chatbot (copies config + sections, not knowledge)

## Backend Changes

| File | Change |
|------|--------|
| `chatbot_models.py` | Add `sections` M2M, expand `PERSONA_CHOICES` to 6 |
| `chatbot_guardrails.py` | 6 detailed persona templates with education-specific system prompts |
| `chatbot_serializers.py` | Add `sections` field, section detail in list serializer |
| `chatbot_views.py` | Section-based student filtering, clone endpoint, section picker data |
| `chatbot_urls.py` | Add clone URL |
| Migration | Add M2M table + update persona choices |

## Frontend Changes

| File | Change |
|------|--------|
| `types/chatbot.ts` | 6 persona types, section fields |
| `ChatbotBuilderPage.tsx` | Single-page NotebookLM layout with section picker |
| `GuardrailConfig.tsx` | 6 visual persona cards instead of radio buttons |
| `ChatbotListPage.tsx` | Section badge tags, section filter dropdown |
| `StudentChatbotsPage.tsx` | Section-filtered flat list |
| `ChatbotCard.tsx` | Section badges |
| `openmaicService.ts` | Clone API, sections in payloads |
