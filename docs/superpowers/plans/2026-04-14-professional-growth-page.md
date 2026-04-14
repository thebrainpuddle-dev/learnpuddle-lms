# Professional Growth Page Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge teacher Competency + Achievements into a single "Professional Growth" page with three focused sections: skills overview, recognition, recommended next steps.

**Architecture:** Single new page component (`ProfessionalGrowthPage.tsx`) consuming three existing API endpoints via react-query. Two old pages and their routes/sidebar entries are deleted. No backend changes.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, react-query, Lucide icons, react-router-dom

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `frontend/src/pages/teacher/ProfessionalGrowthPage.tsx` | Single merged page with skills, badges, recommendations |
| Modify | `frontend/src/App.tsx` | Replace two lazy imports + two routes with one |
| Modify | `frontend/src/components/layout/TeacherSidebar.tsx` | Replace two nav items with one |
| Delete | `frontend/src/pages/teacher/CompetencyPage.tsx` | Old competency page |
| Delete | `frontend/src/pages/teacher/GamificationPage.tsx` | Old achievements page |

---

## Chunk 1: Create the Professional Growth Page

### Task 1: Create ProfessionalGrowthPage.tsx

**Files:**
- Create: `frontend/src/pages/teacher/ProfessionalGrowthPage.tsx`

- [ ] **Step 1: Create the page file with imports, constants, and sub-components**

