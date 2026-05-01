---
tags: [review, task/FE-024, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-23
---

# Review: FE-024 — Type-safe `adminRemindersService` (remove `any` from preview/send)

## Verdict: APPROVE

## Summary
Tight, surgical type-hardening pass on a service that sits on a
privileged (admin) surface. The new `ReminderPayload` interface models
the backend contract accurately, the response type on `send` (`sent` +
`failed`) pins the callers to the real shape, and the one call site
that needed updating (`ReportDrillDown`) is updated. Structural
compatibility with the other callers (`ManualSendSection`,
`AnalyticsPage`) verified by inspection — they already passed
payloads shaped like `ReminderPayload`.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
- **`assignment_id` is typed as plain optional** rather than a
  discriminated union keyed on `reminder_type === 'ASSIGNMENT_DUE'`.
  The author calls this out and defers explicitly. Fine for now — a
  discriminated union is a noticeable refactor at each call site and
  the backend will still reject a missing `assignment_id` on an
  ASSIGNMENT_DUE send. Log a follow-up task if the reminder type set
  stabilises.
- **`reminder_type: string`** is too loose given the backend has a
  closed enum (`COURSE_ENROLLED`, `ASSIGNMENT_DUE`, `CUSTOM`, …). A
  `ReminderType` string-literal union would let TS catch typos like
  `'CUSTOM_' + 'x'`. Nice-to-have, not a gate.
- **Pre-existing `any` in `ReportDrillDown`** at two unrelated lines
  (`onError: (error: any)` and `rows.map((r: any) => …)`) is **out of
  scope** for this PR but noted for future cleanup.

## Positive Observations
- **`teacher_ids?: string[]` is correctly optional** — the "omit = send
  to all" backend contract is preserved, and the JSDoc on that field
  captures the semantics so the next reader doesn't have to read the
  server code to learn it. This is the exact judgement call that would
  have broken `ManualSendSection` if the field had been promoted to
  required.
- **`ReminderSendResponse { sent: number; failed: number }`** is
  declared alongside the service and used to type `onSuccess` in
  `ReportDrillDown`. That immediately gives callers intellisense on
  `data.sent` / `data.failed` and removes another hidden `any`.
- **`scheduled_at` is documented as reserved** — matches the TODO
  already in `ManualSendSection`. Intentional shape parked for future
  work, not dead code.
- **JSDoc on every field of `ReminderPayload`** — unusually good for
  a frontend service module. Pays for itself the first time someone
  hovers the field in VS Code instead of reading the backend serializer.
- **No runtime behavior changes** — this is purely additive typing.
  `tsc --noEmit` reports 0 errors; full suite 548/548 per the author.
- **Other services untouched** — the author correctly resisted the urge
  to type-sweep `Record<string, any>` payloads on `adminTeachersService`
  et al. where the schema is legitimately polymorphic.

## Files Touched (verified)
- `frontend/src/services/adminRemindersService.ts` — new
  `ReminderPayload`, `ReminderSendResponse`; signatures updated. Zero
  `any` remaining in this file (grep confirmed). ✓
- `frontend/src/components/analytics/ReportDrillDown.tsx` — import of
  `type ReminderPayload`; `mutationFn: (payload: ReminderPayload) => …`. ✓
- Other callers (`ManualSendSection.tsx`, `AnalyticsPage.tsx`): no code
  change needed; their inline object literals already satisfy the new
  interface (structurally checked).

## Next Steps
- Update `status/review` → `status/done` on FE-024.
- Optional follow-up tasks:
  1. Promote `reminder_type` to a string-literal union.
  2. Discriminated union making `assignment_id` required when
     `reminder_type === 'ASSIGNMENT_DUE'`.
  3. Sweep remaining `any` in `ReportDrillDown` error handlers and row
     maps (separate task — not FE-024's job).

— lp-reviewer
