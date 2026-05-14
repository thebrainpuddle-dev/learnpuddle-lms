// GenerationWizard.gradeMeta.test.tsx
//
// FULL-1 — Step 1 of the GenerationWizard exposes optional grade-aware
// fields (grade level, subject, syllabus board) that flow into the
// backend's `_extract_generation_context` helper. These tests cover:
//
//   1. The three new fields render with the expected accessible labels.
//   2. Typing/selecting values updates the controlled inputs.
//   3. The "Meet your classroom" button stays enabled when the new
//      fields are left blank (graceful default — they're optional).
//
// The tests deliberately avoid asserting on downstream network behavior;
// hook-level coverage of the snake_case mapping lives in the companion
// hook test (useMAICGeneration.gradeMeta.test.tsx).

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// ── Module mocks ──────────────────────────────────────────────────────────────

// Toast provider isn't mounted in tests; provide a no-op stub.
vi.mock('../../common/Toast', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

// Sub-components that aren't under test — flatten to plain divs so the
// wizard renders deterministically.
vi.mock('../PDFUploader', () => ({
  PDFUploader: () => React.createElement('div', { 'data-testid': 'pdf-uploader' }),
}));

vi.mock('../WebSearchPanel', () => ({
  WebSearchPanel: () => React.createElement('div', { 'data-testid': 'web-search-panel' }),
}));

vi.mock('../AgentGenerationStep', () => ({
  AgentGenerationStep: () =>
    React.createElement('div', { 'data-testid': 'agent-generation-step' }),
}));

vi.mock('../OutlineEditor', () => ({
  OutlineEditor: () => React.createElement('div', { 'data-testid': 'outline-editor' }),
}));

vi.mock('../GenerationVisualizer', () => ({
  GenerationVisualizer: () =>
    React.createElement('div', { 'data-testid': 'generation-visualizer' }),
}));

// Hook is replaced by a stable stub — actual generation behaviour is
// covered in the companion hook test.
const startOutlineGenerationMock = vi.fn();
const startContentGenerationMock = vi.fn();
const startV2GenerationMock = vi.fn();
vi.mock('../../../hooks/useMAICGeneration', () => ({
  useMAICGeneration: () => ({
    step: 'idle',
    phase: 'idle',
    currentSceneIdx: 0,
    totalScenes: 0,
    outline: null,
    progress: 0,
    error: null,
    startedAt: null,
    isTabHidden: false,
    firstSceneReadyAt: null,
    startOutlineGeneration: startOutlineGenerationMock,
    updateOutline: vi.fn(),
    startContentGeneration: startContentGenerationMock,
    startV2Generation: startV2GenerationMock,
    retryScene: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
  }),
}));

// Stage store accessor used by the wizard to read failedOutlineIds.
vi.mock('../../../stores/maicStageStore', () => ({
  useMAICStageStore: Object.assign(
    (selector: any) =>
      selector({
        failedOutlineIds: [],
        setSlides: vi.fn(),
        setAgents: vi.fn(),
        setScenes: vi.fn(),
        setSceneSlideBounds: vi.fn(),
      }),
    {
      getState: () => ({
        clearAllOutlineFailures: vi.fn(),
        markOutlineFailed: vi.fn(),
        clearOutlineFailure: vi.fn(),
      }),
    },
  ),
}));

vi.mock('../../../services/openmaicService', () => ({
  maicApi: {
    createClassroom: vi.fn(),
  },
}));

// ── Imports under test (after mocks) ──────────────────────────────────────────

import { GenerationWizard } from '../GenerationWizard';

// ── Helpers ───────────────────────────────────────────────────────────────────

beforeEach(() => {
  // The useDraftCache hook persists to localStorage; clear between tests
  // so each test starts on a clean slate.
  window.localStorage.clear();
  startOutlineGenerationMock.mockReset();
  startContentGenerationMock.mockReset();
  startV2GenerationMock.mockReset();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('GenerationWizard — FULL-1 grade-aware fields', () => {
  it('renders Grade level, Subject, and Syllabus board controls in step 1', () => {
    render(<GenerationWizard />);

    // Labels include "(optional)" suffix on grade and subject — match
    // by accessible name of the control instead of the verbatim label.
    expect(screen.getByLabelText(/grade level/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/subject/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/syllabus board/i)).toBeInTheDocument();
  });

  it('defaults Grade level and Subject to empty, and Syllabus board to "Generic"', () => {
    render(<GenerationWizard />);

    const gradeSelect = screen.getByLabelText(/grade level/i) as HTMLSelectElement;
    const subjectInput = screen.getByLabelText(/subject/i) as HTMLInputElement;
    const boardSelect = screen.getByLabelText(/syllabus board/i) as HTMLSelectElement;

    expect(gradeSelect.value).toBe('');
    expect(subjectInput.value).toBe('');
    expect(boardSelect.value).toBe('Generic');
  });

  it('updates state when user picks values for the new fields', () => {
    render(<GenerationWizard />);

    const gradeSelect = screen.getByLabelText(/grade level/i) as HTMLSelectElement;
    const subjectInput = screen.getByLabelText(/subject/i) as HTMLInputElement;
    const boardSelect = screen.getByLabelText(/syllabus board/i) as HTMLSelectElement;

    fireEvent.change(gradeSelect, { target: { value: 'Grade 9' } });
    fireEvent.change(subjectInput, { target: { value: 'Mathematics' } });
    fireEvent.change(boardSelect, { target: { value: 'CBSE' } });

    expect(gradeSelect.value).toBe('Grade 9');
    expect(subjectInput.value).toBe('Mathematics');
    expect(boardSelect.value).toBe('CBSE');
  });

  it('keeps the "Meet your classroom" button enabled when grade fields are blank', () => {
    render(<GenerationWizard />);

    // Topic is required; fill it. Grade fields stay untouched.
    const topic = screen.getByLabelText(/topic/i) as HTMLInputElement;
    fireEvent.change(topic, { target: { value: 'Photosynthesis' } });

    const next = screen.getByRole('button', { name: /meet your classroom/i });
    expect(next).not.toBeDisabled();
  });

  it('prepares an editable class guide on Step 2 from the teacher settings', async () => {
    render(<GenerationWizard />);

    fireEvent.change(screen.getByLabelText(/topic/i), {
      target: { value: 'Photosynthesis' },
    });
    fireEvent.change(screen.getByLabelText(/grade level/i), {
      target: { value: 'Grade 6' },
    });
    fireEvent.change(screen.getByLabelText(/subject/i), {
      target: { value: 'Science' },
    });
    fireEvent.click(screen.getByRole('button', { name: /meet your classroom/i }));

    const guide = await screen.findByTestId('maic-class-guide') as HTMLTextAreaElement;
    expect(guide.value).toContain('Photosynthesis');
    expect(guide.value).toContain('Grade 6');
    expect(guide.value).toContain('Science');
    expect(guide.value).toContain('PBL/activity brief');
    expect(guide.value).toContain('Agent choreography');
    expect(guide.value).toContain('success criteria');

    fireEvent.change(guide, {
      target: { value: 'Open with a plant mystery, then run a misconception check.' },
    });
    expect(guide.value).toContain('plant mystery');
  });

  it('refreshes a stale generated class guide when teacher settings changed', async () => {
    window.localStorage.setItem(
      'maic.draft.classGuide.v1',
      [
        'Learning goal: Build a 6-scene AI classroom on "Old topic" for general learners.',
        'Class flow: Start with a concrete hook.',
        'Teacher moves: Surface likely misconceptions early.',
        'PBL/activity target: Include one role-based task.',
        'Assessment: Include formative checks.',
      ].join('\n'),
    );
    render(<GenerationWizard />);

    fireEvent.change(screen.getByLabelText(/topic/i), {
      target: { value: 'Photosynthesis' },
    });
    fireEvent.change(screen.getByLabelText(/grade level/i), {
      target: { value: 'Grade 6' },
    });
    fireEvent.change(screen.getByLabelText(/subject/i), {
      target: { value: 'Science' },
    });
    fireEvent.click(screen.getByRole('button', { name: /meet your classroom/i }));

    const guide = await screen.findByTestId('maic-class-guide') as HTMLTextAreaElement;
    expect(guide.value).toContain('Audience and standard');
    expect(guide.value).toContain('Photosynthesis');
    expect(guide.value).toContain('Science');
    expect(guide.value).toContain('PBL/activity brief');
    expect(guide.value).not.toContain('Old topic');
    expect(guide.value).not.toContain('Teacher moves:');
  });
});
