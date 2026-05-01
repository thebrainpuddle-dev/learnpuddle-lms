# Re-Review Request — FE-006 (SAML SSO UI) + FE-007 (Rubric Management UI) — Round 2

**From:** frontend-engineer
**To:** reviewer
**Date:** 2026-04-19
**Re-reviews:** FE-006 r2, FE-007 r2

All required (M-level) items from your REQUEST_CHANGES verdicts are now
addressed. Details below per task.

---

## FE-006 — SAML SSO UI

### M1 resolved — `buildSpUrls` now uses `getPlatformDomain()`

Extracted the function to `frontend/src/utils/samlUrls.ts` so it is
independently testable:

```ts
// frontend/src/utils/samlUrls.ts
import { getPlatformDomain } from './hostRouting';

export function buildSpUrls(subdomain: string, spEntityId: string): SpUrls {
  const platformDomain = getPlatformDomain() || 'learnpuddle.com';
  const scheme = platformDomain.includes('localhost') ? 'http' : 'https';
  const base = `${scheme}://${subdomain}.${platformDomain}`;
  return { entityId, acsUrl, slsUrl, metadataUrl };
}
```

`SettingsPage.tsx` imports from the new utility. The inline function is gone.

**Tests** — `frontend/src/utils/samlUrls.test.ts` (6 tests, all green):
- No env var → falls back to `learnpuddle.com` with `https`
- Custom production domain (`myedtech.io`) → `https`
- `localhost` → `http` (normalizeDomain strips port, so `localhost:3000 → localhost`)
- Saved `spEntityId` is preserved; empty falls back to `saml-sp:<subdomain>`
- Env var flipped to `staging.learnpuddle.com` → all three URL bases updated

### m2 resolved — `idp_metadata_xml` stripped from normal save path

The `onSubmit` payload no longer includes `idp_metadata_xml`. It is sent
**only** in `handleParseMetadata`. Explanatory comment in the source explains
the backend's re-parse-on-non-empty behaviour and the risk of clobbering
manual edits.

---

## FE-007 — Rubric Management UI

### M1 resolved — Server-side pagination wired

Added `page` state and `debouncedSearch` state. The query:
```ts
queryKey: ['rubrics', debouncedSearch, page],
queryFn: () => adminRubricService.listRubrics({ search: debouncedSearch || undefined, page }),
```

Pagination controls shown when `totalPages > 1`:
- "Previous" / "Next" buttons (disabled at boundaries)
- "Page X of Y (N rubric/s)" count label
- `handleSaved` resets `page` to 1 on create/edit so newly created rubrics
  are always visible

`pageSize = 10` constant matches the backend `PAGE_SIZE`.

### M2 resolved — Duplicate search inputs eliminated

Removed `filterColumn="title"` and `filterPlaceholder` from the `<DataTable>`
call. The DataTable now renders with `hideFilter hidePagination` — the only
search control is the page-level `<input type="search">` driving the
server-side query parameter.

### M3 resolved — Both checklist claims now match the code

**(a) Live total points in modal footer:**
```ts
const watchedCriteria = useWatch({ control, name: 'criteria' });
const totalPoints = (watchedCriteria ?? []).reduce(
  (sum, c) => sum + (Number(c?.max_points) || 0), 0
);
```
Footer now renders:
```
Total: <N> pts | [ Cancel ] [ Save changes ]
```
Updates as the user edits any criterion's `max_points`.

**(b) `is_active` now uses shadcn `<Switch>` via `Controller`:**
```tsx
<Controller
  control={control}
  name="is_active"
  render={({ field }) => (
    <Switch id="is_active" checked={field.value} onCheckedChange={field.onChange} />
  )}
/>
```

---

## Polish items addressed

- **m1 (debounce)**: 300 ms `useEffect+setTimeout` debounce on the
  page-level search; also resets `page` to 1 on term change.
- **m5 (delete title flash)**: Added `deleteTitle` state captured at
  button-click time. `ConfirmDialog` receives `title={\`Delete "${deleteTitle}"?\`}`
  — title never becomes "undefined" during the close render.

---

## Verification

```
npx tsc --noEmit   → exit 0, 0 errors
npx vitest run     → Test Files 34 passed (34) / Tests 252 passed (252)
```

(34 files = 33 prior + `samlUrls.test.ts`; 252 = 246 prior + 6 new samlUrls tests)

---

## Non-blocking items from your review (deferred)

- **FE-006 m1** (single-cert display), **m3** (label/htmlFor), **m4**
  (error-state banner), **m5** (`as SAMLDefaultRole` cast) — all optional
  polish per your review. Not addressed in this round.
- **FE-007 m2** (surface backend validation errors in catch), **m3**
  (modal a11y — Escape key, role="dialog", focus trap), **m4** (useMutation
  in modal save flow), **m7** (`feature: null` on Rubrics nav entry) —
  deferred as non-blocking. Will pick up in a follow-up pass.

Ping me when you've had a chance to re-review. Happy to address any
remaining items.

— frontend-engineer

## Processed 2026-04-19

Both reviewed — **APPROVE** on both. Verdict + notes:
- `projects/learnpuddle-lms/reviews/review-FE-006-r2-2026-04-19.md`
- `projects/learnpuddle-lms/reviews/review-FE-007-r2-2026-04-19.md`
- Author notified: `_coordination/inbox/frontend-engineer/REVIEW-VERDICT-FE-006-007-r2-2026-04-19.md`
