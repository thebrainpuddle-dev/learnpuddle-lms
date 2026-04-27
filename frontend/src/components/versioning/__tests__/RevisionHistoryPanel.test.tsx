// src/components/versioning/__tests__/RevisionHistoryPanel.test.tsx
//
// Tests for RevisionHistoryPanel covering:
//  1. List render
//  2. Pagination / "Load more"
//  3. Snapshot view
//  4. Diff mode (compare with previous)
//  5. Diff empty state (first revision)
//  6. Restore happy path
//  7. Restore confirm-dialog cancel
//  8. Restore 404 error
//  9. Restore 500 error
// 10. Tab-badge count (useRevisionCount)

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RevisionHistoryPanel, useRevisionCount } from '../RevisionHistoryPanel';
import * as versioningService from '../../../services/versioningService';
import type { PaginatedRevisions, ContentRevisionDetail } from '../../../services/versioningService';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../../services/versioningService');

// Module-scope mutable toast mock so tests can assert distinct messages.
const toastCalls = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() };
vi.mock('../../../components/common/Toast', () => ({
  useToast: () => toastCalls,
}));

const mockedListRevisions = vi.mocked(versioningService.listRevisions);
const mockedGetRevision = vi.mocked(versioningService.getRevision);
const mockedRestoreRevision = vi.mocked(versioningService.restoreRevision);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const makeRevision = (n: number) => ({
  id: `rev-${n}`,
  revision_number: n,
  target_type: 'course',
  object_id: 'obj-1',
  change_summary: n === 1 ? 'create' : 'update',
  changed_by: `user-${n}`,
  changed_by_name: `User ${n}`,
  created_at: `2026-01-0${n}T00:00:00Z`,
});

const pageOne: PaginatedRevisions = {
  count: 3,
  next: 'http://api/revisions/?page=2',
  previous: null,
  results: [makeRevision(3), makeRevision(2)],
};

const pageTwo: PaginatedRevisions = {
  count: 3,
  next: null,
  previous: 'http://api/revisions/?page=1',
  results: [makeRevision(1)],
};

const detailRev3: ContentRevisionDetail = {
  ...makeRevision(3),
  snapshot_json: { title: 'Course v3', is_published: true },
};

const detailRev2: ContentRevisionDetail = {
  ...makeRevision(2),
  snapshot_json: { title: 'Course v2', is_published: false },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={buildClient()}>{children}</QueryClientProvider>
  );
}

