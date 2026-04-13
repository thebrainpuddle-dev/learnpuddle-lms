// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// Alias jest globals to vitest equivalents for CRA-era tests that use jest.fn(), jest.mock(), etc.
// This is the standard migration shim — remove once all tests import from 'vitest' directly.
(globalThis as any).jest = vi;

// Tiptap packages ship ESM that CRA/Jest doesn't transpile from node_modules.
// Mock these modules globally so tests can import pages/components that use RichTextEditor.
vi.mock('@tiptap/react', () => {
  const React = require('react');
  const createChain = () => {
    let chain: any;
    chain = new Proxy(
      {},
      {
        get: (_target, prop) => {
          if (prop === 'run') return () => true;
          return () => chain;
        },
      }
    );
    return chain;
  };

  return {
    EditorContent: ({ className }: { className?: string }) =>
      React.createElement('div', { className, 'data-testid': 'rich-text-editor-content' }),
    useEditor: vi.fn(() => ({
      getHTML: () => '<p></p>',
      getAttributes: () => ({}),
      isActive: () => false,
      chain: () => createChain(),
      commands: {
        setContent: vi.fn(),
      },
      storage: {
        markdown: {
          getMarkdown: () => '',
        },
      },
    })),
  };
});

vi.mock('@tiptap/starter-kit', () => {
  const ext: any = { configure: () => ext };
  return { __esModule: true, default: ext };
});

vi.mock('@tiptap/extension-underline', () => ({ __esModule: true, default: {} }));
vi.mock('@tiptap/extension-subscript', () => ({ __esModule: true, default: {} }));
vi.mock('@tiptap/extension-superscript', () => ({ __esModule: true, default: {} }));
vi.mock('@tiptap/extension-text-style', () => ({ TextStyle: {} }));
vi.mock('@tiptap/markdown', () => ({ Markdown: {} }));
vi.mock('@tiptap/core', () => ({ Extension: { create: () => ({}) } }));

vi.mock('@tiptap/extension-link', () => {
  const ext: any = { configure: () => ext };
  return { __esModule: true, default: ext };
});

vi.mock('@tiptap/extension-image', () => {
  const ext: any = {
    configure: () => ext,
    extend: () => ext,
  };
  return { __esModule: true, default: ext };
});

vi.mock('@tiptap/extension-placeholder', () => {
  const ext: any = { configure: () => ext };
  return { __esModule: true, default: ext };
});

vi.mock('@tiptap/extension-code-block-lowlight', () => {
  const ext: any = { configure: () => ext };
  return { __esModule: true, default: ext };
});

vi.mock('lowlight', () => ({ createLowlight: () => ({}) }));
