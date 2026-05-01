# Review Request: FE-087 / FE-088

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-29
**Priority:** Normal

---

## Summary

Two final test suites completing coverage for all previously-untested student pages. Both files written and verified passing.

---

## Files changed

| File | Tests | Description |
|------|-------|-------------|
| `frontend/src/pages/student/DiscussionThreadPage.test.tsx` | 41 | Thread view: replies, edit/delete/like, subscribe, reply input |
| `frontend/src/pages/student/CourseViewPage.test.tsx` | 28 | Course split-pane: sidebar, ContentPlayer, auto-select, completion |

**Total: 69 tests**

---

## Coverage highlights

### FE-087 — Student DiscussionThreadPage (41 tests)

- **Loading**: `tp-skeleton` divs present; `h1` absent during fetch
- **Not found**: `{ data: null }` → "Thread not found" text + description
- **Back button**: rendered + `navigate('/student/discussions')` called
- **Thread header**: `h1` title, body text, `open` badge, author name, view count + reply count
- **Course/content labels**: shown when set, hidden when null
- **Subscribe**: "Subscribe" vs "Subscribed" label, `api.post` called on click
- **Replies heading**: h2 + `(2)` count in parens
- **Empty replies**: "No replies yet. Be the first to respond!" when `replies: []`
- **Reply cards**: author name + body, Teacher badge (role≠STUDENT), like count (>0), `(edited)` marker
- **Reply action buttons**: Reply visible when depth < 3; Edit + Delete only for own replies (current user id match)
- **Edit flow**: textarea pre-filled with current body; Save calls `api.put`; Cancel reverts textarea + hides edit mode
- **Delete flow**: clicking Delete → ConfirmDialog opens; confirm → `api.delete`; cancel → no call
- **Reply input**: textarea + "Reply" submit shown for `status='open'`; hidden for `status='closed'`
- **Submit reply**: `api.post('/v1/student/discussions/threads/thread-1/replies/', { body })` called; textarea clears on success
- **Replying-to banner**: "Replying to {name}" shown after clicking Reply on a card; X button clears it; `parent_id` included in payload

### FE-088 — Student CourseViewPage (28 tests)

- **Loading**: spinner with `border-indigo-500` visible; course title absent
- **Back button**: `aria-label="Back to my courses"` → `navigate('/student/courses')`
- **Course title**: rendered as h1 in top bar
- **Progress text**: "{completed}/{total} completed" + "{percentage}% complete"
- **Module sidebar**: module title appears in sidebar
- **Module expand/collapse**: clicking module header shows/hides content items
- **Auto-select content**: on course load, first incomplete unlocked content selected → ContentPlayer rendered with `data-content-id`
- **Content item click**: clicking a content item updates selection → ContentPlayer shows that content
- **Locked content**: `disabled` attribute set on locked content button
- **Completed content**: `CheckCircleSolidIcon` rendered for completed content
- **Content type labels**: "Video" for VIDEO, "Reading" for DOCUMENT
- **ContentPlayer stub**: mocked via `vi.mock('../../components/teacher', ...)` — exposes `onComplete` button
- **"Select an item to begin"**: shown when no selectable content (empty module)
- **ChatWidget**: `data-testid="chat-widget"` present when courseId set
- **Sidebar toggle**: "Toggle course rail" button in DOM; click opens sidebar (JSDOM matchMedia=false → starts closed)
- **Close sidebar**: "Close course rail" button; click closes sidebar
- **handleComplete**: "Mark Complete" (stub button) → `studentService.completeContent(contentId)` called
- **handleComplete error**: `completeContent` rejects → `toast.error('Content Locked', errorMessage)` fired
- **Completion % display**: `{Math.round(percentage)}%` visible in top bar
- **Module lock_reason**: `lock_reason` text shown under locked module title

---

## Notes for reviewer

- `DiscussionThreadPage` uses `api` directly (no useMutation for likes — `handleLikeToggle` calls `api.post/delete` imperatively). `subscribeMutation`, `replyMutation`, `editReplyMutation`, `deleteReplyMutation` all use TanStack mutations.
- `useAuthStore` mock uses `mockImplementation((selector) => selector({ user: { id: 'user-1' } }))` pattern to handle the Zustand selector correctly.
- `CourseViewPage` uses `ToastProvider` wrapper (uses `useToast()`).
- `ContentPlayer`, `ChatWidget`, `CompletionRing` all mocked via `vi.mock()` to isolate page-level logic.
- JSDOM: `window.matchMedia('(min-width: 1024px)').matches` returns `false`, so sidebar starts closed. Tests account for this.
- Both files follow `staleTime: Infinity + refetchOnWindowFocus: false + retry: false + vi.resetAllMocks()` established pattern.

---

## Session completion note

With FE-087 and FE-088 done, **all student page test suites are now written**:

| Pages covered | Test files |
|---|---|
| Student (16 pages) | DashboardPage, CourseListPage, CourseViewPage, AssignmentsPage, QuizPage, AttendancePage, AchievementsPage, ProfilePage, SettingsPage, DiscussionPage, DiscussionThreadPage, StudyNotesPage, StudentChatbotsPage, StudentChatPage, MAICBrowsePage, StudentMAICCreatePage |
| SuperAdmin (3 pages) | DashboardPage, SchoolsPage, DemoBookingsPage |

— frontend-engineer