function renderPanel(props?: Partial<React.ComponentProps<typeof RevisionHistoryPanel>>) {
  return render(
    <Wrapper>
      <RevisionHistoryPanel
        kind="course"
        objectId="obj-1"
        {...props}
      />
    </Wrapper>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RevisionHistoryPanel', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedListRevisions.mockResolvedValue(pageOne);
    mockedGetRevision.mockImplementation(async (_kind, _id, rev) => {
      if (rev === 3) return detailRev3;
      if (rev === 2) return detailRev2;
      return detailRev3;
    });
    mockedRestoreRevision.mockResolvedValue({ id: 'obj-1', title: 'Restored' });
  });

  // ── 1. List render ────────────────────────────────────────────────────────
  it('renders the revision list items after loading', async () => {
    renderPanel();

    await waitFor(() => {
      expect(screen.getByText(/User 3/)).toBeInTheDocument();
      expect(screen.getByText(/User 2/)).toBeInTheDocument();
    });
  });

  // ── 2. Pagination / "Load more" ───────────────────────────────────────────
  it('shows "Load more" button when next page exists, and loads page 2 on click', async () => {
    mockedListRevisions
      .mockResolvedValueOnce(pageOne)
      .mockResolvedValueOnce(pageTwo);

    renderPanel();

    const loadMoreBtn = await screen.findByRole('button', { name: /load more/i });
    expect(loadMoreBtn).toBeInTheDocument();

    fireEvent.click(loadMoreBtn);

    await waitFor(() => {
      expect(screen.getByText(/User 1/)).toBeInTheDocument();
    });

    // "Load more" should disappear once next is null
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument();
    });
  });

  // ── 3. Snapshot view ──────────────────────────────────────────────────────
  it('renders snapshot JSON when a revision is selected', async () => {
    renderPanel();

    await screen.findByText(/User 3/);
    const revItem = screen.getByRole('button', { name: /View revision 3/i });
    fireEvent.click(revItem);

    await waitFor(() => {
      expect(screen.getByText(/Course v3/)).toBeInTheDocument();
    });
  });

  // ── 4. Diff mode ──────────────────────────────────────────────────────────
  it('shows diff view comparing to previous revision when "Compare with prev" toggled', async () => {
    mockedListRevisions.mockResolvedValue({
      ...pageOne,
      results: [makeRevision(3), makeRevision(2)],
    });

    renderPanel();

    await screen.findByText(/User 3/);
    // Select revision 3 (which has revision 2 as previous)
    fireEvent.click(screen.getByRole('button', { name: /View revision 3/i }));

    await waitFor(() => {
      expect(screen.getByText(/Course v3/)).toBeInTheDocument();
    });

    // Toggle diff mode
    const diffBtn = screen.getByRole('button', { name: /Compare with prev/i });
    fireEvent.click(diffBtn);

    await waitFor(() => {
      // Should show the diff view with changed key (is_published changed false → true)
      expect(screen.getByText(/~ is_published:/i)).toBeInTheDocument();
    });
  });

  // ── 5. Diff empty state ───────────────────────────────────────────────────
  it('shows "first revision" message in diff mode when there is no previous revision', async () => {
    // Only one revision exists
    mockedListRevisions.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [makeRevision(1)],
    });
    mockedGetRevision.mockResolvedValue({
      ...makeRevision(1),
      snapshot_json: { title: 'First version' },
    });

    renderPanel();

    await screen.findByText(/User 1/);
    fireEvent.click(screen.getByRole('button', { name: /View revision 1/i }));

    await waitFor(() => {
      expect(screen.getByText(/First version/)).toBeInTheDocument();
    });

    const diffBtn = screen.getByRole('button', { name: /Compare with prev/i });
    fireEvent.click(diffBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/This is the first revision — no previous snapshot/i),
      ).toBeInTheDocument();
    });
  });

  // ── 6. Restore happy path ─────────────────────────────────────────────────
  it('calls restoreRevision and fires onRestored callback after confirming', async () => {
    const onRestored = vi.fn();
    renderPanel({ onRestored });

    await screen.findByText(/User 3/);
    fireEvent.click(screen.getByRole('button', { name: /Restore revision 3/i }));

    // Confirm dialog should appear
    await waitFor(() => {
      expect(screen.getByText(/Restore to revision 3/i)).toBeInTheDocument();
    });

    // Click "Restore" in the dialog
    fireEvent.click(screen.getByRole('button', { name: /^Restore$/i }));

    await waitFor(() => {
      expect(mockedRestoreRevision).toHaveBeenCalledWith('course', 'obj-1', 3);
      expect(onRestored).toHaveBeenCalledTimes(1);
    });
  });

  // ── 7. Restore cancel ────────────────────────────────────────────────────
  it('does NOT call restoreRevision when cancel is clicked in the confirm dialog', async () => {
    renderPanel();

    await screen.findByText(/User 3/);
    fireEvent.click(screen.getByRole('button', { name: /Restore revision 3/i }));

    await waitFor(() => {
      expect(screen.getByText(/Restore to revision 3/i)).toBeInTheDocument();
    });

    // Click Cancel
    fireEvent.click(screen.getByRole('button', { name: /^Cancel$/i }));

    await waitFor(() => {
      expect(mockedRestoreRevision).not.toHaveBeenCalled();
    });
  });

  // ── 8. Restore 404 ───────────────────────────────────────────────────────
  it('shows a 404-specific toast message when restore returns 404', async () => {
    mockedRestoreRevision.mockRejectedValueOnce({
      response: { status: 404 },
    });

    renderPanel();
    await screen.findByText(/User 3/);
    fireEvent.click(screen.getByRole('button', { name: /Restore revision 3/i }));
    await waitFor(() => screen.getByText(/Restore to revision 3/i));
    fireEvent.click(screen.getByRole('button', { name: /^Restore$/i }));

    await waitFor(() => {
      expect(toastCalls.error).toHaveBeenCalledWith(
        'Revision not found',
        expect.stringContaining('deleted'),
      );
    });
  });

  // ── 9. Restore 500 ───────────────────────────────────────────────────────
  it('shows a 500-specific toast message when restore returns 500', async () => {
    mockedRestoreRevision.mockRejectedValueOnce({
      response: { status: 500 },
    });

    renderPanel();
    await screen.findByText(/User 3/);
    fireEvent.click(screen.getByRole('button', { name: /Restore revision 3/i }));
    await waitFor(() => screen.getByText(/Restore to revision 3/i));
    fireEvent.click(screen.getByRole('button', { name: /^Restore$/i }));

    await waitFor(() => {
      expect(toastCalls.error).toHaveBeenCalledWith(
        'Server error',
        expect.stringContaining('server'),
      );
    });
    // Panel should still be mounted (no crash)
    expect(screen.queryByText(/User 3/)).not.toBeNull();
  });

  // ── 9b. Restore generic error ────────────────────────────────────────────
  it('shows a generic toast message when restore returns an unexpected error', async () => {
    mockedRestoreRevision.mockRejectedValueOnce(new Error('Network error'));

    renderPanel();
    await screen.findByText(/User 3/);
    fireEvent.click(screen.getByRole('button', { name: /Restore revision 3/i }));
    await waitFor(() => screen.getByText(/Restore to revision 3/i));
    fireEvent.click(screen.getByRole('button', { name: /^Restore$/i }));

    await waitFor(() => {
      expect(toastCalls.error).toHaveBeenCalledWith(
        'Restore failed',
        expect.stringContaining('unexpected'),
      );
    });
  });

  // ── 9c. Diff mode — previous revision fetch error ──────────────────────────
  it('shows an error alert in diff mode when the previous-revision query fails', async () => {
    // Revision 3 is selected; revision 2 (prev) fails to load.
    mockedListRevisions.mockResolvedValue({
      ...pageOne,
      results: [makeRevision(3), makeRevision(2)],
    });
    mockedGetRevision.mockImplementation(async (_kind, _id, rev) => {
      if (rev === 3) return detailRev3;
      // Simulating a network error for rev 2
      throw Object.assign(new Error('Network timeout'), {
        response: { status: 503 },
      });
    });

    renderPanel();

    await screen.findByText(/User 3/);
    fireEvent.click(screen.getByRole('button', { name: /View revision 3/i }));
    await waitFor(() => {
      expect(screen.getByText(/Course v3/)).toBeInTheDocument();
    });

    // Toggle diff mode — this enables prevDetailQuery which will fail.
    const diffBtn = screen.getByRole('button', { name: /Compare with prev/i });
    fireEvent.click(diffBtn);

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveTextContent(/Could not load previous revision/i);
    });
  });

  // ── 10. Tab-badge count ───────────────────────────────────────────────────
  it('useRevisionCount returns the count from the API', async () => {
    mockedListRevisions.mockResolvedValue({
      count: 7,
      next: null,
      previous: null,
      results: [],
    });

    let capturedCount = -1;
    function Counter() {
      capturedCount = useRevisionCount('course', 'obj-1');
      return <span data-testid="count">{capturedCount}</span>;
    }

    render(
      <QueryClientProvider client={buildClient()}>
        <Counter />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('count')).toHaveTextContent('7');
    });
  });
});
