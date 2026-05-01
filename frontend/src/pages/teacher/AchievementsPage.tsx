// src/pages/teacher/AchievementsPage.tsx
//
// Teacher Gamification Dashboard — personal XP history, earned badges with rarity
// visual treatment, current streak (with freeze tokens), and league standing.
//
// FE-009: complements the Admin gamification page by giving teachers a dedicated
// hub to see their own progress, celebrate badges, and protect their streak.

import React, { useMemo, useState } from 'react';
import axios from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { format, parseISO, isValid } from 'date-fns';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import {
  TrophyIcon,
  BoltIcon,
  FireIcon,
  StarIcon,
  ShieldCheckIcon,
  SparklesIcon,
  LockClosedIcon,
  ArrowRightIcon,
  AcademicCapIcon,
  ClipboardDocumentCheckIcon,
  DocumentCheckIcon,
  CircleStackIcon,
} from '@heroicons/react/24/outline';
import { Loading, useToast, ConfirmDialog } from '../../components/common';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/ui/badge';
import {
  gamificationService,
  type TeacherXPSummary,
  type TeacherBadge,
  type BadgeDefinition,
  type XPTransaction,
  type LeaderboardResponse,
  type StreakFreezeInventory,
  type CurrentLeague,
} from '../../services/gamificationService';
import {
  masteryService,
  mpToNumber,
  type MasterySummary,
  type MasteryHistoryPage,
} from '../../services/masteryService';
import {
  coinsService,
  parseInsufficientCoinsError,
  type CoinBalance,
} from '../../services/coinsService';
// WalletPage removed 2026-04-23; keep the fallback price constant local here
// (used only by the streak-freeze purchase tooltip below).
const DEFAULT_STREAK_FREEZE_PRICE = 50;
import { usePageTitle } from '../../hooks/usePageTitle';
import { useModeLabels } from '../../hooks/useModeLabels';

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(raw: string | null | undefined): string {
  if (!raw) return '—';
  try {
    const d = parseISO(raw);
    return isValid(d) ? format(d, 'dd MMM yyyy') : '—';
  } catch {
    return '—';
  }
}

function fmtShortDay(raw: string): string {
  try {
    const d = parseISO(raw);
    return isValid(d) ? format(d, 'dd MMM') : '';
  } catch {
    return '';
  }
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: string; error?: string } | undefined;
    if (data?.error) return data.error;
    if (data?.detail) return data.detail;
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

// ── Rarity classification ─────────────────────────────────────────────────────
//
// Rarity is inferred from the badge's criteria_value within its criteria_type,
// so "5 streak days" is Common but "100 streak days" is Legendary. This gives
// teachers the dopamine hit of earning a rare badge without requiring the
// backend to store a rarity column (TASK-014 keeps the data model stable).

type Rarity = 'common' | 'rare' | 'epic' | 'legendary';

const RARITY_META: Record<Rarity, { label: string; ring: string; glow: string; chip: string; icon: string }> = {
  common: {
    label: 'Common',
    ring: 'ring-slate-200',
    glow: '',
    chip: 'bg-slate-100 text-slate-700',
    icon: 'text-slate-500',
  },
  rare: {
    label: 'Rare',
    ring: 'ring-sky-300',
    glow: 'shadow-[0_0_0_4px_rgba(14,165,233,0.08)]',
    chip: 'bg-sky-100 text-sky-800',
    icon: 'text-sky-600',
  },
  epic: {
    label: 'Epic',
    ring: 'ring-violet-300',
    glow: 'shadow-[0_0_0_4px_rgba(139,92,246,0.12)]',
    chip: 'bg-violet-100 text-violet-800',
    icon: 'text-violet-600',
  },
  legendary: {
    label: 'Legendary',
    ring: 'ring-amber-300',
    glow: 'shadow-[0_0_0_4px_rgba(245,158,11,0.16)]',
    chip: 'bg-amber-100 text-amber-800',
    icon: 'text-amber-600',
  },
};

