// src/pages/student/AchievementsPage.tsx
//
// Student achievements page — points, streaks, badges, and gamification progress.

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Trophy,
  Flame,
  Star,
  BookOpen,
  GraduationCap,
  ClipboardCheck,
  Zap,
  Compass,
  CheckCircle2,
  Lock,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { studentService } from '../../services/studentService';
import type { StudentGamificationSummary } from '../../services/studentService';
import { usePageTitle } from '../../hooks/usePageTitle';

// ─── Constants ───────────────────────────────────────────────────────────────

const BREAKDOWN_ITEMS: {
  key: keyof StudentGamificationSummary['points_breakdown'];
  label: string;
  icon: React.ElementType;
  gradient: string;
  bg: string;
}[] = [
  {
    key: 'content_completion',
    label: 'Content Completion',
    icon: BookOpen,
    gradient: 'from-blue-500 to-blue-600',
    bg: 'bg-blue-50',
  },
  {
    key: 'course_completion',
    label: 'Course Completion',
    icon: GraduationCap,
    gradient: 'from-emerald-500 to-emerald-600',
    bg: 'bg-emerald-50',
  },
  {
    key: 'assignment_submission',
    label: 'Assignment Submission',
    icon: ClipboardCheck,
    gradient: 'from-violet-500 to-violet-600',
    bg: 'bg-violet-50',
  },
  {
    key: 'streak_bonus',
    label: 'Streak Bonus',
    icon: Flame,
    gradient: 'from-orange-500 to-orange-600',
    bg: 'bg-orange-50',
  },
  {
    key: 'quest_bonus',
    label: 'Quest Bonus',
    icon: Compass,
    gradient: 'from-amber-500 to-amber-600',
    bg: 'bg-amber-50',
  },
];

// ─── Skeleton Loaders ────────────────────────────────────────────────────────

