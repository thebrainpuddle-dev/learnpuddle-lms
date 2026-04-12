"""
AI Course Generator service layer.

Uses the unified LLM service (OpenRouter / Ollama with automatic fallback)
to generate structured course outlines, module content, quizzes, and summaries.

Usage:
    from apps.courses.ai_service import AICourseGenerator

    generator = AICourseGenerator()
    outline = generator.generate_course_outline(
        topic="Differentiated Instruction",
        description="Strategies for meeting diverse learner needs",
        target_audience="K-12 teachers",
        num_modules=5,
    )
"""

import json
import logging
from typing import Any

from utils.llm_service import llm_generate

logger = logging.getLogger(__name__)


def _extract_raw_json_string(text: str) -> str | None:
    """Extract the raw JSON object substring from LLM response text (no parsing).

    Uses bracket-depth tracking to find the outermost ``{...}`` block.
    Returns the raw string for downstream repair, or ``None`` if no
    balanced braces are found.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_json_object(text: str) -> dict | None:
    """Extract the first JSON object from LLM response text."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _extract_json_array(text: str) -> list | None:
    """Extract the first JSON array from LLM response text.

    Uses bracket-depth tracking (mirrors ``_extract_json_object``) so that
    nested brackets inside strings or sub-arrays are handled correctly,
    rather than naively relying on ``rfind(']')``.
    """
    start = text.find("[")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