```tsx
// src/pages/teacher/ProfessionalGrowthPage.tsx
//
// Merged "Professional Growth" page — skills overview, recognition badges,
// and recommended next steps. Replaces CompetencyPage + GamificationPage.

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Target,
  CheckCircle2,
  AlertTriangle,
  BookOpen,
  Flame,
  Award,
  ChevronRight,
  Sprout,
} from 'lucide-react';
import { teacherService } from '../../services/teacherService';
import { gamificationService } from '../../services/gamificationService';
import type {
  CompetencyDashboard,
  CompetencySkill,
  CompetencyRecommendation,
} from '../../services/teacherService';
import type { BadgeDefinition, TeacherBadge } from '../../services/gamificationService';
import { usePageTitle } from '../../hooks/usePageTitle';
import { cn } from '../../design-system/theme/cn';

// ─── Constants ──────────────────────────────────────────────────────────────

const LEVEL_LABELS = ['Not Assessed', 'Foundational', 'Developing', 'Proficient', 'Advanced', 'Expert'];

const LEVEL_DOT_COLORS: Record<number, string> = {
  0: 'bg-slate-200',
  1: 'bg-sky-400',
  2: 'bg-blue-500',
  3: 'bg-indigo-500',
  4: 'bg-violet-500',
  5: 'bg-amber-500',
};

/**
 * Known Lucide icon names that admins might set in BadgeDefinition.icon.
 * Falls back to criteria_type mapping if icon name is not recognized.
 * Note: seed data currently stores emoji characters (e.g. "🎯") which won't
 * match these — the criteria_type fallback handles that gracefully.
 */
const ICON_NAME_MAP: Record<string, React.ElementType> = {
  target: Target,
  'book-open': BookOpen,
  flame: Flame,
  'check-circle-2': CheckCircle2,
  award: Award,
  star: Award,
};

const CRITERIA_ICON_MAP: Record<string, React.ElementType> = {
  xp_threshold: Target,
  courses_completed: BookOpen,
  streak_days: Flame,
  content_completed: CheckCircle2,
  manual: Award,
};

function getBadgeIcon(definition: BadgeDefinition): React.ElementType {
  // Try the icon field first (if admin set a known Lucide icon name)
  if (definition.icon && ICON_NAME_MAP[definition.icon]) {
    return ICON_NAME_MAP[definition.icon];
  }
  // Fall back to criteria_type mapping
  return CRITERIA_ICON_MAP[definition.criteria_type] ?? Award;
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function LevelBar({ current, target }: { current: number; target: number }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex gap-[3px]">
        {[1, 2, 3, 4, 5].map((lvl) => {
          const isTarget = lvl === target;
          return (
            <div
              key={lvl}
              className={cn(
                'h-2 w-6 rounded-[3px] transition-all duration-300',
                lvl <= current ? LEVEL_DOT_COLORS[current] : 'bg-slate-100',
                isTarget && lvl > current && 'ring-1 ring-inset ring-slate-300',
              )}
            />
          );
        })}
      </div>
      <span className="text-xs tabular-nums font-medium text-slate-400">
        {current}/{target}
      </span>
    </div>
  );
}

function SkillRow({ skill }: { skill: CompetencySkill }) {
  const met = !skill.has_gap && skill.current_level >= skill.target_level && skill.current_level > 0;
  return (
    <div className="flex items-center justify-between px-5 py-3 hover:bg-slate-50/50 transition-colors">
      <div className="min-w-0 flex-1 mr-4">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-slate-900 truncate">{skill.name}</p>
          {skill.has_gap && (
            <span className="flex-shrink-0 inline-flex items-center gap-0.5 rounded-full bg-amber-50 border border-amber-200/60 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
              Growth area
            </span>
          )}
          {met && <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />}
        </div>
        <p className="text-xs text-slate-400 mt-0.5">
          {LEVEL_LABELS[skill.current_level] || 'N/A'}
          <span className="mx-1.5 text-slate-300">&rarr;</span>
          Target: {LEVEL_LABELS[skill.target_level] || 'N/A'}
        </p>
      </div>
      <LevelBar current={skill.current_level} target={skill.target_level} />
    </div>
  );
}

function BadgeCard({ definition, earned }: { definition: BadgeDefinition; earned?: TeacherBadge }) {
  const isEarned = !!earned;
  const Icon = getBadgeIcon(definition);

  return (
    <div
      className={cn(
        'flex flex-col items-center text-center group',
        !isEarned && 'opacity-40',
      )}
      title={definition.description}
    >
      <div
        className={cn(
          'h-16 w-16 rounded-full flex items-center justify-center mb-2 transition-shadow',
          isEarned ? 'group-hover:shadow-md' : '',
        )}
        style={isEarned ? { backgroundColor: definition.color || '#6366f1' } : { backgroundColor: '#e2e8f0' }}
      >
        <Icon className="h-7 w-7 text-white" />
      </div>
      <p className="text-sm font-medium text-slate-900 truncate max-w-[100px]">{definition.name}</p>
      <p className="text-xs text-slate-400 mt-0.5">
        {isEarned && earned
          ? new Date(earned.awarded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
          : ''}
      </p>
    </div>
  );
}

// ─── Skeleton ───────────────────────────────────────────────────────────────

function PageSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div>
        <div className="h-7 w-52 bg-slate-200 rounded-lg" />
        <div className="h-4 w-80 bg-slate-100 rounded mt-2" />
      </div>
      {[1, 2, 3].map((i) => (
        <div key={i} className="rounded-2xl border border-slate-200/80 bg-white h-48" />
      ))}
      <div className="flex gap-6">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex flex-col items-center gap-2">
            <div className="h-16 w-16 rounded-full bg-slate-200" />
            <div className="h-3 w-16 bg-slate-100 rounded" />
          </div>
        ))}
      </div>
      <div className="rounded-2xl border border-slate-200/80 bg-white h-40" />
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────────────────

export const ProfessionalGrowthPage: React.FC = () => {
  usePageTitle('Professional Growth');
  const navigate = useNavigate();

  // ── Data fetching ──────────────────────────────────────────────────────
  const {
    data: competency,
    isLoading: competencyLoading,
    error: competencyError,
  } = useQuery<CompetencyDashboard>({
    queryKey: ['teacherCompetency'],
    queryFn: () => teacherService.getCompetencyDashboard(),
  });

  const { data: badgeDefs, isLoading: badgeDefsLoading } = useQuery<BadgeDefinition[]>({
    queryKey: ['badgeDefinitions'],
    queryFn: () => gamificationService.getBadgeDefinitions(),
  });

  const { data: earnedBadges, isLoading: earnedLoading } = useQuery<TeacherBadge[]>({
    queryKey: ['myBadges'],
    queryFn: () => gamificationService.getMyBadges(),
  });

  const isLoading = competencyLoading || badgeDefsLoading || earnedLoading;

  // ── Loading ────────────────────────────────────────────────────────────
  if (isLoading) return <PageSkeleton />;

  // ── Error (competency is primary — if it fails, show error) ────────────
  if (competencyError || !competency) {
    return (
      <div className="text-center py-24">
        <div className="mx-auto h-14 w-14 rounded-full bg-red-50 flex items-center justify-center mb-4">
          <AlertTriangle className="h-7 w-7 text-red-400" />
        </div>
        <p className="text-sm font-medium text-slate-900">Unable to load growth data</p>
        <p className="text-xs text-slate-500 mt-1">Please try refreshing the page.</p>
      </div>
    );
  }

  // ── Empty state (no skills assigned) ───────────────────────────────────
  if (competency.total_skills === 0) {
    return (
      <div className="text-center py-24">
        <div className="mx-auto h-16 w-16 rounded-full bg-slate-100 flex items-center justify-center mb-4">
          <Sprout className="h-8 w-8 text-slate-300" />
        </div>
        <h2 className="text-lg font-semibold text-slate-900">No Skills Assigned Yet</h2>
        <p className="mt-2 text-sm text-slate-500 max-w-md mx-auto">
          Your coordinator will map professional competencies to your profile.
          Once assigned, you'll see your skill levels and growth recommendations here.
        </p>
      </div>
    );
  }

  // ── Group skills by category ───────────────────────────────────────────
  const skillsByCategory: Record<string, CompetencySkill[]> = {};
  for (const skill of competency.skills) {
    const cat = skill.category || 'General';
    (skillsByCategory[cat] ||= []).push(skill);
  }

  // ── Badge data ─────────────────────────────────────────────────────────
  const earnedSet = new Set((earnedBadges ?? []).map((b) => b.badge.id));
  const allDefs = badgeDefs ?? [];
  const earnedDefs = allDefs.filter((d) => earnedSet.has(d.id));
  const unearnedDefs = allDefs
    .filter((d) => !earnedSet.has(d.id))
    .sort((a, b) => a.sort_order - b.sort_order)
    .slice(0, 4);

  // ── Recommendations (top 5, sorted by gap desc then assigned-first) ────
  const sortedRecs = [...competency.recommendations]
    .map((r) => ({ ...r, _gap: r.target_level - r.current_level }))
    .sort((a, b) => {
      // Assigned first
      if (a.is_assigned !== b.is_assigned) return a.is_assigned ? -1 : 1;
      // Then by gap descending
      return b._gap - a._gap;
    })
    .slice(0, 5);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Professional Growth</h1>
        <p className="mt-1 text-sm text-slate-500">
          Your skills, recognition, and recommended next steps
        </p>
      </div>

      {/* ── Section 1: Skills Overview ──────────────────────────────────── */}
      {Object.entries(skillsByCategory).map(([category, skills]) => {
        const metCount = skills.filter(
          (s) => !s.has_gap && s.current_level >= s.target_level && s.current_level > 0,
        ).length;
        return (
          <div
            key={category}
            className="rounded-2xl border border-slate-200/80 bg-white shadow-sm overflow-hidden"
          >
            <div className="border-b border-slate-100 px-5 py-3.5 bg-slate-50/50">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">{category}</h3>
                <span className="text-[11px] font-medium text-slate-400">
                  {metCount}/{skills.length} met
                </span>
              </div>
            </div>
            <div className="divide-y divide-slate-100">
              {skills.map((skill) => (
                <SkillRow key={skill.id} skill={skill} />
              ))}
            </div>
          </div>
        );
      })}

      {/* ── Section 2: Recognition ─────────────────────────────────────── */}
      {allDefs.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-slate-900 mb-4">Recognition</h2>

          {earnedDefs.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">
              {earnedDefs.map((def) => {
                const earned = (earnedBadges ?? []).find((b) => b.badge.id === def.id);
                return <BadgeCard key={def.id} definition={def} earned={earned} />;
              })}
            </div>
          ) : (
            <p className="text-sm text-slate-400">No badges earned yet. Complete courses and milestones to earn recognition.</p>
          )}

          {unearnedDefs.length > 0 && (
            <div className="mt-6">
              <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">Coming up</p>
              <div className="flex flex-wrap gap-6">
                {unearnedDefs.map((def) => (
                  <BadgeCard key={def.id} definition={def} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Section 3: Recommended Next Steps ──────────────────────────── */}
      {sortedRecs.length > 0 ? (
        <div className="rounded-2xl border border-slate-200/80 bg-white shadow-sm overflow-hidden">
          <div className="border-b border-slate-100 px-5 py-3.5 bg-slate-50/50">
            <h3 className="text-sm font-semibold text-slate-900">Recommended Next Steps</h3>
          </div>
          <div className="divide-y divide-slate-100">
            {sortedRecs.map((rec, idx) => (
              <button
                key={`${rec.course_id}-${rec.skill_name}-${idx}`}
                type="button"
                onClick={() => { if (rec.is_assigned) navigate(`/teacher/courses/${rec.course_id}`); }}
                disabled={!rec.is_assigned}
                className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-slate-50/50 transition-colors disabled:opacity-50 disabled:cursor-default"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900 truncate">{rec.course_title}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Builds <span className="font-medium text-indigo-600">{rec.skill_name}</span> to {LEVEL_LABELS[rec.level_taught] || `Level ${rec.level_taught}`}
                    {!rec.is_assigned && <span className="ml-1.5 text-slate-400">(ask your coordinator to assign)</span>}
                  </p>
                </div>
                {rec.is_assigned && <ChevronRight className="h-4 w-4 text-slate-400 flex-shrink-0" />}
              </button>
            ))}
          </div>
        </div>
      ) : competency.total_gaps === 0 ? (
        <div className="rounded-2xl border border-slate-200/80 bg-white shadow-sm p-8 text-center">
          <CheckCircle2 className="h-8 w-8 text-emerald-500 mx-auto mb-3" />
          <p className="text-sm font-medium text-slate-900">You're meeting all your targets</p>
          <p className="text-xs text-slate-500 mt-1">Great work — keep it up.</p>
        </div>
      ) : null}
    </div>
  );
};
```

