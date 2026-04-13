# TASK-004: Implement React.lazy Code Splitting

**Priority:** P1 (Performance)
**Phase:** 1
**Status:** done
**Assigned:** frontend-engineer
**Estimated:** 2-3 hours

## Problem

In `frontend/src/App.tsx`, all 40+ page components are statically imported. This means the entire application bundle is loaded on initial page load, causing slow TTI (Time to Interactive) especially on mobile/slow connections.

```typescript
// Current: ALL pages loaded upfront
import { LoginPage } from './pages/auth/LoginPage';
import { SuperAdminLoginPage } from './pages/auth/SuperAdminLoginPage';
// ... 40+ more static imports
```

## Fix Required

1. Replace static imports with `React.lazy()` for route-level code splitting
2. Add `<Suspense>` boundaries with loading fallbacks
3. Group by role/feature for optimal chunk sizes:
   - Auth pages (login, register, forgot password)
   - Admin pages
   - Teacher pages
   - Super Admin pages
4. Add per-page `ErrorBoundary` components

## Implementation Pattern

```typescript
// Route-level code splitting
const LoginPage = React.lazy(() => import('./pages/auth/LoginPage'));
const DashboardPage = React.lazy(() => import('./pages/admin/DashboardPage'));

// In router:
<Suspense fallback={<PageLoader />}>
  <Route path="/login" element={<LoginPage />} />
</Suspense>
```

## Files to Modify

- `frontend/src/App.tsx` — Replace static imports with `React.lazy()`
- `frontend/src/components/PageLoader.tsx` — Create loading fallback component
- `frontend/src/components/ErrorBoundary.tsx` — Create error boundary (if not exists)
- Page components may need `export default` added (React.lazy requires default exports)

## Considerations

- Verify each page component has a `default` export (or add one)
- Auth pages (login) could stay static since they're the entry point
- Use named chunk comments for debugging: `import(/* webpackChunkName: "admin" */ ...)`
- With Vite, chunks are automatic — but `manualChunks` in vite.config can optimize grouping

## Acceptance Criteria

- [ ] All non-auth pages use `React.lazy()`
- [ ] `<Suspense>` boundaries with loading indicator
- [ ] Bundle split into role-based chunks (admin, teacher, super-admin)
- [ ] No visual regressions
- [ ] Build succeeds: `npm run build`
- [ ] Lighthouse Performance score improves
