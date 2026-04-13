# TASK-012: Frontend Code Cleanup

**Priority:** P2 (Code Quality)
**Phase:** 2
**Status:** todo
**Assigned:** frontend-engineer
**Estimated:** 2-3 hours

## Problem

Several code quality issues remain in the frontend:

### 1. Remaining console.log (1 instance)
- Need to find and remove the last `console.log` statement

### 2. Toast System (replace any remaining alert() calls)
- While `alert()` calls are currently zero, the codebase needs a proper toast/notification system for future use
- Recommended: sonner (lightweight) or react-hot-toast

### 3. Form Validation Library
- Forms currently use manual `useState` validation
- Need React Hook Form + Zod for type-safe validation
- Priority forms: Login, Registration, Course Editor, Teacher Bulk Import

## Fix Required

### Phase A: Quick Cleanup (30 min)
1. Remove remaining console.log
2. Audit for any `window.confirm()` or `window.prompt()` calls

### Phase B: Toast System (1 hour)
1. Install `sonner` or `react-hot-toast`
2. Create `<Toaster />` provider in App.tsx
3. Create `useToast()` hook wrapper
4. Replace first 3-5 success/error notifications with toasts

### Phase C: Form Validation (2+ hours, can be separate task)
1. Install `react-hook-form` + `zod` + `@hookform/resolvers`
2. Create shared Zod schemas for common forms
3. Migrate LoginPage form as proof-of-concept

## Acceptance Criteria

- [ ] Zero console.log statements in production code
- [ ] Toast system available for notifications
- [ ] At least LoginPage migrated to RHF+Zod (stretch goal)
- [ ] Build succeeds