- [ ] **Step 2: Verify the file compiles**

Run: `cd /Users/rakeshreddy/LMS/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/teacher/ProfessionalGrowthPage.tsx
git commit -m "feat: add ProfessionalGrowthPage merging competency + achievements"
```

---

### Task 2: Update App.tsx — replace routes

**Files:**
- Modify: `frontend/src/App.tsx:140-143` (lazy imports) and `:441-442` (routes)

- [ ] **Step 1: Replace the two lazy imports with one**

Find these lines (around lines 140-143):

```tsx
const GamificationPage = React.lazy(() => import('./pages/teacher/GamificationPage'));
const CompetencyPage = React.lazy(() =>
  import('./pages/teacher/CompetencyPage').then((m) => ({ default: m.CompetencyPage }))
);
```

Replace with:

```tsx
const ProfessionalGrowthPage = React.lazy(() =>
  import('./pages/teacher/ProfessionalGrowthPage').then((m) => ({ default: m.ProfessionalGrowthPage }))
);
```

- [ ] **Step 2: Replace the two route elements with one**

Find these lines (around lines 441-442):

```tsx
        <Route path="gamification" element={<RoutePage><GamificationPage /></RoutePage>} />
        <Route path="competency" element={<RoutePage><CompetencyPage /></RoutePage>} />
```

