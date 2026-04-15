"""
AI Study Summary generation service.

Extracts text from course content (video transcripts, documents, text) and
calls the tenant's configured LLM to generate structured study materials:
summaries, flashcards, key terms, and quiz prep questions.

Functions:
    extract_content_text()        -> str
    generate_study_summary_sse()  -> Generator[str] (SSE events)
"""

import hashlib
import json
import logging

from apps.courses.maic_generation_service import _call_llm, _parse_json_from_llm
from apps.courses.maic_models import TenantAIConfig
from apps.courses.models import Content

logger = logging.getLogger(__name__)


# ─── Content Text Extraction ────────────────────────────────────────────────

def extract_content_text(content: Content) -> str:
    """
    Extract readable text from a Content item.

    Supported content types:
        VIDEO     — pulls full_text from the linked VideoTranscript
        DOCUMENT  — uses text_content (pre-extracted) or empty
        TEXT      — uses text_content directly
        Others    — returns empty string
    """
    if content.content_type == 'VIDEO':
        try:
            asset = content.video_asset
            if asset and hasattr(asset, 'transcript') and asset.transcript:
                return asset.transcript.full_text or ''
        except Exception:
            logger.debug("No video transcript for content %s", content.id)
        return ''

    if content.content_type in ('DOCUMENT', 'TEXT'):
        return content.text_content or ''

    return ''


def compute_text_hash(text: str) -> str:
    """Return SHA-256 hex digest of the given text."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ─── LLM System Prompt ──────────────────────────────────────────────────────

STUDY_SUMMARY_SYSTEM_PROMPT = """You are an expert educational content analyst. Given source material from a course, generate comprehensive study materials in a single JSON response.

Return ONLY a valid JSON object with this exact structure (no markdown fences, no extra text):
{
  "summary": "A structured summary of 3-5 paragraphs covering all key concepts. Use **bold** for important terms and concepts. Organize logically from foundational ideas to advanced applications.",
  "flashcards": [
    {"front": "Question or concept prompt", "back": "Clear, concise answer or explanation"}
  ],
  "key_terms": [
    {"term": "Term or concept name", "definition": "Clear definition in context of the material"}
  ],
  "quiz_prep": [
    {
      "question": "Question text",
      "answer": "Correct answer",
      "type": "mcq",
      "options": ["Option A", "Option B", "Option C", "Option D"]
    }
  ],
  "mind_map": {
    "nodes": [
      {"id": "n1", "label": "2-4 word label", "type": "core|concept|process|detail", "description": "1-2 sentence description"}
    ],
    "edges": [
      {"source": "n1", "target": "n2", "label": "1-2 word relationship"}
    ]
  }
}

Rules for each section:

SUMMARY:
- Write 3-5 paragraphs that capture the essential ideas
- Bold key terms and concepts using **term**
- Progress from foundational concepts to more nuanced points
- Include concrete examples mentioned in the source material
- Do NOT introduce information not present in the source material

FLASHCARDS (8-12 cards):
- Each card should test a distinct concept (no overlapping cards)
- Front side: a clear question, prompt, or "What is...?" query
- Back side: a concise, accurate answer grounded in the material
- Cover a range of topics from the source material
- Vary card types: definitions, cause-effect, comparisons, applications

KEY TERMS (10-15 terms):
- Extract the most important vocabulary and concepts
- Definitions should be self-contained and understandable
- Include technical terms, named concepts, and important phrases
- Order from most fundamental to most specialized

QUIZ PREP (5-8 questions):
- Mix question types:
  - "mcq" (multiple choice): exactly 4 options, one correct answer
  - "true_false": options should be ["True", "False"]
  - "fill_blank": question contains ___ blank, answer fills it
  - "short_answer": open-ended, answer is 1-2 sentences
- Test different cognitive levels: recall, understanding, application
- All questions and answers must be directly supported by the source material
- For MCQ, make distractors plausible but clearly wrong based on the material

