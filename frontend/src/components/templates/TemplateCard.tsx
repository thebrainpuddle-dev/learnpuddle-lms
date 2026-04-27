// src/components/templates/TemplateCard.tsx
//
// Grid card for a single course template in the gallery.

import React from 'react';
import {
  ClockIcon,
  AcademicCapIcon,
  TagIcon,
} from '@heroicons/react/24/outline';
import type { CourseTemplateListItem, TemplateLevel } from '../../services/courseTemplatesService';

interface TemplateCardProps {
  template: CourseTemplateListItem;
  selected?: boolean;
  onClick: () => void;
}

const LEVEL_COLORS: Record<TemplateLevel, string> = {
  BEGINNER: 'bg-emerald-100 text-emerald-700',
  INTERMEDIATE: 'bg-amber-100 text-amber-700',
  ADVANCED: 'bg-red-100 text-red-700',
};

const CATEGORY_LABELS: Record<string, string> = {
  TEACHING_SKILLS: 'Teaching Skills',
  IB_PYP: 'IB PYP',
  IB_MYP: 'IB MYP',
  IB_DP: 'IB DP',
  LEADERSHIP: 'Leadership',
  WELLBEING: 'Wellbeing',
  OTHER: 'Other',
};

/**
 * A clickable card showing template metadata.
 * Highlights when selected.
 */
export const TemplateCard: React.FC<TemplateCardProps> = ({
  template,
  selected = false,
  onClick,
}) => {
  const levelColor = LEVEL_COLORS[template.level] ?? 'bg-gray-100 text-gray-700';
  const categoryLabel = CATEGORY_LABELS[template.category] ?? template.category;

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="template-card"
      className={`flex flex-col rounded-xl border bg-white text-left shadow-sm transition-all duration-150 cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 hover:shadow-md ${
        selected
          ? 'border-primary-500 ring-2 ring-primary-200'
          : 'border-gray-200 hover:border-primary-300'
      }`}
    >
      {/* Thumbnail */}
      <div className="relative h-36 w-full overflow-hidden rounded-t-xl bg-gradient-to-br from-primary-50 to-sky-50 flex-shrink-0">
        {template.thumbnail_url ? (
          <img
            src={template.thumbnail_url}
            alt={template.title}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <AcademicCapIcon className="h-12 w-12 text-primary-200" />
          </div>
        )}
        {/* Level badge */}
        <span
          className={`absolute top-2 right-2 rounded-full px-2 py-0.5 text-[11px] font-semibold ${levelColor}`}
        >
          {template.level}
        </span>
      </div>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-2 p-3">
        <h3 className="line-clamp-2 text-sm font-semibold text-gray-900 leading-snug">
          {template.title}
        </h3>
        {template.description && (
          <p className="line-clamp-2 text-xs text-gray-500 leading-relaxed">
            {template.description}
          </p>
        )}

        <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
          {/* Category chip */}
          <span className="flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600">
            <TagIcon className="h-3 w-3" />
            {categoryLabel}
          </span>
          {/* Hours */}
          {template.estimated_hours > 0 && (
            <span className="flex items-center gap-1 text-[11px] text-gray-500">
              <ClockIcon className="h-3 w-3" />
              {template.estimated_hours}h
            </span>
          )}
          {/* Language */}
          <span className="ml-auto text-[11px] text-gray-400 uppercase">
            {template.language}
          </span>
        </div>
      </div>
    </button>
  );
};
