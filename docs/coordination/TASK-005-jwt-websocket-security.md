# TASK-005: Fix JWT Token in WebSocket URL Query String

**Priority:** P1 (Security)
**Phase:** 2
**Status:** done
**Assigned:** backend-security
**Estimated:** 1-2 hours

## Problem

In `frontend/src/hooks/useNotifications.ts` (line ~121), the JWT access token is passed in the WebSocket URL query string:

```typescript
const wsUrl = `${WS_BASE_URL}/ws/notifications/?token=${accessToken}`;
```

**Security Risk:** Tokens in URLs are visible in:
- Browser history
- Server/proxy access logs
- Referer headers
- Network monitoring tools

## Fix Required

Move JWT authentication to the WebSocket subprotocol or first-message pattern:

### Option A: Subprotocol (Preferred)
```typescript
const ws = new WebSocket(wsUrl, [`Bearer.${accessToken}`]);
```

Backend (`consumers.py`):
```python
async def connect(self):
    token = self.scope.get("subprotocols", [None])[0]
    if token and token.startswith("Bearer."):
        jwt = token[7:]
        # Validate JWT and get user
```

### Option B: First-message auth
```typescript
const ws = new WebSocket(wsUrl);
ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token: accessToken }));
```

## Files to Modify

- `frontend/src/hooks/useNotifications.ts` — Remove token from URL
- `backend/apps/notifications/consumers.py` — Accept token from subprotocol/message
- `backend/apps/notifications/routing.py` — May need middleware changes

## Acceptance Criteria

- [x] JWT token NOT in WebSocket URL
- [x] Authentication still works for WebSocket connections
- [x] Token refresh handled correctly for long-lived connections
- [x] No regression in real-time notifications

## Implementation Notes (2026-04-20)

- Chose **Option A: Subprotocol** (`Sec-WebSocket-Protocol: Bearer.<jwt>`).
- Frontend (`frontend/src/hooks/useNotifications.ts`): removed `?token=` from
  the WS URL; JWT now passed as the second argument to `new WebSocket(url, [...])`.
- Backend middleware (`backend/apps/notifications/middleware.py`): reads
  `scope["subprotocols"]`, picks the first entry that starts with `Bearer.`,
  extracts the JWT, validates via SimpleJWT, sets `scope["user"]` and
  `scope["accepted_subprotocol"]`. Non-Bearer subprotocols are ignored.
- Backend consumer (`backend/apps/notifications/consumers.py`): calls
  `await self.accept(subprotocol=scope["accepted_subprotocol"])`, which the
  WebSocket spec requires so the browser confirms the handshake.
- Query-string tokens are **not** accepted — hard cut, no backward
  compatibility. Old clients reconnect after a single refresh because the
  React app is shipped together.
- Token refresh: long-lived connections naturally cycle because `onclose`
  with code != 1000/4001 triggers reconnect, and the hook reads the
  latest `accessToken` from `useAuthStore` on each `connect()`.
- Tests added: `backend/apps/notifications/tests_websocket_auth.py` — covers
  valid/invalid/missing subprotocols, rejects query-string tokens (regression
  guard), and verifies the consumer echoes the Bearer subprotocol back.

## Review (2026-04-20)

**Verdict: APPROVE**

### Note on task-spec drift
The spec pointed at worktree `.claude/worktrees/agent-a76b067d` (branch
`worktree-agent-a76b067d`), which does not exist on disk. The actual
implementation lives in the current branch `maic-sprint-1-presence-rhythm`:
middleware/consumer/hook changes are already committed; the new test file
`backend/apps/notifications/tests_websocket_auth.py` is currently untracked
(needs `git add`). Review proceeded against those files.

### Acceptance criteria
- [x] JWT token NOT in WebSocket URL — `useNotifications.ts` builds
  `${WS_BASE_URL}/ws/notifications/` with no query string, and passes the
  token as the second `WebSocket(url, [...])` arg (`Bearer.<jwt>`).
- [x] Subprotocol echoed back — `consumers.py::connect()` calls
  `self.accept(subprotocol=self.scope.get("accepted_subprotocol"))`,
  satisfying the WebSocket handshake requirement.
- [x] SimpleJWT validation invoked — `middleware.py::get_user_from_token()`
  constructs `AccessToken(token_str)` and resolves the `user_id` claim;
  `User.DoesNotExist`, `InvalidToken`, and `TokenError` all map to
  `AnonymousUser`.
- [x] Tests cover happy path + invalid token + missing subprotocol +
  query-string regression guard + full consumer handshake (echoes
  subprotocol, rejects anonymous with close code 4001).
- [x] Middleware wired in `backend/config/asgi.py`.
- [x] No fallback code path reads `scope["query_string"]` for a token —
  explicitly asserted by `test_middleware_does_not_read_query_string_token`.

### Positive notes
- Token leakage vectors (history, logs, referer) eliminated cleanly.
- Middleware uses `database_sync_to_async` correctly; `select_related`
  avoids an extra query for `tenant`.
- `is_active=True` filter on user lookup is a nice hardening extra.

### Minor (non-blocking)
- `tests_websocket_auth.py` is untracked — owner should `git add` it before
  the next commit so CI actually runs it.
- `BEARER_PREFIX = "Bearer."` — the trailing dot is load-bearing; a short
  code comment near `BEARER_PREFIX` reiterating *why* (avoid colliding with
  a future `Bearer` subprotocol name) would help the next reader.

Marking `Status: done`.
