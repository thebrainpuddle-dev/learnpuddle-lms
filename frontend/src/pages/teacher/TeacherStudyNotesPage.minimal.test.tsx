// Test with real TanStack Query (only api mocked) + staleTime: Infinity
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

vi.mock('../../config/api', () => ({
  default: { get: vi.fn() },
}));

vi.mock('../../components/student/StudySummaryPanel', () => ({
  StudySummaryPanel: vi.fn(() => null),
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

// Real TanStack Query - NOT mocked
import { TeacherStudyNotesPage } from './TeacherStudyNotesPage';
import api from '../../config/api';

describe('real TanStack Query + staleTime fix', () => {
  it('renders empty state without hanging', async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
    const client = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
          staleTime: Infinity,  // KEY: prevents refetch after initial resolve
          refetchOnWindowFocus: false,  // KEY: prevents focus-triggered refetch
        },
      },
    });
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <TeacherStudyNotesPage />
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(await screen.findByText('No courses available')).toBeInTheDocument();
    expect(container).toBeDefined();
  });
});
