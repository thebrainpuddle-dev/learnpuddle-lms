// src/pages/admin/GradebookPage.test.tsx
//
// FE-017: Unit tests for column-def factory functions.
// Each test passes a mock `lbl` that returns a distinguishing
// string ("MOCK_<key>") and asserts the column header renders it.
//
// This proves mode-label wiring works at runtime — i.e. switching a
// tenant to Corporate mode would change "Course" to "Training Program"
// and "Assignment" to "Task" in the Gradebook column headers.

import React from 'react';
import { render, screen } from '@testing-library/react';
import { makeCourseColumns, makeAssignmentColumns } from './GradebookPage';
import type { ModeLabelKey } from '../../stores/tenantStore';

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Mock `lbl` function: returns `MOCK_<key>` so every mode-label substitution
 * is visually distinct from hard-coded strings and from each other.
 */
const mockLbl = (k: ModeLabelKey) => `MOCK_${k}`;

/**
 * Create a minimal TanStack `Column` double.
 * `getCanSort() = false` forces `DataTableColumnHeader` to use the simple
 * non-sortable branch: `<div>{title}</div>` — no sort-button wiring needed.
 */
function fakeColumn() {
  return {
    getCanSort: () => false,
    getIsSorted: () => false as const,
    toggleSorting: vi.fn(),
  };
}

/**
 * Given an array of column defs and an accessorKey, calls the header render
 * function with a fake column and returns the rendered container.
 */
function renderHeader(
  columns: ReturnType<typeof makeCourseColumns> | ReturnType<typeof makeAssignmentColumns>,
  accessorKey: string,
) {
  const col = columns.find((c) => (c as { accessorKey?: string }).accessorKey === accessorKey);
  if (!col) throw new Error(`Column '${accessorKey}' not found`);

  const headerFn = col.header;
  if (typeof headerFn !== 'function') throw new Error(`Column '${accessorKey}' header is not a function`);

  return render(headerFn({ column: fakeColumn() } as Parameters<typeof headerFn>[0]));
}

// ── makeCourseColumns ─────────────────────────────────────────────────────────

describe('makeCourseColumns', () => {
  it('wires lbl("course") into the course_title column header', () => {
    const columns = makeCourseColumns(mockLbl);
    renderHeader(columns, 'course_title');
    expect(screen.getByText('MOCK_course')).toBeInTheDocument();
  });

  it('returns a column for every expected accessorKey', () => {
    const columns = makeCourseColumns(mockLbl);
    const keys = columns.map((c) => (c as { accessorKey?: string }).accessorKey);
    expect(keys).toContain('teacher_name');
    expect(keys).toContain('course_title');
    expect(keys).toContain('status');
    expect(keys).toContain('deadline');
    expect(keys).toContain('completed_at');
  });

  it('does not hard-code "Course" — different lbl produces different header', () => {
    const educationLbl = (k: ModeLabelKey) => (k === 'course' ? 'Course' : k);
    const corporateLbl = (k: ModeLabelKey) => (k === 'course' ? 'Training Program' : k);

    const renderCourseHeader = (lbl: typeof educationLbl) => {
      const cols = makeCourseColumns(lbl);
      const col = cols.find((c) => (c as { accessorKey?: string }).accessorKey === 'course_title')!;
      const headerFn = col.header as (ctx: { column: unknown }) => React.ReactNode;
      return headerFn({ column: fakeColumn() });
    };

    const { unmount } = render(<>{renderCourseHeader(educationLbl)}</>);
    expect(screen.getByText('Course')).toBeInTheDocument();
    unmount();

    render(<>{renderCourseHeader(corporateLbl)}</>);
    expect(screen.getByText('Training Program')).toBeInTheDocument();
  });
});

// ── makeAssignmentColumns ─────────────────────────────────────────────────────

describe('makeAssignmentColumns', () => {
  it('wires lbl("assignment") into the assignment_title column header', () => {
    const columns = makeAssignmentColumns(mockLbl);
    renderHeader(columns, 'assignment_title');
    expect(screen.getByText('MOCK_assignment')).toBeInTheDocument();
  });

  it('returns a column for every expected accessorKey', () => {
    const columns = makeAssignmentColumns(mockLbl);
    const keys = columns.map((c) => (c as { accessorKey?: string }).accessorKey);
    expect(keys).toContain('teacher_name');
    expect(keys).toContain('assignment_title');
    expect(keys).toContain('status');
    expect(keys).toContain('due_date');
    expect(keys).toContain('submitted_at');
  });

  it('does not hard-code "Assignment" — different lbl produces different header', () => {
    const educationLbl = (k: ModeLabelKey) => (k === 'assignment' ? 'Assignment' : k);
    const corporateLbl = (k: ModeLabelKey) => (k === 'assignment' ? 'Task' : k);

    const renderAssignmentHeader = (lbl: typeof educationLbl) => {
      const cols = makeAssignmentColumns(lbl);
      const col = cols.find((c) => (c as { accessorKey?: string }).accessorKey === 'assignment_title')!;
      const headerFn = col.header as (ctx: { column: unknown }) => React.ReactNode;
      return headerFn({ column: { getCanSort: () => false, getIsSorted: () => false, toggleSorting: vi.fn() } });
    };

    const { unmount } = render(<>{renderAssignmentHeader(educationLbl)}</>);
    expect(screen.getByText('Assignment')).toBeInTheDocument();
    unmount();

    render(<>{renderAssignmentHeader(corporateLbl)}</>);
    expect(screen.getByText('Task')).toBeInTheDocument();
  });
});
