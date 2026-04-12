# apps/courses/chatbot_views.py
"""
Teacher chatbot CRUD + student chatbot chat endpoints.
All endpoints gated by @check_feature("feature_maic").
"""
import hashlib
import logging
import time

from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.chatbot_models import (
    AIChatbot, AIChatbotKnowledge, AIChatbotConversation,
)
from apps.courses.chatbot_serializers import (
    AIChatbotSerializer, AIChatbotCreateSerializer,
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

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.md', '.docx'}


# ─── Teacher: Chatbot CRUD ────────────────────────────────────────────

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_chatbot_list_create(request):
    """GET: list teacher's chatbots. POST: create new chatbot."""
    if request.method == "GET":
        chatbots = AIChatbot.objects.filter(creator=request.user)
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
            chatbot=chatbot,
            source_type='text',
            title=title or 'Text Input',
            raw_text=raw_text,
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

        # Save file
        path = f"tenant/{request.tenant.id}/chatbot/{chatbot_id}/{file.name}"
        saved_path = default_storage.save(path, file)

        # Compute hash
        file.seek(0)
        content_hash = hashlib.sha256(file.read()).hexdigest()

        knowledge = AIChatbotKnowledge.objects.create(
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
    """List student conversations for a chatbot."""
    try:
        chatbot = AIChatbot.objects.get(pk=chatbot_id, creator=request.user)
    except AIChatbot.DoesNotExist:
        return Response({"error": "Chatbot not found"}, status=status.HTTP_404_NOT_FOUND)

    conversations = AIChatbotConversation.objects.filter(
        chatbot=chatbot,
    ).select_related('student').order_by('-last_message_at')

    serializer = AIChatbotConversationListSerializer(conversations, many=True)
    return Response(serializer.data)


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
        "total_messages": sum(c.message_count for c in conversations),
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
    )

    serializer = AIChatbotSerializer(chatbots, many=True)
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
    return Response(
        AIChatbotConversationDetailSerializer(conversation).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_conversation_detail(request, chatbot_id, conversation_id):
    """Get conversation detail."""
    chatbot = _verify_student_chatbot_access(request, chatbot_id)
    if isinstance(chatbot, Response):
        return chatbot

    try:
        conversation = AIChatbotConversation.objects.get(
            pk=conversation_id, chatbot=chatbot, student=request.user,
        )
    except AIChatbotConversation.DoesNotExist:
        return Response({"error": "Conversation not found"}, status=status.HTTP_404_NOT_FOUND)

    return Response(AIChatbotConversationDetailSerializer(conversation).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
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
        return Response(
            {"error": "message is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get or create conversation
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

    # Add user message to conversation
    conversation.messages.append({
        "role": "user",
        "content": message,
        "timestamp": int(time.time()),
    })
    conversation.message_count += 1
    conversation.save(update_fields=['messages', 'message_count', 'last_message_at'])

    # Auto-set title from first message
    if not conversation.title:
        conversation.title = message[:100]
        conversation.save(update_fields=['title'])

    # Get AI config
    try:
        ai_config = TenantAIConfig.objects.get(tenant=request.tenant)
    except TenantAIConfig.DoesNotExist:
        return Response(
            {"error": "AI provider not configured"},
            status=status.HTTP_403_FORBIDDEN,
        )

    def sse_generator():
        full_response = {"content": "", "sources": []}
        try:
            gen = stream_chat_response(
                chatbot=chatbot,
                conversation_messages=conversation.messages[:-1],  # Exclude the just-added user msg
                user_message=message,
                ai_config=ai_config,
            )
            for chunk in gen:
                yield chunk

                # Capture the returned data
                if '"type": "done"' in chunk or '"type":"done"' in chunk:
                    pass  # Stream is done

        except Exception as exc:
            logger.exception("Chat stream error")
            yield f"data: {__import__('json').dumps({'type': 'error', 'error': str(exc)})}\n\n"
            return

        # Save assistant response to conversation
        # We need to reconstruct the full content from the stream
        # The stream_chat_response generator doesn't return its result in a way
        # we can capture via `return`, so we accumulate from SSE chunks
        # This is handled by the client sending back the final content,
        # OR we parse the chunks ourselves. For simplicity, we accumulate:

    # We need a wrapper that saves the response after streaming
    def sse_with_save():
        full_content = ""
        sources = []
        import json as _json
        for chunk in sse_generator():
            yield chunk
            # Parse chunk to accumulate content
            if chunk.startswith("data: "):
                try:
                    data = _json.loads(chunk[6:].strip())
                    if data.get("type") == "content":
                        full_content += data.get("content", "")
                    elif data.get("type") == "sources":
                        sources = data.get("sources", [])
                except (ValueError, KeyError):
                    pass

        # Save assistant message
        if full_content:
            conversation.messages.append({
                "role": "assistant",
                "content": full_content,
                "timestamp": int(time.time()),
                "sources": sources if sources else None,
            })
            conversation.message_count += 1
            conversation.save(update_fields=['messages', 'message_count', 'last_message_at'])

    response = StreamingHttpResponse(
        sse_with_save(),
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
