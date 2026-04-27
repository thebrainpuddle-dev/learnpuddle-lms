// src/components/versioning/RevisionHistoryPanel.tsx
//
// Two-pane revision history panel consumed by CourseEditorPage,
// ModuleContentEditor, and content editors.
//
// Left pane:  paginated list of revisions ("Load more" button, no infinite scroll).
// Right pane: snapshot viewer for the selected revision, with optional diff
//             against the immediately preceding revision.
//
// Props:
//   kind      — "course" | "module" | "content"
//   objectId  — UUID of the target object
//   onRestored — optional callback invoked after a successful restore

import React, { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import {
  ArrowPathIcon,
  ClockIcon,
  ArrowsRightLeftIcon,
  DocumentMagnifyingGlassIcon,
} from '@heroicons/react/24/outline';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { useToast } from '../common/Toast';
import { RevisionListItem } from './RevisionListItem';
import { JsonDiffView } from './JsonDiffView';
import type { VersioningKind, ContentRevisionListItem } from '../../services/versioningService';
import {
  listRevisions,
  getRevision,
  restoreRevision,
} from '../../services/versioningService';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RevisionHistoryPanelProps {
  kind: VersioningKind;
  objectId: string;
  /** Called after a successful restore so callers can refresh their data. */
  onRestored?: () => void;
}

// ---------------------------------------------------------------------------
// Query key factories
// ---------------------------------------------------------------------------

const revisionKeys = {
  list: (kind: VersioningKind, id: string, page: number) =>
    ['revisions', 'list', kind, id, page] as const,
  detail: (kind: VersioningKind, id: string, rev: number) =>
    ['revisions', 'detail', kind, id, rev] as const,
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const RevisionHistoryPanel: React.FC<RevisionHistoryPanelProps> = ({
  kind,
  objectId,
  onRestored,
}) => {
  const toast = useToast();
  const queryClient = useQueryClient();

  // ── State ────────────────────────────────────────────────────────────────
  const [page, setPage] = useState(1);
  const [allRevisions, setAllRevisions] = useState<ContentRevisionListItem[]>([]);
  const [selectedRev, setSelectedRev] = useState<ContentRevisionListItem | null>(null);
  const [diffMode, setDiffMode] = useState(false);
  const [confirmRestore, setConfirmRestore] = useState<ContentRevisionListItem | null>(null);

  // ── List query ───────────────────────────────────────────────────────────
  const listQuery = useQuery({
    queryKey: revisionKeys.list(kind, objectId, page),
    queryFn: () => listRevisions(kind, objectId, page),
    placeholderData: keepPreviousData,
    enabled: !!objectId,
  });

  // Accumulate pages into `allRevisions` when new data arrives.
  React.useEffect(() => {
    if (!listQuery.data) return;
    const incoming = listQuery.data.results;
    setAllRevisions((prev) => {
      // Deduplicate by id (avoids doubles on React strict mode double-effect).
      const existingIds = new Set(prev.map((r) => r.id));
      const fresh = incoming.filter((r) => !existingIds.has(r.id));
      return page === 1 ? incoming : [...prev, ...fresh];
    });
  }, [listQuery.data, page]);

  const hasMore =
    listQuery.data != null &&
    listQuery.data.next != null;

  const totalCount = listQuery.data?.count ?? 0;

  // ── Detail query — only fires when a revision is selected ────────────────
  const detailQuery = useQuery({
    queryKey: revisionKeys.detail(kind, objectId, selectedRev?.revision_number ?? 0),
    queryFn: () => getRevision(kind, objectId, selectedRev!.revision_number),
    enabled: selectedRev != null,
  });

  // Snapshot of the revision immediately before the selected one (for diff).
  // Compute unconditionally from revision_number so the detail query can fetch
  // it directly even when the predecessor row hasn't been loaded into allRevisions
  // yet (e.g. predecessor lives on a page the user hasn't scrolled to).
  const prevRevNumber = selectedRev != null && selectedRev.revision_number > 1
    ? selectedRev.revision_number - 1
    : null;

  const prevDetailQuery = useQuery({
    queryKey: revisionKeys.detail(kind, objectId, prevRevNumber ?? 0),
    queryFn: () => getRevision(kind, objectId, prevRevNumber!),
    enabled: diffMode && prevRevNumber != null,
  });

  // ── Restore mutation ─────────────────────────────────────────────────────
  const restoreMutation = useMutation({
    mutationFn: (rev: ContentRevisionListItem) =>
      restoreRevision(kind, objectId, rev.revision_number),
    onSuccess: (_data, rev) => {
      toast.success(
        `Restored to revision ${rev.revision_number}`,
        'A new revision has been created preserving the current state.',
      );
      // Invalidate so the list refetches and shows the new restore revision.
      queryClient.invalidateQueries({ queryKey: ['revisions', 'list', kind, objectId] });
      // Reset to page 1 to show the fresh head.
      setPage(1);
      setAllRevisions([]);
      setSelectedRev(null);
      onRestored?.();
    },
    onError: (err: unknown) => {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        toast.error('Revision not found', 'The revision may have been deleted.');
      } else if (status === 500) {
        toast.error('Server error', 'The restore failed on the server. Check the server logs.');
      } else {
        toast.error('Restore failed', 'An unexpected error occurred. Please try again.');
      }
    },
  });

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleSelect = useCallback((rev: ContentRevisionListItem) => {
    setSelectedRev((prev) => (prev?.id === rev.id ? null : rev));
  }, []);

  const handleRestoreClick = useCallback((rev: ContentRevisionListItem) => {
    setConfirmRestore(rev);
  }, []);

  const handleConfirmRestore = useCallback(() => {
    if (confirmRestore) {
      restoreMutation.mutate(confirmRestore);
    }
    setConfirmRestore(null);
  }, [confirmRestore, restoreMutation]);

  const handleLoadMore = useCallback(() => {
    setPage((p) => p + 1);
  }, []);

  // ── Render helpers ───────────────────────────────────────────────────────
  const renderBadge = () => {
    if (totalCount === 0) return null;
    const label = totalCount > 99 ? '99+' : String(totalCount);
    return (
      <span className="ml-1.5 inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
        {label}
      </span>
    );
  };

  // ── Empty / loading states ───────────────────────────────────────────────
  const isInitialLoading = listQuery.isLoading && allRevisions.length === 0;

  if (isInitialLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-400">
        <ArrowPathIcon className="h-6 w-6 animate-spin mr-2" />
        Loading revision history…
      </div>
    );
  }

  if (listQuery.isError) {
    return (
      <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
        Failed to load revision history. Please refresh and try again.
      </div>
    );
  }

  if (allRevisions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-gray-400 gap-3">
        <ClockIcon className="h-10 w-10" />
        <p className="text-sm font-medium">No revision history yet.</p>
        <p className="text-xs text-gray-400">Revisions are created automatically on each save.</p>
      </div>
    );
  }

  // ── Main render ──────────────────────────────────────────────────────────
  const selectedDetail = detailQuery.data;
  const prevDetail = prevDetailQuery.data;

  return (
    <>
      <div className="flex flex-col lg:flex-row gap-4 h-full min-h-[400px]">
        {/* ── Left pane: revision list ─────────────────────────────────────── */}
        <div className="lg:w-72 flex-shrink-0 flex flex-col">
          <div className="flex items-center gap-2 mb-3">
            <ClockIcon className="h-5 w-5 text-gray-400" />
            <span className="text-sm font-semibold text-gray-700">
              Revision history
            </span>
            {renderBadge()}
          </div>

          <div className="flex-1 overflow-y-auto space-y-1 pr-1">
            {allRevisions.map((rev) => (
              <RevisionListItem
                key={rev.id}
                revision={rev}
                isSelected={selectedRev?.id === rev.id}
                onSelect={handleSelect}
                onRestoreClick={handleRestoreClick}
              />
            ))}
          </div>

          {hasMore && (
            <button
              type="button"
              onClick={handleLoadMore}
              disabled={listQuery.isFetching}
              className="mt-3 w-full py-2 text-sm font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
            >
              {listQuery.isFetching ? (
                <span className="flex items-center justify-center gap-1.5">
                  <ArrowPathIcon className="h-4 w-4 animate-spin" />
                  Loading…
                </span>
              ) : (
                'Load more'
              )}
            </button>
          )}
        </div>

        {/* ── Right pane: snapshot / diff viewer ──────────────────────────── */}
        <div className="flex-1 flex flex-col min-w-0">
          {!selectedRev ? (
            <div className="flex flex-col items-center justify-center h-full py-16 text-gray-400 gap-3">
              <DocumentMagnifyingGlassIcon className="h-10 w-10" />
              <p className="text-sm">Select a revision on the left to view its snapshot.</p>
            </div>
          ) : (
            <>
              {/* Toolbar */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-700">
                    Snapshot — v{selectedRev.revision_number}
                  </span>
                  {detailQuery.isLoading && (
                    <ArrowPathIcon className="h-4 w-4 animate-spin text-gray-400" />
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {/* Diff toggle */}
                  <button
                    type="button"
                    onClick={() => setDiffMode((d) => !d)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 ${
                      diffMode
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                    title="Toggle diff against previous revision"
                  >
                    <ArrowsRightLeftIcon className="h-3.5 w-3.5" />
                    Compare with prev
                  </button>

                  {/* Restore button */}
                  <button
                    type="button"
                    onClick={() => handleRestoreClick(selectedRev)}
                    disabled={restoreMutation.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-100 text-amber-700 hover:bg-amber-200 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Restore this version
                  </button>
                </div>
              </div>

              {/* Content */}
              {detailQuery.isLoading ? (
                <div className="flex items-center justify-center py-12 text-gray-400">
                  <ArrowPathIcon className="h-5 w-5 animate-spin mr-2" />
                  Loading snapshot…
                </div>
              ) : detailQuery.isError ? (
                <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
                  Failed to load snapshot.
                </div>
              ) : selectedDetail ? (
                diffMode ? (
                  prevDetailQuery.isError ? (
                    <div
                      role="alert"
                      className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700"
                      data-testid="prev-detail-error"
                    >
                      Could not load previous revision
                      {(prevDetailQuery.error as Error | null)?.message
                        ? `: ${(prevDetailQuery.error as Error).message}`
                        : '.'}
                    </div>
                  ) : prevDetail ? (
                    <JsonDiffView
                      oldValue={prevDetail.snapshot_json}
                      newValue={selectedDetail.snapshot_json}
                      className="flex-1 max-h-[560px]"
                    />
                  ) : selectedRev.revision_number === 1 ? (
                    <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 text-sm text-amber-700">
                      This is the first revision — no previous snapshot to compare against.
                      <div className="mt-2">
                        <JsonDiffView
                          oldValue={undefined}
                          newValue={selectedDetail.snapshot_json}
                          className="max-h-[480px]"
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-center py-12 text-gray-400">
                      <ArrowPathIcon className="h-5 w-5 animate-spin mr-2" />
                      Loading previous snapshot…
                    </div>
                  )
                ) : (
                  <div className="flex-1 overflow-auto rounded-lg border border-gray-200 bg-gray-50 p-3 max-h-[560px]">
                    <pre className="text-xs font-mono text-gray-700 whitespace-pre-wrap break-words">
                      {JSON.stringify(selectedDetail.snapshot_json, null, 2)}
                    </pre>
                  </div>
                )
              ) : null}
            </>
          )}
        </div>
      </div>

      {/* Restore confirm dialog */}
      <ConfirmDialog
        isOpen={confirmRestore != null}
        onClose={() => setConfirmRestore(null)}
        onConfirm={handleConfirmRestore}
        title={`Restore to revision ${confirmRestore?.revision_number ?? ''}`}
        message="Restore will create a new revision — the current state is preserved and you can undo this operation by restoring the latest revision."
        confirmLabel="Restore"
        cancelLabel="Cancel"
        variant="warning"
        loading={restoreMutation.isPending}
      />
    </>
  );
};

// ---------------------------------------------------------------------------
// Revision count badge hook — used by editor tabs to show "History (N)"
// ---------------------------------------------------------------------------

export function useRevisionCount(
  kind: VersioningKind,
  objectId: string | undefined,
): number {
  const query = useQuery({
    queryKey: ['revisions', 'list', kind, objectId ?? '', 1],
    queryFn: () => listRevisions(kind, objectId!, 1),
    enabled: !!objectId,
    staleTime: 30_000,
  });
  return query.data?.count ?? 0;
}
