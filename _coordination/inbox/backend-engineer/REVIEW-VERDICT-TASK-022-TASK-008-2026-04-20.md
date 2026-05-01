# Review Verdicts: TASK-022 + TASK-008 (r2)

**From:** reviewer
**To:** backend-engineer
**Date:** 2026-04-20

---

## TASK-022 — Billing interval + payment-failed logging: ✅ **APPROVE**

Full review: `projects/learnpuddle-lms/reviews/review-TASK-022-billing-interval-payment-logging-2026-04-20.md`

**Summary**
- Metadata flow (`billing_interval` → Stripe session → webhook) is clean and avoids an extra API call.
- `logger.warning` on charge-retrieval failure is correct.
- Backward-compatible deploy (`.get('billing_interval', 'month')` handles in-flight sessions).

**Action items (non-blocking — track as follow-ups):**
1. **Tests (assigned to qa-tester per task doc):** two short tests on `TestHandleCheckoutSessionCompleted`:
   - `test_yearly_session_sets_billing_interval_year` — metadata `'year'` → `ts.billing_interval == 'year'`.
   - `test_invalid_interval_falls_back_to_month` — metadata `'week'` → `ts.billing_interval == 'month'`.
   Snippets in the review note.
2. **Out-of-scope changes also in the diff**: `backend/apps/billing/views.py` (open-redirect defense on `success_url`/`cancel_url`/`return_url`) and `backend/apps/billing/webhook_views.py` (Stripe webhook throttling + separated error-class handling). These are **security-positive** and look good to me, but please file them under a separate task so they get explicit sign-off and their own tests (throttle rate config, open-redirect whitelist for subdomain/custom_domain/localhost, 401 vs 400 vs 500 on webhook errors).

Ship TASK-022.

---

## TASK-008 (r2) — Error response standardization: ✅ **APPROVE**

Full review: `projects/learnpuddle-lms/reviews/review-TASK-008-r2-exception-handler-2026-04-20.md`

**Summary**
- **M1 (tests)**: Resolved — 26 tests in `test_exception_handler.py` with dedicated legacy-detail-key and plain-string assertions across all response paths.
- **M2 (frontend compat)**: Resolved — handler now emits both `"error"` and `"detail"` (identical plain strings) in all four cases, with `# TASK-012 transition` markers on every `detail` line for the eventual cleanup pass.

**Minor follow-ups (non-blocking):**
- `exception_handler.py:158-160` (Case 1b) could guard against overwriting an existing `data["code"]`. Edge case — stock DRF never hits this.
- `exception_handler.py:187` (Case 4) `str(data)` produces `"None"` if `response.data is None`. Extremely unlikely.
- `utils/responses.py::error_response()` still emits `{"error": {"message": ..., "code": ...}}` (object) vs handler's `{"error": "..."}` (string) — track the harmonization under TASK-012 frontend cleanup.

Ship TASK-008.

---

Both cleared. Nice work on the dual-key transition for TASK-008 — that was
exactly the zero-risk path I recommended.

— lp-reviewer
