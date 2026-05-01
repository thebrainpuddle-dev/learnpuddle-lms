# apps/courses/maic_consumers.py
"""F2 (P0) — WebSocket consumer for per-element MAIC image-task events.

Streams image-task state transitions (pending → generating → done|failed)
emitted by ``fill_classroom_images`` to a single classroom's subscribers.

Auth contract — mirrors ``apps/notifications/consumers.py``:
  - JWT carried via the WebSocket ``Sec-WebSocket-Protocol: Bearer.<jwt>``
    subprotocol; ``JWTAuthMiddleware`` populates ``scope["user"]``.
  - Anonymous connections are rejected with code 4001.
  - The connection is rejected (4003) when the user can't view the
    target classroom under the project's existing visibility rules.

Visibility gate (WAVE-F2-F1, 2026-04-28):
  Defers to ``maic_views._can_view_classroom`` — the single canonical
  rule shared with the HTTP ``teacher_maic_classroom_detail`` path. The
  consumer no longer treats every same-tenant teacher / HOD /
  IB_COORDINATOR as allowed; only the creator (any role), SCHOOL_ADMIN,
  SUPER_ADMIN, and a section-eligible STUDENT can subscribe. Peer
  teachers who guess a classroom UUID are rejected with 4003.

Group naming: ``maic_classroom_<uuid>``. Tasks call
``channel_layer.group_send(group_name, {"type": "maic.image.task", ...})``.
The consumer's ``maic_image_task`` handler forwards each event as JSON
to the connected client.

Event payload (matches the contract in the F2 task spec):
    {
      "type": "maic.image.task",
      "classroom_id": "<uuid>",
      "element_key": "<scene_idx>:<slide_idx>:<element_idx>:<element_id_or_idx-N>",
      "status": "pending" | "generating" | "done" | "failed",
      "src": "<url>",          # only when status == "done"
      "error_code": "...",     # only when status == "failed"
      "updated_at": "<iso8601>"
    }
"""

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


def maic_classroom_group_name(classroom_id) -> str:
    """Return the channel-layer group name for a classroom.

    Single source of truth so producers (Celery tasks) and consumers
    (this module) cannot drift out of sync.
    """
    return f"maic_classroom_{classroom_id}"


class MAICClassroomConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for MAIC classroom-scoped real-time events.

    Currently emits per-element image-task state via the
    ``maic.image.task`` channel-layer message type. Designed to host
    future scoped-to-this-classroom events without requiring a second
    socket per page (e.g. F3 scene-ready milestones).
    """

    async def connect(self):
        self.user = self.scope.get("user", AnonymousUser())
        if self.user.is_anonymous:
            logger.warning("MAIC ws: rejected anonymous connection")
            await self.close(code=4001)
            return

        self.classroom_id = self.scope["url_route"]["kwargs"]["classroom_id"]

        # Visibility check — defer to the canonical helper so the rules
        # stay in sync with the GET endpoint.
        if not await self._user_can_view_classroom(
            self.user,
            self.classroom_id,
        ):
            logger.info(
                "MAIC ws: user=%s denied access to classroom=%s",
                self.user.id,
                self.classroom_id,
            )
            await self.close(code=4003)
            return

        self.group_name = maic_classroom_group_name(self.classroom_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # Echo back the JWT subprotocol exactly like the notifications
        # consumer does — required by the WebSocket spec for handshake.
        accepted_subprotocol = self.scope.get("accepted_subprotocol")
        await self.accept(subprotocol=accepted_subprotocol)
        logger.info(
            "MAIC ws: connected user=%s classroom=%s",
            self.user.id,
            self.classroom_id,
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def receive_json(self, content):
        """Minimal client → server contract.

        We only support a ping/pong heartbeat right now. The image-task
        store is server-authoritative — clients never push transitions.
        """
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def maic_image_task(self, event):
        """Channel-layer handler for ``{"type": "maic.image.task", ...}``.

        Strips the internal ``type`` key (which Channels uses to dispatch
        the handler), then forwards every other field plus the standard
        ``"type": "maic.image.task"`` shape to the WebSocket client.
        """
        # Use a fresh dict so we don't mutate the channel-layer event
        # (which other consumers in the same group also receive).
        payload = {k: v for k, v in event.items() if k != "type"}
        payload["type"] = "maic.image.task"
        await self.send_json(payload)

    # ─── DB helpers ────────────────────────────────────────────────────

    @database_sync_to_async
    def _user_can_view_classroom(self, user, classroom_id) -> bool:
        """Return True iff *user* may view *classroom_id*.

        Defers to ``maic_views._can_view_classroom`` — the canonical
        gate shared with the HTTP path. See WAVE-F2-F1 for the
        tightening rationale (peer teachers in the same tenant must
        NOT be able to subscribe to image-task events for classrooms
        they did not create).
        """
        from apps.courses.maic_models import MAICClassroom
        from apps.courses.maic_views import _can_view_classroom

        try:
            classroom = MAICClassroom.all_objects.get(pk=classroom_id)
        except MAICClassroom.DoesNotExist:
            return False

        return bool(_can_view_classroom(user, classroom))
