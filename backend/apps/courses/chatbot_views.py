# apps/courses/chatbot_views.py
"""
Teacher chatbot CRUD + student chatbot chat endpoints.
All endpoints gated by @check_feature("feature_maic").
"""
import hashlib
import logging
import os

from django.core.files.storage import default_storage
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

logger = logging.getLogger(__name__)


class ChatbotChatThrottle(UserRateThrottle):
    rate = '30/minute'


MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.md', '.docx'}
MAX_MESSAGES_PER_CONVERSATION = 200


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
        )
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

    chatbot = serializer.save(
        tenant=request.tenant,
        creator=request.user,
    )
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
        chatbot = AIChatbot.objects.get(pk=chatbot_id, creator=request.user)
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(AIChatbotSerializer(chatbot).data)

    if request.method == "PATCH":
        serializer = AIChatbotCreateSerializer(chatbot, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AIChatbotSerializer(chatbot).data)

    # DELETE — soft deactivate
    chatbot.is_active = False
    chatbot.save(update_fields=['is_active', 'updated_at'])
    return Response(status=status.HTTP_204_NO_CONTENT)


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
        sources = AIChatbotKnowledge.objects.filter(chatbot=chatbot)
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

        knowledge = AIChatbotKnowledge.objects.create(
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

        knowledge = AIChatbotKnowledge.objects.create(
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

        knowledge = AIChatbotKnowledge.objects.create(
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
        knowledge = AIChatbotKnowledge.objects.get(pk=knowledge_id, chatbot=chatbot)
    except (AIChatbot.DoesNotExist, AIChatbotKnowledge.DoesNotExist):
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    # Delete file from storage
    if knowledge.file_url:
        try:
            default_storage.delete(knowledge.file_url)
        except Exception:
            pass

    knowledge.delete()  # CASCADE deletes chunks
    return Response(status=status.HTTP_204_NO_CONTENT)


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


# ─── Student: Chatbot Access ──────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_chatbot_list(request):
    """List chatbots available to this student (via course assignments)."""
    from apps.courses.models import Course

    # Find courses assigned to this student
    student_course_ids = Course.objects.filter(
        assigned_students=request.user,
        is_active=True,
        is_published=True,
    ).values_list('id', flat=True)

    # Find teachers assigned to those courses
    teacher_ids = Course.objects.filter(
        id__in=student_course_ids,
    ).values_list('assigned_teachers', flat=True).distinct()

    # Get active chatbots from those teachers
    chatbots = AIChatbot.objects.filter(
        creator_id__in=teacher_ids,
        is_active=True,
    ).annotate(
        _knowledge_count=Count('knowledge_sources', distinct=True),
        _conversation_count=Count('conversations', distinct=True),
    )

    serializer = AIChatbotStudentSerializer(chatbots, many=True)
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
    # Client sends chat history from sessionStorage (list of {role, content} dicts)
    history = request.data.get("history", [])

    if not message:
        return Response(
            {"error": "message is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(message) > 4000:
        return Response(
            {"error": "Message too long"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate history format
    if not isinstance(history, list):
        history = []
    # Sanitize: keep only role and content keys, filter invalid entries
    sanitized_history = []
    for msg in history:
        if isinstance(msg, dict) and msg.get("role") in ("user", "assistant") and msg.get("content"):
            sanitized_history.append({"role": msg["role"], "content": msg["content"]})

    # Get or create conversation (metadata only, no messages stored)
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

    # Check message limit
    if conversation.message_count >= MAX_MESSAGES_PER_CONVERSATION:
        return Response(
            {"error": "This conversation has reached its message limit. Please start a new conversation."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Update conversation metadata (title, message_count) — no messages saved
    conversation.message_count += 1
    if not conversation.title:
        conversation.title = message[:100]
    conversation.save(update_fields=['message_count', 'last_message_at', 'title'])

    # Get AI config
    try:
        ai_config = TenantAIConfig.objects.get(tenant=request.tenant)
    except TenantAIConfig.DoesNotExist:
        return Response(
            {"error": "AI provider not configured"},
            status=status.HTTP_403_FORBIDDEN,
        )

    import json as _json

    def sse_stream():
        try:
            gen = stream_chat_response(
                chatbot=chatbot,
                conversation_messages=sanitized_history,
                user_message=message,
                ai_config=ai_config,
            )
            for chunk in gen:
                # Intercept the done event to inject conversation_id
                if chunk.startswith("data: "):
                    try:
                        data = _json.loads(chunk[6:].strip())
                        if data.get("type") == "done":
                            done_data = {"type": "done", "conversation_id": str(conversation.pk)}
                            yield f"data: {_json.dumps(done_data)}\n\n"
                            continue
                    except (ValueError, KeyError):
                        pass
                yield chunk
        except GeneratorExit:
            pass
        except Exception:
            logger.exception("Chat stream error")
            yield f"data: {_json.dumps({'type': 'error', 'error': 'An error occurred while generating the response.'})}\n\n"

        # Increment message_count for the assistant response
        try:
            conversation.refresh_from_db(fields=['message_count'])
            conversation.message_count += 1
            conversation.save(update_fields=['message_count', 'last_message_at'])
        except Exception:
            logger.exception("Failed to update conversation message_count")

    response = StreamingHttpResponse(
        sse_stream(),
        content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


def _verify_student_chatbot_access(request, chatbot_id):
    """Verify student has access to chatbot via course assignments."""
    from apps.courses.models import Course

    try:
        chatbot = AIChatbot.objects.get(pk=chatbot_id, is_active=True)
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check: student shares at least one active course with chatbot creator
    shared_course = Course.objects.filter(
        assigned_students=request.user,
        assigned_teachers=chatbot.creator,
        is_active=True,
        is_published=True,
    ).exists()

    if not shared_course:
        return Response(
            {"error": "You don't have access to this chatbot"},
            status=status.HTTP_403_FORBIDDEN,
        )

    return chatbot