Replace with:

```tsx
        <Route path="growth" element={<RoutePage><ProfessionalGrowthPage /></RoutePage>} />
```

- [ ] **Step 3: Verify it compiles**

Run: `cd /Users/rakeshreddy/LMS/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: replace competency + gamification routes with /teacher/growth"
```

---

### Task 3: Update TeacherSidebar.tsx — replace nav items

**Files:**
- Modify: `frontend/src/components/layout/TeacherSidebar.tsx:50-55` (TOOLS_NAV array)

- [ ] **Step 1: Replace two nav items with one**

In the `TOOLS_NAV` array (lines 50-56), find:

```tsx
  { label: 'Competency', href: '/teacher/competency', icon: Compass },
  { label: 'Achievements', href: '/teacher/gamification', icon: BarChart3 },
```

Replace with:

```tsx
  { label: 'My Growth', href: '/teacher/growth', icon: TrendingUp },
```

- [ ] **Step 2: Update imports — remove unused icons, add TrendingUp**

In the import block (lines 8-25), the icons `Compass` and `BarChart3` are no longer used by this file. Remove them from the import and add `TrendingUp`:

Find:

```tsx
  BarChart3,
  Compass,
```

Replace with:

```tsx
  TrendingUp,
```

(Keep all other icons — `LayoutDashboard`, `BookOpen`, `Megaphone`, `ClipboardList`, `Settings`, `HelpCircle`, `LogOut`, `X`, `Presentation`, `MessageSquare`, `GraduationCap`, `Bot`, `Sparkles`, `ShieldCheck` are still used.)