function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 animate-pulse ${className}`}>
      <div className="h-4 w-24 bg-slate-200 rounded mb-4" />
      <div className="h-8 w-20 bg-slate-200 rounded mb-2" />
      <div className="h-3 w-32 bg-slate-100 rounded" />
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <div className="h-7 w-48 bg-slate-200 rounded animate-pulse" />
        <div className="h-4 w-72 bg-slate-100 rounded animate-pulse mt-2" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonCard key={i} className="h-44" />
        ))}
      </div>
    </div>
  );
}

// ─── Progress Ring ───────────────────────────────────────────────────────────

function ProgressRing({
  percentage,
  size = 80,
  strokeWidth = 6,
  color = '#6366f1',
  bgColor = '#e2e8f0',
}: {
  percentage: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  bgColor?: string;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percentage / 100) * circumference;

  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={bgColor}
        strokeWidth={strokeWidth}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        className="transition-all duration-1000 ease-out"
      />
    </svg>
  );
}

// ─── Hero Stats Row ──────────────────────────────────────────────────────────

function HeroStats({ data }: { data: StudentGamificationSummary }) {
  const nextBadge = data.badges.find((b) => !b.unlocked);
  const unlockedCount = data.badges.filter((b) => b.unlocked).length;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {/* Total Points */}
      <div className="relative overflow-hidden bg-gradient-to-br from-indigo-500 to-indigo-700 rounded-2xl shadow-lg shadow-indigo-200/50 p-6 text-white">
        <div className="absolute top-0 right-0 w-32 h-32 bg-white/5 rounded-full -translate-y-8 translate-x-8" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-white/5 rounded-full translate-y-6 -translate-x-6" />
        <div className="relative">
          <div className="flex items-center gap-2 mb-3">
            <div className="p-2 bg-white/20 rounded-xl backdrop-blur-sm">
              <Trophy className="h-5 w-5" />
            </div>
            <span className="text-sm font-medium text-indigo-100">Total Points</span>
          </div>
          <p className="text-4xl font-extrabold tabular-nums tracking-tight">
            {data.points_total.toLocaleString()}
          </p>
          <p className="text-sm text-indigo-200 mt-1">
            {unlockedCount} badge{unlockedCount !== 1 ? 's' : ''} unlocked
          </p>
        </div>
      </div>

      {/* Current Streak */}
      <div className="relative overflow-hidden bg-gradient-to-br from-amber-500 to-orange-600 rounded-2xl shadow-lg shadow-amber-200/50 p-6 text-white">
        <div className="absolute top-0 right-0 w-32 h-32 bg-white/5 rounded-full -translate-y-8 translate-x-8" />
        <div className="relative">
          <div className="flex items-center gap-2 mb-3">
            <div className="p-2 bg-white/20 rounded-xl backdrop-blur-sm">
              <Flame className="h-5 w-5" />
            </div>
            <span className="text-sm font-medium text-amber-100">Current Streak</span>
          </div>
          <p className="text-4xl font-extrabold tabular-nums tracking-tight">
            {data.streak.current_days}
            <span className="text-lg font-semibold ml-1">day{data.streak.current_days !== 1 ? 's' : ''}</span>
          </p>
          <p className="text-sm text-amber-200 mt-1">
            Target: {data.streak.target_days} days
          </p>
          {/* Streak progress bar */}
          <div className="mt-3">
            <div className="w-full bg-white/20 rounded-full h-2">
              <div
                className="bg-white h-2 rounded-full transition-all duration-700 ease-out"
                style={{
                  width: `${Math.min(100, (data.streak.current_days / data.streak.target_days) * 100)}%`,
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Next Badge */}
      <div className="relative overflow-hidden bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 sm:col-span-2 lg:col-span-1">
        <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-50/50 rounded-full -translate-y-8 translate-x-8" />
        <div className="relative">
          <div className="flex items-center gap-2 mb-3">
            <div className="p-2 bg-amber-50 rounded-xl">
              <Star className="h-5 w-5 text-amber-500" />
            </div>
            <span className="text-sm font-medium text-slate-500">Next Badge</span>
          </div>
          {nextBadge ? (
            <div className="flex items-center gap-4">
              <ProgressRing
                percentage={nextBadge.progress_percentage}
                size={72}
                strokeWidth={6}
                color={nextBadge.color || '#6366f1'}
              />
              <div className="min-w-0 flex-1">
                <p className="text-base font-bold text-slate-900 truncate">{nextBadge.name}</p>
                <p className="text-sm text-slate-500">Level {nextBadge.level}</p>
                <p className="text-xs text-slate-400 mt-1">
                  {data.points_total.toLocaleString()} / {nextBadge.min_points.toLocaleString()} pts
                </p>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <div className="p-3 bg-gradient-to-br from-amber-400 to-amber-500 rounded-full">
                <Sparkles className="h-6 w-6 text-white" />
              </div>
              <div>
                <p className="text-base font-bold text-slate-900">All Badges Unlocked!</p>
                <p className="text-sm text-slate-500">You've earned every badge</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Points Breakdown ────────────────────────────────────────────────────────

function PointsBreakdown({ data }: { data: StudentGamificationSummary }) {
  const maxPoints = Math.max(
    ...Object.values(data.points_breakdown),
    1, // avoid division by zero
  );

  return (
    <div>
      <h2 className="text-[15px] font-semibold text-slate-900 mb-3">Points Breakdown</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {BREAKDOWN_ITEMS.map((item) => {
          const points = data.points_breakdown[item.key];
          const percentage = maxPoints > 0 ? (points / maxPoints) * 100 : 0;
          const Icon = item.icon;

          return (
            <div
              key={item.key}
              className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-5 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className={`p-2.5 rounded-xl ${item.bg}`}>
                  <Icon className="h-5 w-5 text-slate-700" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-slate-700 truncate">{item.label}</p>
                  <p className="text-lg font-bold text-slate-900 tabular-nums">{points.toLocaleString()} pts</p>
                </div>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                <div
                  className={`h-2.5 rounded-full bg-gradient-to-r ${item.gradient} transition-all duration-700 ease-out`}
                  style={{ width: `${percentage}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Badges Grid ─────────────────────────────────────────────────────────────

