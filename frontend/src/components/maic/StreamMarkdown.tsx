// src/components/maic/StreamMarkdown.tsx
//
// Renders markdown content with optional streaming cursor animation.
// Uses react-markdown with custom component overrides for consistent styling
// in the MAIC ChatPanel and lecture notes.

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { cn } from '../../lib/utils';

interface StreamMarkdownProps {
  /** The markdown content */
  content: string;
  /** Whether the content is still being streamed (show typing cursor) */
  isStreaming?: boolean;
  /** Custom class name for the wrapper */
  className?: string;
}

/**
 * StreamMarkdown renders markdown with prose-like typography and an optional
 * blinking cursor when `isStreaming` is true. Wrapped in React.memo for perf.
 */
export const StreamMarkdown = React.memo<StreamMarkdownProps>(
  function StreamMarkdown({ content, isStreaming = false, className }) {
    if (!content) {
      // When streaming but no content yet, show just the cursor
      if (isStreaming) {
        return (
          <span className={cn('stream-markdown', className)}>
            <span className="stream-markdown-cursor" aria-hidden="true">
              |
            </span>
            <style>{CURSOR_KEYFRAMES}</style>
          </span>
        );
      }
      return null;
    }

    return (
      <div className={cn('stream-markdown', className)}>
        <div className="stream-markdown-prose">
          <ReactMarkdown components={markdownComponents}>
            {content}
          </ReactMarkdown>
        </div>
        {isStreaming && (
          <span className="stream-markdown-cursor" aria-hidden="true">
            |
          </span>
        )}
        {isStreaming && <style>{CURSOR_KEYFRAMES}</style>}
      </div>
    );
  },
);

// ─── Cursor animation CSS ──────────────────────────────────────────────────

const CURSOR_KEYFRAMES = `
@keyframes stream-blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}
.stream-markdown-cursor {
  display: inline;
  font-weight: 700;
  color: currentColor;
  animation: stream-blink 1s step-end infinite;
  margin-left: 1px;
}
`;

// ─── Custom markdown component overrides ────────────────────────────────────

const markdownComponents: React.ComponentProps<typeof ReactMarkdown>['components'] = {
  // Headings
  h1: ({ children }) => (
    <h1 className="text-lg font-semibold text-gray-900 mt-3 mb-1.5 first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-base font-semibold text-gray-900 mt-3 mb-1.5 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold text-gray-900 mt-2.5 mb-1 first:mt-0">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-sm font-semibold text-gray-800 mt-2 mb-1 first:mt-0">
      {children}
    </h4>
  ),

  // Paragraphs
  p: ({ children }) => (
    <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
  ),

  // Emphasis
  strong: ({ children }) => (
    <strong className="font-semibold text-gray-900">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,

  // Lists
  ul: ({ children }) => (
    <ul className="mb-2 ml-4 space-y-1 list-disc marker:text-gray-400">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-2 ml-4 space-y-1 list-decimal marker:text-gray-400">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="leading-relaxed pl-1">{children}</li>
  ),

  // Code: inline vs block
  code: ({ className, children, ...props }) => {
    const isBlock = className?.includes('language-');
    if (isBlock) {
      return (
        <pre className="bg-gray-900 text-gray-100 rounded px-3 py-2 overflow-x-auto my-2">
          <code className="text-xs font-mono">{children}</code>
        </pre>
      );
    }
    return (
      <code
        className="bg-gray-100 px-1.5 py-0.5 rounded text-xs font-mono"
        {...props}
      >
        {children}
      </code>
    );
  },

  // Pre — wrap for code blocks that don't have a language class
  pre: ({ children }) => (
    <pre className="bg-gray-900 text-gray-100 rounded px-3 py-2 overflow-x-auto my-2 text-xs font-mono">
      {children}
    </pre>
  ),

  // Blockquote
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-gray-300 pl-3 my-2 italic text-gray-600">
      {children}
    </blockquote>
  ),

  // Horizontal rule
  hr: () => <hr className="my-3 border-gray-200" />,

  // Links
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary-600 underline hover:text-primary-800"
    >
      {children}
    </a>
  ),

  // Tables
  table: ({ children }) => (
    <div className="overflow-x-auto my-2">
      <table className="min-w-full text-xs border-collapse border border-gray-200 rounded overflow-hidden">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
  th: ({ children }) => (
    <th className="px-3 py-1.5 text-left font-semibold text-gray-700 border border-gray-200">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-1.5 border border-gray-200">{children}</td>
  ),
};
