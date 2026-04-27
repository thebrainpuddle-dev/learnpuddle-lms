// src/components/reportBuilder/AggregateBuilder.test.tsx
//
// Tests the AggregateBuilder component: add rows with default values,
// edit fn/field/alias, remove rows.

import React, { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AggregateBuilder } from './AggregateBuilder';
import type {
  AggregateEntry,
  ReportAggregateFn,
} from '../../services/reportBuilderService';

const FIELDS = ['teacher_id', 'percent'];
const FNS: ReportAggregateFn[] = ['count', 'avg', 'sum'];

function Harness({ initial }: { initial?: AggregateEntry[] }) {
  const [value, setValue] = useState<AggregateEntry[]>(initial ?? []);
  return (
    <AggregateBuilder
      availableFields={FIELDS}
      availableFns={FNS}
      value={value}
      onChange={setValue}
    />
  );
}

describe('AggregateBuilder', () => {
  it('renders the empty-state copy when no aggregates are configured', () => {
    render(<Harness />);
    expect(screen.getByTestId('aggregate-empty')).toBeInTheDocument();
  });

  it('adds a default row (count, id) when "Add aggregate" is clicked', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByTestId('aggregate-add'));
    expect(screen.getByTestId('aggregate-fn-0')).toHaveValue('count');
    expect(screen.getByTestId('aggregate-field-0')).toHaveValue('id');
  });

  it('allows editing fn/field/alias on an existing row', async () => {
    const user = userEvent.setup();
    render(
      <Harness
        initial={[{ fn: 'count', field: 'id', alias: '' }]}
      />,
    );
    await user.selectOptions(screen.getByTestId('aggregate-fn-0'), 'avg');
    await user.selectOptions(screen.getByTestId('aggregate-field-0'), 'percent');
    const aliasInput = screen.getByTestId('aggregate-alias-0') as HTMLInputElement;
    await user.type(aliasInput, 'avg_score');
    expect(screen.getByTestId('aggregate-fn-0')).toHaveValue('avg');
    expect(screen.getByTestId('aggregate-field-0')).toHaveValue('percent');
    expect(aliasInput.value).toBe('avg_score');
  });

  it('removes a row when the trash button is clicked', async () => {
    const user = userEvent.setup();
    render(
      <Harness
        initial={[{ fn: 'count', field: 'id', alias: '' }]}
      />,
    );
    expect(screen.getByTestId('aggregate-row-0')).toBeInTheDocument();
    await user.click(screen.getByTestId('aggregate-remove-0'));
    expect(screen.queryByTestId('aggregate-row-0')).toBeNull();
    expect(screen.getByTestId('aggregate-empty')).toBeInTheDocument();
  });

  it('always surfaces "id" in the field dropdown even if absent from whitelist', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByTestId('aggregate-add'));
    const fieldSelect = screen.getByTestId('aggregate-field-0');
    // id + the two whitelist fields should be present
    expect(Array.from(fieldSelect.querySelectorAll('option')).map((o) => o.value))
      .toEqual(expect.arrayContaining(['id', 'teacher_id', 'percent']));
  });
});
