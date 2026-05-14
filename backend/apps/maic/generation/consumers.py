"""Generation-progress WebSocket consumer (Phase 4 Session 6, MAIC-428.3).

Mounted at `/ws/maic/generation/<job_id>/`. The HTTP POST to
`/api/maic/v2/generate/` returns a `{job_id}`; the client opens this
socket with the same id and receives a stream of progress events:

    outline_done    — Stage 1 complete, with outlines + languageDirective.
    scene_done      — One scene finished. Includes completed/total counts.
    finalized       — All scenes ready; full result on the DB row.
    error           — A task in the chain failed; payload.message has the
                      reason. The client should stop spinning.

The consumer subscribes to a Channels layer group named
`maic_generation_<job_id>`. Workers publish events via
`channel_layer.group_send(...)` (see apps/maic/generation/tasks.py:
_emit_progress).

On connect we hydrate the connecting client with the current job
status read from the DB row — this lets a client that joins mid-run
see "we're 4 of 10 scenes done" immediately instead of waiting for
the next scene_done event.

Tenant isolation: the consumer rejects (4003) if the connecting
user's tenant doesn't own the MaicGenerationJob row. Anonymous users
are rejected (4001). MAIC v2 disabled globally or for the tenant
rejects with 4403.
"""
from __future__ import annotations

import logging
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from apps.maic.models import MaicGenerationJob


logger = logging.getLogger("apps.maic.generation.consumers")


@database_sync_to_async
def _user_has_maic_v2_access(user) -> bool:
    """Run the shared MAIC v2 gate in a DB-safe sync context."""
    from apps.maic.permissions import user_has_maic_v2_access

    return user_has_maic_v2_access(user)


@database_sync_to_async
def _load_job(job_id: str, tenant_id: int) -> MaicGenerationJob | None:
    """Tenant-scoped job lookup. Returns None if the row is in a
    different tenant or doesn't exist (caller treats both the same)."""
    try:
        return MaicGenerationJob.objects.all_tenants().get(
            pk=job_id, tenant_id=tenant_id
        )
    except MaicGenerationJob.DoesNotExist:
        return None


class GenerationConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for v2 generation progress.

    Lifecycle:
      connect()      — auth + tenant gate, attach to channel group,
                       send hydrate event with current status.
      receive_json() — no client commands accepted in Phase 4
                       (consumer is read-only for now).
      generation_progress() — channel-layer message handler, forwards
                              events to the client.
      disconnect()   — leave the group.
    """

    group_name: str

    async def connect(self) -> None:
        self.user = self.scope.get("user", AnonymousUser())
        if self.user.is_anonymous:
            logger.warning("Generation WS: rejected anonymous connection")
            await self.close(code=4001)
            return

        self.job_id: str = self.scope["url_route"]["kwargs"]["job_id"]
        self.tenant_id = getattr(self.user, "tenant_id", None)

        if self.tenant_id is None:
            logger.warning(
                "Generation WS: user %s has no tenant_id; rejecting",
                self.user.id,
            )
            await self.close(code=4004)
            return

        if not await _user_has_maic_v2_access(self.user):
            logger.warning(
                "Generation WS: user %s tenant=%s failed v2 access gate",
                self.user.id,
                self.tenant_id,
            )
            await self.close(code=4403)
            return

        job = await _load_job(self.job_id, self.tenant_id)
        if job is None:
            logger.warning(
                "Generation WS: job %s not visible to tenant %s",
                self.job_id, self.tenant_id,
            )
            await self.close(code=4003)
            return

        self.group_name = f"maic_generation_{self.job_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        accepted_subprotocol = self.scope.get("accepted_subprotocol")
        await self.accept(subprotocol=accepted_subprotocol)

        # Hydrate the new client with current state — they may have
        # connected mid-run, in which case progress events for already-
        # completed scenes have already been broadcast and missed.
        await self.send_json({
            "event": "hydrate",
            "payload": {
                "status": job.status,
                "progress": job.progress or {},
                "result": job.result or {},
                "error": job.error or "",
            },
        })

        logger.info(
            "Generation WS connect job=%s user=%s tenant=%s",
            self.job_id, self.user.id, self.tenant_id,
        )

    async def receive_json(self, content: dict[str, Any], **kwargs) -> None:
        """No client commands in Phase 4 — the consumer is read-only.
        Phase 5+ may add cancel/retry actions."""
        logger.debug(
            "Generation WS ignoring client message: %s", content.get("type")
        )

    async def generation_progress(self, message: dict[str, Any]) -> None:
        """Channel-layer handler for events from worker tasks.

        Worker calls:
            channel_layer.group_send(
                f"maic_generation_{job_id}",
                {"type": "generation.progress", "event": ..., "payload": ...},
            )

        Channels turns the dotted type into the underscore method name
        `generation_progress` on this consumer.
        """
        await self.send_json({
            "event": message.get("event"),
            "payload": message.get("payload", {}),
        })

    async def disconnect(self, close_code: int) -> None:
        group = getattr(self, "group_name", None)
        if group:
            try:
                await self.channel_layer.group_discard(group, self.channel_name)
            except Exception:  # noqa: BLE001
                # Best-effort — connection is already closing.
                pass
        logger.info(
            "Generation WS disconnect job=%s code=%d",
            getattr(self, "job_id", "<pre-accept>"),
            close_code,
        )
