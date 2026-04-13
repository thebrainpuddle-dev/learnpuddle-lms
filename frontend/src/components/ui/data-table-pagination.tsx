// src/components/ui/data-table-pagination.tsx
//
// Pagination controls for DataTable, built on top of @tanstack/react-table
// and the shadcn/ui Button component.
//
// Usage (standalone — normally used internally by DataTable):
//   import { DataTablePagination } from '@/components/ui/data-table-pagination';
//   <DataTablePagination table={tableInstance} />

import React from 'react';
import { type Table } from '@tanstack/react-table';
import { Button } from './button';
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
} from '@heroicons/react/24/outline';
import { cn } from '../../lib/utils';

interface DataTablePaginationProps<TData> {
  table: Table<TData>;
  /** Page size options shown in the select dropdown. */
  pageSizeOptions?: number[];
  /** If true, show "X of Y row(s) selected" text. */
  showSelectedCount?: boolean;
  /** Class name applied to the wrapper div. */
  className?: string;
}

export function DataTablePagination<TData>({
  table,
  pageSizeOptions = [10, 20, 30, 50],
  showSelectedCount = false,
  className,
}: DataTablePaginationProps<TData>) {
  return (
    <div
      className={cn(
        'flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between px-2',
        className,
      )}
    >
      {/* Left: selection count or row count */}
      <div className="text-sm text-gray-500">
        {showSelectedCount ? (
          <>
            {table.getFilteredSelectedRowModel().rows.length} of{' '}
            {table.getFilteredRowModel().rows.length} row(s) selected.
          </>
        ) : (
          <>
            {table.getFilteredRowModel().rows.length} row(s) total.
          </>
        )}
      </div>

      {/* Right: page size + navigation */}
      <div className="flex items-center gap-4 sm:gap-6 lg:gap-8">
        {/* Rows per page */}
        <div className="flex items-center gap-2">
          <label htmlFor="dt-page-size" className="text-sm font-medium text-gray-700">Rows per page</label>
          <select
            id="dt-page-size"
            value={table.getState().pagination.pageSize}
            onChange={(e) => table.setPageSize(Number(e.target.value))}
            className="h-8 w-[70px] rounded-md border border-gray-300 bg-white px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>

        {/* Page indicator */}
        <div className="flex w-[100px] items-center justify-center text-sm font-medium text-gray-700">
          Page {table.getState().pagination.pageIndex + 1} of{' '}
          {table.getPageCount()}
        </div>

        {/* Navigation buttons */}
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
            aria-label="Go to first page"
          >
            <ChevronDoubleLeftIcon className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            aria-label="Go to previous page"
          >
            <ChevronLeftIcon className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            aria-label="Go to next page"
          >
            <ChevronRightIcon className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
            disabled={!table.getCanNextPage()}
            aria-label="Go to last page"
          >
            <ChevronDoubleRightIcon className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
