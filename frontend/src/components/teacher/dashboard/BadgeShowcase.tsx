import React from 'react';
import type { TeacherBadgeLevel } from '../../../services/teacherService';
import { GlassBadgeIcon } from './GlassBadgeIcons';

interface BadgeShowcaseProps {
  badges: TeacherBadgeLevel[];
  currentLevel: number;
}

export const BadgeShowcase: React.FC<BadgeShowcaseProps> = ({ badges, currentLevel }) => {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-end justify-between">
        <div>
          <p className="text-lg font-semibold text-slate-900">Ripple Badges</p>
          <p className="text-xs text-slate-500">Glass 3D progression system</p>
        </div>
        <p className="text-xs font-semibold text-violet-600">Current Level: {currentLevel}</p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {badges.map((badge) => (
          <article
            key={badge.key}
            className={`rounded-xl border p-3 transition ${
              badge.unlocked
                ? 'border-violet-200 bg-violet-50/40'
                : 'border-slate-200 bg-slate-50 opacity-75'
            }`}
          >
            <div className="flex items-center justify-center">
              <GlassBadgeIcon level={badge.level as 1 | 2 | 3 | 4 | 5} />
            </div>
            <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Level {badge.level}</p>
            <p className="text-sm font-semibold text-slate-900">{badge.name}</p>
            <p className="text-xs text-slate-500">{badge.ripple_range}</p>
          </article>
        ))}
      </div>
    </div>
  );
};
