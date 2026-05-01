# FE-024 Review Request — Type-safe adminRemindersService (remove any from preview/send)

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-22
**Task:** FE-024 — Remove `any` from `adminRemindersService.preview` and `.send` signatures

---

## Context

`adminRemindersService.ts` had two loosely-typed method signatures:
```typescript
// Before
async preview(payload: any): Promise<ReminderPreviewResponse>
async send(payload: any): Promise<any>
```

The `any` types suppressed TypeScript's ability to catch mismatches between callers and the
API layer. Now that `@typescript-eslint/parser` is installed (FE-023), these surfaces show
up as exploitable gaps — a badly-shaped payload silently compiles.

---

## Changes

### `frontend/src/services/adminRemindersService.ts`

Added two new exported interfaces and updated both method signatures:

```typescript
/** Payload accepted by both /reminders/preview/ and /reminders/send/. */
export interface ReminderPayload {
  reminder_type: string;
  /**
   * Target teacher IDs. Omit (or pass undefined) to target all eligible
   * teachers — the backend interprets a missing field as "send to everyone".
   */
  teacher_ids?: string[];
  subject?: string;
  message?: string;
  /** Required when reminder_type is "ASSIGNMENT_DUE". */
  assignment_id?: string;
  /** ISO-8601 datetime; reserved for scheduled send (backend support pending). */
  scheduled_at?: string;
}

/** Response returned by /reminders/send/. */
export interface ReminderSendResponse {
  sent: number;
  failed: number;
}

// Updated signatures:
async preview(payload: ReminderPayload): Promise<ReminderPreviewResponse>
async send(payload: ReminderPayload): Promise<ReminderSendResponse>
```

**Key decisions:**
- `teacher_ids` is optional (`string[] | undefined`) — `ManualSendSection` passes `undefined`
  when no teachers are selected, relying on the backend's "omit = send to all" semantics.
  If made required, existing callers would fail.
- `scheduled_at` documented as reserved for a future backend pass (referenced in the
  `ManualSendSection` TODO comment already in the codebase).
- No `assignment_id` validation (e.g. "required when ASSIGNMENT_DUE") — that would need a
  discriminated union. Added as a plain optional for now; enough to document the field.

### `frontend/src/components/analytics/ReportDrillDown.tsx`

```typescript
// Before
import { adminRemindersService } from '../../services/adminRemindersService';
const sendReminderMutation = useMutation({
  mutationFn: (payload: any) => adminRemindersService.send(payload),
  ...
});

// After
import { adminRemindersService, type ReminderPayload } from '../../services/adminRemindersService';
const sendReminderMutation = useMutation({
  mutationFn: (payload: ReminderPayload) => adminRemindersService.send(payload),
  ...
});
```

---

## Verification

| Check | Result |
|-------|--------|
| `tsc --noEmit` | ✅ 0 errors |
| `npm test` (548 tests) | ✅ 548/548 passed |
| All three call-sites compile without cast | ✅ ManualSendSection, ReportDrillDown, AnalyticsPage |

---

## Non-breaking notes

- `adminTeachersService` and other services with `Record<string, any>` are untouched —
  those are legitimately polymorphic (metadata blobs, admin action payloads). Typed
  separately if/when their schemas stabilise.
- The `ReminderSendResponse` type caught that `ReportDrillDown`'s `onSuccess` references
  `data.sent` and `data.failed` — these now match the declared interface, confirming the
  backend contract is correct.

— frontend-engineer
