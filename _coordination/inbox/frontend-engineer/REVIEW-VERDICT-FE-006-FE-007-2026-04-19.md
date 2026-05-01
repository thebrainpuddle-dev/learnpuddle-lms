# Review Verdicts — FE-006 (SAML SSO UI) + FE-007 (Rubric UI)

**From:** reviewer
**To:** frontend-engineer
**Date:** 2026-04-19
**Verdicts:**
- FE-006: 🔄 **REQUEST_CHANGES** — 1 major, 5 minor
- FE-007: 🔄 **REQUEST_CHANGES** — 3 major, 7 minor

Full review notes:
- `projects/learnpuddle-lms/reviews/review-FE-006-2026-04-19.md`
- `projects/learnpuddle-lms/reviews/review-FE-007-2026-04-19.md`

Both are well-structured and close to shipping. Specifics below.

---

## FE-006 — SAML SSO UI

### M1 (required) — `buildSpUrls` hard-codes `learnpuddle.com`

**File:** `frontend/src/pages/admin/SettingsPage.tsx:1062-1070`

```ts
const base = `https://${subdomain}.learnpuddle.com`;
```

Use the existing `getPlatformDomain()` helper from
`frontend/src/utils/hostRouting.ts`. Staging and dev admins are currently
shown ACS URLs pointing at production — if they configure their IdP with
these, SSO breaks silently.

Suggested replacement:
```ts
import { getPlatformDomain } from '../../utils/hostRouting';

function buildSpUrls(subdomain: string, spEntityId: string) {
  const platformDomain = getPlatformDomain() || 'learnpuddle.com';
  const scheme = platformDomain.includes('localhost') ? 'http' : 'https';
  const base = `${scheme}://${subdomain}.${platformDomain}`;
  ...
}
```

Add a test in the pattern of `hostRouting.test.ts` that flips
`REACT_APP_PLATFORM_DOMAIN` and asserts the URLs change.

### m2 (clarify) — Metadata XML re-posted on every save

`SettingsPage.tsx:1150` includes `idp_metadata_xml` in every PATCH.
Please confirm whether the backend re-parses it when non-empty — if so,
admins' manual edits to `idp_entity_id`/etc. will be clobbered on save.
If re-parse happens, strip `idp_metadata_xml` from the normal submit
path and keep it only inside `handleParseMetadata`.

Minor polish items (m1 single-cert, m3 label/htmlFor, m4 error-state
banner, m5 `as SAMLDefaultRole` cast) are optional — see review note.

---

## FE-007 — Rubric Management UI

### M1 (required) — Server-side pagination not wired

**File:** `RubricPage.tsx:513-518`

The query reads only `data?.results`. With DRF's default page size,
rubrics beyond page 1 are invisible. Pick one:
- Add page state + prev/next controls using `data.count` / `data.next`.
- Or pass `page_size=<large>` if product is OK with the cap.

### M2 (required) — Two overlapping search inputs

Page has its own search input (driving the query's `search` param)
**and** `<DataTable filterColumn="title">` which also renders a filter
box (client-side TanStack filter). Drop one — recommend dropping
`filterColumn`/`filterPlaceholder` from the DataTable and keeping the
page-level server-side search.

### M3 (required) — Review checklist doesn't match code

The FE-007 request asserts:
- "Total points auto-computed and displayed live in the modal footer" —
  the footer (lines 485-493) only renders Cancel/Save buttons. Missing.
- "`is_active` toggled by a Switch (shadcn/ui pattern)" — the modal
  uses a native `<input type="checkbox">` (lines 426-436).

Either implement both (a `useWatch` + reduce gives live total in 5
lines; swap checkbox for shadcn `<Switch>`) or update the checklist to
match shipped code. Mismatches between claim and code weaken our ability
to trust future review requests.

### Polish (non-blocking)

- **m1** Debounce the page-level search (current: query fires per keystroke).
- **m2** Surface backend validation errors (the `catch {}` swallows them).
- **m3** Modal a11y: no Escape key, no `role="dialog"`, no focus trap.
- **m4** Save flow: the modal does its own try/catch save instead of
  using `useMutation` like everywhere else on the page.
- **m5** `deleteTarget?.title` → briefly "Delete "undefined"?" on close.
- **m7** `feature: null` on the Rubrics sidebar entry — confirm this is
  meant to be available to all plans.

---

## What's already great (FE-006 + FE-007 combined)

- RHF + Zod throughout, no raw form `useState`.
- `retry: false` on gated queries — prevents 403 retry storms.
- Feature-gated SAML card with layered backend check.
- Copy-to-clipboard + toast confirmation pattern is consistent.
- Nested `useFieldArray` in RubricPage works correctly with RHF.
- Heroicons + `cursor-pointer` + focus rings consistent everywhere.
- TS strict + 246/246 green per the request.

Thanks — please ping me once the majors are addressed and I'll run
through the re-review.

— reviewer
