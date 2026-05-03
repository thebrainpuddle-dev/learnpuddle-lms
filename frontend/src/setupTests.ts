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

// PRE-EXISTING TECH DEBT — flagged by the no-mocks/no-fakes rule in
// CLAUDE.md ("Hard rule — production-real only"). The original
// RichTextEditor.test.tsx + dependents (~90 tests across the LMS)
// were written assuming this mock; removing it crashes them because
// `tiptap-extension-code-block-lowlight` calls `createLowlight()` at
// module-evaluate time with grammars happy-dom can't tolerate.
//
// MAIC v2 work (CodeElement, Whiteboard, etc.) MUST un-mock with
// `vi.unmock('lowlight')` at the top of each test file so the
// production lowlight pipeline is what's actually verified.
//
// TODO: migrate RichTextEditor + dependents to Playwright e2e and
// delete this mock. Tracked alongside the FakeAudio / MockWebSocket
// migration in the post-Phase-2 e2e infrastructure work.
vi.mock('lowlight', () => ({
  createLowlight: () => ({
    highlight: () => ({ type: 'root', children: [] }),
  }),
  common: {},
}));

// @xyflow/react (React Flow) accesses the DOM and registers ResizeObserver
// at module-load time which hangs in happy-dom. Mock it globally so any test
// file that transitively imports MindMapTab (or any React-Flow-using component)
// doesn't stall the Vitest worker.
vi.mock('@xyflow/react', () => ({
  ReactFlow: () => null,
  MiniMap: () => null,
  Controls: () => null,
  Background: () => null,
  Panel: () => null,
  Handle: () => null,
  useNodesState: () => [[], () => {}],
  useEdgesState: () => [[], () => {}],
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
  MarkerType: { ArrowClosed: 'arrowclosed' },
  BackgroundVariant: { Dots: 'dots', Lines: 'lines', Cross: 'cross' },
}));

// dagre graph layout library — not needed in unit tests.
vi.mock('@dagrejs/dagre', () => ({
  default: {
    graphlib: { Graph: class { setDefaultEdgeLabel() {} setGraph() {} setNode() {} setEdge() {} nodes() { return []; } edges() { return []; } node() { return { x: 0, y: 0, width: 100, height: 50 }; } } },
    layout: () => {},
  },
}));
