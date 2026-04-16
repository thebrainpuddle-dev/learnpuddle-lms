// src/components/maic/PromptInput.tsx
//
// Enhanced chat textarea with auto-resize, slash command palette, attachment
// chips, suggestion pills, character count, and send/stop button states.

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  SendHorizontal,
  Loader2,
  Square,
  Paperclip,
  X,
  FileText,
  Image as ImageIcon,
  Film,
  File,
  Search,
  BookOpen,
  Brain,
  MessageSquare,
  Sparkles,
} from 'lucide-react';
import { cn } from '../../lib/utils';

// ─── Slash Commands ──────────────────────────────────────────────────────────

interface SlashCommand {
  command: string;
  label: string;
  description: string;
  icon: React.ReactNode;
}

const SLASH_COMMANDS: SlashCommand[] = [
  { command: '/explain', label: 'Explain', description: 'Explain current slide', icon: <BookOpen className="h-3.5 w-3.5" /> },
  { command: '/quiz', label: 'Quiz', description: 'Generate a quiz', icon: <Sparkles className="h-3.5 w-3.5" /> },
  { command: '/summary', label: 'Summary', description: 'Summarize the lesson', icon: <FileText className="h-3.5 w-3.5" /> },
  { command: '/discuss', label: 'Discuss', description: 'Start a discussion', icon: <MessageSquare className="h-3.5 w-3.5" /> },
  { command: '/search', label: 'Search', description: 'Search the web', icon: <Search className="h-3.5 w-3.5" /> },
];

// ─── Attachment type icon mapper ─────────────────────────────────────────────

