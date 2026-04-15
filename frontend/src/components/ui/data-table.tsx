// src/components/ui/data-table.tsx
//
// Reusable DataTable component built on @tanstack/react-table.
// Integrates with the existing shadcn/ui Table component and supports
// sorting, filtering, and pagination out of the box.
//
// NOTE: @tanstack/react-table must be installed before this component can be used.
//   npm install @tanstack/react-table
//
// Usage:
//   import { DataTable, DataTableColumnHeader } from '@/components/ui/data-table';
//
//   const columns: ColumnDef<MyRow>[] = [
//     { accessorKey: 'name', header: ({ column }) => <DataTableColumnHeader column={column} title="Name" /> },
//     { accessorKey: 'email', header: 'Email' },
//   ];
//
//   <DataTable columns={columns} data={rows} />

import React, { useState } from 'react';
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
  type VisibilityState,
  type Table as TanStackTable,
  type Column,
  type Row,
} from '@tanstack/react-table';

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './table';
import { Button } from './button';
import { Input } from './input';
import { DataTablePagination } from './data-table-pagination';
import { cn } from '../../lib/utils';
import {
  ChevronUpIcon,
  ChevronDownIcon,
  ChevronUpDownIcon,
} from '@heroicons/react/24/outline';

// ── Type helpers ────────────────────────────────────────────────────────

/** Re-export commonly used TanStack types for convenience. */
export type { ColumnDef, SortingState, ColumnFiltersState, VisibilityState, Row };

/** Alias for the TanStack table instance (generic). */
export type DataTableInstance<TData> = TanStackTable<TData>;

// ── DataTableColumnHeader ───────────────────────────────────────────────

interface DataTableColumnHeaderProps<TData, TValue>
  extends React.HTMLAttributes<HTMLDivElement> {
  column: Column<TData, TValue>;
  title: string;
}

/**
 * Column header with sort toggle. Clicking cycles through
 * ascending -> descending -> no sort.
 */
export function DataTableColumnHeader<TData, TValue>({
  column,
  title,
  className,
}: DataTableColumnHeaderProps<TData, TValue>) {
  if (!column.getCanSort()) {
    return <div className={cn(className)}>{title}</div>;
  }

  const sorted = column.getIsSorted();

  const ariaSortValue = sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : 'none';

  return (
    <button
      type="button"
      className={cn(
        '-ml-3 flex h-8 items-center gap-1 rounded-md px-3 text-xs font-medium uppercase tracking-wide text-gray-500',
        'hover:bg-gray-100 hover:text-gray-700',
        'data-[state=open]:bg-gray-100',
        className,
      )}
      onClick={() => column.toggleSorting(sorted === 'asc')}
      aria-sort={ariaSortValue}
    >
      <span>{title}</span>
      {sorted === 'desc' ? (
        <ChevronDownIcon className="ml-1 h-4 w-4" />
      ) : sorted === 'asc' ? (
        <ChevronUpIcon className="ml-1 h-4 w-4" />
      ) : (
        <ChevronUpDownIcon className="ml-1 h-4 w-4 text-gray-400" />
      )}
    </button>
  );
}

// ── DataTable ───────────────────────────────────────────────────────────

interface DataTableProps<TData, TValue> {
  /** Column definitions (from @tanstack/react-table). */
  columns: ColumnDef<TData, TValue>[];
  /** Data array to render. */
  data: TData[];
  /** Optional key accessor to identify filter-able column (shown as search box). */
  filterColumn?: string;
  /** Placeholder for the filter input. */
  filterPlaceholder?: string;
  /** If true, hide the built-in filter input. */
  hideFilter?: boolean;
  /** If true, hide the pagination controls. */
  hidePagination?: boolean;
  /** Default page size. */
  pageSize?: number;
  /** Message shown when no rows match. */
  emptyMessage?: string;
  /** Extra toolbar content rendered to the right of the filter. */
  toolbarRight?: React.ReactNode;
  /** Callback when a row is clicked. */
  onRowClick?: (row: TData) => void;
  /** Class name applied to the wrapper div. */
  className?: string;
}

export function DataTable<TData, TValue>({
  columns,
  data,
  filterColumn,
  filterPlaceholder = 'Filter...',
  hideFilter = false,
  hidePagination = false,
  pageSize = 10,
  emptyMessage = 'No results.',
  toolbarRight,
  onRowClick,
  className,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [rowSelection, setRowSelection] = useState({});

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    initialState: {
      pagination: { pageSize },
    },
  });

  return (
    <div className={cn('space-y-4', className)}>
      {/* Toolbar */}
      {(!hideFilter || toolbarRight) && (
        <div className="flex items-center justify-between gap-2">
          {!hideFilter && filterColumn && (
            <Input
              placeholder={filterPlaceholder}
              value={
                (table.getColumn(filterColumn)?.getFilterValue() as string) ?? ''
              }
              onChange={(event) =>
                table
                  .getColumn(filterColumn)
                  ?.setFilterValue(event.target.value)
              }
              className="max-w-sm"
            />
          )}
          {toolbarRight && <div className="ml-auto flex items-center gap-2">{toolbarRight}</div>}
        </div>
      )}

      {/* Table */}
      <div className="rounded-md border border-gray-200 overflow-x-auto">
        <Table className="min-w-[600px]">
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id} colSpan={header.colSpan}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && 'selected'}
                  className={cn(onRowClick && 'cursor-pointer')}
                  onClick={() => onRowClick?.(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center text-gray-500"
                >
                  {emptyMessage}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {!hidePagination && <DataTablePagination table={table} />}
    </div>
  );
}
