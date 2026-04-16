// src/components/maic/ai-elements/CodeBlock.tsx
//
// Syntax-highlighted code display with line numbers and copy button.
// Uses basic regex-based highlighting for common languages.

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Copy, Check } from 'lucide-react';
import { cn } from '../../../lib/utils';

interface CodeBlockProps {
  code: string;
  language?: string;
  showLineNumbers?: boolean;
  className?: string;
}

// ─── Basic keyword highlighting ───────────────────────────────────────────────

type HighlightRule = { pattern: RegExp; className: string };

const JS_TS_RULES: HighlightRule[] = [
  // Comments (single-line)
  { pattern: /(\/\/.*$)/gm, className: 'codeblock-comment' },
  // Strings (double-quoted, single-quoted, template literals)
  { pattern: /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g, className: 'codeblock-string' },
  // Numbers
  { pattern: /\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g, className: 'codeblock-number' },
  // Keywords
  {
    pattern: /\b(const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|new|this|class|extends|import|export|from|default|async|await|try|catch|finally|throw|typeof|instanceof|in|of|yield|interface|type|enum|implements|abstract|declare|readonly|public|private|protected|static|void|null|undefined|true|false)\b/g,
    className: 'codeblock-keyword',
  },
];

const PYTHON_RULES: HighlightRule[] = [
  { pattern: /(#.*$)/gm, className: 'codeblock-comment' },
  { pattern: /("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, className: 'codeblock-string' },
  { pattern: /\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g, className: 'codeblock-number' },
  {
    pattern: /\b(def|class|return|if|elif|else|for|while|break|continue|import|from|as|try|except|finally|raise|with|yield|lambda|pass|del|global|nonlocal|assert|in|not|and|or|is|True|False|None|async|await|self)\b/g,
    className: 'codeblock-keyword',
  },
];

const DEFAULT_RULES: HighlightRule[] = [
  { pattern: /(\/\/.*$|#.*$)/gm, className: 'codeblock-comment' },
  { pattern: /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, className: 'codeblock-string' },
  { pattern: /\b(\d+\.?\d*)\b/g, className: 'codeblock-number' },
];

function getRulesForLanguage(language?: string): HighlightRule[] {
  switch (language?.toLowerCase()) {
    case 'javascript':
    case 'js':
    case 'typescript':
    case 'ts':
    case 'tsx':
    case 'jsx':
      return JS_TS_RULES;
    case 'python':
    case 'py':
      return PYTHON_RULES;
    default:
      return DEFAULT_RULES;
  }
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function highlightCode(code: string, language?: string): string {
  const rules = getRulesForLanguage(language);
  let html = escapeHtml(code);

  // We use placeholder tokens to avoid double-replacement
  const tokens: string[] = [];

  for (const rule of rules) {
    html = html.replace(rule.pattern, (match) => {
      const index = tokens.length;
      tokens.push(`<span class="${rule.className}">${match}</span>`);
      return `\x00${index}\x00`;
    });
  }

  // Restore tokens
  for (let i = 0; i < tokens.length; i++) {
    html = html.replace(`\x00${i}\x00`, tokens[i]);
  }

  return html;
}

// ─── Component ────────────────────────────────────────────────────────────────

export const CodeBlock = React.memo<CodeBlockProps>(function CodeBlock({
  code,
  language,
  showLineNumbers = false,
  className,
}) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API may not be available
    }
  }, [code]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const lines = code.split('\n');
  const highlightedHtml = highlightCode(code, language);

  return (
    <div className={cn('relative group rounded-lg overflow-hidden bg-gray-950 text-gray-100', className)}>
      {/* Language label */}
      {language && (
        <div className="absolute top-0 left-0 px-3 py-1 text-[10px] font-mono text-gray-400 uppercase tracking-wider select-none">
          {language}
        </div>
      )}

      {/* Copy button */}
      <button
        type="button"
        onClick={handleCopy}
        className={cn(
          'absolute top-1.5 right-1.5 p-1.5 rounded-md transition-colors z-10',
          'text-gray-400 hover:text-gray-200 hover:bg-gray-800',
          'opacity-0 group-hover:opacity-100 focus:opacity-100',
        )}
        aria-label={copied ? 'Copied' : 'Copy code'}
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-green-400" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>

      {/* Code area */}
      <pre className={cn('overflow-x-auto text-sm font-mono', language ? 'pt-7 pb-3 px-3' : 'p-3')}>
        {showLineNumbers ? (
          <div className="flex">
            {/* Line numbers gutter */}
            <div className="select-none text-right pr-4 text-gray-600 shrink-0" aria-hidden="true">
              {lines.map((_, i) => (
                <div key={i} className="leading-relaxed">
                  {i + 1}
                </div>
              ))}
            </div>
            {/* Code content */}
            <code
              className="flex-1 min-w-0"
              dangerouslySetInnerHTML={{ __html: highlightedHtml }}
            />
          </div>
        ) : (
          <code dangerouslySetInnerHTML={{ __html: highlightedHtml }} />
        )}
      </pre>

      {/* Highlight colors */}
      <style>{HIGHLIGHT_STYLES}</style>
    </div>
  );
});

const HIGHLIGHT_STYLES = `
.codeblock-keyword { color: #c084fc; }
.codeblock-string { color: #86efac; }
.codeblock-comment { color: #6b7280; font-style: italic; }
.codeblock-number { color: #fdba74; }
`;
