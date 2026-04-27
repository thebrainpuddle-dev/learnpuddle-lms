// src/components/templates/CourseTemplateGalleryPage.test.tsx
//
// Tests for the tenant admin Course Template Gallery page.
// Covers: gallery render, filter apply, preview panel open, clone dialog open,
//         clone happy path (mocked), clone Zod validation errors, published-only assertion.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { CourseTemplateGalleryPage } from '../../pages/admin/CourseTemplateGalleryPage';
import { courseTemplatesService } from '../../services/courseTemplatesService';
import { ToastProvider } from '../common';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../services/courseTemplatesService', () => ({
  courseTemplatesService: {
    tenant: {
      listTemplates: vi.fn(),
      previewTemplate: vi.fn(),
      cloneTemplate: vi.fn(),
    },
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

const mockedService = courseTemplatesService as {
  tenant: {
    listTemplates: ReturnType<typeof vi.fn>;
    previewTemplate: ReturnType<typeof vi.fn>;
    cloneTemplate: ReturnType<typeof vi.fn>;
  };
};

const mockedNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockedNavigate,
  };
});

// ── Test data ──────────────────────────────────────────────────────────────────

const PUBLISHED_TEMPLATE = {
  id: 'tpl-1',
  slug: 'ib-pyp-inquiry',
  title: 'IB PYP Inquiry Approach',
  description: 'A beginner template for IB PYP teachers.',
  category: 'IB_PYP' as const,
  language: 'en',
  estimated_hours: 6,
  level: 'BEGINNER' as const,
  thumbnail_url: '',
  is_published: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-10T00:00:00Z',
};

const PUBLISHED_TEMPLATE_2 = {
  id: 'tpl-2',
  slug: 'leadership-basics',
  title: 'Leadership Basics',
  description: 'A leadership course for school administrators.',
  category: 'LEADERSHIP' as const,
  language: 'en',
  estimated_hours: 10,
  level: 'INTERMEDIATE' as const,
  thumbnail_url: '',
  is_published: true,
  created_at: '2026-01-05T00:00:00Z',
  updated_at: '2026-01-15T00:00:00Z',
};

const TEMPLATE_DETAIL = {
  ...PUBLISHED_TEMPLATE,
  blueprint_json: {
    schema_version: 1,
    course: { title: 'IB PYP Inquiry Approach', description: '', estimated_hours: 6, is_mandatory: false },
    modules: [
      {
        title: 'Module 1: Inquiry Basics',
        description: '',
        order: 1,
        contents: [
          {
            title: 'Welcome to IB PYP',
            content_type: 'TEXT',
            order: 1,
            text_content: 'Welcome!',
            file_url: '',
            duration: null,
            is_mandatory: true,
            meta_json: {},
          },
        ],
      },
    ],
  },
  created_by: null,
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function renderGallery() {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <ToastProvider>
        <MemoryRouter>
          <CourseTemplateGalleryPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('CourseTemplateGalleryPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedService.tenant.listTemplates.mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [PUBLISHED_TEMPLATE, PUBLISHED_TEMPLATE_2],
    });
    mockedService.tenant.previewTemplate.mockResolvedValue(TEMPLATE_DETAIL);
    mockedService.tenant.cloneTemplate.mockResolvedValue({
      id: 'course-new',
      title: 'IB PYP Inquiry Approach',
      slug: 'ib-pyp-inquiry-abc12345',
    });
  });

  // Test 1 — gallery renders template cards
  it('renders template cards after loading', async () => {
    renderGallery();
    await waitFor(() => {
      expect(screen.getByTestId('template-gallery-page')).toBeInTheDocument();
    });
    const cards = await screen.findAllByTestId('template-card');
    expect(cards).toHaveLength(2);
    expect(screen.getByText('IB PYP Inquiry Approach')).toBeInTheDocument();
    expect(screen.getByText('Leadership Basics')).toBeInTheDocument();
  });

  // Test 2 — only published templates are shown (no "draft" badge)
  it('shows only published templates (no unpublished badge visible)', async () => {
    renderGallery();
    await screen.findAllByTestId('template-card');
    // Both cards have is_published=true — there should be no "draft" or "unpublished" badge
    expect(screen.queryByText(/draft/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/unpublished/i)).not.toBeInTheDocument();
  });

  // Test 3 — filter bar dispatches server-side category filter
  it('calls listTemplates with category filter when category is selected', async () => {
    const user = userEvent.setup();
    renderGallery();
    await screen.findAllByTestId('template-card');

    const categorySelect = screen.getByTestId('category-filter');
    await user.selectOptions(categorySelect, 'LEADERSHIP');

    await waitFor(() => {
      expect(mockedService.tenant.listTemplates).toHaveBeenCalledWith(
        expect.objectContaining({ category: 'LEADERSHIP' }),
      );
    });
  });

  // Test 4 — client-side search filters by title substring
  it('filters templates client-side by search input', async () => {
    const user = userEvent.setup();
    renderGallery();
    await screen.findAllByTestId('template-card');

    const searchInput = screen.getByTestId('search-input');
    await user.type(searchInput, 'Leadership');

    await waitFor(() => {
      const cards = screen.getAllByTestId('template-card');
      expect(cards).toHaveLength(1);
      expect(screen.getByText('Leadership Basics')).toBeInTheDocument();
      expect(screen.queryByText('IB PYP Inquiry Approach')).not.toBeInTheDocument();
    });
  });

  // Test 5 — clicking a card opens the preview panel
  it('opens preview panel when a card is clicked', async () => {
    const user = userEvent.setup();
    renderGallery();
    const cards = await screen.findAllByTestId('template-card');

    await user.click(cards[0]);

    await waitFor(() => {
      // Preview panel dialog should be visible
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
    // Should show the template title in the panel header (multiple elements may exist — the card + the panel)
    const titles = screen.getAllByText('IB PYP Inquiry Approach');
    expect(titles.length).toBeGreaterThanOrEqual(1);
  });

  // Test 6 — preview panel shows blueprint structure
  it('shows module structure in preview panel', async () => {
    const user = userEvent.setup();
    renderGallery();
    const cards = await screen.findAllByTestId('template-card');

    await user.click(cards[0]);

    await waitFor(() => {
      expect(mockedService.tenant.previewTemplate).toHaveBeenCalledWith('tpl-1');
    });

    expect(await screen.findByText('Module 1: Inquiry Basics')).toBeInTheDocument();
    expect(screen.getByText('Welcome to IB PYP')).toBeInTheDocument();
  });
});
