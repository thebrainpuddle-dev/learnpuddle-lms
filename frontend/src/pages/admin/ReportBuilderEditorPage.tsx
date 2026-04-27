// src/pages/admin/ReportBuilderEditorPage.tsx
//
// Create / edit form for a ReportDefinition.
//
// Sections:
//   1. Basics   — name, description, data_source.
//   2. Filters  — dynamic FilterBuilder, driven by data source whitelist.
//   3. Group By — GroupByChips.
//   4. Aggregates — AggregateBuilder.
//
// On submit: POST (create) or PATCH (edit) → navigate to detail page.

import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import { useZodForm } from '../../hooks/useZodForm';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useToast } from '../../components/common/Toast';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useReportBuilderStore } from '../../stores/reportBuilderStore';
import {
  reportBuilderService,
  type FilterEntry,
  type GroupByEntry,
  type AggregateEntry,
  type ReportDataSource,
  normaliseGroupBy,
  serialiseGroupBy,
} from '../../services/reportBuilderService';
import { FilterBuilder } from '../../components/reportBuilder/FilterBuilder';
import { GroupByChips } from '../../components/reportBuilder/GroupByChips';
import { AggregateBuilder } from '../../components/reportBuilder/AggregateBuilder';

// ─── Zod schema (basics only — filters/group/agg are validated server-side) ──

const EditorSchema = z.object({
  name: z.string().min(1, 'Name is required').max(300),
  description: z.string().max(2000).optional().default(''),
  data_source: z.enum([
    'courses',
    'teacher_progress',
    'assignments',
    'quiz_attempts',
    'gamification',
    'certifications',
  ]),
});

type EditorBasics = z.infer<typeof EditorSchema>;

