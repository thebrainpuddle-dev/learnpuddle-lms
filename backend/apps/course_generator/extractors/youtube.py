"""YouTube transcript extractor for TASK-060 — AI Course Generator.

Uses youtube-transcript-api to fetch the auto-generated or manual captions
for a public YouTube video.  If the library is missing or the transcript is
unavailable, raises a descriptive error — never silently continues.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

CHAR_CAP = 100_000

# Allowlisted hostnames for SSRF defence (validated again in views.py)
ALLOWED_HOSTNAMES = frozenset(
    {"youtube.com", "www.youtube.com", "youtu.be"}
)


class YouTubeExtractor:
    """Fetch transcript text from a YouTube video URL."""

    def extract(self, url: str) -> str:
        """Return up to CHAR_CAP chars of transcript text.

        Args:
            url: A YouTube video URL.

        Returns:
            Concatenated transcript text.

        Raises:
            ValueError: If the URL is not a recognised YouTube URL.
            RuntimeError: If youtube-transcript-api is not installed, or the
                transcript is unavailable (YOUTUBE_TRANSCRIPT_UNAVAILABLE).
        """
        video_id = self._parse_video_id(url)
        if not video_id:
            raise ValueError(
                f"INVALID_YOUTUBE_URL: Cannot parse video ID from URL: {url!r}"
            )

        try:
            from youtube_transcript_api import (
                YouTubeTranscriptApi,
                TranscriptsDisabled,
                NoTranscriptFound,
                VideoUnavailable,
            )
        except ImportError:
            raise RuntimeError(
                "YOUTUBE_TRANSCRIPT_UNAVAILABLE: youtube-transcript-api is not "
                "installed. Add youtube-transcript-api>=0.6 to requirements.txt."
            )

        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        except (TranscriptsDisabled, NoTranscriptFound) as exc:
            raise RuntimeError(
                f"YOUTUBE_TRANSCRIPT_UNAVAILABLE: No transcript available for "
                f"video {video_id!r}: {exc}"
            )
        except VideoUnavailable as exc:
            raise RuntimeError(
                f"YOUTUBE_TRANSCRIPT_UNAVAILABLE: Video {video_id!r} is unavailable: {exc}"
            )
        except Exception as exc:
            raise RuntimeError(
                f"YOUTUBE_TRANSCRIPT_UNAVAILABLE: Failed to fetch transcript for "
                f"{video_id!r}: {exc}"
            )

        parts: list[str] = []
        total = 0
        for entry in transcript_list:
            text = (entry.get("text") or "").strip()
            if not text:
                continue
            remaining = CHAR_CAP - total
            if len(text) >= remaining:
                parts.append(text[:remaining])
                break
            parts.append(text)
            total += len(text)

        return " ".join(parts)

    @staticmethod
    def _parse_video_id(url: str) -> str | None:
        """Extract the 11-char video ID from a YouTube URL."""
        parsed = urlparse(url)
        host = parsed.hostname or ""

        if host in ("youtube.com", "www.youtube.com"):
            qs = parse_qs(parsed.query)
            ids = qs.get("v", [])
            if ids:
                return ids[0]
            # Support /embed/<id> and /shorts/<id>
            m = re.match(r"^/(embed|shorts|v)/([A-Za-z0-9_-]{11})", parsed.path)
            if m:
                return m.group(2)

        if host == "youtu.be":
            path = parsed.path.lstrip("/")
            if re.match(r"^[A-Za-z0-9_-]{11}", path):
                return path[:11]

        return None
