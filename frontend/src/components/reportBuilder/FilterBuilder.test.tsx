// src/components/reportBuilder/FilterBuilder.test.tsx
//
// Tests the FilterBuilder component: add/remove rows, field/op selection,
// value parsing for 'in' (comma-separated list), and type coercion.

import React, { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FilterBuilder } from './FilterBuilder';
import type { FieldTypeMap } from './FilterBuilder';
import type {
  FilterEntry,
  ReportFilterOp,
} from '../../services/reportBuilderService';

const FIELDS = ['id', 'teacher_id', 'status'];
const OPS: ReportFilterOp[] = ['eq', 'ne', 'in', 'gte'];

function Harness({
  initial,
  fieldTypes,
  onChangeSpy,
}: {
  initial?: FilterEntry[];
  fieldTypes?: FieldTypeMap;
  onChangeSpy?: (v: FilterEntry[]) => void;
}) {
  const [value, setValue] = useState<FilterEntry[]>(initial ?? []);
  return (
    <FilterBuilder
      availableFields={FIELDS}
      availableOperators={OPS}
      value={value}
      onChange={(next) => {
        setValue(next);
        onChangeSpy?.(next);
      }}
      fieldTypes={fieldTypes}
    />
  );
}

describe('FilterBuilder', () => {
  it('renders the empty-state message when no filters exist', () => {
    render(<Harness />);
    expect(screen.getByTestId('filter-empty')).toBeInTheDocument();
  });

  it('adds a new filter row when "Add filter" is clicked', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByTestId('filter-add'));
    expect(screen.getByTestId('filter-row-0')).toBeInTheDocument();
    // Row defaults to first field + first op
    expect(screen.getByTestId('filter-field-0')).toHaveValue('id');
    expect(screen.getByTestId('filter-op-0')).toHaveValue('eq');
  });

  it('lets the user change field + operator via selects', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByTestId('filter-add'));
    await user.selectOptions(screen.getByTestId('filter-field-0'), 'status');
    await user.selectOptions(screen.getByTestId('filter-op-0'), 'in');
    expect(screen.getByTestId('filter-field-0')).toHaveValue('status');
    expect(screen.getByTestId('filter-op-0')).toHaveValue('in');
  });

  it('removes a row when the trash button is clicked', async () => {
    const user = userEvent.setup();
    render(
      <Harness
        initial={[{ field: 'id', op: 'eq', value: '42' }]}
      />,
    );
    expect(screen.getByTestId('filter-row-0')).toBeInTheDocument();
    await user.click(screen.getByTestId('filter-remove-0'));
    expect(screen.queryByTestId('filter-row-0')).toBeNull();
    expect(screen.getByTestId('filter-empty')).toBeInTheDocument();
  });

  it('round-trips comma-separated values for the "in" operator', async () => {
    const user = userEvent.setup();
    render(
      <Harness
        initial={[{ field: 'status', op: 'in', value: ['a', 'b'] }]}
      />,
    );
    // stringifyValue converts ['a','b'] → 'a, b' for display
    const input = screen.getByTestId('filter-value-0') as HTMLInputElement;
    expect(input.value).toBe('a, b');
    // Programmatically setting the input value re-parses into an array and re-displays joined with ", "
    await user.clear(input);
    // fireEvent change directly so our parser sees the whole string at once
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set;
    nativeSetter?.call(input, 'x,y,z');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect((input as HTMLInputElement).value).toBe('x, y, z');
  });

  // ── Type coercion tests ───────────────────────────────────────────────────

  it('coerces a valid number string to a Number when fieldTypes declares "number"', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(
      <Harness
        initial={[{ field: 'id', op: 'eq', value: '' }]}
        fieldTypes={{ id: 'number' }}
        onChangeSpy={spy}
      />,
    );
    const input = screen.getByTestId('filter-value-0');
    await user.clear(input);
    await user.type(input, '42');
    // After blurring or when React processes the final change
    await waitFor(() => {
      const lastCall = spy.mock.calls.at(-1)?.[0] as FilterEntry[] | undefined;
      const val = lastCall?.[0]?.value;
      // Should have been coerced to a number
      expect(typeof val).toBe('number');
      expect(val).toBe(42);
    });
    // No error alert
    expect(screen.queryByTestId('filter-coerce-error-0')).toBeNull();
  });

  it('shows a coercion error and blocks onChange when a number field gets a non-numeric value', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(
      <Harness
        initial={[{ field: 'id', op: 'eq', value: '' }]}
        fieldTypes={{ id: 'number' }}
        onChangeSpy={spy}
      />,
    );
    const input = screen.getByTestId('filter-value-0');
    await user.clear(input);
    await user.type(input, 'notanumber');

    await waitFor(() => {
      expect(screen.getByTestId('filter-coerce-error-0')).toBeInTheDocument();
      expect(screen.getByTestId('filter-coerce-error-0')).toHaveTextContent(/not a valid number/i);
    });
    // onChange should NOT have been called with the invalid value as a number
    const numberCallArgs = spy.mock.calls.filter(
      (args) => typeof (args[0] as FilterEntry[])[0]?.value === 'number',
    );
    expect(numberCallArgs).toHaveLength(0);
  });

  it('coerces boolean field: "true" string → boolean true', async () => {
    const spy = vi.fn();
    render(
      <Harness
        initial={[{ field: 'status', op: 'eq', value: '' }]}
        fieldTypes={{ status: 'boolean' }}
        onChangeSpy={spy}
      />,
    );
    const input = screen.getByTestId('filter-value-0') as HTMLInputElement;
    // Set the full string at once so coercion sees "true" (not intermediate chars).
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set;
    nativeSetter?.call(input, 'true');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await waitFor(() => {
      const lastCall = spy.mock.calls.at(-1)?.[0] as FilterEntry[] | undefined;
      expect(lastCall?.[0]?.value).toBe(true);
    });
  });

  it('leaves date fields as strings without coercion', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(
      <Harness
        initial={[{ field: 'teacher_id', op: 'eq', value: '' }]}
        fieldTypes={{ teacher_id: 'date' }}
        onChangeSpy={spy}
      />,
    );
    const input = screen.getByTestId('filter-value-0');
    await user.clear(input);
    await user.type(input, '2026-01-01');
    await waitFor(() => {
      const lastCall = spy.mock.calls.at(-1)?.[0] as FilterEntry[] | undefined;
      expect(lastCall?.[0]?.value).toBe('2026-01-01');
    });
    // No error for date fields
    expect(screen.queryByTestId('filter-coerce-error-0')).toBeNull();
  });
});
