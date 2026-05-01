---
tags: [review, task/FE-014, task/TASK-019, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: FE-014 — Puddle Coins Wallet UI + Purchase Flow

## Verdict: APPROVE

## Summary

Solid, typed, well-tested wallet surface. Zero `any` in the service layer,
every Axios error path narrowed through a typed helper, formula-injection
hardened CSV export, disabled-when-unaffordable Buy button, lazy route,
consistent Lucide-sidebar / Heroicons-page icon split. 393/393 vitest pass,
`tsc --noEmit` clean (as reported; surface checks confirm no obvious type
smells in the new files).

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. **Hard-coded `DEFAULT_STREAK_FREEZE_PRICE = 100`** (`WalletPage.tsx` L65).
   Pragmatic ship decision — the backend balance endpoint doesn't currently
   expose `price_streak_freeze`, so the UI needs a fallback. The real risk
   is drift: if the backend bumps the price, the Shop card advertises the
   old price until the user tries to buy. Server still enforces correctly,
   so this is UX-only. Filing follow-up note to backend-engineer to add the
   field on `GET /coins/` (or a `/coins/prices/` endpoint). Not blocking.
2. **Modal close-on-backdrop while pending.** `onClose={() => !purchaseMut.isPending && setPurchaseOpen(false)}` (L626) correctly blocks closure during the request, but backdrop click still *attempts* to close. Headless UI handles this fine; just noting. No change needed.
3. **`COIN_REASON_LABELS` is typed `Record<string, string>`** (coinsService.ts L45). Could have been keyed to `CoinReason` for compile-time completeness. Non-blocking style nit.

## Verification performed

### `coinsService.ts`
- Zero `any`. All types explicit (`CoinReason` union, `CoinTransaction`,
  `CoinBalance`, `CoinHistoryResponse`, `PurchaseResponse`, `PurchasedToken`,
  `InsufficientCoinsPayload`).
- `parseInsufficientCoinsError` (L127–L141) correctly narrows via
  `axios.isAxiosError` guard + status 400 + runtime typeof checks on
  `balance`/`price`. Returns `null` on non-match. Exactly right.
- Three endpoint wrappers map 1:1 to TASK-019 URLs. No surprise mutations.
- No `console.log`.

### `WalletPage.tsx`
- Lazy route confirmed in `App.tsx` L198–L199 and mounted under
  `/teacher/wallet` inside the `ProtectedRoute allowedRoles={[TEACHER, HOD,
  IB_COORDINATOR]}` block (App.tsx L496–L520).
- `downloadCoinsCsv` (L69–L96): formula-injection hardening via
  `^[=+\-@]` → `'` prefix. Also quotes on `[",\n]` and doubles embedded
  `"`. Correct hardening; matches the pattern used on other export
  pages.
- Shop card "Buy" button disabled when `!canAfford || purchaseMut.isPending`
  (L539). Visual state flips variant to `outline` + text to "Not enough"
  when broke. Good UX.
- Purchase flow: bespoke Headless UI `Dialog` with an after-purchase row.
  Confirm button disabled while pending; backdrop close guarded. Success
  toasts + invalidates three query keys. 400 insufficient-funds path
  surfaces `{balance, price}` via `parseInsufficientCoinsError`.
- Pagination controls gated on `hasNext || hasPrev`; `data-testid`
  present on `wallet-page-prev` / `wallet-page-next`.
- Empty-state and load-failure branches both render.

### Sidebar
- `TeacherSidebar.tsx` L28 imports `Coins` from `lucide-react`.
  L47: `{ label: 'Wallet', href: '/teacher/wallet', icon: Coins }` under
  "My Learning" — matches existing Lucide-for-sidebar convention.
  No naming collision: `Coins` is a Lucide icon only used here.

### Response-shape mismatch flagged by FE
- Confirmed legit: backend `TeacherCoinBalanceSerializer` returns
  `{teacher_id, balance, lifetime_earned, lifetime_spent, last_txn_at,
  updated_at}` — no `price_streak_freeze`. Frontend's optional-typing +
  fallback strategy is the right ship-today call. Follow-up filed
  (`_coordination/inbox/backend-engineer/FOLLOWUP-coins-price-exposure-2026-04-20.md`).

## Positive Observations

- `parseInsufficientCoinsError` is exactly the right shape for this: one
  typed helper, callers just branch on null/not-null. Reusable.
- `tabular-nums` on every amount/balance number — subtle but right.
- Three separate query-invalidations on success
  (`teacherCoinBalance`, `teacherCoinHistory`, `teacherStreakFreezeInventory`)
  — the last one is the non-obvious one; if omitted, the
  AchievementsPage streak-freeze inventory count wouldn't refresh.
- `useToast()` consistently used, no `alert()`, no `console.log`.
- CSV export has no PII concerns — transaction ledger is already owned
  by the requesting teacher. Good.

## Follow-up items

- `_coordination/inbox/backend-engineer/FOLLOWUP-coins-price-exposure-2026-04-20.md`
  — requests that the BE expose `price_streak_freeze` either on
  `GET /coins/` or as a dedicated `/coins/prices/` route so the
  `DEFAULT_STREAK_FREEZE_PRICE` fallback can be removed from the client.
