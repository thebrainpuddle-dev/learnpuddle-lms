# FE-019 Review Request — Translation Follow-ups: Collapse Publish Duplicate + Thread contentId

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-21
**Tasks:** TASK-064b-M1 + TASK-064-L1

---

## Summary

Two follow-up cleanups to the TASK-064 Translation UI, completing items
raised in the TASK-064b review:

1. **TASK-064b-M1** — Collapse the duplicated publish flow: move all
   publish logic into `translationStore.publishTranslation()` so the
   component uses the return value instead of maintaining its own inline
   copy.

2. **TASK-064-L1** — Thread `contentId` through `TranslatePage` by
   fetching the full course after job creation, flattening all
   `modules[].contents[]` into `allContents`, and rendering:
   - If `allContents.length > 1` → collapsible `ContentReviewCard`
     per content item (first card open by default).
   - If `allContents.length <= 1` → single `<TranslationReview
     contentId={allContents[0]?.id}>` (publish button now reachable
     for single-content courses).

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/stores/translationStore.ts` | `publishTranslation` action now returns `{ rows_published, skipped } \| null` so callers can render a result banner without a second store call |
| `frontend/src/pages/admin/translation/TranslationReview.tsx` | Removed 25-line inline `handlePublish` duplicate; now calls `publishTranslation(contentId, activeLocale, toast)` from store and uses return value to set local `publishBanner` state |
| `frontend/src/pages/admin/translation/TranslatePage.tsx` | Added `fetchCourse` call after job creation; new local `ContentReviewCard` component (toggle header + `defaultOpen` + lazy `TranslationReview` body); multi-content fanout vs single-content fallback |
| `frontend/src/pages/admin/translation/__tests__/translation.test.tsx` | Added `fetchCourse` mock, `makeMockCourse` helper, updated Test 4 to mock `fetchCourse`, added Test 18 (course with 2 contents → 2 independent cards → clicking one's Publish doesn't affect the other) |

---

## TASK-064b-M1 Detail

### Before

`TranslationReview.tsx` had its own 25-line `handlePublish` function that:
1. Checked `publishState[pubKey]` locally
2. Called `translationService.publishTranslation()` directly
3. Showed toasts inline
4. Set `publishState` via a separate `set()` in the store

...duplicating exactly the same logic that lived in `translationStore.publishTranslation`.

### After

```tsx
const handlePublish = async () => {
  if (!contentId) return;
  const pubKey = `${contentId}:${activeLocale}`;
  if (publishState[pubKey] === 'publishing') return;

  setPublishBanner(null);
  const result = await publishTranslation(contentId, activeLocale, toast);
  if (result) {
    setPublishBanner({ rowsPublished: result.rows_published, skipped: result.skipped });
  }
};
```

Store action now returns `{ rows_published, skipped } | null`.
All toast logic, publishState transitions, and error handling live in the store.

---

## TASK-064-L1 Detail

`TranslatePage` previously rendered a single `<TranslationReview>` without
a `contentId` prop after job creation — the publish button was unreachable
because `contentId` was undefined.

### New flow

```tsx
// After job creation + course fetch:
const allContents = course?.modules.flatMap(m => m.contents) ?? [];

if (allContents.length > 1) {
  return allContents.map((content, idx) => (
    <ContentReviewCard
      key={content.id}
      content={content}
      courseId={courseId}
      jobId={jobId}
      targetLanguages={targetLanguages}
      onRetry={handleRetry}
      defaultOpen={idx === 0}  // first card expanded
    />
  ));
}

// Single content or fetch failed:
return (
  <TranslationReview
    courseId={courseId}
    jobId={jobId}
    targetLanguages={targetLanguages}
    onRetry={handleRetry}
    contentId={allContents[0]?.id}  // now threaded through
  />
);
```

`ContentReviewCard` is a local (file-scoped) collapsible wrapper component
with a chevron toggle, accessible `focus:ring`, and `data-testid` on both
the card container and the toggle button.

---

## Test Coverage

**Test 18** (new): "renders two collapsible cards and each has an independent Publish button"
- Mocks `fetchCourse` to return a course with 2 content items
- Asserts 2 `content-review-card-*` containers render
- Expands card 1, clicks its Publish button → `publishTranslation` called with `contentId1`
- Expands card 2, clicks its Publish button → `publishTranslation` called with `contentId2`
- Confirms the two publish calls are independent (no shared state leak)

---

## Verification

```
npx vitest run src/pages/admin/translation/__tests__/translation.test.tsx
→ 22 passed (22)

npx tsc --noEmit
→ 0 errors
```

---

## Minor note

Test 18 generates two `act()` warnings from async state updates inside
`TranslationReview` (the polling useEffect). These are pre-existing
(same pattern as Test 4 and Test 5 before this change) and are not caused
by the new code. The tests themselves pass clean.

— frontend-engineer
