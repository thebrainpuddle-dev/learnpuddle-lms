# Review Request — FE-014 Puddle Coins Wallet UI + Purchase Flow

**From**: frontend-engineer
**To**: reviewer
**Date**: 2026-04-20
**Phase**: Phase 4 — Gamification (TASK-019 frontend surface)

## What changed

### `frontend/src/services/coinsService.ts` (new)
Typed client for the three TASK-019 endpoints:

| Endpoint | Method | Type |
|----------|--------|------|
| `/gamification/coins/` | GET | `CoinBalance` |
| `/gamification/coins/history/` | GET | `CoinHistoryResponse` (DRF page) |
| `/gamification/coins/purchase/streak-freeze/` | POST | `PurchaseResponse` |

- Zero `any` — explicit `CoinReason`, `CoinTransaction`, `CoinBalance`, `CoinHistoryResponse`, `PurchaseResponse`, `PurchasedToken`, `InsufficientCoinsPayload`.
- Helper `parseInsufficientCoinsError(err)` narrows Axios errors into `{balance, price}` for the 400 toast.
- Exports `COIN_REASON_LABELS` so the history table renders human strings.

### `frontend/src/pages/teacher/WalletPage.tsx` (new, `/teacher/wallet`)
Three sections:
1. **Hero** — gradient card with `CircleStackIcon`, balance in large tabular-nums, last-txn-at timestamp.
2. **Lifetime stats** — two cards for `lifetime_earned` (emerald, ArrowUpRight) and `lifetime_spent` (orange, ArrowDownRight).
3. **Shop** — "Streak Freeze Token" row with price, Buy button gated on `balance >= price`.
4. **Transaction history** — TanStack `DataTable` (Date, Reason, Reference, Amount) + CSV export with formula-injection hardening (`'=SUM(...)`), server-side pagination.

**Purchase flow** uses a bespoke Headless UI `Dialog` (not `ConfirmDialog`) because we need to show balance/price/after rows and control close timing around the toast. Modal displays:
- Your balance / Price / After purchase (computed)
- Specific red warning when not affordable
- On confirm → `purchaseMut.mutate()`
- Success → toast + invalidate `teacherCoinBalance`, `teacherCoinHistory`, `teacherStreakFreezeInventory`
- 400 insufficient → toast with `{balance, price}` from error body

### `frontend/src/pages/teacher/AchievementsPage.tsx` (enhanced)
- Added `coinBalanceQ` + `buyFreezeMutation` (coin-funded streak-freeze purchase).
- **Wallet pill** (`[data-testid=achievements-wallet-pill]`) in the header: amber pill with `CircleStackIcon` + balance + "coins", routes to `/teacher/wallet`.
- **Buy freeze token** secondary CTA under the streak card, rendered only when `summary.current_streak > 0 && tokenCount === 0`. Opens a warning-variant `ConfirmDialog` that shows price and current balance, confirms through `coinsService.purchaseStreakFreeze()`.

### `frontend/src/App.tsx`
Added lazy route:
```tsx
const TeacherWalletPage = React.lazy(() =>
  import('./pages/teacher/WalletPage').then((m) => ({ default: m.WalletPage }))
);
<Route path="wallet" element={<RoutePage><TeacherWalletPage /></RoutePage>} />
```

### `frontend/src/components/layout/TeacherSidebar.tsx`
Added `Wallet` nav entry (Lucide `Coins` icon) under "My Learning" between Achievements and Challenges.

## Response-shape mismatch worth flagging

The task brief quotes the balance response as `{balance, lifetime_earned, lifetime_spent, price_streak_freeze}`, but `TeacherCoinBalanceSerializer` in `backend/apps/progress/gamification_serializers.py` currently returns:
```
{teacher_id, balance, lifetime_earned, lifetime_spent, last_txn_at, updated_at}
```
— no `price_streak_freeze`. The only place the price is exposed is the 400 `InsufficientCoinsError` payload. Handling:
- `CoinBalance.price_streak_freeze` is typed **optional**.
- UI falls back to `DEFAULT_STREAK_FREEZE_PRICE = 100` (matches `GamificationConfig.coin_price_streak_freeze` default).
- If the BE later adds the field to the serializer, the UI picks it up automatically — no FE changes required.

Suggest the BE team either include `price_streak_freeze` on the GET response or add a lightweight `/gamification/coins/prices/` endpoint so we don't ship a hard-coded fallback in production.

## Test results

```
npx tsc --noEmit  → 0 errors
npx vitest run    → Test Files 48 passed (48) / Tests 393 passed (393)
```

New test counts:
- `WalletPage.test.tsx` — 7 cases (balance hero, shop card, afford-true, afford-false, purchase-success, insufficient-coins 400 toast, empty history)
- `AchievementsPage.test.tsx` — 2 new cases (wallet pill + buy-freeze confirm modal)

## Checklist

- [x] TypeScript strict — 0 errors, zero `any` in service
- [x] Tests green — 393/393
- [x] Lazy route in `App.tsx`
- [x] Sidebar nav "Wallet" under "My Learning"
- [x] CSV export uses formula-injection hardening (`'=/+/-/@` prefix)
- [x] Heroicons for page icons, Lucide for sidebar (matching existing conventions)
- [x] `cursor-pointer` on interactive elements
- [x] `useToast()` for success/error; no `alert()`
- [x] No `console.log`
- [x] Mutation invalidates `teacherCoinBalance`, `teacherCoinHistory`, `teacherStreakFreezeInventory`
- [x] Insufficient-balance 400 surfaces `{balance, price}` from error body (not generic toast)

— frontend-engineer
