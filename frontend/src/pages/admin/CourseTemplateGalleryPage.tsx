// src/pages/admin/CourseTemplateGalleryPage.tsx
//
// Tenant admin gallery of published course templates.
// Server-side filters: category, language, level.
// Client-side filter: search by title substring.

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  MagnifyingGlassIcon,
  FunnelIcon,
  AcademicCapIcon,
} from '@heroicons/react/24/outline';
import {
  courseTemplatesService,
  type CourseTemplateListItem,
  type TemplateCategory,
  type TemplateLevel,
} from '../../services/courseTemplatesService';
import { TemplateCard } from '../../components/templates/TemplateCard';
import { TemplatePreviewPanel } from '../../components/templates/TemplatePreviewPanel';
import { CloneTemplateDialog } from '../../components/templates/CloneTemplateDialog';
import { usePageTitle } from '../../hooks/usePageTitle';
import { EmptyState } from '../../components/common';

const CATEGORIES: { value: TemplateCategory | ''; label: string }[] = [
  { value: '', label: 'All categories' },
  { value: 'TEACHING_SKILLS', label: 'Teaching Skills' },
  { value: 'IB_PYP', label: 'IB PYP' },
  { value: 'IB_MYP', label: 'IB MYP' },
  { value: 'IB_DP', label: 'IB DP' },
  { value: 'LEADERSHIP', label: 'Leadership' },
  { value: 'WELLBEING', label: 'Wellbeing' },
  { value: 'OTHER', label: 'Other' },
];

const LEVELS: { value: TemplateLevel | ''; label: string }[] = [
  { value: '', label: 'All levels' },
  { value: 'BEGINNER', label: 'Beginner' },
  { value: 'INTERMEDIATE', label: 'Intermediate' },
  { value: 'ADVANCED', label: 'Advanced' },
];

const LANGUAGES: { value: string; label: string }[] = [
  { value: '', label: 'All languages' },
  { value: 'en', label: 'English' },
  { value: 'hi', label: 'Hindi' },
  { value: 'fr', label: 'French' },
  { value: 'es', label: 'Spanish' },
  { value: 'ar', label: 'Arabic' },
];

/**
 * Gallery page: browse published course templates, preview them in a slide-over
 * panel, and clone one into the current tenant.
 */
export const CourseTemplateGalleryPage: React.FC = () => {
  usePageTitle('Course Templates');

  // ── Server-side filters ────────────────────────────────────────────────────
  const [category, setCategory] = useState<TemplateCategory | ''>('');
  const [language, setLanguage] = useState<string>('');
  const [level, setLevel] = useState<TemplateLevel | ''>('');

  // ── Client-side search ─────────────────────────────────────────────────────
  const [search, setSearch] = useState('');

  // ── UI state ──────────────────────────────────────────────────────────────
  const [previewTemplate, setPreviewTemplate] = useState<CourseTemplateListItem | null>(null);
  const [cloneTemplate, setCloneTemplate] = useState<CourseTemplateListItem | null>(null);

  // ── Data ──────────────────────────────────────────────────────────────────
  const { data, isLoading, isError } = useQuery({
    queryKey: ['courseTemplates', { category, language, level }],
    queryFn: () =>
      courseTemplatesService.tenant.listTemplates({
        category: category || undefined,
        language: language || undefined,
        level: level || undefined,
      }),
    staleTime: 2 * 60 * 1000,
  });

  const templates = data?.results ?? [];

  // Client-side title substring search
  const filtered = useMemo<CourseTemplateListItem[]>(() => {
    if (!search.trim()) return templates;
    const q = search.toLowerCase();
    return templates.filter((t) => t.title.toLowerCase().includes(q));
  }, [templates, search]);

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleCardClick = (t: CourseTemplateListItem) => {
    setPreviewTemplate(t);
  };

  const handleCloneOpen = () => {
    setCloneTemplate(previewTemplate);
  };

  const handleCloneClose = () => {
    setCloneTemplate(null);
  };

  const handlePreviewClose = () => {
    setPreviewTemplate(null);
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      <div className="space-y-6 p-4 sm:p-6" data-testid="template-gallery-page">
        {/* Page header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Course Templates</h1>
          <p className="mt-1 text-sm text-gray-500">
            Browse platform-curated templates and clone one into your school to get started.
          </p>
        </div>

        {/* Filter bar */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center" data-testid="filter-bar">
          {/* Search */}
          <div className="relative flex-1 max-w-sm">
            <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search templates…"
              aria-label="Search templates"
              data-testid="search-input"
              className="block w-full rounded-lg border border-gray-300 bg-white pl-9 pr-3 py-2 text-sm placeholder-gray-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-200 transition-colors"
            />
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <FunnelIcon className="h-4 w-4 text-gray-400 flex-shrink-0" />

            {/* Category */}
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as TemplateCategory | '')}
              data-testid="category-filter"
              aria-label="Filter by category"
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-200 transition-colors cursor-pointer"
            >
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>

            {/* Language */}
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              data-testid="language-filter"
              aria-label="Filter by language"
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-200 transition-colors cursor-pointer"
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>

            {/* Level */}
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value as TemplateLevel | '')}
              data-testid="level-filter"
              aria-label="Filter by level"
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-200 transition-colors cursor-pointer"
            >
              {LEVELS.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Results count */}
        {!isLoading && !isError && (
          <p className="text-xs text-gray-400" aria-live="polite">
            {filtered.length} template{filtered.length !== 1 ? 's' : ''} found
          </p>
        )}

        {/* Grid */}
        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="animate-pulse rounded-xl border border-gray-200 bg-gray-100 h-64"
              />
            ))}
          </div>
        ) : isError ? (
          <EmptyState
            title="Failed to load templates"
            description="We couldn't fetch templates right now. Please try again."
            icon={<AcademicCapIcon className="h-12 w-12 text-gray-300" />}
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No templates found"
            description={
              search
                ? `No templates match "${search}". Try a different search.`
                : 'No published templates are available yet.'
            }
            icon={<AcademicCapIcon className="h-12 w-12 text-gray-300" />}
          />
        ) : (
          <div
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
            data-testid="template-grid"
          >
            {filtered.map((t) => (
              <TemplateCard
                key={t.id}
                template={t}
                selected={previewTemplate?.id === t.id}
                onClick={() => handleCardClick(t)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Slide-over preview */}
      <TemplatePreviewPanel
        template={previewTemplate}
        onClose={handlePreviewClose}
        onClone={handleCloneOpen}
      />

      {/* Clone dialog */}
      <CloneTemplateDialog template={cloneTemplate} onClose={handleCloneClose} />
    </>
  );
};