MIND MAP (mind_map):
- Create a concept map showing relationships between key ideas
- Central "core" node for the main topic (1 node)
- Add 4-8 "concept" nodes for key ideas/theories
- Add 3-6 "process" nodes for procedures/steps/methods
- Add 3-5 "detail" nodes for supporting facts/examples
- Total: 12-20 nodes, 15-25 edges
- Each node: {"id": "n1", "label": "2-4 word label", "type": "core|concept|process|detail", "description": "1-2 sentence description"}
- Each edge: {"source": "n1", "target": "n2", "label": "1-2 word relationship"}
- Ensure every node is connected (no orphans)
- Core node should connect to all concept nodes"""


# ─── SSE Helpers ─────────────────────────────────────────────────────────────

def _sse_data(payload: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


# ─── SSE Generator ──────────────────────────────────────────────────────────

def generate_study_summary_sse(content: Content, ai_config: TenantAIConfig):
    """
    Generator that yields SSE-formatted strings for study summary generation.

    Extracts text from the content, calls the LLM, parses the structured JSON
    response, and yields each section as a separate SSE event. On completion,
    returns the parsed data dict (accessible via generator return value) so the
    caller can persist it.

    Yields:
        SSE events with types: status, summary, flashcards, key_terms, quiz_prep, done, error
    """
    # 1. Extract source text
    yield _sse_data({"type": "status", "message": "Extracting content..."})

    source_text = extract_content_text(content)

    if len(source_text.strip()) < 50:
        yield _sse_data({
            "type": "error",
            "error": "Not enough content to generate a study summary. "
                     "The source material must contain at least 50 characters of text.",
        })
        return None

    # 2. Truncate for LLM input
    truncated_text = source_text[:8000]

    yield _sse_data({"type": "status", "message": "Generating summary..."})

    # 3. Call LLM
    user_prompt = (
        f"Generate comprehensive study materials for the following course content:\n\n"
        f"Content title: {content.title}\n\n"
        f"Source material:\n{truncated_text}"
    )

    try:
        raw_response = _call_llm(
            config=ai_config,
            system_prompt=STUDY_SUMMARY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.4,
            max_tokens=6000,
        )
    except Exception as exc:
        logger.error("LLM call failed for study summary (content %s): %s", content.id, exc)
        yield _sse_data({"type": "error", "error": "Failed to generate study summary. Please try again."})
        return None

    if not raw_response:
        yield _sse_data({"type": "error", "error": "AI returned an empty response. Please try again."})
        return None

    # 4. Parse JSON
    parsed = _parse_json_from_llm(raw_response)

    if not parsed or not isinstance(parsed, dict):
        logger.warning("Failed to parse study summary JSON for content %s", content.id)
        yield _sse_data({"type": "error", "error": "Failed to parse AI response. Please try again."})
        return None

    # 5. Validate and yield each section
    summary_text = parsed.get("summary", "")
    flashcards = parsed.get("flashcards", [])
    key_terms = parsed.get("key_terms", [])
    quiz_prep = parsed.get("quiz_prep", [])

    # Yield summary
    if summary_text:
        yield _sse_data({"type": "summary", "content": summary_text})

    # Yield flashcards
    if flashcards and isinstance(flashcards, list):
        valid_cards = [
            c for c in flashcards
            if isinstance(c, dict) and c.get("front") and c.get("back")
        ]
        yield _sse_data({"type": "flashcards", "cards": valid_cards})
    else:
        yield _sse_data({"type": "flashcards", "cards": []})

    # Yield key terms
    if key_terms and isinstance(key_terms, list):
        valid_terms = [
            t for t in key_terms
            if isinstance(t, dict) and t.get("term") and t.get("definition")
        ]
        yield _sse_data({"type": "key_terms", "terms": valid_terms})
    else:
        yield _sse_data({"type": "key_terms", "terms": []})

    # Yield quiz prep
    if quiz_prep and isinstance(quiz_prep, list):
        valid_questions = [
            q for q in quiz_prep
            if isinstance(q, dict) and q.get("question") and q.get("answer")
        ]
        yield _sse_data({"type": "quiz_prep", "questions": valid_questions})
    else:
        yield _sse_data({"type": "quiz_prep", "questions": []})

    # Yield mind map
    mind_map = parsed.get("mind_map", {})
    if mind_map and isinstance(mind_map, dict):
        nodes = mind_map.get("nodes", [])
        edges = mind_map.get("edges", [])
        valid_nodes = [n for n in nodes if isinstance(n, dict) and n.get("id") and n.get("label")]
        valid_edges = [e for e in edges if isinstance(e, dict) and e.get("source") and e.get("target")]
        yield _sse_data({"type": "mind_map", "nodes": valid_nodes, "edges": valid_edges})
    else:
        yield _sse_data({"type": "mind_map", "nodes": [], "edges": []})

    yield _sse_data({"type": "done"})

    # Return the parsed data so the caller can persist it
    return {
        "summary": summary_text,
        "flashcards": flashcards if isinstance(flashcards, list) else [],
        "key_terms": key_terms if isinstance(key_terms, list) else [],
        "quiz_prep": quiz_prep if isinstance(quiz_prep, list) else [],
        "mind_map": mind_map if isinstance(mind_map, dict) else {},
    }
