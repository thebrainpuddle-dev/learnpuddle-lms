// src/pages/teacher/GamificationPage.tsx

import { useEffect, useState } from 'react';
import { useGamificationStore } from '../../stores/gamificationStore';
import { useAuthStore } from '../../stores/authStore';
import type { BadgeDefinition, TeacherBadge } from '../../services/gamificationService';

// ── Helpers ──────────────────────────────────────────────────────────

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);
  const diffWeek = Math.floor(diffDay / 7);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin} minute${diffMin > 1 ? 's' : ''} ago`;
  if (diffHr < 24) return `${diffHr} hour${diffHr > 1 ? 's' : ''} ago`;
  if (diffDay === 1) return 'yesterday';
  if (diffDay < 7) return `${diffDay} days ago`;
  if (diffWeek === 1) return '1 week ago';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

const CATEGORY_COLORS: Record<string, string> = {
  milestone: 'bg-blue-100 text-blue-800',
  streak: 'bg-orange-100 text-orange-800',
  completion: 'bg-green-100 text-green-800',
  skill: 'bg-purple-100 text-purple-800',
  special: 'bg-yellow-100 text-yellow-800',
};

const REASON_LABELS: Record<string, { label: string; icon: string }> = {
  content_completion: { label: 'Content Completed', icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
  course_completion: { label: 'Course Completed', icon: 'M4.26 10.147a60.436 60.436 0 00-.491 6.347A48.627 48.627 0 0112 20.904a48.627 48.627 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.57 50.57 0 00-2.658-.813A59.905 59.905 0 0112 3.493a59.902 59.902 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.697 50.697 0 0112 13.489a50.702 50.702 0 017.74-3.342' },
  assignment_submission: { label: 'Assignment Submitted', icon: 'M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z' },
  quiz_submission: { label: 'Quiz Completed', icon: 'M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z' },
  streak_day: { label: 'Streak Bonus', icon: 'M15.362 5.214A8.252 8.252 0 0112 21 8.25 8.25 0 016.038 7.048 8.287 8.287 0 009 9.6a8.983 8.983 0 013.361-6.867 8.21 8.21 0 003 2.48z' },
  badge_award: { label: 'Badge Award', icon: 'M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z' },
  manual_adjustment: { label: 'Admin Adjustment', icon: 'M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75' },
};

// ── Spinner ──────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div className="flex justify-center py-12">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-tp-accent" />
    </div>
  );
}

// ── Section 1: XP Overview Cards ─────────────────────────────────────

function XPOverviewCards() {
  const { summary } = useGamificationStore();
  if (!summary) return null;

  const progressPercent = summary.next_level_xp
    ? Math.min(100, Math.round(((summary.next_level_xp - summary.xp_to_next_level) / summary.next_level_xp) * 100))
    : 100;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Total XP */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[13px] font-medium text-slate-500">Total XP</span>
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700">
            Lv {summary.level}
          </span>
        </div>
        <p className="text-[20px] font-bold text-slate-900 tabular-nums">{summary.total_xp.toLocaleString()}</p>
        <p className="text-[11px] text-slate-400 mt-1">{summary.level_name}</p>
        <div className="mt-3">
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
            <span>Progress</span>
            <span>{summary.xp_to_next_level > 0 ? `${summary.xp_to_next_level} XP to next` : 'Max level'}</span>
          </div>
          <div className="w-full bg-slate-200 rounded-full h-2">
            <div
              className="bg-tp-accent h-2 rounded-full transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      </div>

      {/* Current Streak */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[13px] font-medium text-slate-500">Current Streak</span>
          <span className={`text-2xl ${summary.current_streak >= 10 ? 'text-red-500' : summary.current_streak >= 5 ? 'text-orange-500' : summary.current_streak >= 1 ? 'text-orange-400' : 'text-slate-300'}`}>
            {summary.current_streak > 0 ? (
              <svg className={`${summary.current_streak >= 10 ? 'h-7 w-7' : summary.current_streak >= 5 ? 'h-6 w-6' : 'h-5 w-5'}`} fill="currentColor" viewBox="0 0 24 24">
                <path d="M15.362 5.214A8.252 8.252 0 0112 21 8.25 8.25 0 016.038 7.048 8.287 8.287 0 009 9.6a8.983 8.983 0 013.361-6.867 8.21 8.21 0 003 2.48z" />
              </svg>
            ) : (
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.362 5.214A8.252 8.252 0 0112 21 8.25 8.25 0 016.038 7.048 8.287 8.287 0 009 9.6a8.983 8.983 0 013.361-6.867 8.21 8.21 0 003 2.48z" />
              </svg>
            )}
          </span>
        </div>
        <p className="text-[20px] font-bold text-slate-900 tabular-nums">{summary.current_streak} day{summary.current_streak !== 1 ? 's' : ''}</p>
        <p className="text-[11px] text-slate-400 mt-1">Best: {summary.longest_streak} days</p>
      </div>

      {/* Badges Earned */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[13px] font-medium text-slate-500">Badges Earned</span>
          <svg className="h-5 w-5 text-yellow-500" fill="currentColor" viewBox="0 0 24 24">
            <path d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
          </svg>
        </div>
        <p className="text-[20px] font-bold text-slate-900 tabular-nums">{summary.badges.length}</p>
        <p className="text-[11px] text-slate-400 mt-1">badges collected</p>
      </div>

      {/* Monthly XP */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[13px] font-medium text-slate-500">This Month</span>
          <svg className="h-5 w-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
          </svg>
        </div>
        <p className="text-[20px] font-bold text-slate-900 tabular-nums">+{summary.xp_this_month.toLocaleString()}</p>
        <p className="text-[11px] text-slate-400 mt-1">XP earned this month</p>
      </div>
    </div>
  );
}

// ── Section 2: Badges Grid ───────────────────────────────────────────

function BadgesGrid({ earnedBadges, allBadges }: { earnedBadges: TeacherBadge[]; allBadges: BadgeDefinition[] }) {
  const earnedBadgeIds = new Set(earnedBadges.map((b) => b.badge.id));

  // Combine earned badge info with all badge definitions
  const badgeItems = allBadges.map((def) => {
    const earned = earnedBadges.find((b) => b.badge.id === def.id);
    return { definition: def, earned };
  });

  if (badgeItems.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-8 text-center">
        <svg className="h-8 w-8 mx-auto mb-3 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
        </svg>
        <p className="text-[13px] font-medium text-slate-900">No badges available yet.</p>
        <p className="text-[13px] text-slate-400 mt-1">Badges will appear here once they are configured.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
      {badgeItems.map((item) => {
        const isEarned = earnedBadgeIds.has(item.definition.id);
        return (
          <div
            key={item.definition.id}
            className={`relative bg-white rounded-2xl border shadow-sm p-4 text-center transition-all ${
              isEarned ? 'border-slate-200/80 hover:shadow-md' : 'border-slate-100 opacity-50 grayscale'
            }`}
          >
            {/* Badge icon circle */}
            <div
              className={`mx-auto h-14 w-14 rounded-full flex items-center justify-center text-white text-2xl mb-3 ${
                isEarned ? '' : 'bg-slate-300'
              }`}
              style={isEarned ? { backgroundColor: item.definition.color || '#6366f1' } : undefined}
            >
              {isEarned ? (
                item.definition.icon || (
                  <svg className="h-7 w-7" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
                  </svg>
                )
              ) : (
                <svg className="h-7 w-7 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
                </svg>
              )}
            </div>

            {/* Badge name */}
            <p className="text-[13px] font-medium text-slate-900 truncate">{item.definition.name}</p>

            {/* Category tag */}
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold mt-1 ${
              CATEGORY_COLORS[item.definition.category] ?? 'bg-slate-100 text-slate-800'
            }`}>
              {item.definition.category}
            </span>

            {/* Date or locked */}
            <p className="text-[11px] text-slate-400 mt-2">
              {isEarned && item.earned ? formatDate(item.earned.awarded_at) : 'Locked'}
            </p>
          </div>
        );
      })}
    </div>
  );
}

