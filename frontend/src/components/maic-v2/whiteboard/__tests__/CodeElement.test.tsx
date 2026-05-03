/**
 * Tests for src/components/maic-v2/whiteboard/CodeElement.tsx
 * (MAIC-214.1). Exercises the REAL lowlight + highlight.js
 * pipeline (no stub) per the no-mocks/no-fakes rule in CLAUDE.md.
 *
 * setupTests.ts ships a global lowlight stub for pre-Phase-2
 * RichTextEditor tests (pre-existing tech debt — flagged for
 * Playwright migration). We `vi.unmock` here so production lowlight
 * is what's actually verified.
 */
import { describe, test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.unmock('lowlight');

import { CodeElement } from '../CodeElement';
import type { Action } from '../../../../lib/maic-v2/action-types';

type C = Extract<Action, { type: 'wb_draw_code' }>;


function make(overrides: Partial<C> = {}): C {
  return {
    id: 'a1',
    type: 'wb_draw_code',
    language: 'javascript',
    code: 'const x = 42;\nconsole.log(x);',
    x: 0,
    y: 0,
    ...overrides,
  };
}


describe('CodeElement', () => {
  test('renders the wrapper with data-element-id + data-language', () => {
    render(<CodeElement element={make({ id: 'a1', elementId: 'c1' })} />);
    const el = screen.getByTestId('maic-v2-wb-code');
    expect(el).toHaveAttribute('data-element-id', 'c1');
    expect(el).toHaveAttribute('data-language', 'javascript');
  });

  test('falls back to id when elementId absent', () => {
    render(<CodeElement element={make({ id: 'a1' })} />);
    expect(screen.getByTestId('maic-v2-wb-code')).toHaveAttribute('data-element-id', 'a1');
  });

  test('positions absolute at action coords + sizes container', () => {
    render(<CodeElement element={make({ x: 50, y: 100, width: 320, height: 220 })} />);
    const el = screen.getByTestId('maic-v2-wb-code');
    const style = el.getAttribute('style') ?? '';
    expect(style).toContain('left: 50px');
    expect(style).toContain('top: 100px');
    expect(style).toContain('width: 320px');
    expect(style).toContain('height: 220px');
  });

  test('default 400×240 when w/h omitted', () => {
    render(<CodeElement element={make()} />);
    const el = screen.getByTestId('maic-v2-wb-code');
    const style = el.getAttribute('style') ?? '';
    expect(style).toContain('width: 400px');
    expect(style).toContain('height: 240px');
  });

  test('renders one <div data-line-id="L{n}"> per source line', () => {
    const { container } = render(
      <CodeElement element={make({ code: 'a\nb\nc\nd' })} />,
    );
    const lines = container.querySelectorAll('[data-line-id]');
    expect(lines).toHaveLength(4);
    expect(lines[0]).toHaveAttribute('data-line-id', 'L1');
    expect(lines[3]).toHaveAttribute('data-line-id', 'L4');
  });

  test('emits highlight.js token spans for keywords (real lowlight)', () => {
    const { container } = render(
      <CodeElement
        element={make({ language: 'javascript', code: 'const x = 42;' })}
      />,
    );
    // lowlight + highlight.js's javascript grammar tags `const` as
    // hljs-keyword.
    const keywords = container.querySelectorAll('.hljs-keyword');
    expect(keywords.length).toBeGreaterThan(0);
  });

  test('emits text content matching the source for plain text fallback', () => {
    const { container } = render(
      <CodeElement element={make({ language: 'plaintext', code: 'hello world' })} />,
    );
    // Even without highlight grammar, the line content must appear.
    expect(container.textContent).toContain('hello world');
  });

  test('falls through gracefully when lowlight throws on unknown language', () => {
    // 'totally-not-a-language' isn't registered. The renderHast tree
    // wrap catches the throw and emits the raw line text.
    const { container } = render(
      <CodeElement element={make({ language: 'totally-not-a-language', code: 'abc\nxyz' })} />,
    );
    const lines = container.querySelectorAll('[data-line-id]');
    expect(lines).toHaveLength(2);
    expect(container.textContent).toContain('abc');
    expect(container.textContent).toContain('xyz');
  });

  test('shows the file-name header when fileName provided', () => {
    render(<CodeElement element={make({ fileName: 'main.ts' })} />);
    const header = screen.getByTestId('maic-v2-wb-code-filename');
    expect(header).toBeInTheDocument();
    expect(header.textContent).toBe('main.ts');
  });

  test('hides the file-name header when fileName omitted', () => {
    render(<CodeElement element={make()} />);
    expect(screen.queryByTestId('maic-v2-wb-code-filename')).toBeNull();
  });

  test('empty source still renders one (empty) line div', () => {
    const { container } = render(<CodeElement element={make({ code: '' })} />);
    // An empty string split('\n') = [''] — 1 line.
    const lines = container.querySelectorAll('[data-line-id]');
    expect(lines).toHaveLength(1);
  });

  test('language is lowercased so caller-case-mismatch still highlights', () => {
    render(<CodeElement element={make({ language: 'JavaScript', code: 'const x;' })} />);
    expect(screen.getByTestId('maic-v2-wb-code')).toHaveAttribute(
      'data-language',
      'javascript',
    );
  });

  test('python keywords highlight via the same code path', () => {
    const { container } = render(
      <CodeElement
        element={make({ language: 'python', code: 'def hello():\n    return 1' })}
      />,
    );
    // Python's `def` is a hljs-keyword.
    expect(container.querySelectorAll('.hljs-keyword').length).toBeGreaterThan(0);
  });
});