export const ReportBuilderEditorPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  usePageTitle(isEdit ? 'Edit report' : 'New report');
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();

  // ── Schema (whitelists) ─────────────────────────────────────────────────
  const { schema, ensureSchema } = useReportBuilderStore();
  useEffect(() => {
    ensureSchema().catch(() => {
      toast.error(
        'Schema unavailable',
        'Could not load field whitelists. Please refresh.',
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Existing definition (edit mode) ─────────────────────────────────────
  const definitionQuery = useQuery({
    queryKey: ['reportBuilder', 'definition', id],
    queryFn: () => reportBuilderService.getDefinition(id!),
    enabled: isEdit,
  });

  // ── Form state ──────────────────────────────────────────────────────────
  const form = useZodForm({
    schema: EditorSchema,
    defaultValues: {
      name: '',
      description: '',
      data_source: 'teacher_progress' as ReportDataSource,
    },
  });

  // Hydrate form once the definition arrives (edit mode).
  useEffect(() => {
    if (!isEdit || !definitionQuery.data) return;
    const d = definitionQuery.data;
    form.reset({
      name: d.name,
      description: d.description,
      data_source: d.data_source,
    });
    setFilters(d.filters_json ?? []);
    setGroupBy(normaliseGroupBy(d.group_by_json));
    setAggregates(d.aggregates_json ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [definitionQuery.data, isEdit]);

  // ── DSL state (lives outside the form since it's a dynamic JSON tree) ──
  const [filters, setFilters] = useState<FilterEntry[]>([]);
  const [groupBy, setGroupBy] = useState<GroupByEntry[]>([]);
  const [aggregates, setAggregates] = useState<AggregateEntry[]>([]);

  // Selected data source drives the field / op / agg whitelists.
  const dataSource = form.watch('data_source');
  const selectedSchema = useMemo(() => {
    if (!schema) return null;
    return schema.find((s) => s.name === dataSource) ?? null;
  }, [schema, dataSource]);

  const availableFields = selectedSchema?.fields ?? [];
  const availableOps = selectedSchema?.operators ?? [];
  const availableFns = selectedSchema?.aggregates ?? [];

  // Reset DSL rows if data source changes to one where existing field refs
  // would fail server-side validation (only when NOT hydrating existing data).
  const prevDataSource = React.useRef<string | null>(null);
  useEffect(() => {
    if (!selectedSchema) return;
    if (prevDataSource.current && prevDataSource.current !== selectedSchema.name) {
      setFilters((prev) =>
        prev.filter((f) => selectedSchema.fields.includes(f.field)),
      );
      setGroupBy((prev) =>
        prev.filter((g) => selectedSchema.fields.includes(g.field)),
      );
      setAggregates((prev) =>
        prev.filter(
          (a) => a.field === 'id' || selectedSchema.fields.includes(a.field),
        ),
      );
    }
    prevDataSource.current = selectedSchema.name;
  }, [selectedSchema]);

  // ── Mutations ───────────────────────────────────────────────────────────
  const saveMutation = useMutation({
    mutationFn: async (basics: EditorBasics) => {
      const payload = {
        name: basics.name,
        description: basics.description ?? '',
        data_source: basics.data_source,
        filters_json: filters,
        group_by_json: serialiseGroupBy(groupBy),
        aggregates_json: aggregates,
      };
      if (isEdit && id) {
        return reportBuilderService.updateDefinition(id, payload);
      }
      return reportBuilderService.createDefinition(payload);
    },
    onSuccess: (saved) => {
      toast.success(
        isEdit ? 'Report updated' : 'Report created',
        `"${saved.name}" was saved successfully.`,
      );
      queryClient.invalidateQueries({
        queryKey: ['reportBuilder', 'definitions'],
      });
      if (isEdit && id) {
        queryClient.invalidateQueries({
          queryKey: ['reportBuilder', 'definition', id],
        });
      }
      navigate(`/admin/reports/builder/${saved.id}`);
    },
    onError: (err: unknown) => {
      const data =
        (err as { response?: { data?: Record<string, unknown> } })?.response
          ?.data ?? {};
      const detail =
        (data as { definition_schema?: string[] }).definition_schema?.join?.(
          '; ',
        ) ??
        (data as { detail?: string; error?: string }).detail ??
        (data as { error?: string }).error ??
        'Validation failed. Check field names and operators.';
      toast.error('Save failed', String(detail));
    },
  });

  const onSubmit = form.handleSubmit((basics) => {
    saveMutation.mutate(basics);
  });

  // ── Render ──────────────────────────────────────────────────────────────
  if (isEdit && definitionQuery.isLoading) {
    return (
      <div className="p-6 text-sm text-gray-500" data-testid="editor-loading">
        Loading report…
      </div>
    );
  }

  return (
    <div
      className="max-w-4xl space-y-6 p-4 sm:p-6"
      data-testid="report-builder-editor-page"
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => navigate('/admin/reports/builder')}
          className="rounded-md p-1.5 text-gray-500 hover:bg-gray-100"
          aria-label="Back to list"
        >
          <ArrowLeftIcon className="h-4 w-4" />
        </button>
        <h1 className="text-2xl font-bold text-gray-900">
          {isEdit ? 'Edit report' : 'New report'}
        </h1>
      </div>

      <form onSubmit={onSubmit} className="space-y-8">
        {/* ── Basics ─────────────────────────────────────────────────── */}
        <section className="space-y-4 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800">Basics</h2>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-700">
              Name <span className="text-red-500">*</span>
            </label>
            <Controller
              control={form.control}
              name="name"
              render={({ field }) => (
                <Input
                  {...field}
                  placeholder="e.g. Active teachers per department"
                  data-testid="editor-name"
                />
              )}
            />
            {form.formState.errors.name?.message && (
              <p className="text-xs text-red-600" role="alert">
                {form.formState.errors.name.message}
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-700">
              Description
            </label>
            <Controller
              control={form.control}
              name="description"
              render={({ field }) => (
                <textarea
                  {...field}
                  rows={3}
                  placeholder="Explain what this report tracks…"
                  data-testid="editor-description"
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
                />
              )}
            />
            {form.formState.errors.description?.message && (
              <p className="text-xs text-red-600" role="alert">
                {form.formState.errors.description.message}
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-700">
              Data source <span className="text-red-500">*</span>
            </label>
            <Controller
              control={form.control}
              name="data_source"
              render={({ field }) => (
                <select
                  {...field}
                  data-testid="editor-data-source"
                  aria-label="Data source"
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
                >
                  {(schema ?? []).map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.label}
                    </option>
                  ))}
                </select>
              )}
            />
            {form.formState.errors.data_source?.message && (
              <p className="text-xs text-red-600" role="alert">
                {form.formState.errors.data_source.message}
              </p>
            )}
          </div>
        </section>

        {/* ── Filters ────────────────────────────────────────────────── */}
        <section className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800">Filters</h2>
          <FilterBuilder
            availableFields={availableFields}
            availableOperators={availableOps}
            value={filters}
            onChange={setFilters}
            disabled={saveMutation.isPending}
          />
        </section>

        {/* ── Group By ───────────────────────────────────────────────── */}
        <section className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800">Group by</h2>
          <GroupByChips
            availableFields={availableFields}
            value={groupBy.map((g) => g.field)}
            onChange={(next) => setGroupBy(next.map((f) => ({ field: f })))}
            disabled={saveMutation.isPending}
          />
        </section>

        {/* ── Aggregates ─────────────────────────────────────────────── */}
        <section className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800">Aggregates</h2>
          <AggregateBuilder
            availableFields={availableFields}
            availableFns={availableFns}
            value={aggregates}
            onChange={setAggregates}
            disabled={saveMutation.isPending}
          />
        </section>

        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => navigate('/admin/reports/builder')}
            disabled={saveMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            loading={saveMutation.isPending}
            data-testid="editor-submit"
          >
            {isEdit ? 'Save changes' : 'Create report'}
          </Button>
        </div>
      </form>
    </div>
  );
};
