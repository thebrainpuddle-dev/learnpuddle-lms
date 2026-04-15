# apps/courses/chatbot_views.py
"""
Teacher chatbot CRUD + student chatbot chat endpoints.
All endpoints gated by @check_feature("feature_maic").
"""
import hashlib
import json
import logging
import os

from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Count, Q, Sum
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes, throttle_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.courses.chatbot_models import (
    AIChatbot, AIChatbotKnowledge, AIChatbotConversation,
)
from apps.courses.chatbot_serializers import (
    AIChatbotSerializer, AIChatbotStudentSerializer,
    AIChatbotCreateSerializer,
    AIChatbotKnowledgeSerializer,
    AIChatbotConversationListSerializer,
    AIChatbotConversationDetailSerializer,
)
from apps.courses.chatbot_tasks import ingest_chatbot_knowledge
from apps.courses.chatbot_rag_service import stream_chat_response
from apps.courses.maic_models import TenantAIConfig
from utils.decorators import (
    teacher_or_admin, student_or_admin, tenant_required, check_feature,
)
from utils.audit import log_audit

logger = logging.getLogger(__name__)


class ChatbotChatThrottle(UserRateThrottle):
    rate = '30/minute'


MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.md', '.docx'}
MAX_MESSAGES_PER_CONVERSATION = 200
MAX_HISTORY_FROM_CLIENT = 40  # hard cap on history messages from client


def _sanitize_history(history) -> list[dict]:
    """Validate, sanitize, and cap history length from client."""
    if not isinstance(history, list):
        return []
    sanitized = []
    for msg in history[-MAX_HISTORY_FROM_CLIENT:]:
        if (isinstance(msg, dict)
                and msg.get("role") in ("user", "assistant")
                and isinstance(msg.get("content"), str)
                and msg["content"].strip()):
            sanitized.append({
                "role": msg["role"],
                "content": msg["content"][:8000],  # cap individual message length
            })
    return sanitized


