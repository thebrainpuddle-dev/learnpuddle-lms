# Professional Growth Page — Design Spec

## Goal

Merge the existing Competency and Achievements pages into a single "My Professional Growth" page that teachers actually find useful. Three focused sections: skills overview, recognition, recommended next steps. No gaming language, no vanity metrics.

## Why

The current Competency page reads like a performance review spreadsheet — teachers don't understand what "Skill Gap: 2" means or why they should care about a 72% score ring. The current Achievements page uses gaming vocabulary (XP, levels, streaks, leaderboards) that feels patronizing to professional educators. Neither page drives action.

The merged page answers three questions a teacher actually has:
1. Where am I strong and where should I grow?
2. What have I been recognized for?
3. What should I do next?

## What Changes

### Route

- **New:** `/teacher/growth` — single page, "My Growth" in sidebar
- **Remove:** `/teacher/competency` route and `CompetencyPage.tsx`
- **Remove:** `/teacher/gamification` route and `GamificationPage.tsx`
- **Sidebar:** Replace "Competency" + "Achievements" entries with single "My Growth" (Sprout or TrendingUp icon)

### Files

| Action | File |
|--------|------|
| Create | `frontend/src/pages/teacher/ProfessionalGrowthPage.tsx` |
| Modify | `frontend/src/App.tsx` — replace two routes with one |
| Modify | `frontend/src/components/layout/TeacherSidebar.tsx` — replace two nav items with one |
| Delete | `frontend/src/pages/teacher/CompetencyPage.tsx` |
| Delete | `frontend/src/pages/teacher/GamificationPage.tsx` |

### Backend

No backend changes. The page consumes three existing endpoints:
- `GET /teacher/competency/` — skills, categories, recommendations
- `GET /gamification/badges/` — teacher's earned badges
- `GET /gamification/badge-definitions/` — all badge definitions

The gamification summary/leaderboard/XP-history endpoints are no longer consumed by this page.

---

## Page Layout

