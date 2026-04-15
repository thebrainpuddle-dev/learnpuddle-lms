// src/components/certifications/RankingsLinksTab.tsx
//
// Admin tab for tracking school rankings across major platforms and
// providing quick-access links to board portals, accreditation bodies,
// and government/regulatory sites relevant to Indian schools.

import React, { useState, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import {
  Trophy,
  TrendingUp,
  TrendingDown,
  Minus,
  ExternalLink,
  Link2,
  Globe,
  Building2,
  Award,
  GraduationCap,
  Landmark,
  Plus,
  Pencil,
  Trash2,
  X,
} from 'lucide-react';
import api from '../../config/api';
import { cn } from '../../lib/utils';
import { Button } from '../common/Button';
import { FormField } from '../common/FormField';
import { useToast, ConfirmDialog } from '../common';
import { useZodForm } from '../../hooks/useZodForm';

// ── Types ────────────────────────────────────────────────────────────

interface RankingEntry {
  id: string;
  platform: string;
  platform_display: string;
  year: number;
  rank: number | null;
  previous_rank: number | null;
  category: string;
  score: number | null;
  survey_url: string;
  notes: string;
  trend: 'up' | 'down' | 'same' | 'new';
}

interface QuickLink {
  title: string;
  url: string;
  category: 'BOARD' | 'RANKING' | 'ACCREDITATION' | 'GOVERNMENT';
  description?: string;
}

// ── Constants ────────────────────────────────────────────────────────

const PREDEFINED_PLATFORMS = [
  { value: 'educationworld', label: 'EducationWorld (EWISR)' },
  { value: 'cfore', label: 'Cfore Rankings' },
  { value: 'times_school', label: 'Times School Survey' },
  { value: 'education_today', label: 'EducationToday' },
  { value: 'iirf', label: 'IIRF' },
] as const;

const QUICK_LINKS: QuickLink[] = [
  // Board Portals
  { title: 'CBSE SARAS 6.0', url: 'https://saras.cbse.gov.in', category: 'BOARD', description: 'CBSE affiliation management & status check' },
  { title: 'CISCE e-Affiliation', url: 'https://eaffiliation.cisce.org', category: 'BOARD', description: 'ICSE/ISC affiliation portal' },
  { title: 'UDISE+', url: 'https://udiseplus.gov.in', category: 'BOARD', description: 'Unified school data submission' },
  { title: 'Know Your School', url: 'https://kys.udiseplus.gov.in', category: 'BOARD', description: 'Public school information lookup' },
  { title: 'IB Organization', url: 'https://ibo.org', category: 'BOARD', description: 'IB programmes, authorization & resources' },
  { title: 'Cambridge CIE Direct', url: 'https://direct.cie.org.uk', category: 'BOARD', description: 'Cambridge centre admin portal' },

  // Rankings & Surveys
  { title: 'EducationWorld Survey', url: 'https://educationworld.in/india-school-rankings-survey-form', category: 'RANKING', description: 'Submit EWISR annual survey' },
  { title: 'Cfore Rankings', url: 'https://cforerankings.com', category: 'RANKING', description: 'School ranking methodology & results' },
  { title: 'Times School Survey', url: 'https://timesschoolsurvey.com', category: 'RANKING', description: 'City-wise school rankings' },
  { title: 'EducationToday', url: 'https://educationtoday.co', category: 'RANKING', description: 'India School Merit Awards' },

  // Accreditation Bodies
  { title: 'NABET/QCI', url: 'https://nabet.qci.org.in/school_accreditation', category: 'ACCREDITATION', description: 'National accreditation for schools' },
  { title: 'CIS', url: 'https://cois.org/for-schools/international-accreditation', category: 'ACCREDITATION', description: 'International school accreditation' },
  { title: 'IGBC Green School', url: 'https://igbc.in/igbcgreenschools', category: 'ACCREDITATION', description: 'Green school certification' },
  { title: 'Cambridge Recognition', url: 'https://cambridgeinternational.org/recognition-search', category: 'ACCREDITATION', description: 'Check university recognition' },

  // Government & Regulatory
  { title: 'NEP 2020', url: 'https://education.gov.in', category: 'GOVERNMENT', description: 'National Education Policy resources' },
  { title: 'Karnataka Education', url: 'https://schooleducation.karnataka.gov.in', category: 'GOVERNMENT', description: 'State education department' },
  { title: 'Delhi Education', url: 'https://edudel.nic.in', category: 'GOVERNMENT', description: 'Delhi education directorate' },
  { title: 'Maharashtra Education', url: 'https://education.maharashtra.gov.in', category: 'GOVERNMENT', description: 'Maharashtra SARAL portal' },
];

const CATEGORY_CONFIG: Record<QuickLink['category'], { label: string; icon: React.FC<{ className?: string }> }> = {
  BOARD: { label: 'Board Portals', icon: GraduationCap },
  RANKING: { label: 'Rankings & Surveys', icon: Trophy },
  ACCREDITATION: { label: 'Accreditation Bodies', icon: Award },
  GOVERNMENT: { label: 'Government & Regulatory', icon: Landmark },
};

// ── Zod Schema ───────────────────────────────────────────────────────

const RankingFormSchema = z.object({
  platform: z.string().min(1, 'Platform is required'),
  custom_platform: z.string().optional(),
  year: z.coerce.number().min(2000, 'Year must be 2000 or later').max(2100),
  rank: z.coerce.number().min(1, 'Rank must be at least 1').nullable().optional(),
  category: z.string().min(1, 'Category is required'),
  score: z.coerce.number().min(0).max(100).nullable().optional(),
  survey_url: z.string().url('Must be a valid URL').or(z.literal('')).optional(),
  notes: z.string().max(500).optional(),
});

type RankingFormData = z.infer<typeof RankingFormSchema>;

// ── Helpers ──────────────────────────────────────────────────────────

function extractDomain(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function getTrendDiff(rank: number | null, previousRank: number | null): number | null {
  if (rank == null || previousRank == null) return null;
  return previousRank - rank;
}

// ── Loading Skeleton ─────────────────────────────────────────────────

const RankingsSkeleton: React.FC = () => (
  <div className="animate-pulse space-y-3">
    {Array.from({ length: 3 }).map((_, i) => (
      <div key={i} className="flex gap-4">
        {Array.from({ length: 6 }).map((_, j) => (
          <div key={j} className="h-10 bg-gray-100 rounded-lg flex-1" />
        ))}
      </div>
    ))}
  </div>
);

// ── Trend Badge ──────────────────────────────────────────────────────

const TrendBadge: React.FC<{ trend: RankingEntry['trend']; rank: number | null; previousRank: number | null }> = ({
  trend,
  rank,
  previousRank,
}) => {
  const diff = getTrendDiff(rank, previousRank);

  if (trend === 'new') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
        NEW
      </span>
    );
  }

  if (trend === 'up' && diff != null) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
        <TrendingUp className="h-3.5 w-3.5" />
        {diff}
      </span>
    );
  }

  if (trend === 'down' && diff != null) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-semibold text-red-700">
        <TrendingDown className="h-3.5 w-3.5" />
        {Math.abs(diff)}
      </span>
    );
  }

  // same
  return (
    <span className="inline-flex items-center gap-1 text-gray-400">
      <Minus className="h-3.5 w-3.5" />
    </span>
  );
};

