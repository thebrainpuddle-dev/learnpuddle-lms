---
tags: [review, task/FE-003, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-19
author: frontend-engineer
branch: maic-sprint-1-presence-rhythm
round: r2
files:
  - frontend/src/pages/admin/QuestionBankPage.tsx
  - frontend/src/components/layout/AdminSidebar.tsx
  - frontend/src/pages/admin/GradebookPage.tsx
---

# Review: FE-003 r2 — Question Bank Management UI

## Verdict: APPROVE

All previously-flagged issues (M1, M2) and the nice-to-fix items are addressed correctly. Client-side validation now mirrors backend semantics exactly. Ship it.

## Verification

### M1 — `QuestionSchema.superRefine` enforces choice-set rules
`frontend/src/pages/admin/QuestionBankPage.tsx:93-148` now:

- Bails early if `question_type` is not in `CHOICE_TYPES` (i.e. SHORT/ESSAY do not get choice validation, matching backend).
- Rejects any empty-after-trim choice text (`path: ['choices']`).
- Rejects `choices.length < 2`.
- **MCQ** / **TRUE_FALSE**: requires `correctCount === 1`.
- **MULTI**: requires `correctCount >= 2`.

Compared line-by-line against `backend/apps/progress/assessment_serializers.py:68-118` `QuestionSerializer.validate`:

| Rule | Client | Server |
|------|--------|--------|
| Non-empty choice text | `choices.some((c) => !c.text.trim())` → error | `(c.get("text") or "").strip()` truthy check |
| ≥2 choices | `choices.length < 2` → error | `len(choices) < 2` → ValidationError |
| MCQ: exactly 1 correct | `correctCount !== 1` → error | `correct_count != 1` → ValidationError |
| TRUE_FALSE: exactly 1 correct | `correctCount !== 1` → error | Same |
| MULTI: ≥2 correct | `correctCount < 2` → error | `correct_count < 2` → ValidationError |

Parity is exact. No drift paths — a form that passes client validation will pass server validation for every code path I traced.

### M2 — Typed cast replaces `as any`
`QuestionBankPage.tsx:580`:
```ts
adminQuestionBankService.listQuestions(
  bank.id,
  (typeFilter as QuestionType) || undefined,
)
```
- `typeFilter` is `string` from `<select>`. Empty string ("All types") short-circuits via `|| undefined`, so the service omits the `?type=` param. Non-empty string is narrowed to `QuestionType`. `QuestionType` union values are the only options rendered in the `<option>` list, so the cast is sound.
- No `any` in the file anymore — confirmed by grep.

### Nice-to-fix — TRUE_FALSE seeding no longer clobbers edits
`QuestionBankPage.tsx:303-316` useEffect starts with:
```ts
if (editingQuestion) return;
```
Seeding now only runs on fresh "Create" modal open when `question_type === 'TRUE_FALSE'`. Opening an existing TRUE_FALSE question where "False" is the correct answer will no longer reset it to "True."

### Nice-to-fix — Sidebar icon differentiation
`frontend/src/components/layout/AdminSidebar.tsx:73-74`:
- Gradebook → `ClipboardDocumentListIcon`
- Assessments → `TableCellsIcon`
Distinct. Visual ambiguity resolved.

### Bonus (FE-001 follow-up) — CSV formula injection hardening
`frontend/src/pages/admin/GradebookPage.tsx:60-85` `downloadCsv`:
```ts
let s = String(v).replace(/"/g, '""');          // 1. escape quotes
// ...
if (/^[=+\-@]/.test(s)) s = `'${s}`;            // 2. prefix formula triggers
return /[",\n]/.test(s) ? `"${s}"` : s;          // 3. quote-wrap if needed
```
Order of operations matches RFC 4180 + OWASP CSV-injection guidance:
- `=5+5` → `'=5+5` (no quotes needed) — opened in Excel/Sheets as literal text.
- `="evil"` → after quote-escape `="evil"` (quotes doubled inside) → prefixed `'="evil"` → wrapped `"'=""evil"""` — parsed as literal `'="evil"`, formula disarmed.
- `-cmd|calc` → `'-cmd|calc` — disarmed.
Safe.

### TypeScript
Author reports `npx tsc --noEmit` clean (0 errors). Spot-checked the cast and schema types — consistent.

## Positive Observations

- Superrefine issues all `path: ['choices']`, so errors surface at the array-level `FieldError` slot — render it (already present in the existing error renderer).
- Client + server validation parity means round-trips don't produce surprising 400s.
- No new lint-disables introduced.
- CSV fix is defensive-in-depth and tested against the classic attack vectors.

## Minor Nits (non-blocking)

- `superRefine` could short-circuit after the first "empty text" issue to avoid double-reporting, but reporting all issues at once is arguably better UX.
- Consider a unit test for `QuestionSchema` superRefine — pure function, trivial to test, would catch drift if backend rules change.

## Next Actions
- Merge; mark FE-003 `status/done`.
- Optional: add Jest cases for `QuestionSchema` in a follow-up.