function rarityFor(def: BadgeDefinition): Rarity {
  const v = def.criteria_value;
  switch (def.criteria_type) {
    case 'xp_threshold':
      if (v >= 5000) return 'legendary';
      if (v >= 1000) return 'epic';
      if (v >= 250) return 'rare';
      return 'common';
    case 'streak_days':
      if (v >= 60) return 'legendary';
      if (v >= 30) return 'epic';
      if (v >= 7) return 'rare';
      return 'common';
    case 'courses_completed':
      if (v >= 20) return 'legendary';
      if (v >= 10) return 'epic';
      if (v >= 3) return 'rare';
      return 'common';
    case 'content_completed':
      if (v >= 200) return 'legendary';
      if (v >= 50) return 'epic';
      if (v >= 10) return 'rare';
      return 'common';
    case 'manual':
      // Manually-awarded badges are always at least Epic — they're hand-picked.
      return 'epic';
    default:
      return 'common';
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface StatCardProps {
  icon: React.ElementType;
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'primary' | 'amber' | 'orange' | 'emerald' | 'violet';
}

const TONE_CLASSES: Record<NonNullable<StatCardProps['tone']>, { bg: string; icon: string }> = {
  primary: { bg: 'bg-primary-50', icon: 'text-primary-600' },
  amber: { bg: 'bg-amber-50', icon: 'text-amber-600' },
  orange: { bg: 'bg-orange-50', icon: 'text-orange-600' },
  emerald: { bg: 'bg-emerald-50', icon: 'text-emerald-600' },
  violet: { bg: 'bg-violet-50', icon: 'text-violet-600' },
};

function StatCard({ icon: Icon, label, value, hint, tone = 'primary' }: StatCardProps) {
  const t = TONE_CLASSES[tone];
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex items-center gap-3">
        <div className={`h-10 w-10 rounded-lg ${t.bg} flex items-center justify-center flex-shrink-0`}>
          <Icon className={`h-5 w-5 ${t.icon}`} />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-gray-500 truncate">{label}</p>
          <p className="text-xl font-bold text-gray-900 tabular-nums leading-tight">{value}</p>
          {hint && <p className="text-[11px] text-gray-400 mt-0.5 truncate">{hint}</p>}
        </div>
      </div>
    </div>
  );
}

interface BadgeCardProps {
  def: BadgeDefinition;
  earned: boolean;
  awardedAt?: string;
}

function BadgeCard({ def, earned, awardedAt }: BadgeCardProps) {
  const rarity = rarityFor(def);
  const meta = RARITY_META[rarity];
  const baseColor = def.color ?? '#3b82f6';

  return (
    <div
      data-testid={`badge-card-${def.id}`}
      data-earned={earned ? 'true' : 'false'}
      data-rarity={rarity}
      className={`relative rounded-xl border p-4 flex items-center gap-3 transition-all ${
        earned
          ? `border-gray-200 bg-white ring-1 ${meta.ring} ${meta.glow}`
          : 'border-dashed border-gray-200 bg-gray-50/60'
      }`}
    >
      <div
        className={`h-12 w-12 rounded-full flex items-center justify-center flex-shrink-0 ${
          earned ? '' : 'grayscale opacity-60'
        }`}
        style={{ backgroundColor: `${baseColor}1f` }}
      >
        {earned ? (
          <StarIcon className="h-6 w-6" style={{ color: baseColor }} />
        ) : (
          <LockClosedIcon className="h-5 w-5 text-gray-400" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <p className="text-sm font-semibold text-gray-900 truncate">{def.name}</p>
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold uppercase tracking-wide ${meta.chip}`}
          >
            {meta.label}
          </span>
        </div>
        <p className="text-xs text-gray-500 line-clamp-2 mt-0.5">
          {def.description || 'Earn this achievement to unlock.'}
        </p>
        {earned && awardedAt && (
          <p className="text-[11px] text-emerald-600 mt-1 font-medium">
            Earned {fmtDate(awardedAt)}
          </p>
        )}
      </div>
    </div>
  );
}

// ── Mastery Points card (TASK-018) ────────────────────────────────────────────

interface MasteryBreakdown {
  totals: Record<'quiz_mastery' | 'assignment_mastery' | 'course_mastery_bonus' | 'admin_adjust', number>;
  counts: Record<'quiz_mastery' | 'assignment_mastery' | 'course_mastery_bonus' | 'admin_adjust', number>;
}

interface MasteryPointsCardProps {
  totalMp: number;
  breakdown: MasteryBreakdown;
  sparkline: Array<{ day: string; label: string; mp: number }>;
}

function MasteryPointsCard({
  totalMp,
  breakdown,
  sparkline,
}: MasteryPointsCardProps) {
  return (
    <Link
      to="/teacher/mastery"
      className="rounded-xl border border-gray-200 bg-white p-4 hover:bg-gray-50 transition-colors cursor-pointer col-span-2 lg:col-span-1"
      data-testid="achievements-mastery-card"
    >
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-lg bg-emerald-50 flex items-center justify-center flex-shrink-0">
          <AcademicCapIcon className="h-5 w-5 text-emerald-600" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-gray-500 truncate">
            Mastery Points
          </p>
          <p
            className="text-xl font-bold text-gray-900 tabular-nums leading-tight"
            data-testid="achievements-mp-total"
          >
            {totalMp.toFixed(2)}
          </p>
          <div
            className="flex items-center gap-2 mt-1 text-[10px] text-gray-500"
            aria-label="Mastery breakdown"
          >
            <span
              className="inline-flex items-center gap-0.5"
              title="Quiz mastery"
              data-testid="mp-breakdown-quiz"
            >
              <ClipboardDocumentCheckIcon className="h-3 w-3 text-indigo-500" />
              {breakdown.counts.quiz_mastery}
            </span>
            <span
              className="inline-flex items-center gap-0.5"
              title="Assignment mastery"
              data-testid="mp-breakdown-assignment"
            >
              <DocumentCheckIcon className="h-3 w-3 text-violet-500" />
              {breakdown.counts.assignment_mastery}
            </span>
            <span
              className="inline-flex items-center gap-0.5"
              title="Course bonus"
              data-testid="mp-breakdown-course"
            >
              <TrophyIcon className="h-3 w-3 text-emerald-500" />
              {breakdown.counts.course_mastery_bonus}
            </span>
          </div>
        </div>
      </div>
      {/* Sparkline (last 30 days) */}
      {sparkline.some((d) => d.mp > 0) && (
        <div className="mt-2 h-8" data-testid="mp-sparkline">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkline} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
              <Line
                type="monotone"
                dataKey="mp"
                stroke="#10b981"
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="mt-1 text-[10px] text-primary-600 inline-flex items-center gap-0.5">
        View MP history <ArrowRightIcon className="h-3 w-3" />
      </p>
    </Link>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export const AchievementsPage: React.FC = () => {
  usePageTitle('My Achievements');
  const toast = useToast();
  const queryClient = useQueryClient();
  const { label } = useModeLabels();
  const [confirmFreeze, setConfirmFreeze] = useState(false);
  const [buyFreezeOpen, setBuyFreezeOpen] = useState(false);

  const summaryQ = useQuery<TeacherXPSummary>({
    queryKey: ['teacherGamificationSummary'],
    queryFn: () => gamificationService.getSummary(),
  });

  const badgesQ = useQuery<TeacherBadge[]>({
    queryKey: ['teacherMyBadges'],
    queryFn: () => gamificationService.getMyBadges(),
  });

  const badgeDefsQ = useQuery<BadgeDefinition[]>({
    queryKey: ['teacherBadgeDefinitions'],
    queryFn: () => gamificationService.getBadgeDefinitions(),
  });

  const xpHistoryQ = useQuery<XPTransaction[]>({
    queryKey: ['teacherXPHistory'],
    queryFn: () => gamificationService.getXPHistory(),
  });

  const leaderboardQ = useQuery<LeaderboardResponse>({
    queryKey: ['teacherLeaderboard', 'weekly'],
    queryFn: () => gamificationService.getLeaderboard('weekly'),
  });

  // TASK-015 — freeze token inventory (drives "Use freeze" button gating).
  const inventoryQ = useQuery<StreakFreezeInventory>({
    queryKey: ['teacherStreakFreezeInventory'],
    queryFn: () => gamificationService.getStreakFreezeInventory(),
  });

  // TASK-016 — current league (replaces placeholder hero card).
  const currentLeagueQ = useQuery<CurrentLeague>({
    queryKey: ['teacherCurrentLeague'],
    queryFn: () => gamificationService.getCurrentLeague(),
    // League data is optional — a failure shouldn't wedge the whole page.
    retry: false,
  });

  // TASK-018 — Mastery Points summary + recent ledger page for the sparkline.
  // Failures are non-fatal; the MP card renders a zero-state rather than
  // wedging the whole achievements page.
  const masterySummaryQ = useQuery<MasterySummary>({
    queryKey: ['teacherMasterySummary'],
    queryFn: () => masteryService.getTeacherSummary(),
    retry: false,
  });

  const masteryHistoryQ = useQuery<MasteryHistoryPage>({
    queryKey: ['teacherMasteryHistory', 1, ''],
    queryFn: () => masteryService.getTeacherHistory({ page: 1 }),
    retry: false,
  });

  // TASK-019 / FE-014 — coin balance for wallet pill + buy-freeze flow.
  const coinBalanceQ = useQuery<CoinBalance>({
    queryKey: ['teacherCoinBalance'],
    queryFn: () => coinsService.getBalance(),
    retry: false,
  });

  const buyFreezeMutation = useMutation({
    mutationFn: () => coinsService.purchaseStreakFreeze(),
    onSuccess: (data) => {
      toast.success(
        `Streak-freeze token purchased! New balance: ${data.balance.balance.toLocaleString()} coins.`,
      );
      queryClient.invalidateQueries({ queryKey: ['teacherCoinBalance'] });
      queryClient.invalidateQueries({ queryKey: ['teacherStreakFreezeInventory'] });
      queryClient.invalidateQueries({ queryKey: ['teacherCoinHistory'] });
      setBuyFreezeOpen(false);
    },
    onError: (err: unknown) => {
      const insufficient = parseInsufficientCoinsError(err);
      if (insufficient) {
        toast.error(
          `Not enough coins — you have ${insufficient.balance.toLocaleString()}, need ${insufficient.price.toLocaleString()}.`,
        );
      } else {
        toast.error('Could not complete purchase. Please try again.');
      }
      setBuyFreezeOpen(false);
    },
  });

  const useFreezeMutation = useMutation({
    mutationFn: () => gamificationService.useStreakFreeze(),
    onSuccess: (res) => {
      toast.success(
        `Streak protected! ${res.freezes_remaining} freeze${res.freezes_remaining === 1 ? '' : 's'} left.`,
      );
      queryClient.invalidateQueries({ queryKey: ['teacherGamificationSummary'] });
      queryClient.invalidateQueries({ queryKey: ['teacherStreakFreezeInventory'] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, 'Could not use streak freeze'));
    },
    onSettled: () => setConfirmFreeze(false),
  });

  // ── Derived data ────────────────────────────────────────────────────────────

  const summary = summaryQ.data;
  const myBadges = badgesQ.data ?? [];
  const allBadges = badgeDefsQ.data ?? [];
  const xpHistory = xpHistoryQ.data ?? [];

  const earnedBadgeIds = useMemo(
    () => new Set(myBadges.map((b) => b.badge.id)),
    [myBadges],
  );

  const awardedAtByBadge = useMemo(() => {
    const map = new Map<string, string>();
    myBadges.forEach((b) => map.set(b.badge.id, b.awarded_at));
    return map;
  }, [myBadges]);

  // Build a simple daily XP trend for the last 14 days.
  const xpTrend = useMemo(() => {
    const today = new Date();
    const bucket = new Map<string, number>();
    for (let i = 13; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const key = format(d, 'yyyy-MM-dd');
      bucket.set(key, 0);
    }
    xpHistory.forEach((tx) => {
      if (!tx.created_at) return;
      try {
        const d = parseISO(tx.created_at);
        if (!isValid(d)) return;
        const key = format(d, 'yyyy-MM-dd');
        if (bucket.has(key)) {
          bucket.set(key, (bucket.get(key) ?? 0) + tx.xp_amount);
        }
      } catch {
        /* skip */
      }
    });
    return Array.from(bucket.entries()).map(([day, xp]) => ({
      day,
      label: fmtShortDay(day),
      xp,
    }));
  }, [xpHistory]);

  // ── MP derivations (TASK-018) ─────────────────────────────────────────────
  const masterySummary = masterySummaryQ.data;
  const masteryTxns = masteryHistoryQ.data?.results ?? [];

  const masteryBreakdown = useMemo(() => {
    const totals = {
      quiz_mastery: 0,
      assignment_mastery: 0,
      course_mastery_bonus: 0,
      admin_adjust: 0,
    };
    const counts = {
      quiz_mastery: 0,
      assignment_mastery: 0,
      course_mastery_bonus: 0,
      admin_adjust: 0,
    };
    masteryTxns.forEach((tx) => {
      if (tx.reason in totals) {
        totals[tx.reason] += mpToNumber(tx.amount);
        counts[tx.reason] += 1;
      }
    });
    return { totals, counts };
  }, [masteryTxns]);

  // 30-day MP sparkline — bucket ledger entries by day.
  const masterySparkline = useMemo(() => {
    const today = new Date();
    const bucket = new Map<string, number>();
    for (let i = 29; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      bucket.set(format(d, 'yyyy-MM-dd'), 0);
    }
    masteryTxns.forEach((tx) => {
      if (!tx.created_at) return;
      try {
        const d = parseISO(tx.created_at);
        if (!isValid(d)) return;
        const key = format(d, 'yyyy-MM-dd');
        if (bucket.has(key)) {
          bucket.set(key, (bucket.get(key) ?? 0) + mpToNumber(tx.amount));
        }
      } catch {
        /* skip */
      }
    });
    return Array.from(bucket.entries()).map(([day, mp]) => ({
      day,
      label: fmtShortDay(day),
      mp,
    }));
  }, [masteryTxns]);

  const myLeagueEntry = useMemo(() => {
    if (!leaderboardQ.data || !summary) return null;
    // The backend already filters the leaderboard to the current tenant;
    // match the viewer's entry by their XP summary (top_xp === total_xp is a
    // near-guaranteed unique signal, but we fall back to name match via the
    // auth store if needed — here we look for exact level + total_xp parity).
    const entries = leaderboardQ.data.entries;
    return (
      entries.find((e) => e.total_xp === summary.total_xp && e.level === summary.level) ?? null
    );
  }, [leaderboardQ.data, summary]);

  const progressPct = useMemo(() => {
    if (!summary?.next_level_xp) return 100;
    return Math.min(100, Math.round((summary.total_xp / summary.next_level_xp) * 100));
  }, [summary]);

  const isLoading =
    summaryQ.isLoading || badgesQ.isLoading || badgeDefsQ.isLoading || xpHistoryQ.isLoading;

  if (isLoading) return <Loading />;

  if (!summary) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Achievements</h1>
          <p className="mt-1 text-sm text-gray-500">
            Your XP, badges, streak, and league standing all in one place.
          </p>
        </div>
        <div className="rounded-xl border border-dashed border-gray-200 bg-white p-12 text-center">
          <SparklesIcon className="h-10 w-10 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-gray-500">
            We couldn't load your gamification summary right now. Please try again shortly.
          </p>
        </div>
      </div>
    );
  }

  if (summary.opted_out) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Achievements</h1>
          <p className="mt-1 text-sm text-gray-500">
            Your XP, badges, streak, and league standing all in one place.
          </p>
        </div>
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-6">
          <div className="flex items-center gap-3">
            <ShieldCheckIcon className="h-6 w-6 text-amber-600 flex-shrink-0" />
            <div>
              <p className="text-sm font-semibold text-amber-900">
                You've opted out of gamification
              </p>
              <p className="text-xs text-amber-800 mt-0.5">
                Points, badges and leaderboards are hidden for your account. You can re-enable this
                in Settings → Preferences whenever you'd like.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // TASK-015 — prefer the real inventory token count when available; fall back
  // to "any active streak" when the inventory call hasn't resolved yet so the
  // button doesn't flicker disabled on first paint.
  const inventory = inventoryQ.data;
  const tokenCount = inventory?.token_count;
  const canUseFreeze =
    typeof tokenCount === 'number'
      ? tokenCount > 0 && summary.current_streak > 0
      : summary.current_streak > 0;
  const currentLeague = currentLeagueQ.data;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Achievements</h1>
          <p className="mt-1 text-sm text-gray-500">
            Your XP, badges, streak, and league standing all in one place.
          </p>
        </div>
      </div>

      {/* Level + progress hero */}
      <div className="rounded-2xl bg-gradient-to-r from-primary-600 via-primary-500 to-sky-500 p-5 text-white shadow-sm">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="h-14 w-14 rounded-2xl bg-white/15 backdrop-blur-sm flex items-center justify-center flex-shrink-0">
            <TrophyIcon className="h-7 w-7 text-white" />
          </div>
          <div className="flex-1 min-w-[220px]">
            <p className="text-xs uppercase tracking-wide text-white/70 font-semibold">
              Level {summary.level}
            </p>
            <p className="text-lg font-bold leading-tight">{summary.level_name}</p>
            <div className="mt-3">
              <div
                role="progressbar"
                aria-valuenow={progressPct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Progress to next level"
                className="relative h-2 rounded-full bg-white/20 overflow-hidden"
              >
                <div
                  className="h-full bg-white rounded-full transition-all duration-500"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <p className="mt-1.5 text-[11px] text-white/80 tabular-nums">
                {summary.total_xp.toLocaleString()} XP
                {summary.next_level_xp != null
                  ? ` · ${summary.xp_to_next_level.toLocaleString()} to next level`
                  : ' · Max level reached'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <StatCard
          icon={BoltIcon}
          label="XP this week"
          value={summary.xp_this_week.toLocaleString()}
          hint={`${summary.xp_this_month.toLocaleString()} this month`}
          tone="amber"
        />
        <StatCard
          icon={FireIcon}
          label="Current streak"
          value={`${summary.current_streak}d`}
          hint={`Longest: ${summary.longest_streak}d`}
          tone="orange"
        />
        <StatCard
          icon={StarIcon}
          label="Badges earned"
          value={`${myBadges.length}/${allBadges.length || myBadges.length}`}
          hint="Keep learning to unlock more"
          tone="violet"
        />
        {/* TASK-018 — Mastery Points card with breakdown + sparkline */}
        <MasteryPointsCard
          totalMp={mpToNumber(masterySummary?.total_mastery_points)}
          breakdown={masteryBreakdown}
          sparkline={masterySparkline}
        />
        <div
          className="rounded-xl border border-gray-200 bg-white p-4"
          data-testid="achievements-league-card"
        >
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-primary-50 flex items-center justify-center flex-shrink-0">
              <TrophyIcon className="h-5 w-5 text-primary-600" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-gray-500 truncate">{label('league')}</p>
              <p className="text-xl font-bold text-gray-900 tabular-nums leading-tight">
                {currentLeague?.tier_name ?? (myLeagueEntry ? `#${myLeagueEntry.rank}` : '—')}
              </p>
              <p className="text-[11px] text-gray-400 mt-0.5 truncate">
                {currentLeague?.tier_code
                  ? `${currentLeague.members.length} in cohort`
                  : 'Weekly league'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Streak + XP trend */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Streak + freeze card */}
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <div className="flex items-center gap-2 mb-3">
            <FireIcon className="h-4 w-4 text-orange-500" />
            <h2 className="text-sm font-semibold text-gray-900">{label('streak')}</h2>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-bold text-gray-900 tabular-nums">
              {summary.current_streak}
            </span>
            <span className="text-sm text-gray-500">day{summary.current_streak === 1 ? '' : 's'}</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Last XP earned {fmtDate(summary.last_xp_at)}
          </p>

          <div className="mt-4 pt-4 border-t border-gray-100">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs font-semibold text-gray-900">
                  Streak freeze
                  {typeof tokenCount === 'number' && (
                    <span
                      className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full bg-primary-50 text-primary-700 font-semibold"
                      data-testid="streak-freeze-token-count"
                    >
                      {tokenCount} token{tokenCount === 1 ? '' : 's'}
                    </span>
                  )}
                </p>
                <p className="text-[11px] text-gray-500 line-clamp-2">
                  {tokenCount === 0
                    ? 'No tokens — earn one by keeping your streak alive.'
                    : 'Missed a day? Burn a freeze token to keep your streak alive.'}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={!canUseFreeze}
                onClick={() => setConfirmFreeze(true)}
                leftIcon={<ShieldCheckIcon className="h-4 w-4" />}
                data-testid="streak-freeze-button"
              >
                {tokenCount === 0 ? 'No tokens' : 'Use freeze'}
              </Button>
            </div>
            {/* TASK-019 / FE-014 — Buy-freeze secondary action.
                Visible only when the streak is active but the teacher has
                run out of tokens. */}
            {summary.current_streak > 0 && tokenCount === 0 && (
              <div className="mt-3 flex items-center justify-between gap-2 rounded-lg border border-amber-100 bg-amber-50/60 px-3 py-2">
                <p className="text-[11px] text-amber-800">
                  Buy a token with Puddle Coins to keep your streak safe.
                </p>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => setBuyFreezeOpen(true)}
                  leftIcon={<CircleStackIcon className="h-4 w-4" />}
                  data-testid="buy-freeze-button"
                >
                  Buy freeze token
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* XP trend chart */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 lg:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <BoltIcon className="h-4 w-4 text-amber-500" />
            <h2 className="text-sm font-semibold text-gray-900">XP earned (last 14 days)</h2>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={xpTrend} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#94a3b8' }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickLine={false} axisLine={false} width={30} />
                <Tooltip
                  cursor={{ stroke: '#e2e8f0', strokeWidth: 1 }}
                  formatter={(v: number) => [`${v} XP`, 'Earned']}
                  labelFormatter={(l: string) => `Day: ${l}`}
                  contentStyle={{ fontSize: 11, borderRadius: 8 }}
                />
                <Line
                  type="monotone"
                  dataKey="xp"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  activeDot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Badges grid */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <div className="flex items-center justify-between gap-2 mb-4">
          <div className="flex items-center gap-2">
            <StarIcon className="h-4 w-4 text-violet-500" />
            <h2 className="text-sm font-semibold text-gray-900">Badges</h2>
            <Badge variant="secondary">{myBadges.length} earned</Badge>
          </div>
          <p className="text-xs text-gray-400">
            Rarity is inferred from each badge's difficulty.
          </p>
        </div>
        {allBadges.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/60 p-8 text-center">
            <SparklesIcon className="h-8 w-8 text-gray-300 mx-auto mb-2" />
            <p className="text-xs text-gray-500">No badges are configured yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {allBadges.map((def) => (
              <BadgeCard
                key={def.id}
                def={def}
                earned={earnedBadgeIds.has(def.id)}
                awardedAt={awardedAtByBadge.get(def.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Recent XP activity */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3.5 border-b border-gray-100">
          <BoltIcon className="h-4 w-4 text-amber-500" />
          <h2 className="text-sm font-semibold text-gray-900">Recent XP activity</h2>
        </div>
        {xpHistory.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-500">
            No XP earned yet — complete a lesson to get started.
          </div>
        ) : (
          <ul className="divide-y divide-gray-50">
            {xpHistory.slice(0, 10).map((tx) => (
              <li
                key={tx.id}
                className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50 transition-colors"
              >
                <div className="h-8 w-8 rounded-full bg-amber-50 flex items-center justify-center flex-shrink-0">
                  <BoltIcon className="h-4 w-4 text-amber-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {(tx.description || tx.reason || 'XP awarded').replace(/_/g, ' ')}
                  </p>
                  <p className="text-[11px] text-gray-500">{fmtDate(tx.created_at)}</p>
                </div>
                <span
                  className={`text-sm font-semibold tabular-nums ${
                    tx.xp_amount >= 0 ? 'text-emerald-600' : 'text-red-600'
                  }`}
                >
                  {tx.xp_amount >= 0 ? '+' : ''}
                  {tx.xp_amount}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ConfirmDialog
        isOpen={confirmFreeze}
        title="Use streak freeze"
        message="This will consume one freeze token to protect your current streak for today. Continue?"
        confirmLabel="Use freeze"
        onConfirm={() => useFreezeMutation.mutate()}
        onClose={() => setConfirmFreeze(false)}
        loading={useFreezeMutation.isPending}
      />

      {/* TASK-019 / FE-014 — Buy freeze token confirm */}
      <ConfirmDialog
        isOpen={buyFreezeOpen}
        title="Buy streak freeze token"
        message={
          coinBalanceQ.data
            ? `Spend ${(coinBalanceQ.data.price_streak_freeze ?? DEFAULT_STREAK_FREEZE_PRICE).toLocaleString()} coins to mint one freeze token. You have ${coinBalanceQ.data.balance.toLocaleString()} coins.`
            : `Spend ${DEFAULT_STREAK_FREEZE_PRICE.toLocaleString()} coins to mint one freeze token.`
        }
        confirmLabel="Buy"
        variant="warning"
        onConfirm={() => buyFreezeMutation.mutate()}
        onClose={() => setBuyFreezeOpen(false)}
        loading={buyFreezeMutation.isPending}
      />
    </div>
  );
};

export default AchievementsPage;
