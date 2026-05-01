// src/pages/admin/CourseTemplateGalleryPage.test.tsx
//
// FE-049: Comprehensive tests for the admin Course Template Gallery page.
// Covers: page header, filter controls, loading skeleton, template grid,
//         client-side search, empty/error states, preview panel open/close,
//         server-side filter calls (category / language), and singular count.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { CourseTemplateGalleryPage } from './CourseTemplateGalleryPage';
import {
  courseTemplatesService,
  type CourseTemplateListItem,
} from '../../services/courseTemplatesService';

// ── Module mocks ───────────────────────────────────────────────────────────────

vi.mock('../../services/courseTemplatesService', () => ({
  courseTemplatesService: {
    tenant: {
      listTemplates: vi.fn(),
    },
  },
}));

vi.mock('../../components/templates/TemplateCard', () => ({
  TemplateCard: ({
    template,
    onClick,
  }: {
    template: CourseTemplateListItem;
    onClick: () => void;
  }) => (
    <div data-testid="template-card" onClick={onClick}>
      {template.title}
    </div>
  ),
}));

vi.mock('../../components/templates/TemplatePreviewPanel', () => ({
  TemplatePreviewPanel: ({
    template,
    onClose,
  }: {
    template: CourseTemplateListItem | null;
    onClose: () => void;
  }) =>
    template ? (
      <div data-testid="preview-panel">
        {template.title}
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

vi.mock('../../components/templates/CloneTemplateDialog', () => ({
  CloneTemplateDialog: ({
    template,
  }: {
    template: CourseTemplateListItem | null;
  }) =>
    template ? (
      <div data-testid="clone-dialog">{template.title}</div>
    ) : null,
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

vi.mock('../../components/common', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../components/common')>();
  return {
    ...actual,
    EmptyState: ({
      title,
      description,
    }: {
      title: string;
      description?: string;
    }) => (
      <div role="status">
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </div>
    ),
  };
});

// ── Typed mock reference ───────────────────────────────────────────────────────

const mockedListTemplates =
  courseTemplatesService.tenant.listTemplates as ReturnType<typeof vi.fn>;

// ── Fixtures ───────────────────────────────────────────────────────────────────

const TEMPLATE_1: CourseTemplateListItem = {
  id: 'tmpl-1',
  slug: 'intro-ib-pyp',
  title: 'Introduction to IB PYP',
  description: 'A comprehensive PYP introduction course',
  category: 'IB_PYP',
  level: 'BEGINNER',
  language: 'en',
  thumbnail_url: '',
  estimated_hours: 3,
  is_published: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const TEMPLATE_2: CourseTemplateListItem = {
  id: 'tmpl-2',
  slug: 'teaching-skills-masterclass',
  title: 'Teaching Skills Masterclass',
  description: 'Advanced teaching methods',
  category: 'TEACHING_SKILLS',
  level: 'ADVANCED',
  language: 'en',
  thumbnail_url: '',
  estimated_hours: 6,
  is_published: true,
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-01-16T00:00:00Z',
};

const TEMPLATES_RESPONSE = {
  count: 2,
  next: null,
  previous: null,
  results: [TEMPLATE_1, TEMPLATE_2],
};

// ── Render helper ──────────────────────────────────────────────────────────────

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CourseTemplateGalleryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Test suite ─────────────────────────────────────────────────────────────────

describe('CourseTemplateGalleryPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedListTemplates.mockResolvedValue(TEMPLATES_RESPONSE);
  });

  // ── 1. Page header ───────────────────────────────────────────────────────────

  describe('Page header', () => {
    it('renders the "Course Templates" h1 heading', async () => {
      renderPage();
      await waitFor(() =>
        expect(
          screen.getByRole('heading', { level: 1, name: 'Course Templates' }),
        ).toBeInTheDocument(),
      );
    });

    it('renders the subtitle containing "Browse platform-curated templates"', async () => {
      renderPage();
      await waitFor(() =>
        expect(
          screen.getByText(/Browse platform-curated templates/i),
        ).toBeInTheDocument(),
      );
    });
  });

  // ── 2. Filter controls ───────────────────────────────────────────────────────

  describe('Filter controls', () => {
    it('renders the search input with the correct placeholder', () => {
      renderPage();
      expect(
        screen.getByPlaceholderText('Search templates…'),
      ).toBeInTheDocument();
    });

    it('search input has aria-label "Search templates"', () => {
      renderPage();
      expect(
        screen.getByRole('textbox', { name: 'Search templates' }),
      ).toBeInTheDocument();
    });

    it('category dropdown renders "All categories" option', () => {
      renderPage();
      const select = screen.getByTestId('category-filter');
      expect(select).toBeInTheDocument();
      expect(
        screen.getByRole('option', { name: 'All categories' }),
      ).toBeInTheDocument();
    });

    it('language dropdown renders "All languages" option', () => {
      renderPage();
      const select = screen.getByTestId('language-filter');
      expect(select).toBeInTheDocument();
      expect(
        screen.getByRole('option', { name: 'All languages' }),
      ).toBeInTheDocument();
    });

    it('level dropdown renders "All levels" option', () => {
      renderPage();
      const select = screen.getByTestId('level-filter');
      expect(select).toBeInTheDocument();
      expect(
        screen.getByRole('option', { name: 'All levels' }),
      ).toBeInTheDocument();
    });
  });

  // ── 3. Loading state ─────────────────────────────────────────────────────────

  describe('Loading state', () => {
    it('shows 8 animate-pulse skeleton divs while the query is pending', () => {
      // Return a promise that never resolves so the query stays in loading state.
      mockedListTemplates.mockReturnValue(new Promise(() => {}));
      renderPage();
      const skeletons = document
        .querySelectorAll('.animate-pulse');
      expect(skeletons.length).toBe(8);
    });
  });

  // ── 4. Template grid ─────────────────────────────────────────────────────────

  describe('Template grid', () => {
    it('renders a card for TEMPLATE_1 "Introduction to IB PYP"', async () => {
      renderPage();
      expect(
        await screen.findByText('Introduction to IB PYP'),
      ).toBeInTheDocument();
    });

    it('renders a card for TEMPLATE_2 "Teaching Skills Masterclass"', async () => {
      renderPage();
      expect(
        await screen.findByText('Teaching Skills Masterclass'),
      ).toBeInTheDocument();
    });

    it('shows "2 templates found" results count after load', async () => {
      renderPage();
      expect(
        await screen.findByText('2 templates found'),
      ).toBeInTheDocument();
    });

    it('renders the template-grid container when results are loaded', async () => {
      renderPage();
      // Wait for cards to appear first, then verify the grid wrapper.
      await screen.findAllByTestId('template-card');
      expect(screen.getByTestId('template-grid')).toBeInTheDocument();
    });
  });

  // ── 5. Client-side search ────────────────────────────────────────────────────

  describe('Client-side search', () => {
    it('typing "IB PYP" shows only TEMPLATE_1 and updates count to "1 template found"', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findAllByTestId('template-card');

      await user.type(screen.getByTestId('search-input'), 'IB PYP');

      await waitFor(() => {
        const cards = screen.getAllByTestId('template-card');
        expect(cards).toHaveLength(1);
        expect(screen.getByText('Introduction to IB PYP')).toBeInTheDocument();
        expect(
          screen.queryByText('Teaching Skills Masterclass'),
        ).not.toBeInTheDocument();
        expect(screen.getByText('1 template found')).toBeInTheDocument();
      });
    });

    it('typing "Teaching" shows only TEMPLATE_2', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findAllByTestId('template-card');

      await user.type(screen.getByTestId('search-input'), 'Teaching');

      await waitFor(() => {
        const cards = screen.getAllByTestId('template-card');
        expect(cards).toHaveLength(1);
        expect(
          screen.getByText('Teaching Skills Masterclass'),
        ).toBeInTheDocument();
        expect(
          screen.queryByText('Introduction to IB PYP'),
        ).not.toBeInTheDocument();
      });
    });

    it('typing a non-matching string shows the "No templates found" empty state with match description', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findAllByTestId('template-card');

      await user.type(screen.getByTestId('search-input'), 'xyznonexistent');

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
        expect(screen.getByText('No templates found')).toBeInTheDocument();
        expect(
          screen.getByText(
            /No templates match "xyznonexistent"\. Try a different search\./i,
          ),
        ).toBeInTheDocument();
      });
    });
  });

  // ── 6. Empty state ───────────────────────────────────────────────────────────

  describe('Empty state', () => {
    it('shows "No templates found" with "No published templates are available yet." when the list is empty and no search is active', async () => {
      mockedListTemplates.mockResolvedValue({
        count: 0,
        next: null,
        previous: null,
        results: [],
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('No templates found')).toBeInTheDocument();
        expect(
          screen.getByText('No published templates are available yet.'),
        ).toBeInTheDocument();
      });
    });

    it('renders the EmptyState component (role="status") for the empty list case', async () => {
      mockedListTemplates.mockResolvedValue({
        count: 0,
        next: null,
        previous: null,
        results: [],
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });
    });
  });

  // ── 7. Error state ───────────────────────────────────────────────────────────

  describe('Error state', () => {
    it('shows "Failed to load templates" when listTemplates throws', async () => {
      mockedListTemplates.mockRejectedValue(new Error('Network error'));

      renderPage();

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load templates'),
        ).toBeInTheDocument();
      });
    });

    it('renders the EmptyState component (role="status") for the error case', async () => {
      mockedListTemplates.mockRejectedValue(new Error('Network error'));

      renderPage();

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });
    });
  });

  // ── 8. Template click → preview panel ───────────────────────────────────────

  describe('Template click → preview panel', () => {
    it('clicking a template card opens the preview panel with the template title', async () => {
      const user = userEvent.setup();
      renderPage();
      const cards = await screen.findAllByTestId('template-card');

      await user.click(cards[0]);

      expect(screen.getByTestId('preview-panel')).toBeInTheDocument();
      // The stub renders the template title inside the panel.
      const panel = screen.getByTestId('preview-panel');
      expect(panel).toHaveTextContent('Introduction to IB PYP');
    });

    it('closing the preview panel hides it', async () => {
      const user = userEvent.setup();
      renderPage();
      const cards = await screen.findAllByTestId('template-card');

      // Open the panel.
      await user.click(cards[0]);
      expect(screen.getByTestId('preview-panel')).toBeInTheDocument();

      // Close it.
      await user.click(screen.getByRole('button', { name: 'Close' }));

      await waitFor(() => {
        expect(screen.queryByTestId('preview-panel')).not.toBeInTheDocument();
      });
    });
  });

  // ── 9. Server-side filter calls ──────────────────────────────────────────────

  describe('Server-side filter calls', () => {
    it('selecting "Teaching Skills" from the category dropdown calls listTemplates with category="TEACHING_SKILLS"', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findAllByTestId('template-card');

      const categorySelect = screen.getByTestId('category-filter');
      await user.selectOptions(categorySelect, 'TEACHING_SKILLS');

      await waitFor(() => {
        expect(mockedListTemplates).toHaveBeenCalledWith(
          expect.objectContaining({ category: 'TEACHING_SKILLS' }),
        );
      });
    });

    it('selecting "Hindi" from the language dropdown calls listTemplates with language="hi"', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findAllByTestId('template-card');

      const languageSelect = screen.getByTestId('language-filter');
      await user.selectOptions(languageSelect, 'hi');

      await waitFor(() => {
        expect(mockedListTemplates).toHaveBeenCalledWith(
          expect.objectContaining({ language: 'hi' }),
        );
      });
    });
  });

  // ── 10. Singular result count ────────────────────────────────────────────────

  describe('Singular result count', () => {
    it('shows "1 template found" (singular, not "1 templates found") when only one result', async () => {
      mockedListTemplates.mockResolvedValue({
        count: 1,
        next: null,
        previous: null,
        results: [TEMPLATE_1],
      });

      renderPage();

      expect(await screen.findByText('1 template found')).toBeInTheDocument();
      expect(
        screen.queryByText('1 templates found'),
      ).not.toBeInTheDocument();
    });
  });
});
