// src/pages/teacher/ProfessionalGrowthPage.tsx
//
// Merged "Professional Growth" page — skills overview, recognition badges,
// and recommended next steps. Replaces CompetencyPage + GamificationPage.

import React, { useState } from 'react';
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
  TrendingUp,
  ArrowUpRight,
  Sparkles,
} from 'lucide-react';
import { teacherService } from '../../services/teacherService';
import { gamificationService } from '../../services/gamificationService';
import type {
  CompetencyDashboard,
  CompetencySkill,
} from '../../services/teacherService';
import type { BadgeDefinition, TeacherBadge } from '../../services/gamificationService';
import { usePageTitle } from '../../hooks/usePageTitle';
import { cn } from '../../design-system/theme/cn';

// ─── Constants ──────────────────────────────────────────────────────────────

const LEVEL_LABELS = ['Not Assessed', 'Foundational', 'Developing', 'Proficient', 'Advanced', 'Expert'];

const CATEGORY_ACCENTS: Record<string, { border: string; bg: string; text: string; bar: string }> = {
  'Approaches to Teaching': {
    border: 'border-l-indigo-500',
    bg: 'bg-indigo-50/50',
    text: 'text-indigo-700',
    bar: 'from-indigo-400 to-indigo-600',
  },
  'Approaches to Learning': {
    border: 'border-l-violet-500',
    bg: 'bg-violet-50/50',
    text: 'text-violet-700',
    bar: 'from-violet-400 to-violet-600',
  },
  'Pedagogical Practice': {
    border: 'border-l-sky-500',
    bg: 'bg-sky-50/50',
    text: 'text-sky-700',
    bar: 'from-sky-400 to-sky-600',
  },
  'Professional Growth': {
    border: 'border-l-emerald-500',
    bg: 'bg-emerald-50/50',
    text: 'text-emerald-700',
    bar: 'from-emerald-400 to-emerald-600',
  },
};

const DEFAULT_ACCENT = {
  border: 'border-l-slate-400',
  bg: 'bg-slate-50/50',
  text: 'text-slate-600',
  bar: 'from-slate-400 to-slate-600',
};

function getCategoryAccent(category: string) {
  return CATEGORY_ACCENTS[category] || DEFAULT_ACCENT;
}

// ─── Badge icon mapping ─────────────────────────────────────────────────────

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
  if (definition.icon && ICON_NAME_MAP[definition.icon]) {
    return ICON_NAME_MAP[definition.icon];
  }
  return CRITERIA_ICON_MAP[definition.criteria_type] ?? Award;
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function StatTile({
  label,
  value,
  sublabel,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number | string;
  sublabel?: string;
  icon: React.ElementType;
  accent: string;
}) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm transition-all duration-300 hover:shadow-md hover:-translate-y-0.5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</p>
          <p className="mt-2 text-3xl font-bold tracking-tight text-slate-900">{value}</p>
          {sublabel && (
            <p className="mt-1 text-xs text-slate-400">{sublabel}</p>
          )}
        </div>
        <div className={cn('flex h-10 w-10 items-center justify-center rounded-xl transition-transform duration-300 group-hover:scale-110', accent)}>
          <Icon className="h-5 w-5 text-white" />
        </div>
      </div>
      {/* Decorative gradient corner */}
      <div className="absolute -bottom-8 -right-8 h-24 w-24 rounded-full bg-gradient-to-br from-slate-100/80 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
    </div>
  );
}

function GradientProgressBar({
  current,
  target,
  gradient,
}: {
  current: number;
  target: number;
  gradient: string;
}) {
  const maxLevel = 5;
  const fillPercent = (current / maxLevel) * 100;
  const targetPercent = (target / maxLevel) * 100;

  return (
    <div className="flex items-center gap-3">
      <div className="relative h-2 w-28 overflow-hidden rounded-full bg-slate-100">
        {/* Filled portion */}
        <div
          className={cn(
            'absolute inset-y-0 left-0 rounded-full bg-gradient-to-r transition-all duration-700 ease-out',
            gradient,
          )}
          style={{ width: `${fillPercent}%` }}
        />
        {/* Target marker */}
        {target > current && (
          <div
            className="absolute top-0 h-full w-0.5 bg-slate-300"
            style={{ left: `${targetPercent}%` }}
          />
        )}
      </div>
      <span className="min-w-[2.5rem] text-right text-xs font-medium tabular-nums text-slate-400">
        {current}/{target}
      </span>
    </div>
  );
}

