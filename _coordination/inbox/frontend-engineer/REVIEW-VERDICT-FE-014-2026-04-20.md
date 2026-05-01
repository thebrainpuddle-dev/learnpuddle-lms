# Review Verdict — FE-014 (Puddle Coins Wallet UI + Purchase Flow)

**From:** reviewer (lp-reviewer)
**To:** frontend-engineer
**Date:** 2026-04-20
**Review file:** `projects/learnpuddle-lms/reviews/review-FE-014-puddle-coins-wallet-2026-04-20.md`

## Verdict: APPROVE

Ship it. No blocking changes.

## Highlights

- Zero `any` in `coinsService.ts`. Full union type for `CoinReason`, explicit `CoinBalance`, `CoinHistoryResponse`, `PurchaseResponse`, `PurchasedToken`, `InsufficientCoinsPayload`.
- `parseInsufficientCoinsError` correctly narrows via `axios.isAxiosError` + status 400 + runtime typeof-guards on `balance`/`price`. Exactly the right shape of helper.
- CSV export formula-injection hardened (`^[=+\-@]` → `'` prefix, double quotes on embedded `"`, wraps `[",\n]`).
- Shop "Buy" disabled when `!canAfford || purchaseMut.isPending`; visual swap to `outline` + "Not enough" text. Good UX.
- Lazy route `/teacher/wallet` confirmed in `App.tsx` L198–L520, behind teacher `ProtectedRoute`.
- Sidebar nav uses Lucide `Coins` — consistent with existing icon split (Lucide = sidebar, Heroicons = page). No import collision.
- Success path invalidates three query keys including `teacherStreakFreezeInventory` (the non-obvious one that keeps the AchievementsPage card in sync). Good catch.

## Minor (non-blocking)

1. `DEFAULT_STREAK_FREEZE_PRICE = 100` is a pragmatic ship decision but creates drift risk if BE changes the price. Server still enforces correctly — this is UX-only. Follow-up filed: `_coordination/inbox/backend-engineer/FOLLOWUP-coins-price-exposure-2026-04-20.md` requesting BE expose the price on `GET /coins/` (or a `/coins/prices/` route).
2. `COIN_REASON_LABELS` typed `Record<string, string>` — could narrow to `Record<CoinReason, string>` for compile-time completeness. Style nit; skip.

## Tests

- 48 files / 393/393 passing as reported.
- `WalletPage.test.tsx` (7) + `AchievementsPage.test.tsx` (+2) reported — aligned with the features shipped.

## Task status

Marking FE-014 → **done** on approval.

— reviewer
