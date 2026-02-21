// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// Tiptap packages ship ESM that CRA/Jest doesn't transpile from node_modules.
// Mock these modules globally so tests can import pages/components that use RichTextEditor.
jest.mock('@tiptap/react', () => {
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
    useEditor: jest.fn(() => ({
      getHTML: () => '<p></p>',
      getAttributes: () => ({}),
      isActive: () => false,
      chain: () => createChain(),
      commands: {
        setContent: jest.fn(),
      },
      storage: {
        markdown: {
          getMarkdown: () => '',
        },
      },
    })),
  };
});

jest.mock('@tiptap/starter-kit', () => {
  const ext: any = { configure: () => ext };
  return { __esModule: true, default: ext };
});

jest.mock('@tiptap/extension-underline', () => ({ __esModule: true, default: {} }));
jest.mock('@tiptap/extension-subscript', () => ({ __esModule: true, default: {} }));
jest.mock('@tiptap/extension-superscript', () => ({ __esModule: true, default: {} }));
jest.mock('@tiptap/extension-text-style', () => ({ TextStyle: {} }));
jest.mock('@tiptap/markdown', () => ({ Markdown: {} }));
jest.mock('@tiptap/core', () => ({ Extension: { create: () => ({}) } }));

jest.mock('@tiptap/extension-link', () => {
  const ext: any = { configure: () => ext };
  return { __esModule: true, default: ext };
});

jest.mock('@tiptap/extension-image', () => {
  const ext: any = {
    configure: () => ext,
    extend: () => ext,
  };
  return { __esModule: true, default: ext };
});

jest.mock('@tiptap/extension-placeholder', () => {
  const ext: any = { configure: () => ext };
  return { __esModule: true, default: ext };
});

jest.mock('@tiptap/extension-code-block-lowlight', () => {
  const ext: any = { configure: () => ext };
  return { __esModule: true, default: ext };
});

jest.mock('lowlight', () => ({ createLowlight: () => ({}) }));
