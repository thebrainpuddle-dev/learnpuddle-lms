import json
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
from typing import Any

import requests as http_requests

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.files.storage import default_storage

from apps.courses.models import Content
from apps.courses.video_models import VideoAsset, VideoTranscript
from apps.progress.models import Assignment, Quiz, QuizQuestion
from apps.users.models import User


MAX_VIDEO_DURATION_SECONDS = 60 * 60  # 1 hour


def _safe_storage_url(path: str) -> str:
    """
    Return a storage URL. For FileSystemStorage this is typically a relative URL
    (e.g. /media/...), which will be made absolute at the API layer.
    """
    return default_storage.url(path)


def _tenant_video_prefix(tenant_id: str, content_id: str) -> str:
    return f"tenant/{tenant_id}/videos/{content_id}"


def _download_to_tempfile(storage_path: str, suffix: str = "") -> str:
    """
    Download a storage object to a local tempfile and return the local path.
    """
    fd, local_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with default_storage.open(storage_path, "rb") as src, open(local_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return local_path


def _upload_dir(local_dir: str, storage_prefix: str) -> dict[str, str]:
    """
    Upload all files in `local_dir` (non-recursive) into `storage_prefix`.
    Returns mapping of filename -> storage_path.
    """
    uploaded: dict[str, str] = {}
    for name in os.listdir(local_dir):
        p = os.path.join(local_dir, name)
        if not os.path.isfile(p):
            continue
        key = f"{storage_prefix}/{name}"
        with open(p, "rb") as f:
            default_storage.save(key, f)
        uploaded[name] = key
    return uploaded


SUBPROCESS_TIMEOUT = 300  # 5 minutes max for any ffmpeg/ffprobe call


def _run_ffprobe(local_input_path: str) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        local_input_path,
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=SUBPROCESS_TIMEOUT)
    return json.loads(out.decode("utf-8"))


def _extract_video_stream_meta(ffprobe_json: dict[str, Any]) -> dict[str, Any]:
    streams = ffprobe_json.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None) or {}
    fmt = ffprobe_json.get("format") or {}
    duration = fmt.get("duration") or video_stream.get("duration")
    try:
        duration_s = int(float(duration)) if duration is not None else None
    except Exception:
        duration_s = None
    return {
        "duration_seconds": duration_s,
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "codec": video_stream.get("codec_name") or "",
    }


def _to_vtt(segments: list[dict[str, Any]]) -> str:
    def _fmt(t: float) -> str:
        # VTT time: HH:MM:SS.mmm
        ms = int(round(t * 1000))
        s = ms // 1000
        ms = ms % 1000
        hh = s // 3600
        mm = (s % 3600) // 60
        ss = s % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"

    lines = ["WEBVTT", ""]
    for i, seg in enumerate(segments, start=1):
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(f"{_fmt(start)} --> {_fmt(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _basic_terms(text: str, limit: int = 40) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z\\-]{3,}", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    terms = sorted(freq.keys(), key=lambda k: (-freq[k], k))
    return terms[:limit]


logger = logging.getLogger(__name__)


def _generate_quiz_via_ollama(transcript_text: str, question_count: int = 6) -> list[dict[str, Any]] | None:
    """
    Call local Ollama LLM to generate contextual quiz questions from transcript.
    Returns parsed question list or None if Ollama is unavailable/fails.
    """
    from django.conf import settings as conf
    base_url = getattr(conf, "OLLAMA_BASE_URL", "http://localhost:11434")
    model = getattr(conf, "OLLAMA_MODEL", "mistral")

    mcq_count = max(1, question_count - 2)
    sa_count = min(2, question_count)

    prompt = f"""You are an educational quiz generator for a teacher training platform.
Based on the following lesson transcript, generate exactly {question_count} quiz questions as a JSON array.

Requirements:
- {mcq_count} questions must be "MCQ" (multiple choice) with exactly 4 options each
- {sa_count} questions must be "SHORT_ANSWER" (open-ended)
- Questions should test understanding, not just recall
- Each MCQ must have one clearly correct answer

For each question, use this exact JSON structure:
{{
  "question_type": "MCQ" or "SHORT_ANSWER",
  "prompt": "the question text",
  "options": ["A", "B", "C", "D"] (for MCQ only, empty [] for SHORT_ANSWER),
  "correct_answer": {{"option_index": 0}} (for MCQ, index of correct option) or {{}} (for SHORT_ANSWER),
  "explanation": "brief explanation of the correct answer",
  "points": 1 (for MCQ) or 2 (for SHORT_ANSWER)
}}

Transcript (first 4000 chars):
---
{transcript_text[:4000]}
---

Respond with ONLY a valid JSON array. No markdown, no explanation, just the array."""

    try:
        resp = http_requests.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.7}},
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")

        # Extract JSON array from response (LLMs sometimes wrap in markdown)
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            questions = json.loads(raw[start:end])
            # Validate structure
            valid = []
            for q in questions:
                if isinstance(q, dict) and "question_type" in q and "prompt" in q:
                    # Ensure required fields have defaults
                    q.setdefault("options", [])
                    q.setdefault("correct_answer", {})
                    q.setdefault("explanation", "")
                    q.setdefault("points", 1 if q["question_type"] == "MCQ" else 2)
                    valid.append(q)
            if len(valid) >= 2:
                logger.info(f"Ollama generated {len(valid)} quiz questions via {model}")
                return valid[:question_count]
    except http_requests.ConnectionError:
        logger.info("Ollama not available (connection refused), falling back to deterministic generator")
    except http_requests.Timeout:
        logger.warning("Ollama timed out after 120s")
    except Exception as e:
        logger.warning(f"Ollama quiz generation failed: {e}")
    return None


