---
tags: [review, task/FE-009, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: FE-009 — Teacher Achievements Page

## Verdict: APPROVE (with two minor follow-ups)

## Summary
Polished, accessible, well-isolated page. Reuses every `gamificationService`
method without backend changes, handles opt-out gracefully, and the 7
vitest cases actually test what's claimed (including rarity metadata via
stable `data-*` hooks rather than class-name sniffing). Rarity is inferred
client-side from `criteria_value` within `criteria_type` — a pragmatic
choice given TASK-014 left rarity off the model; the default fallback is
safe.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **League rank is inferred heuristically.**
   `AchievementsPage.tsx:333-343` matches the viewer's entry by
   `total_xp === summary.total_xp && level === summary.level`. In a small
   tenant with tied scores, two teachers could land on the same rank and
   the first one in the list would be labelled as "me". The author flagged
   this in the review request and suggested an `is_me` flag on the
   leaderboard entry — agreed, file as a follow-up. Non-blocking because
   the displayed rank is visually prefixed with "League rank" and mis-attribution
   is benign.

2. **Streak-freeze button ignores token inventory.**
   `canUseFreeze = summary.current_streak > 0` means the button is enabled
   even when a teacher has zero freeze tokens; the backend rejects with a
   400 and we surface the error via `toast.error`. With TASK-015 shipping
   the `/streak-freeze/inventory/` endpoint, the page could (and likely
   should, in a follow-up) disable the button when `token_count === 0` and
   show a helpful "Earn by keeping your streak" hint. Non-blocking because
   the error path is handled.

3. **Rarity thresholds on `manual` criteria.** `rarityFor` returns `'epic'`
   for every `manual` badge, which is a reasonable default but means a
   manually-awarded "Common" participation badge would silently appear as
   "Epic" in the gallery. Consider either (a) honouring a future backend
   `rarity` column when it lands, or (b) letting admins override via badge
   metadata. Note in comment is helpful; no action needed now.

## Positive Observations

- **No `any`, no `console.log`, no debug code.** `getErrorMessage` narrows
  `unknown` via `axios.isAxiosError` first, then `instanceof Error`, with
  a fallback string.
- **Strict typing throughout**: `Rarity` is a union literal,
  `RARITY_META` uses `Record<Rarity, {...}>`, `StatCardProps.tone` is a
  restricted union, and `setupMocks` uses
  `Partial<Record<keyof typeof gamificationService, unknown>>` rather
  than `any`.
- **Accessibility**: `role="progressbar"`, `aria-valuenow/min/max`, and
  `aria-label="Progress to next level"` on the level hero; the test
  asserts `aria-valuenow === '70'`, which correctly catches a broken
  fraction calculation.
- **Destructive action uses `ConfirmDialog`** (the shared component, not
  a custom modal), with `loading` forwarded from
  `useFreezeMutation.isPending`. This matches the established pattern.
- **Rarity visual mapping has a `default` case** returning `'common'` so an
  unexpected `criteria_type` (e.g. a new enum value added on the backend)
  won't crash — it silently degrades. Acceptable, and safer than throwing.
- **Opt-out is a calm, explicit state** rather than hiding navigation; the
  test `shows the opt-out state when the teacher has opted out` verifies
  the hero/stat cards are unmounted.
- **Lazy route wiring is correct**: `frontend/src/App.tsx:180-182` defines
  `TeacherAchievementsPage` via `React.lazy`, and line 496 mounts it at
  `<Route path="achievements" element={<RoutePage>…</RoutePage>} />`
  under the teacher parent route. `TeacherSidebar.tsx:43` adds the nav
  entry under *My Learning* with the Trophy icon.
- **Chart is stubbed in tests** via `vi.mock('recharts', …)` so jsdom
  doesn't explode on `<ResponsiveContainer>`. This is the right pattern.
- **XP-trend bucketing** uses `new Map` with pre-seeded zero days so the
  chart always renders 14 bars, not a ragged subset. Good UX detail.
- **Recent-activity humanisation** (`tx.description || tx.reason`, with
  `.replace(/_/g, ' ')`) means `content_completion` displays as
  "content completion" — cheap and effective.

## Test Audit (7 cases)

| Test | What it actually asserts | Verdict |
|------|--------------------------|---------|
| renders the level hero | Heading, level name, XP + progress + `aria-valuenow="70"` | Tight, also sanity-checks the 420/600 = 70% math |
| shows stat cards | Week XP, streak, badge count, league rank | Reads all four cards, including `1/2` badge ratio |
| badges earned/locked with rarity | Uses `data-testid`, `data-earned`, `data-rarity` | Stable hooks, not class-name sniffing |
| XP trend chart renders | `data-testid="line-chart"` | Verifies recharts stub is connected |
| recent XP activity | Description + signed amount (`+30`, `+20`) | Asserts the humanisation replaced underscores |
| use streak freeze | Click + dialog confirm + service called | Tests the happy-path mutation end-to-end |
| opt-out state | Opt-out banner present, hero/cards unmounted | Good; avoids false-positives on cached render |

All 7 tests fail if the page regresses in their specific area. No snapshot
tests, no implementation coupling beyond the `data-testid` hooks the page
itself exposes.

## Decision

APPROVE. Minor issues (1) and (2) are good candidates for a light follow-up
ticket once TASK-015's inventory endpoint is exercised from this page.