function SkillRow({
  skill,
  gradient,
  isHovered,
  onHover,
  onLeave,
}: {
  skill: CompetencySkill;
  gradient: string;
  isHovered: boolean;
  onHover: () => void;
  onLeave: () => void;
}) {
  const met = !skill.has_gap && skill.current_level >= skill.target_level && skill.current_level > 0;

  return (
    <div
      className={cn(
        'group flex items-center justify-between px-5 py-3.5 transition-all duration-200 cursor-default',
        isHovered ? 'bg-slate-50/80' : 'hover:bg-slate-50/40',
      )}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
    >
      <div className="min-w-0 flex-1 mr-4">
        <div className="flex items-center gap-2">
          {/* Animated accent bar on hover */}
          <div
            className={cn(
              'h-5 w-0.5 rounded-full transition-all duration-300',
              isHovered ? 'scale-y-100 opacity-100 bg-gradient-to-b ' + gradient : 'scale-y-50 opacity-0 bg-slate-300',
            )}
          />
          <p
            className={cn(
              'text-sm font-medium transition-all duration-300',
              isHovered ? 'text-slate-900 translate-x-0' : 'text-slate-600 -translate-x-2',
            )}
          >
            {skill.name}
          </p>
          {skill.has_gap && (
            <span className="flex-shrink-0 inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200/60 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
              <ArrowUpRight className="h-2.5 w-2.5" />
              Growth area
            </span>
          )}
          {met && (
            <span className="flex-shrink-0 inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200/60 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
              <CheckCircle2 className="h-2.5 w-2.5" />
              Met
            </span>
          )}
        </div>
        <p
          className={cn(
            'text-xs mt-0.5 transition-all duration-300',
            isHovered ? 'text-slate-500 translate-x-2.5' : 'text-slate-400 translate-x-0',
          )}
        >
          {LEVEL_LABELS[skill.current_level] || 'N/A'}
          <span className="mx-1.5 text-slate-300">&rarr;</span>
          {LEVEL_LABELS[skill.target_level] || 'N/A'}
        </p>
      </div>
      <GradientProgressBar current={skill.current_level} target={skill.target_level} gradient={gradient} />
    </div>
  );
}

function CategoryCard({ category, skills }: { category: string; skills: CompetencySkill[] }) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const accent = getCategoryAccent(category);
  const metCount = skills.filter(
    (s) => !s.has_gap && s.current_level >= s.target_level && s.current_level > 0,
  ).length;
  const allMet = metCount === skills.length;

  return (
    <div
      className={cn(
        'group/card overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm transition-all duration-300 hover:shadow-md border-l-4',
        accent.border,
      )}
    >
      {/* Header */}
      <div className={cn('flex items-center justify-between px-5 py-4', accent.bg)}>
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-slate-900">{category}</h3>
        </div>
        <div className="flex items-center gap-2">
          {allMet && (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200/60 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-600">
              <Sparkles className="h-3 w-3" />
              All met
            </span>
          )}
          <span
            className={cn(
              'inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold tabular-nums',
              allMet
                ? 'bg-emerald-50 text-emerald-600'
                : 'bg-slate-100 text-slate-500',
            )}
          >
            {metCount}/{skills.length}
          </span>
        </div>
      </div>

      {/* Skills list */}
      <div className="divide-y divide-slate-100/80">
        {skills.map((skill, idx) => (
          <SkillRow
            key={skill.id}
            skill={skill}
            gradient={accent.bar}
            isHovered={hoveredIdx === idx}
            onHover={() => setHoveredIdx(idx)}
            onLeave={() => setHoveredIdx(null)}
          />
        ))}
      </div>
    </div>
  );
}