def _generate_quiz_deterministic(transcript_text: str, question_count: int = 6) -> list[dict[str, Any]]:
    """
    Deterministic fallback quiz generator when Ollama is not available.
    Produces term-based MCQs + generic short-answer prompts.
    """
    terms = _basic_terms(transcript_text, limit=60)
    rng = random.Random(1337)
    rng.shuffle(terms)

    questions: list[dict[str, Any]] = []

    mcq_terms = terms[: max(0, min(4, len(terms)))]
    for term in mcq_terms:
        pool = [t for t in terms if t != term][:20]
        distractors = rng.sample(pool, k=min(3, len(pool))) if pool else []
        options = [term] + distractors
        rng.shuffle(options)
        correct_idx = options.index(term)
        questions.append({
            "question_type": "MCQ",
            "prompt": f"Which of the following concepts is discussed in this lesson?",
            "options": [o.title() for o in options],
            "correct_answer": {"option_index": correct_idx},
            "explanation": f"The term '{term.title()}' appears in the transcript.",
            "points": 1,
        })

    questions.extend([
        {
            "question_type": "SHORT_ANSWER",
            "prompt": "Summarize the key takeaway of this video in 2-3 sentences.",
            "options": [], "correct_answer": {}, "explanation": "", "points": 2,
        },
        {
            "question_type": "SHORT_ANSWER",
            "prompt": "List 3 important concepts mentioned in the video and explain why they matter.",
            "options": [], "correct_answer": {}, "explanation": "", "points": 2,
        },
    ])
    return questions[:question_count]


def _generate_quiz_questions(transcript_text: str, question_count: int = 6) -> list[dict[str, Any]]:
    """
    Generate quiz questions from transcript.
    Tries Ollama LLM first (like NotebookLM), falls back to deterministic generator.
    """
    # Try Ollama LLM first
    ollama_result = _generate_quiz_via_ollama(transcript_text, question_count)
    if ollama_result:
        return ollama_result

    # Fall back to deterministic generator
    return _generate_quiz_deterministic(transcript_text, question_count)


