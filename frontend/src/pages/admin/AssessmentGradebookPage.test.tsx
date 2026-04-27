// src/pages/admin/AssessmentGradebookPage.test.tsx
//
// FE-017: Unit tests for the `makeColumns` factory function.
// Verifies that mode-label wiring propagates through to column headers
// so Corporate-mode tenants see "Employee" instead of "Teacher" in the
// Assessment Gradebook's first column.

import React from 'react';
import { render, screen } from '@testing-library/react';
import { makeColumns } from './AssessmentGradebookPage';
import type { ModeLabelKey } from '../../stores/tenantStore';

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Mock `lbl` — returns `MOCK_<key>` to distinguish mode-label substitutions
 * from any hard-coded strings.
 */
const mockLbl = (k: ModeLabelKey) => `MOCK_${k}`;

/**
 * Create a minimal TanStack `Column` double.
 * `getCanSort() = false` forces `DataTableColumnHeader` to use the simple
 * non-sortable branch: `<div>{title}</div>`.
 */
function fakeColumn() {
  return {
    getCanSort: () => false,
    getIsSorted: () => false as const,
    toggleSorting: vi.fn(),
  };
}

/**
 * Render the header of the column identified by `accessorKey`.
 */
function renderHeader(columns: ReturnType<typeof makeColumns>, accessorKey: string) {
  const col = columns.find((c) => (c as { accessorKey?: string }).accessorKey === accessorKey);
  if (!col) throw new Error(`Column '${accessorKey}' not found`);

  const headerFn = col.header;
  if (typeof headerFn !== 'function') throw new Error(`Column '${accessorKey}' header is not a function`);

  return render(headerFn({ column: fakeColumn() } as Parameters<typeof headerFn>[0]));
}

// ── makeColumns ───────────────────────────────────────────────────────────────

describe('makeColumns (AssessmentGradebookPage)', () => {
  it('wires lbl("learner") into the teacher_name column header', () => {
    const columns = makeColumns(mockLbl);
    renderHeader(columns, 'teacher_name');
    expect(screen.getByText('MOCK_learner')).toBeInTheDocument();
  });

  it('returns columns for all expected accessorKeys', () => {
    const columns = makeColumns(mockLbl);
    const keys = columns.map((c) => (c as { accessorKey?: string }).accessorKey);
    expect(keys).toContain('teacher_name');
    expect(keys).toContain('quiz_attempts');
    expect(keys).toContain('quiz_best_score_percent');
    expect(keys).toContain('quiz_passed');
    expect(keys).toContain('assignments_submitted');
    expect(keys).toContain('progress_percent');
  });

  it('does not hard-code "Teacher" — different lbl produces different header text', () => {
    const educationLbl = (k: ModeLabelKey) => (k === 'learner' ? 'Teacher' : k);
    const corporateLbl = (k: ModeLabelKey) => (k === 'learner' ? 'Employee' : k);

    const renderLearnerHeader = (lbl: typeof educationLbl) => {
      const cols = makeColumns(lbl);
      const col = cols.find((c) => (c as { accessorKey?: string }).accessorKey === 'teacher_name')!;
      const headerFn = col.header as (ctx: { column: unknown }) => React.ReactNode;
      return headerFn({ column: fakeColumn() });
    };

    const { unmount } = render(<>{renderLearnerHeader(educationLbl)}</>);
    expect(screen.getByText('Teacher')).toBeInTheDocument();
    unmount();

    render(<>{renderLearnerHeader(corporateLbl)}</>);
    expect(screen.getByText('Employee')).toBeInTheDocument();
  });
});
