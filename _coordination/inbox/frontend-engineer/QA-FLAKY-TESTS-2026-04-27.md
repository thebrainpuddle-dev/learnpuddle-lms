# QA — Flaky Test Report: DashboardPage + RubricPage

**From:** qa-tester
**To:** frontend-engineer
**Date:** 2026-04-27
**Priority:** Low (non-blocking, pre-existing)

---

## What I found

During the full frontend suite run, 2 pre-existing tests fail under load but
pass when run in isolation. These are not new regressions.

---

### 1. `DashboardPage.test.tsx > DashboardPage > renders the hero heading`

```typescript
// line 124 in DashboardPage.test.tsx
it('renders the hero heading', async () => {
  renderPage();
  expect(await screen.findByText(/Welcome back, Admin/)).toBeInTheDocument();
});
```

**Full suite result:** 7057ms → FAIL (exceeded default findBy timeout ~5000ms)
**Isolated result:** PASS

**Fix:** Use explicit timeout:
```typescript
expect(await screen.findByText(/Welcome back, Admin/, {}, { timeout: 10000 }))
  .toBeInTheDocument();
```

---

### 2. `RubricPage.test.tsx > RubricPage > disables Next button on the last page`

```typescript
// lines 454-469 in RubricPage.test.tsx
it('disables Next button on the last page', async () => {
  vi.mocked(adminRubricService.listRubrics)
    .mockResolvedValueOnce(makeListResponse(mockRubrics, { count: 12 }))
    .mockResolvedValue(makeListResponse(mockRubrics, { count: 12, page: 2 }));
  const user = userEvent.setup();
  renderRubricPage();
  const nextBtn = await screen.findByRole('button', { name: /next/i });
  await user.click(nextBtn);
  await waitFor(() => {
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
  });
});
```

**Full suite result:** 1529ms → FAIL
**Isolated result:** PASS

**Fix:** Add explicit `timeout` to the `waitFor`:
```typescript
await waitFor(() => {
  expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
}, { timeout: 5000 });
```

Or, wrap the click in `act()` to ensure React flush:
```typescript
await act(async () => {
  await user.click(nextBtn);
});
await waitFor(() => {
  expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
});
```

---

## Root cause

Both failures are timing-related. The async queries use default vitest/Testing
Library timeouts (~1000-5000ms). Under the full 1428-test suite with parallel
workers, CPU load increases and React's async state processing takes longer,
causing the timeouts to be hit.

---

## Note

These files are outside QA's ownership. Please apply the fix at your
convenience — they don't block any current feature work.

— qa-tester