// ── Section 3: Leaderboard Preview ──────────────────────────────────

function LeaderboardPreview() {
  const { teacherLeaderboard, fetchTeacherLeaderboard } = useGamificationStore();
  const { user } = useAuthStore();
  const [period, setPeriod] = useState<'weekly' | 'monthly' | 'all_time'>('weekly');

  useEffect(() => {
    fetchTeacherLeaderboard(period);
  }, [period, fetchTeacherLeaderboard]);

  const entries = teacherLeaderboard?.entries?.slice(0, 10) ?? [];

  const getRankStyle = (rank: number): string => {
    if (rank === 1) return 'bg-yellow-100 text-yellow-800 ring-2 ring-yellow-300';
    if (rank === 2) return 'bg-slate-100 text-slate-700 ring-2 ring-slate-300';
    if (rank === 3) return 'bg-orange-100 text-orange-800 ring-2 ring-orange-300';
    return 'bg-white text-slate-600';
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm">
      <div className="px-5 py-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-slate-900">Leaderboard</h3>
        <div className="flex items-center gap-2">
          {(['weekly', 'monthly', 'all_time'] as const).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                period === p
                  ? 'bg-tp-accent text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {p === 'weekly' ? 'Weekly' : p === 'monthly' ? 'Monthly' : 'All Time'}
            </button>
          ))}
        </div>
      </div>

      {entries.length === 0 ? (
        <div className="text-center py-8 text-slate-500">
          <p className="text-[13px] font-medium">No leaderboard data for this period.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Rank</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Name</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">XP</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Level</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Streak</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-slate-100">
              {entries.map((entry) => {
                const isCurrentUser = user?.id === entry.teacher_id;
                return (
                  <tr
                    key={entry.teacher_id}
                    className={`${isCurrentUser ? 'bg-orange-50 ring-1 ring-inset ring-orange-200' : 'hover:bg-slate-50'}`}
                  >
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center justify-center h-7 w-7 rounded-full text-xs font-bold ${getRankStyle(entry.rank)}`}>
                        {entry.rank}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-[13px] font-medium text-slate-900">
                        {entry.teacher_name}
                        {isCurrentUser && (
                          <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700">
                            You
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[13px] font-semibold text-slate-900">{entry.total_xp.toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <div className="text-[13px] text-slate-900">{entry.level_name}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[13px] font-medium ${entry.current_streak > 0 ? 'text-orange-600' : 'text-slate-400'}`}>
                        {entry.current_streak > 0 && (
                          <svg className="inline-block h-4 w-4 mr-0.5 -mt-0.5" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M15.362 5.214A8.252 8.252 0 0112 21 8.25 8.25 0 016.038 7.048 8.287 8.287 0 009 9.6a8.983 8.983 0 013.361-6.867 8.21 8.21 0 003 2.48z" />
                          </svg>
                        )}
                        {entry.current_streak}d
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Section 4: Recent XP Activity ───────────────────────────────────

function RecentXPActivity() {
  const { teacherXPHistory } = useGamificationStore();
  const transactions = teacherXPHistory.slice(0, 10);

  if (transactions.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-8 text-center">
        <svg className="h-8 w-8 mx-auto mb-3 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-[13px] font-medium text-slate-900">No XP activity yet.</p>
        <p className="text-[13px] text-slate-400 mt-1">Complete courses, assignments, and quizzes to earn XP.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm">
      <div className="px-5 py-4 border-b border-slate-100">
        <h3 className="text-[15px] font-semibold text-slate-900">Recent Activity</h3>
      </div>
      <div className="divide-y divide-slate-100">
        {transactions.map((tx) => {
          const reasonInfo = REASON_LABELS[tx.reason] ?? { label: tx.reason.replace(/_/g, ' '), icon: 'M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z' };
          const isPositive = tx.xp_amount >= 0;
          return (
            <div key={tx.id} className="px-5 py-3 flex items-center gap-4 hover:bg-slate-50">
              {/* Reason icon */}
              <div className={`flex-shrink-0 h-9 w-9 rounded-xl flex items-center justify-center ${isPositive ? 'bg-green-100' : 'bg-red-100'}`}>
                <svg className={`h-5 w-5 ${isPositive ? 'text-green-600' : 'text-red-600'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={reasonInfo.icon} />
                </svg>
              </div>

              {/* Label and description */}
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-medium text-slate-900">{reasonInfo.label}</p>
                {tx.description && (
                  <p className="text-[11px] text-slate-400 truncate">{tx.description}</p>
                )}
              </div>

              {/* XP amount */}
              <div className="flex-shrink-0 text-right">
                <span className={`text-[13px] font-semibold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                  {isPositive ? '+' : ''}{tx.xp_amount} XP
                </span>
                <p className="text-[11px] text-slate-400">{formatRelativeTime(tx.created_at)}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────

export default function GamificationPage() {
  const {
    summary,
    myBadges,
    badgeDefinitions,
    loading,
    error,
    fetchSummary,
    fetchMyBadges,
    fetchBadgeDefinitions,
    fetchTeacherLeaderboard,
    fetchTeacherXPHistory,
    toggleOptOut,
  } = useGamificationStore();

  const [initialLoading, setInitialLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchSummary(),
      fetchMyBadges(),
      fetchBadgeDefinitions(),
      fetchTeacherLeaderboard('weekly'),
      fetchTeacherXPHistory(),
    ]).finally(() => setInitialLoading(false));
  }, [fetchSummary, fetchMyBadges, fetchBadgeDefinitions, fetchTeacherLeaderboard, fetchTeacherXPHistory]);

  if (initialLoading) return <Spinner />;

  // Gamification not active
  if (!summary && !loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Gamification</h1>
          <p className="mt-1 text-[13px] text-slate-500">Track your progress and achievements.</p>
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-center">
          <svg className="h-12 w-12 mx-auto mb-3 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
          <p className="text-lg font-medium text-amber-900">Gamification is not enabled for your school.</p>
          <p className="text-sm text-amber-700 mt-1">Contact your school administrator to enable gamification features.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Gamification</h1>
        <p className="mt-1 text-[13px] text-slate-500">Track your progress, badges, and rankings.</p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">{error}</div>
      )}

      {/* Opt-out banner */}
      {summary?.opted_out && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-3">
            <svg className="h-5 w-5 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
            </svg>
            <p className="text-sm text-slate-600">
              You've opted out of gamification. Your progress is still tracked but hidden.
            </p>
          </div>
          <button
            onClick={toggleOptOut}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-tp-accent bg-white border border-orange-300 rounded-lg hover:bg-orange-50 transition-colors disabled:opacity-50 flex-shrink-0"
          >
            Opt Back In
          </button>
        </div>
      )}

      {/* Section 1: XP Overview Cards */}
      <XPOverviewCards />

      {/* Section 2: Badges Grid */}
      <div>
        <h2 className="text-[15px] font-semibold text-slate-900 mb-3">Badges</h2>
        <BadgesGrid earnedBadges={myBadges} allBadges={badgeDefinitions} />
      </div>

      {/* Section 3: Leaderboard Preview */}
      <LeaderboardPreview />

      {/* Section 4: Recent XP Activity */}
      <RecentXPActivity />
    </div>
  );
}
