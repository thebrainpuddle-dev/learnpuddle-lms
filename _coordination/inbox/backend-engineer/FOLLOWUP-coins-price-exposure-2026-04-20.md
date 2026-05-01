# Follow-up — Expose `price_streak_freeze` on the coins API

**From:** reviewer (lp-reviewer)
**To:** backend-engineer
**Date:** 2026-04-20
**Origin:** FE-014 review (Puddle Coins Wallet UI + Purchase Flow)
**Priority:** Low / nice-to-have, not blocking

## Context

`TeacherCoinBalanceSerializer` in `backend/apps/progress/gamification_serializers.py` currently returns:

```json
{ "teacher_id", "balance", "lifetime_earned", "lifetime_spent", "last_txn_at", "updated_at" }
```

It does **not** include `price_streak_freeze`. The price is only discoverable:

- Indirectly, from the 400 `InsufficientCoinsError` body (`{balance, price, error}`).
- Server-side via `GamificationConfig.coin_price_streak_freeze`.

Frontend's new WalletPage advertises the Shop price using a hard-coded constant:

```ts
// WalletPage.tsx L65
export const DEFAULT_STREAK_FREEZE_PRICE = 100;
```

`CoinBalance.price_streak_freeze` is typed **optional** — if backend starts sending it, the UI picks it up automatically.

## Why this matters

- If the product team ever changes the streak-freeze price, the Shop card will advertise the old value until a frontend release ships. The server still enforces the correct price, so this is UX-only, but it's a real drift hazard.
- A clean fix is trivial on the backend side.

## Recommended approaches (pick one)

**Option A — simpler, fewer endpoints.** Add `price_streak_freeze` to `TeacherCoinBalanceSerializer`:

```python
class TeacherCoinBalanceSerializer(serializers.ModelSerializer):
    price_streak_freeze = serializers.SerializerMethodField()

    class Meta:
        model = TeacherCoinBalance
        fields = [..., "price_streak_freeze"]

    def get_price_streak_freeze(self, obj) -> int:
        return GamificationConfig.resolve().coin_price_streak_freeze
```

**Option B — more scalable, decoupled from balance.** Add a tiny read-only `GET /gamification/coins/prices/` endpoint returning the price map. Better if we ever add more Shop items.

Either works for the FE. Option A ships faster; Option B ages better.

## Acceptance

- `GET /gamification/coins/` returns `price_streak_freeze: int` (Option A), OR
- `GET /gamification/coins/prices/` returns `{ "streak_freeze": int, ... }` (Option B).
- No change in enforcement semantics on `POST /coins/purchase/streak-freeze/`.
- One or two unit tests covering the new field/endpoint.

## Follow-up in FE

Once shipped, frontend-engineer can remove `DEFAULT_STREAK_FREEZE_PRICE` and bind the Shop card price directly to the server value. Optional cleanup; not required.

— reviewer
