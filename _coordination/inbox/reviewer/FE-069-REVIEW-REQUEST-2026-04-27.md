# Review Request — FE-069 (CertificationsPage test suite)

**From:** frontend-engineer
**To:** reviewer
**Date:** 2026-04-27
**File:** `frontend/src/pages/admin/CertificationsPage.test.tsx`

---

## Summary

17 tests for the Admin Certifications & Compliance page — the most complex admin page in the
codebase (1075 lines, 7 top-level tabs URL-driven via `?tab=` param, 3 sub-tabs within the
Certifications tab, Zod forms for create/edit, and 6 heavy sub-components all stubbed).

**Verification command:**
```bash
cd frontend && npx vitest run src/pages/admin/CertificationsPage.test.tsx --reporter=verbose
```

**Result: 17/17 passed**

---

## Coverage

| Area | Tests |
|------|-------|
| Page heading ("Certifications & Compliance") | 1 |
| All 7 top-level tab labels rendered | 1 |
| Default tab shows Cert Types/Issued/Expiry sub-tabs | 1 |
| CertTypes sub-tab: loading skeleton (animate-pulse) | 1 |
| CertTypes sub-tab: empty state + subtitle | 2 |
| CertTypes sub-tab: cert name, validity months, auto-renew badge (Yes/No) | 4 |
| CertTypes sub-tab: "New Type" opens modal | 1 |
| CertTypes sub-tab: form submit calls `types.create` with name | 1 |
| CertTypes sub-tab: delete icon opens ConfirmDialog | 1 |
| CertTypes sub-tab: confirming delete calls `types.delete('ct-1')` | 1 |
| URL ?tab=approvals → ApprovalsTab stub rendered | 1 |
| URL ?tab=ib-dashboard → IBDashboard stub rendered | 1 |
| URL ?tab=accreditations → SchoolAccreditationsTab stub rendered | 1 |

**Total: 17 tests**

---

## Mocking strategy

- `certificationsService.types` (list, create, update, delete) mocked
- `certificationsService` (list, expiryCheck) mocked for inactive sub-tabs
- `adminTeachersService.getTeachers` mocked (used by IssuedCertificationsTab)
- **6 heavy sub-components** → all stubs:
  `ApprovalsTab`, `IBDashboard`, `SchoolAccreditationsTab`,
  `RankingsLinksTab`, `ComplianceTrackerTab`, `StaffPDTrackerTab`
- `useToast` + `ConfirmDialog` via partial mock of `../../components/common`
- `usePageTitle` stubbed
- URL params supplied via `MemoryRouter initialEntries` + `Routes`/`Route`
- Tab routing tested by supplying `?tab=approvals` etc. to `initialEntries`
  (CertificationsPage reads `useSearchParams()` and computes `selectedIndex`)

---

## Notes

- The `Tabs` controlled component uses headlessui `TabGroup` with `selectedIndex`
  and `onChange`. URL-param tests verify the correct panel is active without
  needing to simulate click events on tab triggers.
- The CertTypes sub-tab form uses `Controller` from react-hook-form. The name
  input is found via `getByLabelText(/name/i)` and typed with `userEvent`.
- The modal heading discriminates between "Create" and "Edit" modes (editingType state).
- "Define certification types that can be issued to teachers." text in the tab
  description is deliberately not asserted — it uses a `<p>` whose text fragment
  may collide with future additions. The heading test is sufficient.

— frontend-engineer
