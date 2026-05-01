# FE-020 Review Request — CommandPalette Teacher + Group Search

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-21
**Task:** FE-020 — Extend CommandPalette (⌘K) with teacher and group search

---

## Context

The admin Command Palette (`src/components/shared/CommandPalette.tsx`) previously
searched courses and content via `/api/v1/courses/search/`. Two `// TODO` comments
were left for teacher and group search. This PR resolves both.

---

## Changes

### `CommandPalette.tsx`

1. **New response types** — `TeacherSearchResponse`, `GroupSearchResponse`

2. **`fetchTeacherResults(query)`** — `GET /api/admin/teachers/?search=...&is_active=true&page_size=5`
   - Fires when `debouncedQuery.length >= 2`
   - Normalises paginated (`{ results: [] }`) vs plain array responses
   - Maps to `SearchResult` with:
     - `title`: `fullName || email` (email fallback for accounts with no name set)
     - `subtitle`: `designation · department` (if both set) or email (only when
       fullName is the title — prevents identical title/subtitle duplication)
     - `href`: `/admin/teachers`
     - `category`: `'teacher'` → appears under **Teachers** section header

3. **`fetchGroupResults()`** — `GET /api/teacher-groups/?page_size=50`
   - Fires once when palette opens (`staleTime: 60_000`)
   - Groups are filtered **client-side** by name/description match
   - Max 5 shown per query
   - `href`: `/admin/groups`
   - `category`: `'group'` → appears under **Groups** section header

4. **Loading state** — `isLoading` is now `isLoadingCourses || isLoadingTeachers`
   so the spinner shows when either API is in flight.

5. **Dependencies** — `allResults` useMemo now includes `teacherResults` and
   `groupResults` in its deps array.

---

### `CommandPalette.test.tsx` (NEW — 15 tests)

| Suite | Tests | What's covered |
|-------|-------|----------------|
| basic | 5 | Input renders, closed state, Escape closes, backdrop closes, default pages shown |
| course search | 2 | Course results from API, navigation to edit page |
| teacher search | 4 | Teacher name+subtitle shown, navigate to /admin/teachers, "Teachers" header, email-only fallback |
| group search | 3 | Client-side filter, navigate to /admin/groups, "Groups" header |
| empty state | 1 | "No results found" when query has no matches |

---

### `TranslationReview.tsx` (minor)

Updated the `contentId` prop JSDoc to remove the stale `TODO TASK-064 L1` comment
(the work was completed in the previous session).

---

## API details

**Teachers:**
- Endpoint: `GET /api/admin/teachers/` (existing endpoint)
- Params: `search`, `is_active=true`, `page_size=5`
- Response shape: `{ results: [{id, first_name, last_name, email, designation, department}] }`

**Groups:**
- Endpoint: `GET /api/teacher-groups/` (existing endpoint; no `search` param server-side)
- Params: `page_size=50`
- Response shape: `{ results: [{id, name, description, group_type}] }`
- Filtering: client-side (`name.includes(q)` or `description.includes(q)`)

---

## Verification

```
npx tsc --noEmit
→ 0 errors

npx vitest run
→ 530 tests / 61 files — all passing
  (was 515/60 before this PR — added 15 CommandPalette tests + 1 translation test
  from FE-019 = 16 new tests, minus previous baseline delta)
```

---

## Non-blocking notes

1. Groups don't have a server-side search endpoint. Client-side filtering on up to
   50 groups is fast and avoids latency. If groups grow to hundreds, a server search
   param should be added to `/teacher-groups/`.

2. Teacher results navigate to `/admin/teachers` (list page) since there's no
   `/admin/teachers/:id` detail route. If a detail page is added later, the `href`
   can be updated to `/admin/teachers/${teacher.id}`.

— frontend-engineer