// ── Quick Link Card ──────────────────────────────────────────────────

const QuickLinkCard: React.FC<{ link: QuickLink }> = ({ link }) => (
  <a
    href={link.url}
    target="_blank"
    rel="noopener noreferrer"
    className="group block bg-white border border-gray-200 rounded-lg p-4 hover:border-indigo-300 hover:shadow-sm transition-all cursor-pointer"
  >
    <div className="flex items-start justify-between gap-2">
      <h4 className="text-sm font-semibold text-gray-900 group-hover:text-indigo-600 transition-colors">
        {link.title}
      </h4>
      <ExternalLink className="h-4 w-4 text-gray-300 group-hover:text-indigo-400 flex-shrink-0 mt-0.5 transition-colors" />
    </div>
    <p className="text-xs text-gray-400 mt-1">{extractDomain(link.url)}</p>
    {link.description && (
      <p className="text-xs text-gray-500 mt-1.5 line-clamp-1">{link.description}</p>
    )}
  </a>
);

// ── Main Component ───────────────────────────────────────────────────

export function RankingsLinksTab() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<RankingEntry | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<RankingEntry | null>(null);
  const [useCustomPlatform, setUseCustomPlatform] = useState(false);

  // ── API Queries ──────────────────────────────────────────────────

  const {
    data: rankings,
    isLoading,
    isError,
    error,
  } = useQuery<RankingEntry[]>({
    queryKey: ['rankings'],
    queryFn: () => api.get('/tenants/rankings/').then((r) => r.data),
  });

  // ── Form ─────────────────────────────────────────────────────────

  const form = useZodForm({
    schema: RankingFormSchema,
    defaultValues: {
      platform: '',
      custom_platform: '',
      year: new Date().getFullYear(),
      rank: null,
      category: '',
      score: null,
      survey_url: '',
      notes: '',
    },
  });

  // ── Mutations ────────────────────────────────────────────────────

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      api.post('/tenants/rankings/create/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rankings'] });
      closeModal();
      toast.success('Ranking added', 'The ranking entry has been created.');
    },
    onError: (err: any) => {
      const detail = err?.response?.data;
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        Object.entries(detail).forEach(([field, messages]) => {
          if (field in RankingFormSchema.shape) {
            form.setError(field as keyof RankingFormData, {
              type: 'server',
              message: Array.isArray(messages) ? (messages as string[])[0] : String(messages),
            });
          }
        });
      }
      toast.error('Failed to create', 'Please check the details and try again.');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      api.patch(`/tenants/rankings/${id}/update/`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rankings'] });
      closeModal();
      toast.success('Ranking updated', 'The ranking entry has been updated.');
    },
    onError: () => {
      toast.error('Failed to update', 'Please check the details and try again.');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/tenants/rankings/${id}/delete/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rankings'] });
      setDeleteConfirm(null);
      toast.success('Ranking deleted', 'The ranking entry has been removed.');
    },
    onError: () => {
      toast.error('Failed to delete', 'Please try again.');
    },
  });

  // ── Modal helpers ────────────────────────────────────────────────

  const closeModal = () => {
    setModalOpen(false);
    setEditingEntry(null);
    setUseCustomPlatform(false);
    form.reset({
      platform: '',
      custom_platform: '',
      year: new Date().getFullYear(),
      rank: null,
      category: '',
      score: null,
      survey_url: '',
      notes: '',
    });
  };

  const openCreateModal = () => {
    form.reset({
      platform: '',
      custom_platform: '',
      year: new Date().getFullYear(),
      rank: null,
      category: '',
      score: null,
      survey_url: '',
      notes: '',
    });
    setEditingEntry(null);
    setUseCustomPlatform(false);
    setModalOpen(true);
  };

  const openEditModal = (entry: RankingEntry) => {
    const isPredefined = PREDEFINED_PLATFORMS.some((p) => p.value === entry.platform);
    setUseCustomPlatform(!isPredefined);
    form.reset({
      platform: isPredefined ? entry.platform : 'custom',
      custom_platform: isPredefined ? '' : entry.platform,
      year: entry.year,
      rank: entry.rank,
      category: entry.category,
      score: entry.score,
      survey_url: entry.survey_url || '',
      notes: entry.notes || '',
    });
    setEditingEntry(entry);
    setModalOpen(true);
  };

  const onSubmit = form.handleSubmit((data) => {
    const platform = useCustomPlatform ? data.custom_platform || '' : data.platform;
    const payload: Record<string, unknown> = {
      platform,
      year: data.year,
      rank: data.rank || null,
      category: data.category,
      score: data.score || null,
      survey_url: data.survey_url || '',
      notes: data.notes || '',
    };

    if (editingEntry) {
      updateMutation.mutate({ id: editingEntry.id, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  });

  // ── Grouped quick links ─────────────────────────────────────────

  const groupedLinks = useMemo(() => {
    const groups: Record<QuickLink['category'], QuickLink[]> = {
      BOARD: [],
      RANKING: [],
      ACCREDITATION: [],
      GOVERNMENT: [],
    };
    QUICK_LINKS.forEach((link) => {
      groups[link.category].push(link);
    });
    return groups;
  }, []);

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div className="space-y-10">
      {/* ── Section 1: Rankings Tracker ────────────────────────────── */}
      <section>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
          <div className="flex items-center gap-2">
            <Trophy className="h-5 w-5 text-amber-500" />
            <h2 className="text-lg font-semibold text-gray-900">School Rankings</h2>
          </div>
          <Button className="w-full sm:w-auto" variant="primary" onClick={openCreateModal}>
            <Plus className="h-5 w-5 mr-2" />
            Add Entry
          </Button>
        </div>

        {isLoading ? (
          <RankingsSkeleton />
        ) : isError ? (
          <div className="text-center py-12 text-gray-500 border border-gray-200 rounded-lg bg-white">
            <Trophy className="h-12 w-12 mx-auto mb-3 text-gray-300" />
            <p className="font-medium text-red-600">Failed to load rankings</p>
            <p className="text-sm mt-1 text-gray-500">
              {(error as any)?.message || 'An unexpected error occurred. Please try again.'}
            </p>
          </div>
        ) : !rankings || rankings.length === 0 ? (
          <div className="text-center py-12 text-gray-500 border border-gray-200 rounded-lg bg-white">
            <Trophy className="h-12 w-12 mx-auto mb-3 text-gray-300" />
            <p className="font-medium">No ranking entries yet.</p>
            <p className="text-sm mt-1">
              Track your school's position across major ranking platforms.
            </p>
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden md:block overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Platform
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Year
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Rank
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Category
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Trend
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Score
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {rankings.map((entry, idx) => (
                    <tr
                      key={entry.id}
                      className={cn(
                        'hover:bg-gray-50 transition-colors',
                        idx % 2 === 1 && 'bg-gray-50/50',
                      )}
                    >
                      <td className="px-4 py-3">
                        <div className="text-sm font-medium text-gray-900">
                          {entry.platform_display}
                        </div>
                        {entry.survey_url && (
                          <a
                            href={entry.survey_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-indigo-500 hover:text-indigo-700 inline-flex items-center gap-1 mt-0.5"
                          >
                            <Link2 className="h-3 w-3" />
                            Survey
                          </a>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">{entry.year}</td>
                      <td className="px-4 py-3 text-sm font-semibold text-gray-900">
                        {entry.rank != null ? `#${entry.rank}` : '\u2014'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600 max-w-[200px] truncate" title={entry.category}>
                        {entry.category}
                      </td>
                      <td className="px-4 py-3">
                        <TrendBadge trend={entry.trend} rank={entry.rank} previousRank={entry.previous_rank} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {entry.score != null ? entry.score : '\u2014'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => openEditModal(entry)}
                            className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50 transition-colors"
                            title="Edit"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => setDeleteConfirm(entry)}
                            className="p-1.5 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden space-y-3">
              {rankings.map((entry) => (
                <div key={entry.id} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-gray-900">{entry.platform_display}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{entry.category}</p>
                    </div>
                    <TrendBadge trend={entry.trend} rank={entry.rank} previousRank={entry.previous_rank} />
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xs text-gray-600 mb-3">
                    <div>
                      <span className="block font-medium text-gray-500">Year</span>
                      <span className="text-gray-900">{entry.year}</span>
                    </div>
                    <div>
                      <span className="block font-medium text-gray-500">Rank</span>
                      <span className="text-gray-900 font-semibold">
                        {entry.rank != null ? `#${entry.rank}` : '\u2014'}
                      </span>
                    </div>
                    <div>
                      <span className="block font-medium text-gray-500">Score</span>
                      <span className="text-gray-900">{entry.score != null ? entry.score : '\u2014'}</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                    {entry.survey_url ? (
                      <a
                        href={entry.survey_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-indigo-500 hover:text-indigo-700 inline-flex items-center gap-1"
                      >
                        <Link2 className="h-3 w-3" />
                        Survey Link
                      </a>
                    ) : (
                      <span />
                    )}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => openEditModal(entry)}
                        className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50 transition-colors"
                        title="Edit"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setDeleteConfirm(entry)}
                        className="p-1.5 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      {/* ── Section 2: Quick Links Panel ──────────────────────────── */}
      <section>
        <div className="flex items-center gap-2 mb-6">
          <Globe className="h-5 w-5 text-indigo-500" />
          <h2 className="text-lg font-semibold text-gray-900">Quick Links</h2>
        </div>

        <div className="space-y-8">
          {(Object.keys(CATEGORY_CONFIG) as Array<QuickLink['category']>).map((category) => {
            const config = CATEGORY_CONFIG[category];
            const links = groupedLinks[category];
            const IconComponent = config.icon;

            return (
              <div key={category}>
                <div className="flex items-center gap-2 pb-2 mb-4 border-b border-gray-200">
                  <IconComponent className="h-4 w-4 text-gray-400" />
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                    {config.label}
                  </h3>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                  {links.map((link) => (
                    <QuickLinkCard key={link.url} link={link} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── Create / Edit Modal ───────────────────────────────────── */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4">
          <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-5 pb-6 sm:rounded-xl sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">
                {editingEntry ? 'Edit Ranking Entry' : 'Add Ranking Entry'}
              </h3>
              <button onClick={closeModal} className="text-gray-400 hover:text-gray-600">
                <X className="h-6 w-6" />
              </button>
            </div>

            <form onSubmit={onSubmit} noValidate className="space-y-4">
              {/* Platform select or custom input */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Platform *
                </label>
                {!useCustomPlatform ? (
                  <Controller
                    control={form.control}
                    name="platform"
                    render={({ field, fieldState }) => (
                      <div>
                        <select
                          {...field}
                          className={cn(
                            'input-field w-full',
                            fieldState.error && 'border-red-500 focus:ring-red-500',
                          )}
                        >
                          <option value="">Select a platform...</option>
                          {PREDEFINED_PLATFORMS.map((p) => (
                            <option key={p.value} value={p.value}>
                              {p.label}
                            </option>
                          ))}
                        </select>
                        {fieldState.error && (
                          <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                        )}
                      </div>
                    )}
                  />
                ) : (
                  <FormField
                    control={form.control}
                    name="custom_platform"
                    placeholder="e.g., India Today Best Schools"
                  />
                )}
                <button
                  type="button"
                  onClick={() => {
                    setUseCustomPlatform((prev) => !prev);
                    if (!useCustomPlatform) {
                      form.setValue('platform', 'custom');
                    } else {
                      form.setValue('platform', '');
                      form.setValue('custom_platform', '');
                    }
                  }}
                  className="mt-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                >
                  {useCustomPlatform ? 'Select from list' : 'Use custom platform name'}
                </button>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="year"
                  label="Year *"
                  type="number"
                  min={2000}
                  max={2100}
                  placeholder={String(new Date().getFullYear())}
                />
                <FormField
                  control={form.control}
                  name="rank"
                  label="Rank"
                  type="number"
                  min={1}
                  placeholder="e.g., 8"
                />
              </div>

              <FormField
                control={form.control}
                name="category"
                label="Category *"
                placeholder="e.g., International Day School, Bangalore"
              />

              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="score"
                  label="Score"
                  type="number"
                  min={0}
                  max={100}
                  step="0.1"
                  placeholder="e.g., 87.5"
                />
                <FormField
                  control={form.control}
                  name="survey_url"
                  label="Survey URL"
                  type="url"
                  placeholder="https://..."
                />
              </div>

              <div>
                <label htmlFor="ranking-notes" className="block text-sm font-medium text-gray-700 mb-1">
                  Notes
                </label>
                <Controller
                  control={form.control}
                  name="notes"
                  render={({ field, fieldState }) => (
                    <div>
                      <textarea
                        {...field}
                        id="ranking-notes"
                        rows={3}
                        className={cn(
                          'input-field w-full resize-none',
                          fieldState.error && 'border-red-500 focus:ring-red-500',
                        )}
                        placeholder="Optional notes about this ranking..."
                        value={field.value ?? ''}
                      />
                      {fieldState.error && (
                        <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                      )}
                    </div>
                  )}
                />
              </div>

              <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-end">
                <Button className="w-full sm:w-auto" variant="outline" type="button" onClick={closeModal}>
                  Cancel
                </Button>
                <Button
                  className="w-full sm:w-auto"
                  variant="primary"
                  type="submit"
                  loading={createMutation.isPending || updateMutation.isPending}
                >
                  {editingEntry ? 'Update' : 'Add Entry'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Delete Confirmation ───────────────────────────────────── */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={() => {
          if (deleteConfirm) deleteMutation.mutate(deleteConfirm.id);
        }}
        title="Delete Ranking Entry"
        message={`Are you sure you want to delete the ${deleteConfirm?.platform_display} (${deleteConfirm?.year}) ranking entry? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        loading={deleteMutation.isPending}
      />
    </div>
  );
}
