# Review Request — FE-045 (BillingPage tests) + FE-046 (CreateTeacherPage tests)

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-27

## Summary

Two new admin-page test suites. Both verified green individually and in the full suite.

| Task | File | Tests | Status |
|------|------|-------|--------|
| FE-045 | `frontend/src/pages/admin/BillingPage.test.tsx` | 29 | ✅ ready for review |
| FE-046 | `frontend/src/pages/admin/CreateTeacherPage.test.tsx` | 20 | ✅ ready for review |

**Total new tests: 49**
**Full suite after:** 1136/1136 passed (0 regressions)

---

## FE-045 — BillingPage (29 tests)

### What's covered

- Page header (h1, subtitle)
- Payment methods banner ("We accept UPI, Credit/Debit Cards...")
- Loading spinner while API calls are pending
- Current Plan section: plan name, status badge (Active/Trial), renewal date, trial-ends label
- Usage bars: Teachers, Courses, Storage with correct counts
- "No Active Plan" empty state when getCurrentPlan rejects
- Plan comparison cards: plan names, Recommended badge, Current Plan badge, INR prices (₹4,999/mo), yearly savings %, "Contact Sales" link for custom-priced Enterprise plan, Upgrade button for regular plans
- Invoice history table: invoice number, GST breakdown, total in INR, status badge, PDF download link
- Empty invoice state ("No invoices yet.")
- Error state: role="alert" + "Failed to load billing data" when all 3 API calls fail

### Mock strategy

- `razorpayService` module-mocked entirely (`getCurrentPlan`, `getPlans`, `getInvoices`, `createOrder`, `verifyPayment`)
- `loadRazorpaySDK` mocked as `vi.fn().mockResolvedValue(undefined)`
- `window.Razorpay` stubbed as a JS class with an `open()` spy
- No `QueryClientProvider` needed (page uses useState/useEffect directly)

---

## FE-046 — CreateTeacherPage (20 tests)

### What's covered

- Page structure: heading, subtitle, all field labels
- Form field attributes: email placeholder, helper text on Password
- Required field validation (Zod): first name, email, password errors on empty submit
- Password mismatch cross-field validation (Zod `.refine()`)
- Successful submission: correct payload sent to `adminTeachersService.createTeacher()`, success toast with full teacher name, navigation to `/admin/teachers`
- Server field-level errors: DRF `{ email: ['A user with this email already exists.'] }` → inline form error + toast
- Generic error: plain Error → `toast.error('Failed to create teacher', ...)`
- Cancel button: navigates without calling service
- Loading state: Create button disabled while mutation pending
- Submit button: `type="submit"` confirmed

### Mock strategy

- `adminTeachersService.createTeacher` mocked via module mock
- `useNavigate` mocked via `importOriginal` spread pattern
- `useToast` mocked via `importOriginal` spread on `../../components/common`
- `QueryClient` with `retry: false` + `ToastProvider` wrapper

---

## No regressions

```
npx vitest run src/pages/admin/BillingPage.test.tsx    → 29/29 passed
npx vitest run src/pages/admin/CreateTeacherPage.test.tsx → 20/20 passed
npx vitest run                                          → 1136/1136 passed
```

— frontend-engineer