def _mark_failed(asset: VideoAsset, message: str):
    asset.status = "FAILED"
    asset.error_message = message[:5000]
    asset.save(update_fields=["status", "error_message", "updated_at"])


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def validate_duration(self, video_asset_id: str) -> str:
    asset = VideoAsset.objects.select_related(
        "content",
        "content__module",
        "content__module__course",
        "content__module__course__tenant",
    ).get(id=video_asset_id)

    if asset.status not in {"UPLOADED", "PROCESSING"}:
        return video_asset_id

    asset.status = "PROCESSING"
    asset.error_message = ""
    asset.save(update_fields=["status", "error_message", "updated_at"])

    if not asset.source_file:
        _mark_failed(asset, "Missing source_file for video asset")
        return video_asset_id

    local_path = None
    try:
        local_path = _download_to_tempfile(asset.source_file, suffix=".mp4")
        meta = _extract_video_stream_meta(_run_ffprobe(local_path))
        duration_s = meta.get("duration_seconds")
        if duration_s is None:
            _mark_failed(asset, "Unable to read video duration (ffprobe)")
            return video_asset_id
        if int(duration_s) > MAX_VIDEO_DURATION_SECONDS:
            _mark_failed(asset, f"Video is too long ({duration_s}s). Max is {MAX_VIDEO_DURATION_SECONDS}s.")
            return video_asset_id

        # Persist metadata
        asset.duration_seconds = int(duration_s)
        asset.width = meta.get("width") or None
        asset.height = meta.get("height") or None
        asset.codec = meta.get("codec") or ""
        asset.save(update_fields=["duration_seconds", "width", "height", "codec", "updated_at"])

        # Mirror into Content.duration (seconds)
        Content.objects.filter(id=asset.content_id).update(duration=int(duration_s), updated_at=timezone.now())
        return video_asset_id
    except FileNotFoundError:
        _mark_failed(asset, "ffprobe not found on worker. Install ffmpeg/ffprobe.")
        return video_asset_id
    except subprocess.TimeoutExpired:
        _mark_failed(asset, "ffprobe timed out. Video file may be corrupt.")
        return video_asset_id
    except subprocess.CalledProcessError as e:
        _mark_failed(asset, f"ffprobe failed: {getattr(e, 'output', b'').decode('utf-8', 'ignore')}")
        return video_asset_id
    finally:
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def transcode_to_hls(self, video_asset_id: str) -> str:
    asset = VideoAsset.objects.select_related(
        "content__module__course__tenant",
    ).get(id=video_asset_id)
    if asset.status == "FAILED":
        return video_asset_id
    if not asset.source_file:
        _mark_failed(asset, "Missing source_file for video asset")
        return video_asset_id

    tenant_id = str(asset.content.module.course.tenant_id)
    content_id = str(asset.content_id)
    prefix = _tenant_video_prefix(tenant_id, content_id)
    hls_prefix = f"{prefix}/hls"

    local_in = None
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            local_in = _download_to_tempfile(asset.source_file, suffix=".mp4")
            out_m3u8 = os.path.join(tmpdir, "master.m3u8")
            seg_pattern = os.path.join(tmpdir, "seg_%05d.ts")

            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                local_in,
                "-c:v",
                "h264",
                "-c:a",
                "aac",
                "-vf",
                "scale='min(1280,iw)':-2",
                "-hls_time",
                "6",
                "-hls_playlist_type",
                "vod",
                "-hls_segment_filename",
                seg_pattern,
                out_m3u8,
            ]
            subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=SUBPROCESS_TIMEOUT)

            uploaded = _upload_dir(tmpdir, hls_prefix)
            master_key = uploaded.get("master.m3u8") or f"{hls_prefix}/master.m3u8"
            master_url = _safe_storage_url(master_key)

            asset.hls_master_url = master_url
            asset.save(update_fields=["hls_master_url", "updated_at"])

            # For teacher playback, point Content.file_url to the HLS master.
            Content.objects.filter(id=asset.content_id).update(file_url=master_url, updated_at=timezone.now())
            return video_asset_id
        except FileNotFoundError:
            _mark_failed(asset, "ffmpeg not found on worker. Install ffmpeg.")
            return video_asset_id
        except subprocess.CalledProcessError as e:
            _mark_failed(asset, f"ffmpeg failed: {getattr(e, 'output', b'').decode('utf-8', 'ignore')}")
            return video_asset_id
        finally:
            if local_in and os.path.exists(local_in):
                try:
                    os.remove(local_in)
                except Exception:
                    pass


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def generate_thumbnail(self, video_asset_id: str) -> str:
    asset = VideoAsset.objects.select_related("content__module__course__tenant").get(id=video_asset_id)
    if asset.status == "FAILED":
        return video_asset_id
    if not asset.source_file:
        _mark_failed(asset, "Missing source_file for video asset")
        return video_asset_id

    tenant_id = str(asset.content.module.course.tenant_id)
    content_id = str(asset.content_id)
    prefix = _tenant_video_prefix(tenant_id, content_id)
    thumb_key = f"{prefix}/thumb.jpg"

    local_in = None
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            local_in = _download_to_tempfile(asset.source_file, suffix=".mp4")
            local_thumb = os.path.join(tmpdir, "thumb.jpg")
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                local_in,
                "-ss",
                "00:00:01.000",
                "-vframes",
                "1",
                local_thumb,
            ]
            subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=SUBPROCESS_TIMEOUT)
            with open(local_thumb, "rb") as f:
                default_storage.save(thumb_key, f)
            asset.thumbnail_url = _safe_storage_url(thumb_key)
            asset.save(update_fields=["thumbnail_url", "updated_at"])
            return video_asset_id
        except FileNotFoundError:
            _mark_failed(asset, "ffmpeg not found on worker. Install ffmpeg.")
            return video_asset_id
        except subprocess.CalledProcessError as e:
            _mark_failed(asset, f"ffmpeg thumbnail failed: {getattr(e, 'output', b'').decode('utf-8', 'ignore')}")
            return video_asset_id
        finally:
            if local_in and os.path.exists(local_in):
                try:
                    os.remove(local_in)
                except Exception:
                    pass


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def transcribe_video(self, video_asset_id: str, language: str = "en") -> str:
    """
    Transcribe video audio using faster-whisper.
    Non-fatal: if transcription fails, the pipeline continues (video is still usable).
    """
    asset = VideoAsset.objects.select_related("content__module__course__tenant").get(id=video_asset_id)
    if asset.status == "FAILED":
        return video_asset_id
    if not asset.source_file:
        logger.warning("transcribe_video: no source_file for asset %s, skipping", video_asset_id)
        return video_asset_id

    tenant_id = str(asset.content.module.course.tenant_id)
    content_id = str(asset.content_id)
    prefix = _tenant_video_prefix(tenant_id, content_id)
    vtt_key = f"{prefix}/captions.vtt"

    local_in = None
    try:
        local_in = _download_to_tempfile(asset.source_file, suffix=".mp4")

        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception:
            logger.warning("transcribe_video: faster-whisper not installed, skipping transcription for asset %s", video_asset_id)
            return video_asset_id

        # Small model by default; override via env if desired.
        model_size = os.getenv("WHISPER_MODEL_SIZE", "small")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        model = WhisperModel(model_size, device=device, compute_type=compute_type)

        segments_iter, info = model.transcribe(local_in, language=language)
        segments: list[dict[str, Any]] = []
        full_parts: list[str] = []
        for seg in segments_iter:
            text = (seg.text or "").strip()
            if not text:
                continue
            segments.append({"start": float(seg.start), "end": float(seg.end), "text": text})
            full_parts.append(text)
        full_text = " ".join(full_parts).strip()

        vtt_text = _to_vtt(segments)
        with tempfile.NamedTemporaryFile("w", suffix=".vtt", delete=False) as tmp:
            tmp.write(vtt_text)
            tmp_path = tmp.name
        try:
            with open(tmp_path, "rb") as f:
                default_storage.save(vtt_key, f)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        vtt_url = _safe_storage_url(vtt_key)
        transcript, _created = VideoTranscript.objects.get_or_create(
            video_asset=asset,
            defaults={
                "language": language,
                "full_text": full_text,
                "segments": segments,
                "vtt_url": vtt_url,
                "generated_at": timezone.now(),
            },
        )
        if not _created:
            transcript.language = language
            transcript.full_text = full_text
            transcript.segments = segments
            transcript.vtt_url = vtt_url
            transcript.generated_at = timezone.now()
            transcript.save()

        return video_asset_id
    except Exception as e:
        # Transcription is non-fatal: log the error but don't mark asset as FAILED.
        # HLS and thumbnail are the critical artifacts; transcript is optional.
        logger.error("transcribe_video failed for asset %s: %s", video_asset_id, e)
        return video_asset_id
    finally:
        if local_in and os.path.exists(local_in):
            try:
                os.remove(local_in)
            except Exception:
                pass


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def generate_assignments(self, video_asset_id: str) -> str:
    """
    Auto-generate reflection + quiz assignments from a video's transcript.
    Non-fatal: if this fails, the video is still usable.
    """
    asset = VideoAsset.objects.select_related(
        "content",
        "content__module",
        "content__module__course",
        "content__module__course__tenant",
    ).get(id=video_asset_id)
    if asset.status == "FAILED":
        return video_asset_id

    transcript = getattr(asset, "transcript", None)
    transcript_text = transcript.full_text if transcript else ""

    content = asset.content
    course = content.module.course
    module = content.module

    try:
        with transaction.atomic():
            # Reflection assignment
            reflection_title = f"Reflection: {content.title}"
            reflection_desc = "Write a short reflection based on the video lesson."
            reflection_instructions = (
                "In 150-300 words, summarize the key points and describe how you would apply them.\n"
                "You may include examples from your classroom."
            )
            reflection_assignment, reflection_created = Assignment.objects.get_or_create(
                course=course,
                module=module,
                content=content,
                generation_source="VIDEO_AUTO",
                title=reflection_title,
                defaults={
                    "description": reflection_desc,
                    "instructions": reflection_instructions,
                    "is_mandatory": True,
                    "is_active": True,
                    "generation_metadata": {"video_asset_id": str(asset.id), "type": "reflection"},
                },
            )

            # Quiz assignment + quiz objects
            quiz_title = f"Quiz: {content.title}"
            quiz_desc = "Auto-generated quiz based on the video transcript."
            quiz_instructions = "Answer the questions. MCQs are auto-graded; short answers may be reviewed."

            quiz_assignment, quiz_created = Assignment.objects.get_or_create(
                course=course,
                module=module,
                content=content,
                generation_source="VIDEO_AUTO",
                title=quiz_title,
                defaults={
                    "description": quiz_desc,
                    "instructions": quiz_instructions,
                    "is_mandatory": True,
                    "is_active": True,
                    "generation_metadata": {"video_asset_id": str(asset.id), "type": "quiz"},
                },
            )

            quiz_obj, _created = Quiz.objects.get_or_create(
                assignment=quiz_assignment,
                defaults={
                    "schema_version": 1,
                    "is_auto_generated": True,
                    "generation_model": os.getenv("QUIZ_GENERATION_MODEL", ""),
                },
            )

            # Idempotency: if questions already exist, don't duplicate.
            if quiz_obj.questions.exists():
                if reflection_created or quiz_created:
                    _notify_new_assignments(course, [a for a, c in [(reflection_assignment, reflection_created), (quiz_assignment, quiz_created)] if c])
                return video_asset_id

            q_payloads = _generate_quiz_questions(transcript_text or content.title, question_count=6)
            for idx, q in enumerate(q_payloads, start=1):
                QuizQuestion.objects.create(
                    quiz=quiz_obj,
                    order=idx,
                    question_type=q["question_type"],
                    prompt=q["prompt"],
                    options=q.get("options") or [],
                    correct_answer=q.get("correct_answer") or {},
                    explanation=q.get("explanation") or "",
                    points=int(q.get("points") or 1),
                )

            if reflection_created or quiz_created:
                _notify_new_assignments(course, [a for a, c in [(reflection_assignment, reflection_created), (quiz_assignment, quiz_created)] if c])
    except Exception as e:
        # Assignment generation is non-fatal: log but don't mark asset as FAILED.
        logger.error("generate_assignments failed for asset %s: %s", video_asset_id, e)

    return video_asset_id