function getAttachmentIcon(type: string): React.ReactNode {
  if (type.startsWith('image/')) return <ImageIcon className="h-3 w-3" />;
  if (type.startsWith('video/')) return <Film className="h-3 w-3" />;
  if (type.includes('pdf') || type.includes('document') || type.includes('text'))
    return <FileText className="h-3 w-3" />;
  return <File className="h-3 w-3" />;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

// ─── Props ───────────────────────────────────────────────────────────────────

export interface PromptInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
  maxLength?: number;
  showCharCount?: boolean;
  suggestions?: string[];
  onSuggestionClick?: (suggestion: string) => void;
  attachments?: Array<{ name: string; type: string; size: number }>;
  onRemoveAttachment?: (index: number) => void;
  onAttach?: () => void;
  onStop?: () => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

export const PromptInput = React.memo<PromptInputProps>(function PromptInput({
  value,
  onChange,
  onSubmit,
  placeholder = 'Ask the classroom...',
  disabled = false,
  loading = false,
  className,
  maxLength,
  showCharCount = false,
  suggestions,
  onSuggestionClick,
  attachments,
  onRemoveAttachment,
  onAttach,
  onStop,
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const commandListRef = useRef<HTMLDivElement>(null);
  const [showCommands, setShowCommands] = useState(false);
  const [commandFilter, setCommandFilter] = useState('');
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);

  // ─── Auto-resize textarea ──────────────────────────────────────────────
  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    // Max 6 lines (~144px at ~24px line-height)
    const maxH = 144;
    ta.style.height = `${Math.min(ta.scrollHeight, maxH)}px`;
    ta.style.overflowY = ta.scrollHeight > maxH ? 'auto' : 'hidden';
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  // ─── Slash command detection ───────────────────────────────────────────
  const filteredCommands = useMemo(() => {
    if (!showCommands) return [];
    const filter = commandFilter.toLowerCase();
    return SLASH_COMMANDS.filter(
      (cmd) =>
        cmd.command.toLowerCase().includes(filter) ||
        cmd.label.toLowerCase().includes(filter),
    );
  }, [showCommands, commandFilter]);

  // Reset selected index when filtered list changes
  useEffect(() => {
    setSelectedCommandIndex(0);
  }, [filteredCommands.length]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      let newValue = e.target.value;
      if (maxLength && newValue.length > maxLength) {
        newValue = newValue.slice(0, maxLength);
      }
      onChange(newValue);

      // Detect slash command
      // We look at the current line to determine if the user is typing a slash command
      const cursorPos = e.target.selectionStart;
      const textBeforeCursor = newValue.slice(0, cursorPos);
      const lastNewline = textBeforeCursor.lastIndexOf('\n');
      const currentLine = textBeforeCursor.slice(lastNewline + 1);

      if (currentLine.startsWith('/')) {
        setShowCommands(true);
        setCommandFilter(currentLine);
      } else {
        setShowCommands(false);
        setCommandFilter('');
      }
    },
    [onChange, maxLength],
  );

  const selectCommand = useCallback(
    (cmd: SlashCommand) => {
      onChange(cmd.command + ' ');
      setShowCommands(false);
      setCommandFilter('');
      textareaRef.current?.focus();
    },
    [onChange],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Handle command palette navigation
      if (showCommands && filteredCommands.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSelectedCommandIndex((i) =>
            i < filteredCommands.length - 1 ? i + 1 : 0,
          );
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSelectedCommandIndex((i) =>
            i > 0 ? i - 1 : filteredCommands.length - 1,
          );
          return;
        }
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          selectCommand(filteredCommands[selectedCommandIndex]);
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowCommands(false);
          return;
        }
        if (e.key === 'Tab') {
          e.preventDefault();
          selectCommand(filteredCommands[selectedCommandIndex]);
          return;
        }
      }

      // Submit on Enter (Shift+Enter for newline)
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (value.trim() && !loading && !disabled) {
          onSubmit(value.trim());
        }
      }
    },
    [showCommands, filteredCommands, selectedCommandIndex, selectCommand, value, loading, disabled, onSubmit],
  );

  // Close command palette on click outside
  useEffect(() => {
    if (!showCommands) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        commandListRef.current &&
        !commandListRef.current.contains(e.target as Node)
      ) {
        setShowCommands(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showCommands]);

  const handleSendClick = useCallback(() => {
    if (loading && onStop) {
      onStop();
      return;
    }
    if (value.trim() && !disabled) {
      onSubmit(value.trim());
    }
  }, [loading, onStop, value, disabled, onSubmit]);

  const charCount = value.length;
  const isOverLimit = maxLength ? charCount > maxLength * 0.9 : false;
  const isAtLimit = maxLength ? charCount >= maxLength : false;

  return (
    <div className={cn('relative', className)}>
      {/* Suggestion pills */}
      {suggestions && suggestions.length > 0 && !loading && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {suggestions.map((suggestion, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onSuggestionClick?.(suggestion)}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-primary-50 text-primary-700 hover:bg-primary-100 transition-colors border border-primary-200"
            >
              <Brain className="h-3 w-3" />
              {suggestion}
            </button>
          ))}
        </div>
      )}

      {/* Main input container */}
      <div
        className={cn(
          'rounded-xl border border-gray-200 bg-white shadow-sm transition-all',
          'focus-within:ring-2 focus-within:ring-primary-500 focus-within:border-primary-500',
          disabled && 'opacity-50 cursor-not-allowed',
        )}
      >
        {/* Attachment chips */}
        {attachments && attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-3 pt-2">
            {attachments.map((file, idx) => (
              <span
                key={idx}
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-gray-100 text-xs text-gray-700 border border-gray-200"
              >
                {getAttachmentIcon(file.type)}
                <span className="truncate max-w-[120px]">{file.name}</span>
                <span className="text-gray-400">{formatFileSize(file.size)}</span>
                {onRemoveAttachment && (
                  <button
                    type="button"
                    onClick={() => onRemoveAttachment(idx)}
                    className="ml-0.5 text-gray-400 hover:text-gray-600 transition-colors"
                    aria-label={`Remove ${file.name}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </span>
            ))}
          </div>
        )}

        {/* Command palette dropdown */}
        {showCommands && filteredCommands.length > 0 && (
          <div
            ref={commandListRef}
            className="absolute bottom-full left-0 mb-1 bg-white rounded-lg shadow-lg border border-gray-200 py-1 min-w-[200px] z-50"
            role="listbox"
            aria-label="Slash commands"
          >
            {filteredCommands.map((cmd, idx) => (
              <button
                key={cmd.command}
                type="button"
                role="option"
                aria-selected={idx === selectedCommandIndex}
                onClick={() => selectCommand(cmd)}
                className={cn(
                  'flex items-center gap-2.5 w-full px-3 py-2 text-left text-sm transition-colors',
                  idx === selectedCommandIndex
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-700 hover:bg-gray-50',
                )}
              >
                <span
                  className={cn(
                    'flex items-center justify-center h-6 w-6 rounded-md',
                    idx === selectedCommandIndex
                      ? 'bg-primary-100 text-primary-600'
                      : 'bg-gray-100 text-gray-500',
                  )}
                >
                  {cmd.icon}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-xs">{cmd.command}</p>
                  <p className="text-[10px] text-gray-400 truncate">{cmd.description}</p>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || loading}
          rows={1}
          className={cn(
            'w-full resize-none border-0 focus:ring-0 bg-transparent p-3 text-sm',
            'placeholder:text-gray-400 outline-none',
            'disabled:cursor-not-allowed',
          )}
          style={{ overflowY: 'hidden' }}
          aria-label="Chat message input"
        />

        {/* Bottom bar: attach, spacer, char count, send */}
        <div className="flex items-center gap-1.5 px-2 pb-2">
          {onAttach && (
            <button
              type="button"
              onClick={onAttach}
              disabled={disabled || loading}
              className={cn(
                'flex items-center justify-center h-7 w-7 rounded-md',
                'text-gray-400 hover:text-gray-600 hover:bg-gray-100',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors',
              )}
              aria-label="Attach file"
            >
              <Paperclip className="h-4 w-4" />
            </button>
          )}

          <div className="flex-1" />

          {/* Character count */}
          {showCharCount && maxLength && (
            <span
              className={cn(
                'text-[10px] tabular-nums mr-1',
                isAtLimit
                  ? 'text-red-500 font-medium'
                  : isOverLimit
                    ? 'text-amber-500'
                    : 'text-gray-300',
              )}
            >
              {charCount}/{maxLength}
            </span>
          )}

          {/* Send / Stop button */}
          <button
            type="button"
            onClick={handleSendClick}
            disabled={!loading && (!value.trim() || disabled)}
            className={cn(
              'flex items-center justify-center h-7 w-7 rounded-lg transition-colors',
              loading
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-primary-600 text-white hover:bg-primary-700',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
            aria-label={loading ? 'Stop generation' : 'Send message'}
          >
            {loading ? (
              <Square className="h-3 w-3" />
            ) : (
              <SendHorizontal className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
});
