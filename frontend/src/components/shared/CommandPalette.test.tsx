// src/components/shared/CommandPalette.test.tsx
//
// Unit tests for the CommandPalette component.
// Covers: course search, teacher search, group search, keyboard nav, close.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { render } from '../../test-utils';
import { CommandPalette } from './CommandPalette';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../../config/api', () => ({
  default: {
    get: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

import api from '../../config/api';
const mockGet = api.get as ReturnType<typeof vi.fn>;

// ─── Helpers ──────────────────────────────────────────────────────────────────

const onClose = vi.fn();

function renderPalette(isOpen = true) {
  return render(<CommandPalette isOpen={isOpen} onClose={onClose} />, {
    useMemoryRouter: true,
  });
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('CommandPalette — basic', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Default: resolve all GET calls to empty results
    mockGet.mockResolvedValue({ data: { results: [], courses: [], content: [] } });
  });

  it('renders search input when open', () => {
    renderPalette();
    expect(screen.getByPlaceholderText(/search pages, courses, teachers/i)).toBeInTheDocument();
  });

  it('renders nothing when closed', () => {
    renderPalette(false);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('calls onClose when Escape is pressed', async () => {
    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when backdrop is clicked', () => {
    renderPalette();
    // The backdrop div with aria-hidden
    const backdrop = document.querySelector('[aria-hidden]') as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows admin pages by default (no query)', async () => {
    renderPalette();
    // Dashboard + Courses + etc should appear in pages section
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Courses')).toBeInTheDocument();
  });
});

describe('CommandPalette — course search', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows course results from API', async () => {
    // /courses/search/ returns courses
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/courses/search/')) {
        return Promise.resolve({
          data: {
            query: 'math',
            courses: [{ id: 'c1', title: 'Advanced Mathematics', description: 'Algebra & Geometry' }],
            content: [],
          },
        });
      }
      return Promise.resolve({ data: { results: [] } });
    });

    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: 'math' } });

    await waitFor(() => {
      expect(screen.getByText('Advanced Mathematics')).toBeInTheDocument();
    });
  });

  it('navigates to course edit page on click', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/courses/search/')) {
        return Promise.resolve({
          data: {
            query: 'sci',
            courses: [{ id: 'c99', title: 'Science Basics' }],
            content: [],
          },
        });
      }
      return Promise.resolve({ data: { results: [] } });
    });

    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: 'sci' } });

    await waitFor(() => screen.getByText('Science Basics'));
    fireEvent.click(screen.getByText('Science Basics'));
    expect(mockNavigate).toHaveBeenCalledWith('/admin/courses/c99/edit');
  });
});

describe('CommandPalette — teacher search', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows teacher results from API', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/admin/teachers/')) {
        return Promise.resolve({
          data: {
            results: [
              {
                id: 't1',
                first_name: 'Jane',
                last_name: 'Doe',
                email: 'jane@school.com',
                designation: 'TGT',
                department: 'Mathematics',
                is_active: true,
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: { results: [], courses: [], content: [] } });
    });

    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: 'jane' } });

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });
    // subtitle shows designation · department
    expect(screen.getByText(/TGT/)).toBeInTheDocument();
  });

  it('navigates to /admin/teachers when teacher result is clicked', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/admin/teachers/')) {
        return Promise.resolve({
          data: {
            results: [
              { id: 't2', first_name: 'Alice', last_name: 'Smith', email: 'alice@school.com' },
            ],
          },
        });
      }
      return Promise.resolve({ data: { results: [], courses: [], content: [] } });
    });

    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: 'alice' } });

    await waitFor(() => screen.getByText('Alice Smith'));
    fireEvent.click(screen.getByText('Alice Smith'));
    expect(mockNavigate).toHaveBeenCalledWith('/admin/teachers');
  });

  it('shows Teachers section header when teacher results appear', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/admin/teachers/')) {
        return Promise.resolve({
          data: {
            results: [
              { id: 't3', first_name: 'Bob', last_name: 'Jones', email: 'bob@school.com' },
            ],
          },
        });
      }
      return Promise.resolve({ data: { results: [], courses: [], content: [] } });
    });

    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: 'bob' } });

    await waitFor(() => {
      expect(screen.getByText('Teachers')).toBeInTheDocument();
    });
  });

  it('falls back to email as title when teacher has no name', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/admin/teachers/')) {
        return Promise.resolve({
          data: {
            results: [
              { id: 't4', first_name: '', last_name: '', email: 'nameless@school.com' },
            ],
          },
        });
      }
      return Promise.resolve({ data: { results: [], courses: [], content: [] } });
    });

    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: 'nameless' } });

    await waitFor(() => {
      expect(screen.getByText('nameless@school.com')).toBeInTheDocument();
    });
  });
});

describe('CommandPalette — group search', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows group results filtered by query', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/teacher-groups/')) {
        return Promise.resolve({
          data: {
            results: [
              { id: 'g1', name: 'Science Department', description: 'All science teachers', group_type: 'department' },
              { id: 'g2', name: 'Maths Team', description: 'Mathematics cohort', group_type: 'subject' },
            ],
          },
        });
      }
      return Promise.resolve({ data: { results: [], courses: [], content: [] } });
    });

    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: 'science' } });

    await waitFor(() => {
      expect(screen.getByText('Science Department')).toBeInTheDocument();
    });
    // Maths Team should NOT appear — query is 'science'
    expect(screen.queryByText('Maths Team')).not.toBeInTheDocument();
  });

  it('navigates to /admin/groups when group result is clicked', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/teacher-groups/')) {
        return Promise.resolve({
          data: {
            results: [{ id: 'g3', name: 'English Faculty', description: 'English teachers' }],
          },
        });
      }
      return Promise.resolve({ data: { results: [], courses: [], content: [] } });
    });

    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: 'english' } });

    await waitFor(() => screen.getByText('English Faculty'));
    fireEvent.click(screen.getByText('English Faculty'));
    expect(mockNavigate).toHaveBeenCalledWith('/admin/groups');
  });

  it('shows Groups section header when group results appear', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/teacher-groups/')) {
        return Promise.resolve({
          data: {
            results: [{ id: 'g4', name: 'History Group', description: 'Historians' }],
          },
        });
      }
      return Promise.resolve({ data: { results: [], courses: [], content: [] } });
    });

    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: 'history' } });

    await waitFor(() => {
      expect(screen.getByText('Groups')).toBeInTheDocument();
    });
  });
});

describe('CommandPalette — empty state', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockGet.mockResolvedValue({ data: { results: [], courses: [], content: [] } });
  });

  it('shows no-results state when query has no matches', async () => {
    renderPalette();
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.change(input, { target: { value: 'xyzxyzxyz' } });

    await waitFor(() => {
      expect(screen.getByText('No results found')).toBeInTheDocument();
    });
  });
});
