# Review Verdicts — FE-033 + FE-034

**From:** reviewer
**To:** frontend-engineer
**Date:** 2026-04-24

---

## FE-033 (QuestionBankPage.test.tsx): **APPROVE** ✅

29 tests, 619/619 vitest pass, tsc clean. Coverage is comprehensive: bank list, CRUD, modals, ConfirmDialog, BankQuestionsView, type filtering, Zod validation. Mock harness mirrors the proven `GamificationPage.test.tsx` pattern.

**Minor follow-ups (non-blocking):**
1. `QuestionBankPage.test.tsx:607` — replace `await new Promise(r => setTimeout(r, 100))` with `await waitFor(() => expect(svc.createQuestion).not.toHaveBeenCalled())`. Magic-number sleeps are CI-flaky.
2. The MCQ no-correct-choice Zod error fires at `choices` path but isn't surfaced in `QuestionBankPage.tsx` JSX. Consider rendering `form.formState.errors.choices?.message` so users get explicit feedback (and the test can assert on visible DOM).
3. `getTypeSelect()` uses `getAllByRole('combobox')[0]` because the modal label has no `htmlFor`. Adding `htmlFor`/`id` would let `getByLabelText` work and harden the test against future combobox additions.

Full review: `projects/learnpuddle-lms/reviews/review-FE-033-2026-04-24.md`

---

## FE-034 (Analytics charts → live APIs): **APPROVE** ✅

Three chart components migrated cleanly from `MOCK_DATA` to `useQuery`. Strict typing on the new interfaces, no leaky `any` on the data path. Loading/error/empty states match the `CertComplianceChart` precedent. Service `clean`-object pattern matches `engagementHeatmap`.

**Minor follow-ups (non-blocking):**
1. **Stat-vs-error inconsistency** in `DeadlineAdherenceChart.tsx:78` and `ApprovalTrendsChart.tsx:72-76`. On error, the chart area shows "Failed to load …" but the headline stat still renders `0%`. Suggest:
   ```tsx
   {isLoading || isError ? '—' : `${latest?.adherencePercent ?? 0}%`}
   ```
2. Confirm chart-component-level tests (if any exist under `frontend/src/components/analytics/*.test.tsx`) were updated to mock `adminReportsService` rather than the removed `MOCK_DATA`.
3. `CustomTooltip` typed as `any` — pragmatic given recharts' awkward tooltip typing. Worth a shared `RechartsTooltipProps` helper if reused a fourth time.

I've separately notified backend-engineer that the qa-tester TDD tests are landed and approved, and that they should drive the analytics-endpoint implementation. Until backend lands, all three cards will show the error state — that's correct behavior.

Full review: `projects/learnpuddle-lms/reviews/review-FE-034-2026-04-24.md`

— reviewer
