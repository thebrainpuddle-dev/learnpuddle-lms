"""Mineru cloud PDF adapter (Phase 10, MAIC-1002).

Source: THU-MAIC/OpenMAIC lib/pdf/mineru-cloud.ts (read for HTTP
        contract; re-implemented in Python per ADR-001a). Async-
        polling pattern from apps/maic/media/adapters/qwen_image.py
        (Phase 9 MAIC-904) — verbatim shape, different terminal
        statuses + result mapping.

Mineru's async flow:
  1. POST /api/v4/extract/task   → {data: {task_id}}
  2. Poll GET /api/v4/extract/task/<id> every ~5s until state in
     {done, failed}
  3. On done: response carries the structured document inline
     (sections, figures, pages, markdown)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, ClassVar

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.integrations_chat.ssrf_guard import SSRFError, validate_webhook_host
from apps.maic.pdf.providers import PDFProviderAdapter, register_adapter
from apps.maic.pdf.types import (
    PDFDocument,
    PDFFigure,
    PDFPage,
    PDFParseRequest,
    PDFParseResult,
    PDFParseState,
    PDFSection,
)


logger = logging.getLogger(__name__)


# Terminal state mapping. Mineru emits lowercase string states.
_TERMINAL_SUCCESS: frozenset[str] = frozenset({"done"})
_TERMINAL_FAILURE: frozenset[str] = frozenset({"failed"})
_IN_PROGRESS: frozenset[str] = frozenset({"pending", "running", "converting"})


@register_adapter
class MineruCloudAdapter(PDFProviderAdapter):
    """Mineru Cloud API adapter.

    Reads from TenantAIConfig:
        get_mineru_api_key() — required
        mineru_base_url — optional, defaults to https://mineru.net/api/v4
    """

    name: ClassVar[str] = "mineru"
    # Outer cap on the whole parse call. Long enough for a 50-page
    # textbook (~90s typical) + headroom for polling cadence.
    default_timeout_seconds: ClassVar[int] = 240

    _DEFAULT_BASE_URL: ClassVar[str] = "https://mineru.net/api/v4"
    _poll_interval_seconds: ClassVar[float] = 5.0
    _poll_timeout_seconds: ClassVar[float] = 210.0  # < default_timeout for headroom

    async def parse(self, req: PDFParseRequest) -> PDFParseResult:
        api_key = self._require_api_key()
        base_url = self._resolved_base_url()
        loop_start = asyncio.get_event_loop().time()

        # Lazy aiohttp import — test-only fakes inject via sys.modules.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError("aiohttp required for Mineru adapter") from exc

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        submit_payload = self._build_submit_payload(req)
        submit_url = f"{base_url}/extract/task"

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: submit
                async with session.post(submit_url, json=submit_payload, headers=headers) as resp:
                    body_text = await resp.text()
                    self._raise_for_status(resp.status, body_text, phase="submit")
                    submit_data = self._parse_json(body_text, phase="submit")
                task_id = self._extract_task_id(submit_data)

                # Step 2: poll until terminal
                terminal_data = await self._poll_task_until_done(
                    session=session,
                    task_id=task_id,
                    headers=headers,
                    base_url=base_url,
                )
        except aiohttp.ClientError as exc:
            raise MaicProviderError(
                f"mineru: network error: {exc}",
            ) from exc

        # Step 3: shape the response into a PDFDocument
        document = self._build_document(
            terminal_data=terminal_data,
            task_id=task_id,
            latency_ms=int((asyncio.get_event_loop().time() - loop_start) * 1000),
        )
        return PDFParseResult(
            document_id=document.document_id,
            document=document,
            state=PDFParseState.DONE,
            latency_ms=document.latency_ms,
        )

    # ── Helpers ────────────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        api_key = self.tenant_config.get_mineru_api_key()
        if not api_key:
            raise MaicConfigError(
                "mineru: api_key required (set mineru_api_key on "
                "TenantAIConfig via set_mineru_api_key())"
            )
        return api_key

    def _resolved_base_url(self) -> str:
        raw = (self.tenant_config.mineru_base_url or "").strip()
        if not raw:
            return self._DEFAULT_BASE_URL.rstrip("/")
        base = raw.rstrip("/")
        if base == self._DEFAULT_BASE_URL.rstrip("/"):
            return base
        try:
            validate_webhook_host(base)
        except SSRFError as exc:
            raise MaicConfigError(
                f"mineru: mineru_base_url failed SSRF check: {exc}"
            ) from exc
        return base

    def _build_submit_payload(self, req: PDFParseRequest) -> dict[str, Any]:
        """Mineru extract-task body. Conservative: only the well-known
        fields. Unknown fields would cause Mineru's API to reject."""
        payload: dict[str, Any] = {
            "url": req.file_url,
            "is_ocr": True,            # better extraction at small cost
            "enable_formula": True,    # textbooks have math
            "enable_table": True,      # textbooks have tables
            "language": "auto",
        }
        if req.page_limit is not None:
            payload["page_limit"] = req.page_limit
        if not req.extract_figures:
            payload["extract_images"] = False
        return payload

    @staticmethod
    def _raise_for_status(status: int, body: str, *, phase: str) -> None:
        if 200 <= status < 300:
            return
        snippet = body[:200] if body else ""
        if status in (401, 403):
            raise MaicConfigError(
                f"mineru: auth failed at {phase} (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"mineru: rate limited at {phase} (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            raise MaicProviderError(
                f"mineru: client error at {phase} (HTTP {status}): {snippet}"
            )
        raise MaicProviderError(
            f"mineru: server error at {phase} (HTTP {status}): {snippet}"
        )

    @staticmethod
    def _parse_json(body: str, *, phase: str) -> dict:
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise MaicProviderError(
                f"mineru: malformed JSON at {phase}: {exc}"
            ) from exc

    @staticmethod
    def _extract_task_id(data: dict) -> str:
        try:
            task_id = data["data"]["task_id"]
        except (KeyError, TypeError) as exc:
            raise MaicProviderError(
                f"mineru: submit response missing data.task_id: {list(data)[:5]}"
            ) from exc
        if not isinstance(task_id, str) or not task_id:
            raise MaicProviderError("mineru: task_id was empty or non-string")
        return task_id

    async def _poll_task_until_done(
        self,
        session,
        task_id: str,
        headers: dict[str, str],
        base_url: str,
    ) -> dict:
        """Poll Mineru until terminal state or deadline.

        Lifts shape from apps/maic/media/adapters/qwen_image.py:
            - deadline check TWICE per iteration (before GET, before sleep)
            - sleep clamped to min(interval, remaining) — never overshoot
            - NO `while True` — only terminal status or deadline exits
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._poll_timeout_seconds
        poll_url = f"{base_url}/extract/task/{task_id}"

        while True:
            now = loop.time()
            if now >= deadline:
                raise MaicProviderError(
                    f"mineru: polling deadline exceeded after "
                    f"{self._poll_timeout_seconds:.0f}s (task_id={task_id})"
                )

            async with session.get(poll_url, headers=headers) as resp:
                body_text = await resp.text()
                self._raise_for_status(resp.status, body_text, phase="poll")
                poll_data = self._parse_json(body_text, phase="poll")

            try:
                state = poll_data["data"]["state"]
            except (KeyError, TypeError) as exc:
                raise MaicProviderError(
                    f"mineru: poll response missing data.state: {list(poll_data)[:5]}"
                ) from exc

            if state in _TERMINAL_SUCCESS:
                return poll_data["data"]

            if state in _TERMINAL_FAILURE:
                err = poll_data["data"].get("err_msg", "")[:200]
                raise MaicProviderError(
                    f"mineru: parse failed (state={state!r}): {err}"
                )

            if state not in _IN_PROGRESS:
                # Unknown status — fail loud (don't spin)
                raise MaicProviderError(
                    f"mineru: unrecognized state {state!r} (task_id={task_id})"
                )

            # Sleep, clamped so we can't overshoot the deadline
            remaining = deadline - loop.time()
            if remaining <= 0:
                # Edge case: deadline tripped during the GET — bail on next iter
                continue
            await asyncio.sleep(min(self._poll_interval_seconds, remaining))

    def _build_document(
        self,
        terminal_data: dict,
        task_id: str,
        latency_ms: int,
    ) -> PDFDocument:
        """Shape Mineru's terminal-success payload into our PDFDocument.

        Mineru returns a rich payload — we extract the fields we
        actually use downstream (Phase 4 outline seed). Unknown fields
        are ignored. Missing fields default to empty lists, which is
        valid (an image-only PDF parses to a doc with 0 sections)."""
        full_zip_url = terminal_data.get("full_zip_url") or ""
        # Mineru includes the parsed content in a `content_list` or
        # `markdown` field depending on which extraction mode succeeded.
        sections: list[PDFSection] = []
        figures: list[PDFFigure] = []
        pages: list[PDFPage] = []

        # `pages` is Mineru's per-page text list (if requested)
        for idx, page_obj in enumerate((terminal_data.get("pages") or []), start=1):
            if not isinstance(page_obj, dict):
                continue
            pages.append(PDFPage(
                page_number=page_obj.get("page_number", idx),
                text=str(page_obj.get("text", "")),
            ))

        # `sections` (if Mineru's heading extractor ran) — we accept
        # whatever shape it provides, defensive on missing fields
        for s_idx, section in enumerate((terminal_data.get("sections") or []), start=1):
            if not isinstance(section, dict):
                continue
            title = (section.get("title") or "").strip()
            if not title:
                continue  # skip headings Mineru could not extract
            sections.append(PDFSection(
                section_id=section.get("id") or f"sec-{s_idx}",
                title=title[:500],
                level=max(1, min(6, int(section.get("level", 1)))),
                text=str(section.get("text", "")),
                page_start=max(1, int(section.get("page_start", 1))),
                page_end=max(1, int(section.get("page_end", 1))),
            ))

        for f_idx, fig in enumerate((terminal_data.get("figures") or []), start=1):
            if not isinstance(fig, dict):
                continue
            figures.append(PDFFigure(
                figure_id=fig.get("id") or f"fig-{f_idx}",
                caption=str(fig.get("caption", ""))[:2_000],
                image_url=fig.get("image_url"),
                page=max(1, int(fig.get("page", 1))),
            ))

        total_pages = (
            int(terminal_data.get("total_pages") or 0)
            or len(pages)
            or 1  # avoid validation failure if Mineru omitted it
        )

        return PDFDocument(
            document_id=task_id,  # use Mineru's task_id as our doc id
            title=str(terminal_data.get("title") or "")[:500],
            total_pages=total_pages,
            sections=sections,
            figures=figures,
            pages=pages,
            provider="mineru",
            latency_ms=latency_ms,
            cost_usd_estimate=None,  # Mineru pricing is account-tier dependent
        )
