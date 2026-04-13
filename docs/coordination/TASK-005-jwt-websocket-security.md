# TASK-005: Fix JWT Token in WebSocket URL Query String

**Priority:** P1 (Security)
**Phase:** 2
**Status:** todo
**Assigned:** frontend-engineer
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

- [ ] JWT token NOT in WebSocket URL
- [ ] Authentication still works for WebSocket connections
- [ ] Token refresh handled correctly for long-lived connections
- [ ] No regression in real-time notifications