def _notify_new_assignments(course, assignments: list[Assignment]):
    """
    Notify teachers who are assigned to this course about new assignments.
    """
    from apps.notifications.services import create_bulk_notifications

    teachers = User.objects.filter(
        tenant=course.tenant,
        role__in=["TEACHER", "HOD", "IB_COORDINATOR"],
        is_active=True,
    )
    if not course.assigned_to_all:
        group_ids = course.assigned_groups.values_list("id", flat=True)
        teacher_ids = course.assigned_teachers.values_list("id", flat=True)
        teachers = teachers.filter(Q(id__in=teacher_ids) | Q(teacher_groups__in=group_ids)).distinct()

    teacher_list = list(teachers)
    if not teacher_list:
        return

    for a in assignments:
        create_bulk_notifications(
            tenant=course.tenant,
            teachers=teacher_list,
            notification_type="SYSTEM",
            title=f"New assignment: {a.title}",
            message=f"A new assignment was generated for the course '{course.title}'.",
            course=course,
            assignment=a,
        )


@shared_task(bind=True)
def finalize_video_asset(self, video_asset_id: str) -> str:
    asset = VideoAsset.objects.get(id=video_asset_id)
    if asset.status == "FAILED":
        return video_asset_id

    # HLS is the only critical artifact. Thumbnail and transcript are nice-to-have.
    if not asset.hls_master_url:
        _mark_failed(asset, "Processing incomplete: missing HLS stream. Try re-uploading.")
    else:
        asset.status = "READY"
        asset.error_message = ""
        asset.save(update_fields=["status", "error_message", "updated_at"])
        if not asset.thumbnail_url:
            logger.warning("finalize_video_asset: asset %s is READY but missing thumbnail", video_asset_id)
    return video_asset_id