class AICourseGenerator:
    """
    Service class for AI-powered course generation.

    All methods try the configured LLM provider chain (OpenRouter -> Ollama)
    and return structured data. Returns None when all providers fail.
    """

    # ------------------------------------------------------------------
    # Course Outline Generation
    # ------------------------------------------------------------------

    def generate_course_outline(
        self,
        topic: str,
        description: str,
        target_audience: str,
        num_modules: int = 5,
        material_context: str = "",
    ) -> dict | None:
        """
        Generate a structured course outline from a topic description.

        Uses OpenMAIC-style pedagogical pipeline: each section includes
        learning objectives, key points, Bloom's taxonomy level, and
        suggested content types.

        Args:
            topic: The course topic
            description: Detailed description of the course
            target_audience: Who the course is for
            num_modules: Number of modules/sections (default 5, max 15)
            material_context: Optional extracted text from uploaded material
                (PDF, DOCX, PPTX) to ground the outline in real content.

        Returns a dict with keys:
            title, description, target_audience, estimated_hours,
            modules: [{title, description, order, learning_objectives,
                       key_points, bloom_level, suggested_types,
                       content_items: [{title, content_type, description, order}]}]

        Returns None if LLM generation fails entirely.
        """
        if num_modules < 1:
            num_modules = 1
        if num_modules > 15:
            num_modules = 15

        system_prompt = (
            "You are an expert instructional designer using evidence-based pedagogy. "
            "You create well-structured professional development courses for teachers "
            "that follow a foundational-to-applied-to-assessment progression. "
            "For each section you identify learning objectives (Bloom's taxonomy), "
            "key teaching points, and appropriate content types. "
            "Always respond with valid JSON only -- no markdown, no extra text."
        )

        material_section = ""
        if material_context:
            material_section = f"""
## Source Material (base the outline on this content)
{material_context[:8000]}
"""

        prompt = f"""You are an instructional designer creating a structured learning module.

Given the topic/material below, create a pedagogically sound outline that follows:
1. Learning Objectives (what the learner will be able to do)
2. Content Sections (logical progression from foundational to applied)
3. Assessment Points (where to check understanding)
4. Key Takeaways (summary points)

## Course Parameters
- Topic: {topic}
- Description: {description}
- Target Audience: {target_audience}
- Number of Sections: {num_modules}
{material_section}
## Requirements
- Each section should have 2-4 content items
- Content items can be of type: VIDEO, DOCUMENT, TEXT, or LINK
- Include a logical progression from foundational to applied to assessment
- For each section, identify Bloom's taxonomy level (Remember, Understand, Apply, Analyze, Evaluate, Create)
- Suggest content types per section: lesson (text content), quiz (assessment), assignment (open-ended), summary
- Estimate total course hours (realistic for teacher PD)

## JSON Schema (return ONLY this JSON object)
{{
  "title": "Course Title",
  "description": "2-3 sentence course description",
  "target_audience": "{target_audience}",
  "estimated_hours": 10.0,
  "modules": [
    {{
      "title": "Section Title",
      "description": "Section description with learning goal",
      "order": 1,
      "learning_objectives": ["Objective 1 using action verbs", "Objective 2"],
      "key_points": ["Key point 1", "Key point 2", "Key point 3"],
      "bloom_level": "Understand",
      "suggested_types": ["lesson", "quiz"],
      "content_items": [
        {{
          "title": "Content Item Title",
          "content_type": "TEXT",
          "description": "Brief description of this content piece",
          "order": 1
        }}
      ]
    }}
  ]
}}

Return exactly {num_modules} sections. Use realistic, specific titles and descriptions relevant to "{topic}" for "{target_audience}". Structure the progression: foundational sections first, then applied, then assessment/synthesis."""

        raw = llm_generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=4096,
            timeout=120,
        )

        if raw is None:
            logger.warning("generate_course_outline: all LLM providers failed for topic=%s", topic)
            return None

        outline = _extract_json_object(raw)
        if outline is None:
            logger.warning("generate_course_outline: could not parse JSON from LLM response")
            return None

        # Validate minimum structure
        if "modules" not in outline or not isinstance(outline["modules"], list):
            logger.warning("generate_course_outline: LLM response missing 'modules' array")
            return None

        # Ensure required top-level keys have defaults
        outline.setdefault("title", topic)
        outline.setdefault("description", description)
        outline.setdefault("target_audience", target_audience)
        outline.setdefault("estimated_hours", 1.0)

        # Normalize modules
        for idx, mod in enumerate(outline["modules"], start=1):
            mod.setdefault("title", f"Module {idx}")
            mod.setdefault("description", "")
            mod.setdefault("order", idx)
            mod.setdefault("learning_objectives", [])
            mod.setdefault("key_points", [])
            mod.setdefault("bloom_level", "Understand")
            mod.setdefault("suggested_types", ["lesson"])
            mod.setdefault("content_items", [])
            # Normalize bloom_level
            valid_blooms = {"Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"}
            if mod["bloom_level"] not in valid_blooms:
                mod["bloom_level"] = "Understand"
            # Normalize suggested_types
            valid_types = {"lesson", "quiz", "assignment", "summary"}
            mod["suggested_types"] = [
                t for t in mod["suggested_types"] if t in valid_types
            ] or ["lesson"]
            for cidx, item in enumerate(mod["content_items"], start=1):
                item.setdefault("title", f"Content {cidx}")
                item.setdefault("content_type", "TEXT")
                item.setdefault("description", "")
                item.setdefault("order", cidx)
                # Normalize content_type
                ct = str(item["content_type"]).upper()
                if ct not in {"VIDEO", "DOCUMENT", "TEXT", "LINK", "AI_CLASSROOM", "CHATBOT"}:
                    item["content_type"] = "TEXT"
                else:
                    item["content_type"] = ct

        logger.info(
            "generate_course_outline: generated outline with %d modules for topic=%s",
            len(outline["modules"]),
            topic,
        )
        return outline

    # ------------------------------------------------------------------
    # Module Content Generation
    # ------------------------------------------------------------------

    def generate_module_content(
        self,
        module_title: str,
        module_description: str,
        content_type: str = "TEXT",
        material_context: str = "",
    ) -> dict | None:
        """
        Generate detailed content for a specific module.

        Uses OpenMAIC-style pedagogical prompts per content type:
        - TEXT/lesson: Structured HTML with h2/h3, callout boxes, examples, analogies
        - VIDEO: Video script with sections and talking points
        - DOCUMENT: Lesson document with exercises and references
        - LINK: Curated resource descriptions

        Args:
            module_title: Title of the module
            module_description: Description of the module
            content_type: VIDEO, DOCUMENT, TEXT, or LINK (default TEXT)
            material_context: Optional extracted text from uploaded material
                to ground the generated content in real source material.

        Returns a dict with keys:
            title, content_type, text_content, key_points, estimated_duration_minutes

        Returns None if LLM generation fails.
        """
        content_type = content_type.upper()
        if content_type not in {"VIDEO", "DOCUMENT", "TEXT", "LINK"}:
            content_type = "TEXT"

        type_instructions = {
            "TEXT": (
                "Write structured lesson content as rich HTML. This will be rendered in a modern LMS.\n\n"
                "## Structure (follow this progression):\n"
                "1. **Hook** — An engaging opening scenario, question, or statistic\n"
                "2. **Learning Objectives** — 2-3 clear objectives in a styled box\n"
                "3. **Core Concepts** — 2-4 sections with explanations, examples, analogies\n"
                "4. **Practical Activity** — A concrete classroom exercise\n"
                "5. **Key Takeaways** — Bullet summary of main points\n\n"
                "## HTML Components (use these styled elements):\n"
                '- Headings: <h2 style="color:#1e40af;border-bottom:2px solid #dbeafe;padding-bottom:8px;margin-top:24px">Section Title</h2>\n'
                '- Subheadings: <h3 style="color:#374151;margin-top:16px">Subsection</h3>\n'
                '- Info box: <div style="background:#eff6ff;border-left:4px solid #3b82f6;padding:16px;border-radius:8px;margin:16px 0"><strong>💡 Key Concept:</strong> text</div>\n'
                '- Tip box: <div style="background:#f0fdf4;border-left:4px solid #22c55e;padding:16px;border-radius:8px;margin:16px 0"><strong>✅ Pro Tip:</strong> text</div>\n'
                '- Warning box: <div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:16px;border-radius:8px;margin:16px 0"><strong>⚠️ Common Mistake:</strong> text</div>\n'
                '- Example box: <div style="background:#f8fafc;border:1px solid #e2e8f0;padding:16px;border-radius:8px;margin:16px 0"><strong>📋 Example:</strong> text</div>\n'
                '- Activity box: <div style="background:#faf5ff;border-left:4px solid #a855f7;padding:16px;border-radius:8px;margin:16px 0"><strong>🎯 Try This:</strong> activity description</div>\n'
                '- Objectives box: <div style="background:#f0f9ff;border:2px solid #0ea5e9;padding:16px;border-radius:12px;margin:16px 0"><strong>🎓 Learning Objectives</strong><ul style="margin-top:8px"><li>Objective 1</li></ul></div>\n'
                '- Comparison table: <table style="width:100%;border-collapse:collapse;margin:16px 0"><thead><tr style="background:#f1f5f9"><th style="padding:12px;border:1px solid #e2e8f0;text-align:left">Header</th></tr></thead><tbody><tr><td style="padding:12px;border:1px solid #e2e8f0">Cell</td></tr></tbody></table>\n'
                "- Use <strong> for key terms, <em> for emphasis\n"
                "- Use numbered lists <ol> for sequential steps, <ul> for unordered lists\n\n"
                "## Quality Rules:\n"
                "- NOT a wall of text. Every section must be scannable.\n"
                "- Include at least one styled box per core concept.\n"
                "- Include at least one practical example or analogy.\n"
                "- Content should be 800-1500 words.\n"
                "- Write for professional educators, not students."
            ),
            "VIDEO": (
                "Write a detailed video script with sections, talking points, "
                "and on-screen text suggestions. Format as HTML."
            ),
            "DOCUMENT": (
                "Write a detailed lesson document with sections, key concepts, "
                "exercises, and references. Format as HTML."
            ),
            "LINK": (
                "Provide a curated description of what external resources to find, "
                "with suggested search terms and evaluation criteria. Format as HTML."
            ),
        }

        system_prompt = (
            "You are LearnPuddle's senior content creator for teacher professional development. "
            "Create high-quality, pedagogically structured educational content. "
            "Your content should be scannable, visually organized with proper HTML hierarchy, "
            "and include real-world examples and practical applications. "
            "Always respond with valid JSON only -- no markdown fences, no extra text."
        )

        material_section = ""
        if material_context:
            material_section = f"""
## Source Material (base the content on this material)
{material_context[:6000]}
"""

        prompt = f"""Generate detailed {content_type} content for the following module.

## Module
- Title: {module_title}
- Description: {module_description}
- Content Type: {content_type}
{material_section}
## Content Instructions
{type_instructions.get(content_type, type_instructions["TEXT"])}

## JSON Schema (return ONLY this JSON object)
{{
  "title": "{module_title}",
  "content_type": "{content_type}",
  "text_content": "<h2>...</h2><p>...</p>",
  "key_points": ["Key point 1", "Key point 2", "Key point 3"],
  "estimated_duration_minutes": 15
}}

Create thorough, professional content suitable for teacher professional development. Ensure the HTML is well-structured with visual hierarchy."""

        raw = llm_generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=4096,
            timeout=120,
        )

        if raw is None:
            logger.warning("generate_module_content: all LLM providers failed for module=%s", module_title)
            return None

        content = _extract_json_object(raw)
        if content is None:
            logger.warning("generate_module_content: could not parse JSON from LLM response")
            return None

        content.setdefault("title", module_title)
        content.setdefault("content_type", content_type)
        content.setdefault("text_content", "")
        content.setdefault("key_points", [])
        content.setdefault("estimated_duration_minutes", 15)

        logger.info("generate_module_content: generated content for module=%s", module_title)
        return content

    # ------------------------------------------------------------------
    # Quiz Generation (reusable wrapper around existing infrastructure)
    # ------------------------------------------------------------------

    def generate_quiz_from_content(
        self,
        content_text: str,
        num_questions: int = 5,
        material_context: str = "",
        difficulty: str = "medium",
    ) -> list[dict[str, Any]] | None:
        """
        Generate Bloom's-aligned quiz questions from content text using the LLM.

        Questions include plausible distractors, answer explanations, and
        difficulty tags. Aligned to appropriate Bloom's taxonomy levels.

        Args:
            content_text: The source material to generate questions from
            num_questions: Number of questions to generate (1-20)
            material_context: Optional additional context from uploaded material
            difficulty: Target difficulty level (easy, medium, hard)

        Returns a list of question dicts, or None if generation fails.
        Each question has: question_type, prompt, options, correct_answer,
        explanation, points, selection_mode, difficulty.
        """
        if num_questions < 1:
            num_questions = 1
        if num_questions > 20:
            num_questions = 20

        difficulty = difficulty.lower()
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"

        mcq_count = max(2, int(num_questions * 0.6))
        tf_count = 1 if num_questions >= 4 else 0
        sa_count = max(1, num_questions - mcq_count - tf_count)

        bloom_guidance = {
            "easy": "Focus on Remember and Understand levels: recall facts, define terms, explain concepts.",
            "medium": "Focus on Apply and Analyze levels: apply concepts to scenarios, compare approaches, identify patterns.",
            "hard": "Focus on Evaluate and Create levels: critique approaches, justify decisions, design solutions.",
        }

        # Combine source text with material context if provided
        combined_source = content_text[:6000]
        if material_context:
            combined_source = f"{content_text[:4000]}\n\n## Additional Material\n{material_context[:2000]}"

        system_prompt = (
            "You are LearnPuddle's senior assessment architect specializing in "
            "Bloom's taxonomy-aligned assessments. "
            "Create rigorous quiz questions grounded ONLY in the provided source material. "
            "Each question should target a specific Bloom's level and include plausible "
            "distractors (for MCQ) that reflect common misconceptions. "
            "Always respond with a valid JSON array only -- no markdown, no extra text."
        )

        prompt = f"""Create exactly {num_questions} Bloom's-aligned quiz questions from the source material below.

## Source Grounding Rules
1) Use only facts present in the source text.
2) Do not invent policies, steps, or numbers.
3) Each explanation must reference the source and explain why each answer is correct/incorrect.

## Difficulty & Bloom's Alignment
- Difficulty: {difficulty}
- {bloom_guidance[difficulty]}

## Required Mix
- MCQ: {mcq_count}
- TRUE_FALSE: {tf_count}
- SHORT_ANSWER: {sa_count}

## Quality Rules
- Use realistic classroom scenarios where appropriate.
- No trick phrasing.
- No "all of the above" or "none of the above".
- MCQ must have exactly 4 options with plausible distractors.
- Distractors should reflect common misconceptions, not obviously wrong answers.
- Explanations must clarify why the correct answer is right AND why distractors are wrong.
- Each question should include a difficulty tag.

## JSON Schema (return ONLY a JSON array)
For MCQ:
{{
  "question_type": "MCQ",
  "selection_mode": "SINGLE",
  "prompt": "...",
  "options": ["A", "B", "C", "D"],
  "correct_answer": {{"option_index": 0}},
  "explanation": "Correct because... Option B is wrong because...",
  "points": 1,
  "difficulty": "{difficulty}"
}}

For TRUE_FALSE:
{{
  "question_type": "TRUE_FALSE",
  "prompt": "...",
  "correct_answer": {{"value": true}},
  "explanation": "...",
  "points": 1,
  "difficulty": "{difficulty}"
}}

For SHORT_ANSWER:
{{
  "question_type": "SHORT_ANSWER",
  "prompt": "...",
  "correct_answer": {{}},
  "explanation": "Expected response should include...",
  "points": 2,
  "difficulty": "{difficulty}"
}}

## Source Material
{combined_source}

Return exactly {num_questions} items."""

        raw = llm_generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.35,
            max_tokens=4096,
            timeout=180,
        )

        if raw is None:
            logger.warning("generate_quiz_from_content: all LLM providers failed")
            return None

        questions = _extract_json_array(raw)
        if questions is None:
            logger.warning("generate_quiz_from_content: could not parse JSON array from LLM response")
            return None

        # Validate and normalize
        valid: list[dict[str, Any]] = []
        for q in questions:
            if not isinstance(q, dict) or "question_type" not in q or "prompt" not in q:
                continue
            q.setdefault("options", [])
            q.setdefault("correct_answer", {})
            q.setdefault("explanation", "")
            q.setdefault("selection_mode", "SINGLE")
            q.setdefault("points", 2 if q["question_type"] == "SHORT_ANSWER" else 1)
            valid.append(q)

        if len(valid) < 1:
            logger.warning("generate_quiz_from_content: no valid questions parsed from LLM response")
            return None

        logger.info("generate_quiz_from_content: generated %d questions", len(valid))
        return valid[:num_questions]

    # ------------------------------------------------------------------
    # Assignment Generation (OpenMAIC-style with rubric)
    # ------------------------------------------------------------------

    def generate_assignment(
        self,
        topic: str,
        description: str = "",
        material_context: str = "",
        difficulty: str = "medium",
    ) -> dict | None:
        """
        Generate an open-ended assignment prompt with a 4-level rubric,
        success criteria, and example submission guidance.

        Args:
            topic: The assignment topic
            description: Additional context or description
            material_context: Optional extracted text from uploaded material
            difficulty: Target difficulty (easy, medium, hard)

        Returns a dict with keys:
            title, instructions, rubric (list of dicts), success_criteria (list),
            example_guidance, difficulty, estimated_minutes

        Returns None if LLM generation fails.
        """
        difficulty = difficulty.lower()
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"

        difficulty_guidance = {
            "easy": "Create a straightforward assignment focusing on recall and basic application.",
            "medium": "Create an assignment requiring analysis and application of concepts.",
            "hard": "Create a complex assignment requiring evaluation, synthesis, and creative application.",
        }

        material_section = ""
        if material_context:
            material_section = f"""
## Source Material (base the assignment on this content)
{material_context[:6000]}
"""

        description_section = ""
        if description:
            description_section = f"\n- Description: {description}"

        system_prompt = (
            "You are LearnPuddle's senior instructional designer specializing in "
            "performance-based assessments for teacher professional development. "
            "You create open-ended assignments with clear rubrics that measure "
            "authentic understanding and practical application. "
            "Always respond with valid JSON only -- no markdown, no extra text."
        )

        prompt = f"""Create an open-ended assignment with a rubric for the following topic.

## Assignment Parameters
- Topic: {topic}{description_section}
- Difficulty: {difficulty}
- Guidance: {difficulty_guidance[difficulty]}
{material_section}
## Requirements
- Write clear, actionable instructions (2-3 paragraphs)
- Create a 4-level rubric (Exemplary, Proficient, Developing, Beginning)
- Each rubric level should have specific, observable criteria
- Include 3-5 success criteria as a checklist
- Provide brief guidance on what a good submission looks like
- Make the assignment relevant to teaching practice

## JSON Schema (return ONLY this JSON object)
{{
  "title": "Assignment Title",
  "instructions": "Detailed assignment instructions in HTML format...",
  "rubric": [
    {{
      "level": "Exemplary",
      "score": 4,
      "description": "Specific criteria for exemplary performance..."
    }},
    {{
      "level": "Proficient",
      "score": 3,
      "description": "Specific criteria for proficient performance..."
    }},
    {{
      "level": "Developing",
      "score": 2,
      "description": "Specific criteria for developing performance..."
    }},
    {{
      "level": "Beginning",
      "score": 1,
      "description": "Specific criteria for beginning performance..."
    }}
  ],
  "success_criteria": [
    "Criterion 1",
    "Criterion 2",
    "Criterion 3"
  ],
  "example_guidance": "A strong submission would include...",
  "difficulty": "{difficulty}",
  "estimated_minutes": 45
}}

Create a meaningful assignment about "{topic}" suitable for teacher professional development."""

        raw = llm_generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=4096,
            timeout=120,
        )

        if raw is None:
            logger.warning("generate_assignment: all LLM providers failed for topic=%s", topic)
            return None

        result = _extract_json_object(raw)
        if result is None:
            logger.warning("generate_assignment: could not parse JSON from LLM response")
            return None

        # Validate and normalize
        result.setdefault("title", f"Assignment: {topic}")
        result.setdefault("instructions", "")
        result.setdefault("rubric", [])
        result.setdefault("success_criteria", [])
        result.setdefault("example_guidance", "")
        result.setdefault("difficulty", difficulty)
        result.setdefault("estimated_minutes", 45)

        # Ensure rubric has valid structure
        valid_rubric: list[dict[str, Any]] = []
        for item in result.get("rubric", []):
            if isinstance(item, dict) and "level" in item:
                item.setdefault("score", 0)
                item.setdefault("description", "")
                valid_rubric.append(item)
        result["rubric"] = valid_rubric

        logger.info("generate_assignment: generated assignment for topic=%s", topic)
        return result
