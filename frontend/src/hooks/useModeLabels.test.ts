// src/hooks/useModeLabels.test.ts
//
// Tests for the FE-015 useModeLabels hook.
//
// Coverage:
//  1. Returns EDUCATION_DEFAULTS when the store has not been updated
//  2. label('learner') returns 'Teacher' in education mode
//  3. After setModeLabels('corporate', ...) label values flip to corporate defaults
//  4. label('learner') returns 'Employee' in corporate mode
//  5. Custom per-tenant override surfaced by label()
//  6. Unknown key falls back to EDUCATION_DEFAULTS (not undefined / empty)
//  7. mode field reflects active mode
//  8. modeLabels field exposes the full merged map

import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useModeLabels } from './useModeLabels';
import {
  useTenantStore,
  EDUCATION_DEFAULTS,
  CORPORATE_DEFAULTS,
  type ModeLabels,
} from '../stores/tenantStore';

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Reset the Zustand store to its initial state between tests. */
function resetStore() {
  act(() => {
    useTenantStore.getState().reset();
  });
}

function setEducation(overrides?: Partial<ModeLabels>) {
  act(() => {
    useTenantStore.getState().setModeLabels('education', {
      ...EDUCATION_DEFAULTS,
      ...overrides,
    });
  });
}

function setCorporate(overrides?: Partial<ModeLabels>) {
  act(() => {
    useTenantStore.getState().setModeLabels('corporate', {
      ...CORPORATE_DEFAULTS,
      ...overrides,
    });
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useModeLabels', () => {
  beforeEach(resetStore);

  it('1. returns EDUCATION_DEFAULTS before any store update', () => {
    const { result } = renderHook(() => useModeLabels());
    expect(result.current.mode).toBe('education');
    expect(result.current.modeLabels).toEqual(EDUCATION_DEFAULTS);
  });

  it('2. label("learner") returns "Teacher" in education mode', () => {
    setEducation();
    const { result } = renderHook(() => useModeLabels());
    expect(result.current.label('learner')).toBe('Teacher');
  });

  it('3. after setModeLabels("corporate") labels flip to corporate values', () => {
    setCorporate();
    const { result } = renderHook(() => useModeLabels());
    expect(result.current.label('course')).toBe('Training Program');
    expect(result.current.label('course_plural')).toBe('Training Programs');
    expect(result.current.label('badge')).toBe('Achievement');
    expect(result.current.label('league')).toBe('Tier');
    expect(result.current.label('xp')).toBe('Points');
  });

  it('4. label("learner") returns "Employee" in corporate mode', () => {
    setCorporate();
    const { result } = renderHook(() => useModeLabels());
    expect(result.current.label('learner')).toBe('Employee');
    expect(result.current.label('learner_plural')).toBe('Employees');
  });

  it('5. custom per-tenant override is surfaced by label()', () => {
    setEducation({ learner: 'Participant', course: 'Masterclass' });
    const { result } = renderHook(() => useModeLabels());
    expect(result.current.label('learner')).toBe('Participant');
    expect(result.current.label('course')).toBe('Masterclass');
    // Non-overridden keys still return the mode default
    expect(result.current.label('badge')).toBe('Badge');
  });

  it('6. label() falls back to EDUCATION_DEFAULTS for a missing key', () => {
    // Deliberately populate with an incomplete labels object (simulates
    // a pre-migration tenant that returns fewer keys than expected).
    act(() => {
      useTenantStore.getState().setModeLabels('education', {
        ...EDUCATION_DEFAULTS,
        // omit 'streak' — simulating a backend that doesn't send it yet
        streak: undefined as unknown as string,
      });
    });
    const { result } = renderHook(() => useModeLabels());
    // Should fall back to EDUCATION_DEFAULTS['streak'] = 'Streak'
    expect(result.current.label('streak')).toBe(EDUCATION_DEFAULTS['streak']);
  });

  it('7. mode field reflects the active mode', () => {
    setEducation();
    const { result: edu } = renderHook(() => useModeLabels());
    expect(edu.current.mode).toBe('education');

    setCorporate();
    const { result: corp } = renderHook(() => useModeLabels());
    expect(corp.current.mode).toBe('corporate');
  });

  it('8. modeLabels field exposes the full merged map', () => {
    const customLabels: ModeLabels = { ...EDUCATION_DEFAULTS, dashboard: 'Control Room' };
    act(() => {
      useTenantStore.getState().setModeLabels('education', customLabels);
    });
    const { result } = renderHook(() => useModeLabels());
    expect(result.current.modeLabels).toEqual(customLabels);
    expect(result.current.modeLabels.dashboard).toBe('Control Room');
  });

  it('9. hook updates reactively when store mode changes', () => {
    setEducation();
    const { result } = renderHook(() => useModeLabels());
    expect(result.current.label('learner')).toBe('Teacher');

    setCorporate();
    // Zustand subscription should trigger a re-render
    expect(result.current.label('learner')).toBe('Employee');
  });
});