function BadgesGrid({ data }: { data: StudentGamificationSummary }) {
  if (data.badges.length === 0) {
    return (
      <div>
        <h2 className="text-[15px] font-semibold text-slate-900 mb-3">Badges</h2>
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-8 text-center">
          <Star className="h-8 w-8 mx-auto mb-3 text-slate-200" />
          <p className="text-[13px] font-medium text-slate-900">No badges available yet.</p>
          <p className="text-[13px] text-slate-400 mt-1">Keep learning to unlock badges!</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-[15px] font-semibold text-slate-900 mb-3">Badges</h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        {data.badges.map((badge) => (
          <div
            key={badge.key}
            className={`relative bg-white rounded-2xl border shadow-sm p-5 text-center transition-all duration-300 ${
              badge.unlocked
                ? 'border-slate-200/80 hover:shadow-lg hover:-translate-y-0.5'
                : 'border-slate-100 opacity-60'
            }`}
          >
            {/* Unlocked checkmark */}
            {badge.unlocked && (
              <div className="absolute top-3 right-3">
                <CheckCircle2 className="h-5 w-5 text-emerald-500" />
              </div>
            )}

            {/* Badge circle */}
            <div
              className={`mx-auto h-16 w-16 rounded-full flex items-center justify-center mb-3 transition-all duration-300 ${
                badge.unlocked ? 'shadow-md' : 'grayscale'
              }`}
              style={{
                backgroundColor: badge.unlocked ? badge.color || '#6366f1' : '#cbd5e1',
              }}
            >
              {badge.unlocked ? (
                <Star className="h-7 w-7 text-white" />
              ) : (
                <Lock className="h-6 w-6 text-slate-400" />
              )}
            </div>

            {/* Badge name */}
            <p className="text-[13px] font-semibold text-slate-900 truncate">{badge.name}</p>

            {/* Level */}
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold mt-1 bg-indigo-50 text-indigo-700">
              Level {badge.level}
            </span>

            {/* Progress / Points */}
            {badge.unlocked ? (
              <p className="text-[11px] text-emerald-600 font-medium mt-2">
                Unlocked
              </p>
            ) : (
              <div className="mt-3">
                <div className="w-full bg-slate-100 rounded-full h-1.5 mb-1.5 overflow-hidden">
                  <div
                    className="h-1.5 rounded-full bg-gradient-to-r from-indigo-400 to-indigo-600 transition-all duration-700 ease-out"
                    style={{ width: `${badge.progress_percentage}%` }}
                  />
                </div>
                <p className="text-[10px] text-slate-400 tabular-nums">
                  {badge.progress_percentage}% — {badge.min_points.toLocaleString()}
                  {badge.max_points ? ` / ${badge.max_points.toLocaleString()}` : ''} pts
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Streak Tracker ──────────────────────────────────────────────────────────

function StreakTracker({ data }: { data: StudentGamificationSummary }) {
  const { current_days, target_days } = data.streak;

  // Build last 7 days labels and active status.
  // We mark days as "active" for the most recent `current_days` days (capped at 7).
  const today = new Date();
  const days = Array.from({ length: 7 }).map((_, i) => {
    const date = new Date(today);
    date.setDate(today.getDate() - (6 - i));
    const dayLabel = date.toLocaleDateString('en-US', { weekday: 'short' });
    const dayNum = date.getDate();
    const isActive = i >= 7 - Math.min(current_days, 7);
    const isToday = i === 6;
    return { dayLabel, dayNum, isActive, isToday };
  });

  const streakPercentage = target_days > 0 ? Math.min(100, (current_days / target_days) * 100) : 0;

  return (
    <div>
      <h2 className="text-[15px] font-semibold text-slate-900 mb-3">Streak Tracker</h2>
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-gradient-to-br from-amber-400 to-orange-500 rounded-xl shadow-md shadow-amber-200/50">
              <Flame className="h-6 w-6 text-white" />
            </div>
            <div>
              <p className="text-2xl font-extrabold text-slate-900 tabular-nums">
                {current_days} day{current_days !== 1 ? 's' : ''}
              </p>
              <p className="text-sm text-slate-500">
                {current_days >= target_days
                  ? 'Target reached!'
                  : `${target_days - current_days} day${target_days - current_days !== 1 ? 's' : ''} to target`}
              </p>
            </div>
          </div>

          {/* Target progress */}
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex-1 sm:w-40">
              <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                <span>Target Progress</span>
                <span>{Math.round(streakPercentage)}%</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                <div
                  className="h-2.5 rounded-full bg-gradient-to-r from-amber-400 to-orange-500 transition-all duration-700 ease-out"
                  style={{ width: `${streakPercentage}%` }}
                />
              </div>
            </div>
            <Zap
              className={`h-5 w-5 flex-shrink-0 ${
                current_days >= target_days ? 'text-amber-500' : 'text-slate-300'
              }`}
            />
          </div>
        </div>

        {/* Calendar row: last 7 days */}
        <div className="grid grid-cols-7 gap-2 sm:gap-3">
          {days.map((day, i) => (
            <div key={i} className="flex flex-col items-center gap-1.5">
              <span className="text-[10px] font-medium text-slate-400 uppercase">{day.dayLabel}</span>
              <div
                className={`w-10 h-10 sm:w-12 sm:h-12 rounded-full flex items-center justify-center text-sm font-bold transition-all duration-300 ${
                  day.isActive
                    ? 'bg-gradient-to-br from-emerald-400 to-emerald-600 text-white shadow-md shadow-emerald-200/50'
                    : 'bg-slate-100 text-slate-400'
                } ${day.isToday ? 'ring-2 ring-offset-2 ring-indigo-400' : ''}`}
              >
                {day.dayNum}
              </div>
              {day.isActive ? (
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              ) : (
                <div className="w-1.5 h-1.5 rounded-full bg-slate-200" />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Empty State ─────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-12 text-center">
      <div className="mx-auto w-16 h-16 bg-gradient-to-br from-indigo-100 to-amber-100 rounded-full flex items-center justify-center mb-4">
        <Trophy className="h-8 w-8 text-indigo-500" />
      </div>
      <h3 className="text-lg font-bold text-slate-900 mb-2">Start your learning journey!</h3>
      <p className="text-sm text-slate-500 max-w-md mx-auto">
        Complete courses, submit assignments, and build streaks to earn your first points and unlock badges.
      </p>
    </div>
  );
}

// ─── Error State ─────────────────────────────────────────────────────────────

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-2xl p-8 text-center">
      <div className="mx-auto w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mb-3">
        <Zap className="h-6 w-6 text-red-500" />
      </div>
      <p className="text-sm font-medium text-red-900 mb-1">Failed to load achievements</p>
      <p className="text-sm text-red-600 mb-4">Something went wrong. Please try again.</p>
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
      >
        <RefreshCw className="h-4 w-4" />
        Retry
      </button>
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export const AchievementsPage: React.FC = () => {
  usePageTitle('Achievements');

  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery<StudentGamificationSummary>({
    queryKey: ['studentGamification'],
    queryFn: () => studentService.getGamificationSummary(),
  });

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Achievements</h1>
          <p className="mt-1 text-[13px] text-slate-500">Track your learning progress and rewards.</p>
        </div>
        <LoadingSkeleton />
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Achievements</h1>
          <p className="mt-1 text-[13px] text-slate-500">Track your learning progress and rewards.</p>
        </div>
        <ErrorState onRetry={() => refetch()} />
      </div>
    );
  }

  // Empty / no data
  if (!data || (data.points_total === 0 && data.badges.length === 0)) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Achievements</h1>
          <p className="mt-1 text-[13px] text-slate-500">Track your learning progress and rewards.</p>
        </div>
        <EmptyState />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Achievements</h1>
        <p className="mt-1 text-[13px] text-slate-500">Track your learning progress and rewards.</p>
      </div>

      {/* Section 1: Hero Stats Row */}
      <HeroStats data={data} />

      {/* Section 2: Points Breakdown */}
      <PointsBreakdown data={data} />

      {/* Section 3: Badges Grid */}
      <BadgesGrid data={data} />

      {/* Section 4: Streak Tracker */}
      <StreakTracker data={data} />
    </div>
  );
};