- [ ] **Step 3: Verify it compiles**

Run: `cd /Users/rakeshreddy/LMS/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/TeacherSidebar.tsx
git commit -m "feat: replace Competency + Achievements sidebar items with My Growth"
```

---

## Chunk 2: Delete old pages and validate

### Task 4: Delete old page files

**Files:**
- Delete: `frontend/src/pages/teacher/CompetencyPage.tsx`
- Delete: `frontend/src/pages/teacher/GamificationPage.tsx`

- [ ] **Step 1: Delete CompetencyPage.tsx**

```bash
rm frontend/src/pages/teacher/CompetencyPage.tsx
```

- [ ] **Step 2: Delete GamificationPage.tsx**

```bash
rm frontend/src/pages/teacher/GamificationPage.tsx
```

- [ ] **Step 3: Verify no other files import from deleted pages**

Run: `cd /Users/rakeshreddy/LMS/frontend && grep -r "CompetencyPage\|GamificationPage" src/ --include="*.tsx" --include="*.ts" -l`

Expected: No files listed (App.tsx no longer imports them after Task 2).

- [ ] **Step 4: Run full TypeScript check**

Run: `cd /Users/rakeshreddy/LMS/frontend && npx tsc --noEmit 2>&1 | head -30`
Expected: No errors

- [ ] **Step 5: Run production build**

Run: `cd /Users/rakeshreddy/LMS/frontend && npx vite build 2>&1 | tail -5`
Expected: `built in X.XXs` with no errors

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/pages/teacher/CompetencyPage.tsx frontend/src/pages/teacher/GamificationPage.tsx
git commit -m "chore: remove old CompetencyPage and GamificationPage (merged into ProfessionalGrowthPage)"
```

---

### Task 5: Final verification

- [ ] **Step 1: Verify the route works at runtime**

Open `http://keystone.localhost:3000/teacher/growth` in a browser logged in as `priya.sharma@keystoneeducation.in`. Verify:
- Page title says "Professional Growth"
- Skills are grouped by category (Approaches to Teaching, Approaches to Learning, Pedagogical Practice, Professional Growth)
- Each skill shows a level bar with current/target
- Growth area pills appear on skills where current < target
- Green checkmarks appear on met skills
- Recognition section shows earned badges as colored circles with icons
- "Coming up" shows muted unearned badges
- Recommended Next Steps lists courses with skill names

- [ ] **Step 2: Verify old routes are gone**

Navigate to `/teacher/competency` — should show 404 or redirect.
Navigate to `/teacher/gamification` — should show 404 or redirect.

- [ ] **Step 3: Verify sidebar**

Sidebar under "Tools" should show "My Growth" (not "Competency" or "Achievements").
Clicking "My Growth" navigates to `/teacher/growth`.
