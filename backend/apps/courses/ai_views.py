"""
AI Course Generation API views.

Endpoints:
    POST /api/v1/courses/ai/generate-outline/   -- Generate a course outline from a topic
    POST /api/v1/courses/ai/generate-content/    -- Generate content for a module
    POST /api/v1/courses/ai/create-from-outline/  -- Create Course/Module/Content objects from outline
    POST /api/v1/courses/ai/summarize/           -- Summarize text content
"""

import logging

from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.ai_service import AICourseGenerator
from apps.courses.models import Course, Module, Content
from apps.courses.tasks import generate_course_from_outline_async
from utils.decorators import admin_only, tenant_required
from utils.audit import log_audit

logger = logging.getLogger(__name__)

# Rate limit: 30 requests per hour per tenant for outline generation
AI_OUTLINE_RATE_LIMIT = 30
AI_OUTLINE_RATE_WINDOW = 3600  # seconds


def _check_ai_rate_limit(tenant_id: str) -> bool:
    """
    Check if the tenant has exceeded the AI outline generation rate limit.
    Returns True if the request is allowed, False if rate-limited.

    Uses cache.add + cache.incr for atomic increment without TTL reset.
    """
    cache_key = f"ai_outline_rate:{tenant_id}"
    # add() is a no-op if the key already exists, so the TTL is only set once.
    cache.add(cache_key, 0, timeout=AI_OUTLINE_RATE_WINDOW)
    current_count = cache.incr(cache_key)
    return current_count <= AI_OUTLINE_RATE_LIMIT


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def ai_generate_outline(request):
    """
    Generate a structured course outline from a topic description.

    Body:
        topic (str, required): The course topic
        description (str, required): Detailed description of the course
        target_audience (str, required): Who the course is for
        num_modules (int, optional): Number of modules (default 5, max 15)
        material_context (str, optional): Extracted text from uploaded material

    Returns:
        200: Structured course outline JSON
        400: Validation error
        429: Rate limit exceeded
    """
    tenant_id = str(request.tenant.id)

    if not _check_ai_rate_limit(tenant_id):
        return Response(
            {
                "error": "Rate limit exceeded. You can generate up to 5 outlines per hour.",
                "retry_after_seconds": AI_OUTLINE_RATE_WINDOW,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    topic = (request.data.get("topic") or "").strip()
    description = (request.data.get("description") or "").strip()
    target_audience = (request.data.get("target_audience") or "").strip()

    if not topic:
        return Response({"error": "topic is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not description:
        return Response({"error": "description is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not target_audience:
        return Response({"error": "target_audience is required"}, status=status.HTTP_400_BAD_REQUEST)

    # Cap input lengths to prevent abuse / excessive LLM token usage
    topic = topic[:500]
    description = description[:2000]
    target_audience = target_audience[:500]
    material_context = (request.data.get("material_context") or "").strip()[:8000]

    try:
        num_modules = int(request.data.get("num_modules", 5))
    except (TypeError, ValueError):
        num_modules = 5
    num_modules = max(1, min(15, num_modules))

    generator = AICourseGenerator()
    outline = generator.generate_course_outline(
        topic=topic,
        description=description,
        target_audience=target_audience,
        num_modules=num_modules,
        material_context=material_context,
    )

    if outline is None:
        return Response(
            {"error": "AI generation failed. Please try again later or check LLM configuration."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    log_audit(
        action="AI_GENERATE_OUTLINE",
        target_type="Course",
        target_id="",
        changes={"topic": topic, "num_modules": num_modules},
        request=request,
    )

    return Response({"outline": outline}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def ai_generate_content(request):
    """
    Generate detailed content for a specific module.

    Body:
        module_title (str, required): Title of the module
        module_description (str, required): Description of the module
        content_type (str, optional): VIDEO, DOCUMENT, TEXT, or LINK (default TEXT)
        material_context (str, optional): Extracted text from uploaded material

    Returns:
        200: Generated content JSON
        400: Validation error
    """
    module_title = (request.data.get("module_title") or "").strip()
    module_description = (request.data.get("module_description") or "").strip()
    content_type = (request.data.get("content_type") or "TEXT").strip().upper()

    if not module_title:
        return Response({"error": "module_title is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not module_description:
        return Response({"error": "module_description is required"}, status=status.HTTP_400_BAD_REQUEST)

    # Cap input lengths to prevent abuse / excessive LLM token usage
    module_title = module_title[:500]
    module_description = module_description[:2000]
    material_context = (request.data.get("material_context") or "").strip()[:8000]
    if content_type not in {"VIDEO", "DOCUMENT", "TEXT", "LINK"}:
        return Response(
            {"error": "content_type must be one of: VIDEO, DOCUMENT, TEXT, LINK"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    generator = AICourseGenerator()
    content = generator.generate_module_content(
        module_title=module_title,
        module_description=module_description,
        content_type=content_type,
        material_context=material_context,
    )

    if content is None:
        return Response(
            {"error": "AI generation failed. Please try again later or check LLM configuration."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"content": content}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def ai_create_from_outline(request):
    """
    Create actual Course, Module, and Content objects from an approved AI-generated outline.

    For large outlines this dispatches a Celery task and returns a task_id
    that the frontend can poll. For small outlines (<=3 modules) it creates
    objects synchronously.

    Body:
        outline (dict, required): The outline JSON as returned by generate-outline
            Must contain: title, description, modules[]

    Returns:
        201: {"course_id": "<uuid>"}                         -- synchronous creation
        202: {"task_id": "<celery-task-id>", "status": "PENDING"} -- async creation
        400: Validation error
    """
    outline = request.data.get("outline")
    if not outline or not isinstance(outline, dict):
        return Response({"error": "outline is required and must be a JSON object"}, status=status.HTTP_400_BAD_REQUEST)

    title = (outline.get("title") or "").strip()
    description = (outline.get("description") or "").strip()
    modules = outline.get("modules")

    if not title:
        return Response({"error": "outline.title is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not description:
        return Response({"error": "outline.description is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not modules or not isinstance(modules, list):
        return Response({"error": "outline.modules is required and must be a non-empty array"}, status=status.HTTP_400_BAD_REQUEST)

    # For small outlines, create synchronously
    if len(modules) <= 3:
        course_id = _create_course_from_outline(outline, request.tenant, request.user)
        log_audit(
            action="AI_CREATE_COURSE",
            target_type="Course",
            target_id=str(course_id),
            changes={"title": title, "module_count": len(modules), "method": "sync"},
            request=request,
        )
        return Response({"course_id": str(course_id)}, status=status.HTTP_201_CREATED)

    # For larger outlines, dispatch async Celery task
    task = generate_course_from_outline_async.delay(
        outline_data=outline,
        tenant_id=str(request.tenant.id),
        user_id=str(request.user.id),
    )

    log_audit(
        action="AI_CREATE_COURSE_ASYNC",
        target_type="Course",
        target_id="",
        changes={"title": title, "module_count": len(modules), "task_id": task.id},
        request=request,
    )

    return Response(
        {"task_id": task.id, "status": "PENDING"},
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def ai_summarize(request):
    """
    Summarize text content.

    Body:
        text (str, required): The text to summarize
        max_length (int, optional): Maximum summary length in characters (default 500)

    Returns:
        200: {"summary": "..."}
        400: Validation error
    """
    text = (request.data.get("text") or "").strip()
    if not text:
        return Response({"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        max_length = int(request.data.get("max_length", 500))
    except (TypeError, ValueError):
        max_length = 500
    max_length = max(50, min(2000, max_length))

    generator = AICourseGenerator()
    summary = generator.summarize_content(text=text, max_length=max_length)

    if summary is None:
        return Response(
            {"error": "AI summarization failed. Please try again later or check LLM configuration."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"summary": summary}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def ai_generate_assignment(request):
    """
    Generate an open-ended assignment prompt with a 4-level rubric.

    Body:
        topic (str, required): The assignment topic
        description (str, optional): Additional context
        material_context (str, optional): Extracted text from uploaded material
        difficulty (str, optional): easy, medium, or hard (default medium)

    Returns:
        200: { assignment: { title, instructions, rubric, success_criteria, ... } }
        400: Validation error
        503: LLM generation failed
    """
    topic = (request.data.get("topic") or "").strip()
    if not topic:
        return Response({"error": "topic is required"}, status=status.HTTP_400_BAD_REQUEST)

    topic = topic[:500]
    description = (request.data.get("description") or "").strip()[:2000]
    material_context = (request.data.get("material_context") or "").strip()[:8000]
    difficulty = (request.data.get("difficulty") or "medium").strip().lower()

    if difficulty not in ("easy", "medium", "hard"):
        return Response(
            {"error": "difficulty must be one of: easy, medium, hard"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    generator = AICourseGenerator()
    assignment = generator.generate_assignment(
        topic=topic,
        description=description,
        material_context=material_context,
        difficulty=difficulty,
    )

    if assignment is None:
        return Response(
            {"error": "AI generation failed. Please try again later or check LLM configuration."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    log_audit(
        action="AI_GENERATE_ASSIGNMENT",
        target_type="Assignment",
        target_id="",
        changes={"topic": topic, "difficulty": difficulty},
        request=request,
    )

    return Response({"assignment": assignment}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Helper: synchronous course creation from outline
# ---------------------------------------------------------------------------

def _create_course_from_outline(outline: dict, tenant, user) -> str:
    """
    Create Course, Module, and Content objects from an outline dict.
    Returns the created course ID as a string.
    """
    from django.db import transaction

    estimated_hours = outline.get("estimated_hours", 0)
    try:
        estimated_hours = float(estimated_hours)
    except (TypeError, ValueError):
        estimated_hours = 0

    with transaction.atomic():
        course = Course(
            tenant=tenant,
            title=outline["title"][:300],
            description=outline.get("description", ""),
            estimated_hours=estimated_hours,
            is_published=False,
            is_active=True,
            created_by=user,
        )
        # Let Course.save() handle slug generation
        course.save()

        for mod_data in outline.get("modules", []):
            module = Module.objects.create(
                course=course,
                title=mod_data.get("title", "Untitled Module")[:300],
                description=mod_data.get("description", ""),
                order=mod_data.get("order", 0),
                is_active=True,
            )

            for item_data in mod_data.get("content_items", []):
                content_type = str(item_data.get("content_type", "TEXT")).upper()
                if content_type not in {"VIDEO", "DOCUMENT", "TEXT", "LINK"}:
                    content_type = "TEXT"

                Content.objects.create(
                    module=module,
                    title=item_data.get("title", "Untitled Content")[:300],
                    content_type=content_type,
                    text_content=item_data.get("text_content", item_data.get("description", "")),
                    order=item_data.get("order", 0),
                    is_mandatory=True,
                    is_active=True,
                )

    return str(course.id)