def _build_sse_response(chatbot, message, history, ai_config, log_prefix="Chat"):
    """Build a StreamingHttpResponse for SSE chat. Shared by teacher preview and student chat."""
    def sse_stream():
        try:
            gen = stream_chat_response(
                chatbot=chatbot,
                conversation_messages=history,
                user_message=message,
                ai_config=ai_config,
            )
            for chunk in gen:
                yield chunk
        except GeneratorExit:
            pass
        except Exception:
            logger.exception(f"{log_prefix} stream error")
            yield f"data: {json.dumps({'type': 'error', 'error': 'An error occurred while generating the response.'})}\n\n"

    response = StreamingHttpResponse(
        sse_stream(),
        content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# ─── Teacher: Chatbot CRUD ────────────────────────────────────────────

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_chatbot_list_create(request):
    """GET: list teacher's chatbots. POST: create new chatbot."""
    if request.method == "GET":
        chatbots = AIChatbot.objects.filter(creator=request.user).annotate(
            _knowledge_count=Count('knowledge_sources', distinct=True),
            _conversation_count=Count('conversations', distinct=True),
        ).prefetch_related('sections__grade')
        serializer = AIChatbotSerializer(chatbots, many=True)
        return Response(serializer.data)

    # POST
    serializer = AIChatbotCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    # Check tenant limit
    try:
        ai_config = TenantAIConfig.objects.get(tenant=request.tenant)
        limit = ai_config.max_chatbots_per_teacher
    except TenantAIConfig.DoesNotExist:
        limit = 10

    current_count = AIChatbot.objects.filter(creator=request.user).count()
    if current_count >= limit:
        return Response(
            {"error": f"You can create up to {limit} chatbots."},
            status=status.HTTP_403_FORBIDDEN,
        )

    section_ids = serializer.validated_data.pop('section_ids', [])

    # Default persona_preset to 'study_buddy' if not provided
    if 'persona_preset' not in serializer.validated_data or not serializer.validated_data.get('persona_preset'):
        serializer.validated_data['persona_preset'] = 'study_buddy'

    chatbot = serializer.save(
        tenant=request.tenant,
        creator=request.user,
    )

    # Set sections (validate they belong to teacher's assignments)
    if section_ids:
        _set_chatbot_sections(chatbot, section_ids, request.user, request.tenant)
        # Trigger auto-ingestion of course content for assigned sections
        from apps.courses.chatbot_auto_ingest import auto_ingest_course_content
        auto_ingest_course_content.delay(str(chatbot.pk))

    chatbot = AIChatbot.objects.filter(pk=chatbot.pk).annotate(
        _knowledge_count=Count('knowledge_sources', distinct=True),
        _conversation_count=Count('conversations', distinct=True),
    ).prefetch_related('sections__grade').first()

    return Response(
        AIChatbotSerializer(chatbot).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_chatbot_detail(request, chatbot_id):
    """GET/PATCH/DELETE a specific chatbot."""
    try:
        chatbot = AIChatbot.objects.prefetch_related('sections__grade').get(
            pk=chatbot_id, creator=request.user,
        )
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(AIChatbotSerializer(chatbot).data)

    if request.method == "PATCH":
        serializer = AIChatbotCreateSerializer(chatbot, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        section_ids = serializer.validated_data.pop('section_ids', None)
        serializer.save()

        # Update sections if provided
        if section_ids is not None:
            _set_chatbot_sections(chatbot, section_ids, request.user, request.tenant)
            from apps.courses.chatbot_auto_ingest import auto_ingest_course_content
            auto_ingest_course_content.delay(str(chatbot.pk))

        chatbot.refresh_from_db()
        chatbot = AIChatbot.objects.filter(pk=chatbot.pk).prefetch_related(
            'sections__grade',
        ).first()
        return Response(AIChatbotSerializer(chatbot).data)

    # DELETE — soft deactivate
    chatbot.is_active = False
    chatbot.save(update_fields=['is_active', 'updated_at'])
    return Response(status=status.HTTP_204_NO_CONTENT)


def _set_chatbot_sections(chatbot, section_ids, teacher, tenant):
    """Validate and set sections for a chatbot based on teacher's assignments."""
    from apps.academics.models import Section, TeachingAssignment

    # Get sections the teacher is assigned to
    teacher_section_ids = set(
        TeachingAssignment.objects.filter(
            tenant=tenant,
            teacher=teacher,
        ).values_list('sections__id', flat=True)
    )

    # Filter to only sections the teacher has access to
    valid_ids = [sid for sid in section_ids if sid in teacher_section_ids]

    # Also verify sections belong to this tenant
    valid_sections = Section.objects.filter(
        pk__in=valid_ids,
        tenant=tenant,
    )
    chatbot.sections.set(valid_sections)


# ─── Teacher: Clone Chatbot ──────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_chatbot_clone(request, chatbot_id):
    """Clone a chatbot (copies config + sections, not knowledge)."""
    try:
        original = AIChatbot.objects.prefetch_related('sections').get(
            pk=chatbot_id, creator=request.user,
        )
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check limit
    try:
        ai_config = TenantAIConfig.objects.get(tenant=request.tenant)
        limit = ai_config.max_chatbots_per_teacher
    except TenantAIConfig.DoesNotExist:
        limit = 10

    current_count = AIChatbot.objects.filter(creator=request.user).count()
    if current_count >= limit:
        return Response(
            {"error": f"You can create up to {limit} chatbots."},
            status=status.HTTP_403_FORBIDDEN,
        )

    clone = AIChatbot.objects.create(
        tenant=request.tenant,
        creator=request.user,
        name=f"{original.name} (Copy)",
        avatar_url=original.avatar_url,
        persona_preset=original.persona_preset,
        persona_description=original.persona_description,
        custom_rules=original.custom_rules,
        block_off_topic=original.block_off_topic,
        welcome_message=original.welcome_message,
    )
    clone.sections.set(original.sections.all())

    clone = AIChatbot.objects.filter(pk=clone.pk).annotate(
        _knowledge_count=Count('knowledge_sources', distinct=True),
        _conversation_count=Count('conversations', distinct=True),
    ).prefetch_related('sections__grade').first()

    return Response(AIChatbotSerializer(clone).data, status=status.HTTP_201_CREATED)


# ─── Teacher: Sections for picker ─────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_my_sections(request):
    """Return sections this teacher is assigned to (for the chatbot section picker)."""
    from apps.academics.models import TeachingAssignment

    section_ids = TeachingAssignment.objects.filter(
        tenant=request.tenant,
        teacher=request.user,
    ).values_list('sections__id', flat=True).distinct()

    from apps.academics.models import Section
    sections = Section.objects.filter(
        pk__in=section_ids,
        tenant=request.tenant,
    ).select_related('grade').order_by('grade__order', 'name')

    data = [
        {
            'id': str(s.pk),
            'name': s.name,
            'grade_name': s.grade.name,
            'grade_short_code': s.grade.short_code,
            'academic_year': s.academic_year,
        }
        for s in sections
    ]
    return Response(data)


# ─── Teacher: Knowledge CRUD ──────────────────────────────────────────

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
@parser_classes([MultiPartParser, FormParser])
def teacher_knowledge_list_create(request, chatbot_id):
    """GET: list knowledge sources. POST: upload new knowledge."""
    try:
        chatbot = AIChatbot.objects.get(pk=chatbot_id, creator=request.user)
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        sources = AIChatbotKnowledge.all_objects.filter(chatbot=chatbot).order_by('-is_auto', '-created_at')
        serializer = AIChatbotKnowledgeSerializer(sources, many=True)
        return Response(serializer.data)

    # POST — file upload or raw text
    source_type = request.data.get('source_type', 'pdf')
    title = request.data.get('title', '')

    if source_type == 'text':
        raw_text = request.data.get('raw_text', '')
        if not raw_text:
            return Response(
                {"error": "raw_text is required for text source type"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content_hash = hashlib.sha256(raw_text.encode()).hexdigest()

        knowledge = AIChatbotKnowledge.all_objects.create(
            tenant=request.tenant,
            chatbot=chatbot,
            source_type='text',
            title=title or 'Text Input',
            raw_text=raw_text,
            content_hash=content_hash,
        )
    elif source_type == 'url':
        url = request.data.get('url', '').strip()
        if not url:
            return Response(
                {"error": "url is required for url source type"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not url.startswith('http://') and not url.startswith('https://'):
            return Response(
                {"error": "URL must start with http:// or https://"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content_hash = hashlib.sha256(url.encode()).hexdigest()

        knowledge = AIChatbotKnowledge.all_objects.create(
            tenant=request.tenant,
            chatbot=chatbot,
            source_type='url',
            title=title or url,
            file_url=url,
            content_hash=content_hash,
        )
    else:
        # File upload
        file = request.FILES.get('file')
        if not file:
            return Response(
                {"error": "file is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file.size > MAX_UPLOAD_SIZE:
            return Response(
                {"error": f"File size exceeds {MAX_UPLOAD_SIZE // (1024*1024)}MB limit"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ext = '.' + file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
        if ext not in ALLOWED_EXTENSIONS:
            return Response(
                {"error": f"File type not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save file (sanitize filename to prevent path traversal)
        sanitized_name = os.path.basename(file.name).replace('..', '')
        path = f"tenant/{request.tenant.id}/chatbot/{chatbot_id}/{sanitized_name}"
        saved_path = default_storage.save(path, file)

        # Compute hash
        file.seek(0)
        content_hash = hashlib.sha256(file.read()).hexdigest()

        knowledge = AIChatbotKnowledge.all_objects.create(
            tenant=request.tenant,
            chatbot=chatbot,
            source_type='pdf' if ext == '.pdf' else 'document',
            title=title or file.name,
            filename=file.name,
            file_url=saved_path,
            content_hash=content_hash,
        )

    # Trigger async ingestion
    ingest_chatbot_knowledge.delay(str(knowledge.id))

    return Response(
        AIChatbotKnowledgeSerializer(knowledge).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_knowledge_delete(request, chatbot_id, knowledge_id):
    """Delete a knowledge source and its chunks."""
    try:
        chatbot = AIChatbot.objects.get(pk=chatbot_id, creator=request.user)
        knowledge = AIChatbotKnowledge.all_objects.get(pk=knowledge_id, chatbot=chatbot)
    except (AIChatbot.DoesNotExist, AIChatbotKnowledge.DoesNotExist):
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    if knowledge.is_auto:
        return Response(
            {"error": "Auto-ingested sources cannot be deleted. They come from your course content."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Delete file from storage
    if knowledge.file_url:
        try:
            default_storage.delete(knowledge.file_url)
        except Exception:
            pass

    knowledge.delete()  # CASCADE deletes chunks
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_chatbot_refresh_sources(request, chatbot_id):
    """Re-sync auto-ingested sources from course content."""
    try:
        chatbot = AIChatbot.objects.get(pk=chatbot_id, creator=request.user)
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    from apps.courses.chatbot_auto_ingest import auto_ingest_course_content
    auto_ingest_course_content.delay(str(chatbot.pk))
    return Response({"status": "Refresh started. New sources will appear shortly."})


# ─── Teacher: Conversations (read-only) ───────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_conversation_list(request, chatbot_id):
    """List student conversations for a chatbot (paginated, 50 per page)."""
    try:
        chatbot = AIChatbot.objects.get(pk=chatbot_id, creator=request.user)
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    conversations = AIChatbotConversation.objects.filter(
        chatbot=chatbot,
    ).select_related('student').order_by('-last_message_at')

    # Simple cursor pagination using page param
    page = int(request.query_params.get('page', 1))
    page_size = 50
    start = (page - 1) * page_size
    total = conversations.count()
    page_qs = conversations[start:start + page_size]

    serializer = AIChatbotConversationListSerializer(page_qs, many=True)
    return Response({
        "results": serializer.data,
        "count": total,
        "page": page,
        "page_size": page_size,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_conversation_detail(request, chatbot_id, conversation_id):
    """Get full conversation with messages."""
    try:
        chatbot = AIChatbot.objects.get(pk=chatbot_id, creator=request.user)
        conversation = AIChatbotConversation.objects.get(
            pk=conversation_id, chatbot=chatbot,
        )
    except (AIChatbot.DoesNotExist, AIChatbotConversation.DoesNotExist):
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = AIChatbotConversationDetailSerializer(conversation)
    return Response(serializer.data)


# ─── Teacher: Analytics ────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_chatbot_analytics(request, chatbot_id):
    """Usage stats for a chatbot."""
    try:
        chatbot = AIChatbot.objects.get(pk=chatbot_id, creator=request.user)
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    conversations = AIChatbotConversation.objects.filter(chatbot=chatbot)

    return Response({
        "total_conversations": conversations.count(),
        "total_messages": conversations.aggregate(total=Sum('message_count'))['total'] or 0,
        "unique_students": conversations.values('student').distinct().count(),
        "flagged_count": conversations.filter(is_flagged=True).count(),
    })


# ─── Teacher: Chat Preview ────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([ChatbotChatThrottle])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_chat_preview(request, chatbot_id):
    """
    Teacher chat preview — lets the creator test their own chatbot.
    Uses the same SSE streaming logic as the student chat endpoint,
    but verifies ownership (creator) instead of section enrollment.
    No conversation persistence — messages are temporary.
    """
    try:
        chatbot = AIChatbot.objects.get(pk=chatbot_id, creator=request.user)
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    message = request.data.get("message", "").strip()
    if not message:
        return Response({"error": "message is required"}, status=status.HTTP_400_BAD_REQUEST)
    if len(message) > 4000:
        return Response({"error": "Message too long (max 4000 characters)"}, status=status.HTTP_400_BAD_REQUEST)

    sanitized_history = _sanitize_history(request.data.get("history", []))

    try:
        ai_config = TenantAIConfig.objects.get(tenant=request.tenant)
    except TenantAIConfig.DoesNotExist:
        return Response({"error": "AI provider not configured"}, status=status.HTTP_403_FORBIDDEN)

    return _build_sse_response(chatbot, message, sanitized_history, ai_config, "Teacher preview")


# ─── Student: Chatbot Access ──────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_chatbot_list(request):
    """List chatbots available to this student (via section enrollment)."""
    # Get student's section
    student_section_id = getattr(request.user, 'section_fk_id', None)

    if not student_section_id:
        return Response([])

    # Get active chatbots linked to the student's section
    chatbots = AIChatbot.objects.filter(
        sections__id=student_section_id,
        is_active=True,
    ).annotate(
        _knowledge_count=Count('knowledge_sources', distinct=True),
    ).prefetch_related('sections__grade').distinct()

    serializer = AIChatbotStudentSerializer(chatbots, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_chatbot_detail(request, chatbot_id):
    """Get a single chatbot's details (if the student has access via section enrollment)."""
    chatbot = _verify_student_chatbot_access(request, chatbot_id)
    if isinstance(chatbot, Response):
        return chatbot

    serializer = AIChatbotStudentSerializer(chatbot)
    return Response(serializer.data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_conversation_list_create(request, chatbot_id):
    """GET: list student's conversations. POST: start new conversation."""
    # Verify student has access to this chatbot
    chatbot = _verify_student_chatbot_access(request, chatbot_id)
    if isinstance(chatbot, Response):
        return chatbot

    if request.method == "GET":
        conversations = AIChatbotConversation.objects.filter(
            chatbot=chatbot, student=request.user,
        ).order_by('-last_message_at')[:20]
        serializer = AIChatbotConversationListSerializer(conversations, many=True)
        return Response(serializer.data)

    # POST — create new conversation
    conversation = AIChatbotConversation.objects.create(
        tenant=request.tenant,
        chatbot=chatbot,
        student=request.user,
        title='',
    )
    # Return metadata only (messages stored in client sessionStorage, not DB)
    return Response(
        AIChatbotConversationListSerializer(conversation).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_conversation_detail(request, chatbot_id, conversation_id):
    """Get conversation metadata (messages stored in client sessionStorage)."""
    chatbot = _verify_student_chatbot_access(request, chatbot_id)
    if isinstance(chatbot, Response):
        return chatbot

    try:
        conversation = AIChatbotConversation.objects.get(
            pk=conversation_id, chatbot=chatbot, student=request.user,
        )
    except AIChatbotConversation.DoesNotExist:
        return Response({"error": "Conversation not found"}, status=status.HTTP_404_NOT_FOUND)

    # Return metadata only — messages live in client sessionStorage
    return Response(AIChatbotConversationListSerializer(conversation).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([ChatbotChatThrottle])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_chat(request, chatbot_id):
    """Send message to chatbot — returns SSE stream."""
    chatbot = _verify_student_chatbot_access(request, chatbot_id)
    if isinstance(chatbot, Response):
        return chatbot

    message = request.data.get("message", "").strip()
    conversation_id = request.data.get("conversation_id")

    if not message:
        return Response({"error": "message is required"}, status=status.HTTP_400_BAD_REQUEST)
    if len(message) > 4000:
        return Response({"error": "Message too long (max 4000 characters)"}, status=status.HTTP_400_BAD_REQUEST)

    # ── Content guardrail check ──
    from apps.courses.content_guardrails import validate_chat_message as _validate_chat
    try:
        _ai_cfg = TenantAIConfig.objects.get(tenant=request.tenant)
        guardrail = _validate_chat(message, _ai_cfg)
        if not guardrail.allowed:
            log_audit(
                "GUARDRAIL_BLOCK", "AIChatbot",
                target_id=str(chatbot_id),
                target_repr=f"chat_msg:{message[:80]}",
                changes={"reason": guardrail.reason or "blocked"},
                request=request,
            )
            return Response({
                "error": guardrail.reason or "This message was flagged by content safety. Please rephrase.",
            }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except TenantAIConfig.DoesNotExist:
        pass  # Will be caught below when ai_config is loaded

    sanitized_history = _sanitize_history(request.data.get("history", []))

    # Get or create conversation (metadata only, no messages stored server-side)
    if conversation_id:
        try:
            conversation = AIChatbotConversation.objects.get(
                pk=conversation_id, chatbot=chatbot, student=request.user,
            )
        except AIChatbotConversation.DoesNotExist:
            return Response({"error": "Conversation not found"}, status=status.HTTP_404_NOT_FOUND)
    else:
        conversation = AIChatbotConversation.objects.create(
            tenant=request.tenant,
            chatbot=chatbot,
            student=request.user,
            title=message[:100],
        )

    if conversation.message_count >= MAX_MESSAGES_PER_CONVERSATION:
        return Response(
            {"error": "This conversation has reached its message limit. Please start a new one."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Increment for user message
    conversation.message_count += 1
    if not conversation.title:
        conversation.title = message[:100]
    conversation.save(update_fields=['message_count', 'last_message_at', 'title'])

    try:
        ai_config = TenantAIConfig.objects.get(tenant=request.tenant)
    except TenantAIConfig.DoesNotExist:
        return Response({"error": "AI provider not configured"}, status=status.HTTP_403_FORBIDDEN)

    conv_pk = str(conversation.pk)

    def sse_stream():
        try:
            gen = stream_chat_response(
                chatbot=chatbot,
                conversation_messages=sanitized_history,
                user_message=message,
                ai_config=ai_config,
            )
            for chunk in gen:
                # Intercept done event to inject conversation_id
                if chunk.startswith("data: "):
                    try:
                        data = json.loads(chunk[6:].strip())
                        if data.get("type") == "done":
                            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_pk})}\n\n"
                            continue
                    except (ValueError, KeyError):
                        pass
                yield chunk
        except GeneratorExit:
            pass
        except Exception:
            logger.exception("Student chat stream error")
            yield f"data: {json.dumps({'type': 'error', 'error': 'An error occurred while generating the response.'})}\n\n"

        # Increment for assistant response
        try:
            AIChatbotConversation.objects.filter(pk=conv_pk).update(
                message_count=models.F('message_count') + 1,
            )
        except Exception:
            logger.debug("Failed to increment conversation message_count", exc_info=True)

    response = StreamingHttpResponse(
        sse_stream(),
        content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


def _verify_student_chatbot_access(request, chatbot_id):
    """Verify student has access to chatbot via section enrollment."""
    try:
        chatbot = AIChatbot.objects.get(pk=chatbot_id, is_active=True)
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check: student's section is in chatbot's sections
    student_section_id = getattr(request.user, 'section_fk_id', None)
    if not student_section_id:
        return Response(
            {"error": "You don't have access to this chatbot"},
            status=status.HTTP_403_FORBIDDEN,
        )

    has_access = chatbot.sections.filter(pk=student_section_id).exists()
    if not has_access:
        return Response(
            {"error": "You don't have access to this chatbot"},
            status=status.HTTP_403_FORBIDDEN,
        )

    return chatbot