```
┌──────────────────────────────────────────────────────┐
│  Professional Growth                                 │
│  Your skills, recognition, and recommended next steps│
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌─ Approaches to Teaching ──────────────────────┐   │
│  │  Inquiry-Based Teaching      ████░  4/4  ✓    │   │
│  │  Conceptual Understanding    ███░░  3/4  grow │   │
│  │  Collaborative Teaching      ████░  4/4  ✓    │   │
│  │  ...                                          │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ Approaches to Learning ──────────────────────┐   │
│  │  ...                                          │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ Pedagogical Practice ────────────────────────┐   │
│  │  ...                                          │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ Professional Growth (category) ──────────────┐   │
│  │  ...                                          │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ── Recognition ─────────────────────────────────    │
│                                                      │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐      │
│  │ icon │ │ icon │ │ icon │ │ icon │ │ icon │  ...  │
│  │ name │ │ name │ │ name │ │ name │ │ name │      │
│  │ date │ │ date │ │ date │ │ date │ │ date │      │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘      │
│                                                      │
│  Coming up (muted):  ○ badge  ○ badge  ○ badge      │
│                                                      │
│  ── Recommended Next Steps ──────────────────────    │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │  IB Approaches to Teaching                    │   │
│  │  Builds Reggio Emilia Approaches → Proficient │   │
│  │                                    [Continue] │   │
│  ├───────────────────────────────────────────────┤   │
│  │  Assessment for Learning                      │   │
│  │  Builds Assessment-Informed Teaching → Adv.   │   │
│  │                        Ask coordinator to add │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## Section 1: Skills Overview

### Data source
`CompetencyDashboard` from `GET /teacher/competency/`

### Behavior
- Skills grouped by `category` into category cards (static, not collapsible — 4 categories with ~5 skills each doesn't warrant accordion complexity)
- Each category card: white background, subtle border, category name as header
- Each skill row inside:
  - Skill name (left)
  - Level bar: 5 segments, filled to `current_level`, target marker on `target_level` segment (carry over `LevelBar` component from deleted `CompetencyPage.tsx`)
  - Current/target as "3/4" text
  - If `has_gap`: warm-toned "Growth area" label (small, inline, `text-amber-600 bg-amber-50` pill)
  - If met (current >= target and current > 0): quiet green checkmark icon
- Category header shows "X/Y met" count on the right side
- No overall score ring. No stat cards. No filter pills.

### Empty state
If `total_skills === 0`: centered message with icon — "No skills assigned yet. Your coordinator will map professional competencies to your profile."

---

## Section 2: Recognition

### Data source
- `GET /gamification/badge-definitions/` — all definitions
- `GET /gamification/badges/` — teacher's earned badges

### Behavior
- Section divider with "Recognition" heading
- **Earned badges**: wrapping grid (responsive: 2 cols mobile, 3 tablet, 5 desktop)
  - Each badge: circular container (h-16 w-16) with `badge.color` as background, Lucide SVG icon inside (white, h-7 w-7)
  - Badge name below (text-sm, font-medium)
  - Award date below name (text-xs, text-slate-400, "Apr 2, 2026" format)
  - Hover: subtle shadow lift + tooltip with `badge.description`
- **Icon mapping**: The `BadgeDefinition.icon` field stores a string (default `'star'`). Use it as a Lucide icon name lookup. Fallback mapping by `criteria_type` if the icon name doesn't match a known Lucide icon:
  - `xp_threshold` → `Target`
  - `courses_completed` → `BookOpen`
  - `streak_days` → `Flame`
  - `content_completed` → `CheckCircle`
  - `manual` → `Award`
  - Fallback for any unmapped type → `Award`
- **Unearned badges**: "Coming up" label, then up to 4 nearest unearned badges (ordered by `sort_order`) at 40% opacity, no lock icon, just muted. If all earned, this row doesn't render.
- If no badge definitions exist: don't render this section at all (not even the heading).

---

## Section 3: Recommended Next Steps

### Data source
`CompetencyDashboard.recommendations` from `GET /teacher/competency/`

### Behavior
- Section divider with "Recommended Next Steps" heading
- Show top 5 recommendations, sorted assigned-first (actionable items on top), then by computed gap (`target_level - current_level`) descending. The `CompetencyRecommendation` type has `current_level` and `target_level` but no `gap_size` — compute it client-side.
- Each recommendation row:
  - Course title (text-sm, font-medium)
  - "Builds **{skill_name}** to {LEVEL_LABELS[level_taught]}" (text-xs, skill name in indigo)
  - If `is_assigned`: "Continue" link/button that navigates to `/teacher/courses/{course_id}`
  - If not assigned: muted text "Ask your coordinator to assign this" (text-xs, text-slate-400)
- If no recommendations (no gaps): "You're meeting all your targets" message with a green checkmark, one sentence, no fanfare.
- Cap at 5 items. No "show more."

---

## What Gets Removed

| Element | Reason |
|---------|--------|
| Score ring (% overall) | Single number without context is meaningless |
| 4 stat cards | Vanity metrics that don't drive action |
| Filter pills (All/Gaps/Met) | Overengineered for ~18 skills |
| XP points and level system | Gaming language inappropriate for professionals |
| Streak counter | Creates anxiety, not motivation |
| Leaderboard | Toxic comparison among colleagues |
| Recent Activity / XP feed | Low value — teachers don't audit their point log |
| Opt-out banner | No gamification = nothing to opt out of |
| Monthly/weekly XP cards | Gaming metrics |

Note: The backend endpoints for XP, leaderboard, streaks remain unchanged. The admin gamification management pages are unaffected. Only the teacher-facing page changes.

---

## Visual Design Principles

- **Slate color palette**: `slate-900` headings, `slate-500` secondary text, `slate-200` borders. No bright accent colors competing for attention.
- **Rounded-2xl cards** with `border-slate-200/80` and `shadow-sm` — matches existing LMS card pattern.
- **Lucide icons only** — no emoji, no inline SVG paths, no icon fonts.
- **Badge visuals**: Circular containers with the badge's hex color as background, white Lucide icon centered. Clean and consistent. Not 3D, not glossy, not skeuomorphic.
- **Level bars**: Keep existing 5-segment bar design. It works well and is immediately readable.
- **Growth area labels**: `bg-amber-50 text-amber-600 border-amber-200/60` pill — warm but not alarming. The word "Growth area" instead of "Gap" — frames it as opportunity not deficiency.
- **Skeleton loading**: Content-shaped placeholder matching the actual layout. Single skeleton for the whole page since it loads from 2-3 endpoints via `Promise.all`.
- **No animations** beyond subtle hover transitions. No confetti, no progress animations, no number counting up.

---

## Technical Notes

- **Single component file**: `ProfessionalGrowthPage.tsx`. Sub-components (LevelBar, BadgeCard, SkillRow) defined in the same file. Carry over `LevelBar` and `LEVEL_LABELS` constant from the deleted `CompetencyPage.tsx`.
- **Data fetching**: Three `useQuery` calls — competency dashboard, badge definitions, earned badges. Show skeleton until all three resolve. Use `isLoading` from each query combined with `&&`.
- **Error handling**: If competency endpoint fails, show full-page error state. If badge endpoints fail, hide the Recognition section silently (skills are the primary content). No partial error banners.
- **Gamification store**: The page does NOT use `gamificationStore` — it fetches badge data directly via react-query. The store can remain for admin pages that still need it.
- **No new backend work**: All data already available from existing endpoints.
