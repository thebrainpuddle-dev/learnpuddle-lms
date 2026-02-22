import React from 'react';
import { SparklesIcon } from '@heroicons/react/24/solid';
import type { TeacherQuestSummary } from '../../../services/teacherService';

interface DailyQuestCardProps {
  quest: TeacherQuestSummary;
  onClaim: () => void;
  claiming?: boolean;
}

export const DailyQuestCard: React.FC<DailyQuestCardProps> = ({ quest, onClaim, claiming }) => {
  const progressPct = Math.min(100, Math.round((quest.progress_current / Math.max(1, quest.progress_target)) * 100));

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-xl font-semibold text-slate-900">Daily Quest</p>
          <p className="mt-1 text-sm font-semibold text-slate-800">{quest.title}</p>
          <p className="text-sm text-violet-600">+{quest.reward_points} Points</p>
        </div>
        <div className="rounded-xl bg-sky-50 p-2 text-sky-600">
          <SparklesIcon className="h-5 w-5" />
        </div>
      </div>
      <div className="mb-3 h-1.5 rounded-full bg-violet-100">
        <div className="h-full rounded-full bg-violet-400 transition-all" style={{ width: `${progressPct}%` }} />
      </div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          {quest.progress_current}/{quest.progress_target} Completed
        </p>
        <button
          type="button"
          disabled={!quest.claimable || claiming}
          onClick={onClaim}
          className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
            quest.claimed_today
              ? 'bg-emerald-100 text-emerald-700'
              : quest.claimable
                ? 'bg-violet-600 text-white hover:bg-violet-700'
                : 'bg-slate-100 text-slate-400'
          }`}
        >
          {quest.claimed_today ? 'Claimed' : claiming ? 'Claiming...' : 'Claim Reward'}
        </button>
      </div>
    </div>
  );
};