function BadgeCard({ definition, earned }: { definition: BadgeDefinition; earned?: TeacherBadge }) {
  const isEarned = !!earned;
  const Icon = getBadgeIcon(definition);
  const badgeColor = definition.color || '#6366f1';

  return (
    <div
      className={cn(
        'group relative flex flex-col items-center rounded-2xl border p-4 text-center transition-all duration-300',
        isEarned
          ? 'border-slate-200/80 bg-white shadow-sm hover:shadow-lg hover:-translate-y-1 cursor-default'
          : 'border-slate-100 bg-slate-50/50 opacity-50',
      )}
    >
      {/* Badge circle with glow effect */}
      <div className="relative">
        <div
          className={cn(
            'flex h-14 w-14 items-center justify-center rounded-full transition-all duration-300',
            isEarned && 'group-hover:scale-110',
          )}
          style={{
            backgroundColor: isEarned ? badgeColor : '#cbd5e1',
            boxShadow: isEarned ? `0 4px 14px -2px ${badgeColor}40` : 'none',
          }}
        >
          <Icon className="h-6 w-6 text-white" />
        </div>
        {/* Glow ring on hover */}
        {isEarned && (
          <div
            className="absolute inset-0 rounded-full opacity-0 transition-opacity duration-300 group-hover:opacity-100"
            style={{
              boxShadow: `0 0 20px 4px ${badgeColor}30`,
            }}
          />
        )}
      </div>

      {/* Name */}
      <p className="mt-3 text-xs font-semibold text-slate-900 leading-tight line-clamp-2">{definition.name}</p>

      {/* Date */}
      <p className="mt-1 text-[10px] text-slate-400 h-3.5">
        {isEarned && earned
          ? new Date(earned.awarded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
          : ''}
      </p>

      {/* Tooltip on hover */}
      {isEarned && definition.description && (
        <div className="absolute -top-14 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-all duration-200 pointer-events-none z-10 scale-95 group-hover:scale-100">
          <div className="bg-slate-900 text-white text-[11px] rounded-xl px-3.5 py-2 whitespace-nowrap shadow-xl max-w-[200px] text-center leading-snug">
            {definition.description}
          </div>
          <div className="w-2.5 h-2.5 bg-slate-900 rotate-45 mx-auto -mt-1.5" />
        </div>
      )}
    </div>
  );
}

function RecommendationCard({
  rec,
  index,
  onClick,
}: {
  rec: { course_id: string; course_title: string; skill_name: string; level_taught: number; is_assigned: boolean; _gap: number };
  index: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!rec.is_assigned}
      className={cn(
        'group relative w-full overflow-hidden rounded-2xl border p-5 text-left transition-all duration-300',
        rec.is_assigned
          ? 'border-slate-200/80 bg-white shadow-sm hover:shadow-md hover:-translate-y-0.5 cursor-pointer'
          : 'border-slate-100 bg-slate-50/30 cursor-default',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* Priority indicator */}
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-slate-100 text-[10px] font-bold text-slate-500">
              {index + 1}
            </span>
            {rec.is_assigned && (
              <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 border border-indigo-200/60 px-2 py-0.5 text-[10px] font-semibold text-indigo-600">
                Assigned
              </span>
            )}
          </div>

          <p className={cn(
            'text-sm font-semibold leading-snug',
            rec.is_assigned ? 'text-slate-900' : 'text-slate-500',
          )}>
            {rec.course_title}
          </p>

          <p className="mt-1.5 text-xs text-slate-500">
            Builds{' '}
            <span className="font-semibold text-indigo-600">{rec.skill_name}</span>
            {' '}to {LEVEL_LABELS[rec.level_taught] || `Level ${rec.level_taught}`}
          </p>

          {!rec.is_assigned && (
            <p className="mt-2 text-[11px] text-slate-400 italic">
              Ask your coordinator to assign this course
            </p>
          )}
        </div>

        {rec.is_assigned && (
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-slate-100 transition-all duration-300 group-hover:bg-indigo-50 group-hover:text-indigo-600">
            <ChevronRight className="h-4 w-4 text-slate-400 transition-all duration-300 group-hover:text-indigo-600 group-hover:translate-x-0.5" />
          </div>
        )}
      </div>

      {/* Gap severity indicator */}
      {rec._gap > 0 && (
        <div className="mt-3 flex items-center gap-2">
          <div className="flex gap-0.5">
            {Array.from({ length: Math.min(rec._gap, 5) }).map((_, i) => (
              <div
                key={i}
                className={cn(
                  'h-1 w-4 rounded-full',
                  rec._gap >= 3 ? 'bg-amber-400' : rec._gap >= 2 ? 'bg-sky-400' : 'bg-slate-300',
                )}
              />
            ))}
          </div>
          <span className="text-[10px] text-slate-400">
            {rec._gap} {rec._gap === 1 ? 'level' : 'levels'} to target
          </span>
        </div>
      )}
    </button>
  );
}

// ─── Skeleton ───────────────────────────────────────────────────────────────

function PageSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      {/* Header */}
      <div>
        <div className="h-8 w-56 bg-slate-200 rounded-lg" />
        <div className="h-4 w-80 bg-slate-100 rounded mt-2" />
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-2xl border border-slate-200/80 bg-white p-5">
            <div className="h-3 w-20 bg-slate-100 rounded mb-3" />
            <div className="h-8 w-12 bg-slate-200 rounded" />
          </div>
        ))}
      </div>

      {/* Category cards */}
      {[1, 2].map((i) => (
        <div key={i} className="rounded-2xl border border-slate-200/80 bg-white border-l-4 border-l-slate-200">
          <div className="px-5 py-4 bg-slate-50/50">
            <div className="h-4 w-44 bg-slate-200 rounded" />
          </div>
          <div className="divide-y divide-slate-100">
            {[1, 2, 3].map((j) => (
              <div key={j} className="px-5 py-3.5 flex items-center justify-between">
                <div>
                  <div className="h-4 w-48 bg-slate-200 rounded" />
                  <div className="h-3 w-36 bg-slate-100 rounded mt-1.5" />
                </div>
                <div className="h-2 w-28 bg-slate-100 rounded-full" />
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Badges */}
      <div>
        <div className="h-5 w-28 bg-slate-200 rounded mb-4" />
        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="rounded-2xl border border-slate-100 p-4 flex flex-col items-center gap-2">
              <div className="h-14 w-14 rounded-full bg-slate-200" />
              <div className="h-3 w-16 bg-slate-100 rounded" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Section Divider ────────────────────────────────────────────────────────

function SectionDivider({ title, icon: Icon }: { title: string; icon: React.ElementType }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-slate-400" />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">{title}</h2>
      </div>
      <div className="h-px flex-1 bg-gradient-to-r from-slate-200 to-transparent" />
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
      <div className="flex flex-col items-center justify-center py-24">
        <div className="h-16 w-16 rounded-2xl bg-red-50 flex items-center justify-center mb-4">
          <AlertTriangle className="h-8 w-8 text-red-400" />
        </div>
        <p className="text-base font-semibold text-slate-900">Unable to load growth data</p>
        <p className="text-sm text-slate-500 mt-1">Please try refreshing the page.</p>
      </div>
    );
  }

  // ── Empty state (no skills assigned) ───────────────────────────────────
  if (competency.total_skills === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <div className="h-20 w-20 rounded-2xl bg-gradient-to-br from-slate-100 to-slate-50 flex items-center justify-center mb-5 shadow-sm">
          <Sprout className="h-10 w-10 text-slate-300" />
        </div>
        <h2 className="text-xl font-bold text-slate-900">No Skills Assigned Yet</h2>
        <p className="mt-2 text-sm text-slate-500 max-w-md text-center leading-relaxed">
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

  // ── Badge data (silently handle badge endpoint failures) ───────────────
  const earnedSet = new Set((earnedBadges ?? []).map((b) => b.badge.id));
  const allDefs = badgeDefs ?? [];
  const earnedDefs = allDefs.filter((d) => earnedSet.has(d.id));
  const unearnedDefs = allDefs
    .filter((d) => !earnedSet.has(d.id))
    .sort((a, b) => a.sort_order - b.sort_order)
    .slice(0, 4);

  // ── Recommendations (top 5, assigned-first then by gap desc) ───────────
  const sortedRecs = [...competency.recommendations]
    .map((r) => ({ ...r, _gap: r.target_level - r.current_level }))
    .sort((a, b) => {
      if (a.is_assigned !== b.is_assigned) return a.is_assigned ? -1 : 1;
      return b._gap - a._gap;
    })
    .slice(0, 5);

  // ── Computed stats ─────────────────────────────────────────────────────
  const totalSkills = competency.total_skills;
  const metSkills = competency.skills.filter(
    (s) => !s.has_gap && s.current_level >= s.target_level && s.current_level > 0,
  ).length;
  const growthAreas = competency.total_gaps;

  return (
    <div className="space-y-8">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Professional Growth</h1>
        <p className="mt-1 text-sm text-slate-500">
          Your skills, recognition, and recommended next steps
        </p>
      </div>

      {/* ── Summary Stat Tiles ──────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatTile
          label="Skills Met"
          value={`${metSkills}/${totalSkills}`}
          sublabel={metSkills === totalSkills ? 'All targets reached!' : `${totalSkills - metSkills} remaining`}
          icon={CheckCircle2}
          accent="bg-emerald-500"
        />
        <StatTile
          label="Growth Areas"
          value={growthAreas}
          sublabel={growthAreas === 0 ? 'No gaps identified' : 'Skills to develop'}
          icon={TrendingUp}
          accent="bg-amber-500"
        />
        <StatTile
          label="Badges Earned"
          value={`${earnedDefs.length}/${allDefs.length}`}
          sublabel={earnedDefs.length === allDefs.length && allDefs.length > 0 ? 'Complete collection!' : allDefs.length > 0 ? `${allDefs.length - earnedDefs.length} to unlock` : 'None available'}
          icon={Award}
          accent="bg-indigo-500"
        />
      </div>

      {/* ── Section 1: Skills Overview ──────────────────────────────────── */}
      <SectionDivider title="Skills" icon={Target} />

      <div className="space-y-4">
        {Object.entries(skillsByCategory).map(([category, skills]) => (
          <CategoryCard key={category} category={category} skills={skills} />
        ))}
      </div>

      {/* ── Section 2: Recognition ─────────────────────────────────────── */}
      {allDefs.length > 0 && (
        <>
          <SectionDivider title="Recognition" icon={Award} />

          {earnedDefs.length > 0 ? (
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3">
              {earnedDefs.map((def) => {
                const earned = (earnedBadges ?? []).find((b) => b.badge.id === def.id);
                return <BadgeCard key={def.id} definition={def} earned={earned} />;
              })}
              {/* Unearned badges inline */}
              {unearnedDefs.map((def) => (
                <BadgeCard key={def.id} definition={def} />
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/50 p-8 text-center">
              <Award className="h-8 w-8 text-slate-300 mx-auto mb-3" />
              <p className="text-sm font-medium text-slate-500">No badges earned yet</p>
              <p className="text-xs text-slate-400 mt-1">Complete courses and milestones to earn recognition.</p>
            </div>
          )}
        </>
      )}

      {/* ── Section 3: Recommended Next Steps ──────────────────────────── */}
      {sortedRecs.length > 0 ? (
        <>
          <SectionDivider title="Recommended Next Steps" icon={BookOpen} />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {sortedRecs.map((rec, idx) => (
              <RecommendationCard
                key={`${rec.course_id}-${rec.skill_name}-${idx}`}
                rec={rec}
                index={idx}
                onClick={() => { if (rec.is_assigned) navigate(`/teacher/courses/${rec.course_id}`); }}
              />
            ))}
          </div>
        </>
      ) : competency.total_gaps === 0 ? (
        <>
          <SectionDivider title="Next Steps" icon={BookOpen} />
          <div className="rounded-2xl border border-slate-200/80 bg-gradient-to-br from-emerald-50/50 to-white p-8 text-center shadow-sm">
            <div className="mx-auto h-12 w-12 rounded-full bg-emerald-100 flex items-center justify-center mb-3">
              <CheckCircle2 className="h-6 w-6 text-emerald-500" />
            </div>
            <p className="text-sm font-semibold text-slate-900">You're meeting all your targets</p>
            <p className="text-xs text-slate-500 mt-1">Great work — keep it up.</p>
          </div>
        </>
      ) : null}
    </div>
  );
};
