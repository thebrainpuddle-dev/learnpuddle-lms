// src/components/maic/KnowledgeUploader.tsx
//
// Knowledge source manager for AI chatbot. Displays auto-ingested course content
// sources (read-only) separately from manually uploaded sources. Supports
// drag-and-drop file upload (PDF, TXT, MD, DOCX), raw text, and URL input.
// Polls for embedding status updates on pending/processing items.

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  Upload,
  FileText,
  Trash2,
  Plus,
  AlertCircle,
  CheckCircle,
  Loader2,
  Link,
  BookOpen,
  RefreshCw,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { chatbotApi } from '../../services/openmaicService';
import type { AIChatbotKnowledge } from '../../types/chatbot';

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const ACCEPTED_EXTENSIONS = ['.pdf', '.txt', '.md', '.docx'];
const ACCEPTED_MIME_TYPES = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
];
const POLL_INTERVAL = 5_000; // 5 seconds

const statusConfig: Record<
  AIChatbotKnowledge['embedding_status'],
  { label: string; classes: string; dotColor: string }
> = {
  pending: { label: 'Pending', classes: 'bg-amber-50 text-amber-700 border border-amber-200/60', dotColor: 'bg-amber-400' },
  processing: {
    label: 'Processing',
    classes: 'bg-blue-50 text-blue-700 border border-blue-200/60',
    dotColor: 'bg-blue-400 animate-pulse',
  },
  ready: { label: 'Ready', classes: 'bg-emerald-50 text-emerald-700 border border-emerald-200/60', dotColor: 'bg-emerald-500' },
  failed: { label: 'Failed', classes: 'bg-red-50 text-red-700 border border-red-200/60', dotColor: 'bg-red-500' },
};

const sourceTypeBadge: Record<string, { label: string; classes: string }> = {
  pdf: { label: 'PDF', classes: 'bg-red-50 text-red-600 border border-red-100' },
  text: { label: 'Text', classes: 'bg-gray-50 text-gray-600 border border-gray-200' },
  document: { label: 'Doc', classes: 'bg-blue-50 text-blue-600 border border-blue-100' },
  url: { label: 'URL', classes: 'bg-purple-50 text-purple-600 border border-purple-100' },
};

// ─── Knowledge Item Row ──────────────────────────────────────────────────────

function KnowledgeItem({
  item,
  isDeleting,
  onDelete,
}: {
  item: AIChatbotKnowledge;
  isDeleting: boolean;
  onDelete?: (id: string) => void;
}) {
  const status = statusConfig[item.embedding_status] || statusConfig.pending;
  const sourceType = sourceTypeBadge[item.source_type] || sourceTypeBadge.text;

  return (
    <li
      className={cn(
        'group/item flex items-center gap-3 px-4 py-3 transition-colors duration-150',
        'hover:bg-gray-50/50',
        isDeleting && 'opacity-50',
      )}
    >
      {/* Status icon */}
      <div className={cn(
        'shrink-0 h-8 w-8 rounded-lg flex items-center justify-center',
        item.embedding_status === 'ready' ? 'bg-emerald-50' :
        item.embedding_status === 'failed' ? 'bg-red-50' :
        item.embedding_status === 'processing' ? 'bg-blue-50' :
        'bg-gray-50',
      )}>
        {item.embedding_status === 'ready' ? (
          <CheckCircle className="h-4 w-4 text-emerald-500" aria-hidden="true" />
        ) : item.embedding_status === 'failed' ? (
          <AlertCircle className="h-4 w-4 text-red-500" aria-hidden="true" />
        ) : item.embedding_status === 'processing' ? (
          <Loader2 className="h-4 w-4 text-blue-500 animate-spin" aria-hidden="true" />
        ) : (
          <FileText className="h-4 w-4 text-gray-400" aria-hidden="true" />
        )}
      </div>

      {/* Info */}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-800 truncate leading-5">
          {item.title}
        </p>
        <div className="flex items-center gap-1.5 mt-1 flex-wrap">
          <span
            className={cn(
              'inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold',
              sourceType.classes,
            )}
          >
            {sourceType.label}
          </span>
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold',
              status.classes,
            )}
          >
            <span className={cn('h-1 w-1 rounded-full', status.dotColor)} />
            {status.label}
          </span>
          {item.is_auto && (
            <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold bg-teal-50 text-teal-600 border border-teal-100">
              Auto
            </span>
          )}
          {item.content_source_title && (
            <span className="text-[10px] text-gray-400 truncate max-w-[140px]" title={item.content_source_title}>
              from {item.content_source_title}
            </span>
          )}
          {item.chunk_count > 0 && (
            <span className="text-[10px] text-gray-400 font-medium">
              {item.chunk_count} chunk{item.chunk_count !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        {item.embedding_status === 'failed' && item.error_message && (
          <p className="text-xs text-red-500 mt-1 truncate">
            {item.error_message}
          </p>
        )}
      </div>

      {/* Delete button — only for manual sources */}
      {onDelete && (
        <button
          type="button"
          onClick={() => onDelete(item.id)}
          disabled={isDeleting}
          className={cn(
            'shrink-0 p-1.5 rounded-lg transition-all duration-200',
            'text-gray-300 opacity-0 group-hover/item:opacity-100',
            'hover:text-red-500 hover:bg-red-50',
            'disabled:cursor-not-allowed',
          )}
          aria-label={`Delete ${item.title}`}
        >
          {isDeleting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
      )}
    </li>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export function KnowledgeUploader({ chatbotId }: { chatbotId: string }) {
  const [items, setItems] = useState<AIChatbotKnowledge[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTextInput, setShowTextInput] = useState(false);
  const [textTitle, setTextTitle] = useState('');
  const [textContent, setTextContent] = useState('');
  const [showUrlInput, setShowUrlInput] = useState(false);
  const [urlValue, setUrlValue] = useState('');
  const [urlTitle, setUrlTitle] = useState('');
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());

  const inputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Split items into auto-ingested and manual
  const autoItems = items.filter((i) => i.is_auto);
  const manualItems = items.filter((i) => !i.is_auto);

  // ── Fetch knowledge list ──────────────────────────────────────────────

  const fetchItems = useCallback(async () => {
    try {
      const res = await chatbotApi.listKnowledge(chatbotId);
      setItems(res.data);
    } catch {
      // Silently ignore fetch errors during polling
    }
  }, [chatbotId]);

  // Initial load
  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // ── Polling for pending / processing items ────────────────────────────

  useEffect(() => {
    const hasPending = items.some(
      (i) => i.embedding_status === 'pending' || i.embedding_status === 'processing',
    );

    if (hasPending && !pollRef.current) {
      pollRef.current = setInterval(fetchItems, POLL_INTERVAL);
    } else if (!hasPending && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [items, fetchItems]);

  // ── Refresh auto-ingested sources ──────────────────────────────────────

  const handleRefreshSources = useCallback(async () => {
    setRefreshing(true);
    try {
      await chatbotApi.refreshSources(chatbotId);
      // Re-fetch after a short delay to allow the task to start
      setTimeout(fetchItems, 1500);
    } catch {
      setError('Failed to refresh sources. Please try again.');
    } finally {
      setRefreshing(false);
    }
  }, [chatbotId, fetchItems]);

  // ── File validation ───────────────────────────────────────────────────

  const validateFile = useCallback((file: File): string | null => {
    if (file.size > MAX_FILE_SIZE) {
      return `File "${file.name}" exceeds the 10 MB limit.`;
    }
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext) && !ACCEPTED_MIME_TYPES.includes(file.type)) {
      return `File type "${ext}" is not supported. Use PDF, TXT, MD, or DOCX.`;
    }
    return null;
  }, []);

  // ── Upload handler ────────────────────────────────────────────────────

  const uploadFile = useCallback(
    async (file: File) => {
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }

      setError(null);
      setUploading(true);
      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('title', file.name);
        const res = await chatbotApi.uploadKnowledge(chatbotId, formData);
        setItems((prev) => [res.data, ...prev]);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Upload failed. Please try again.',
        );
      } finally {
        setUploading(false);
      }
    },
    [chatbotId, validateFile],
  );

  // ── Drag-and-drop handlers ───────────────────────────────────────────

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) uploadFile(file);
    },
    [uploadFile],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) uploadFile(file);
      if (inputRef.current) inputRef.current.value = '';
    },
    [uploadFile],
  );

  // ── Add raw text ─────────────────────────────────────────────────────

  const handleAddText = useCallback(async () => {
    const title = textTitle.trim() || 'Untitled Text';
    const content = textContent.trim();
    if (!content) {
      setError('Text content cannot be empty.');
      return;
    }

    setError(null);
    setUploading(true);
    try {
      const formData = new FormData();
      const blob = new Blob([content], { type: 'text/plain' });
      formData.append('file', blob, `${title}.txt`);
      formData.append('title', title);
      const res = await chatbotApi.uploadKnowledge(chatbotId, formData);
      setItems((prev) => [res.data, ...prev]);
      setTextTitle('');
      setTextContent('');
      setShowTextInput(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to add text. Please try again.',
      );
    } finally {
      setUploading(false);
    }
  }, [chatbotId, textTitle, textContent]);

  // ── Add URL ──────────────────────────────────────────────────────────

  const handleAddUrl = useCallback(async () => {
    const url = urlValue.trim();
    if (!url) {
      setError('URL cannot be empty.');
      return;
    }
    try {
      new URL(url); // validate URL format
    } catch {
      setError('Please enter a valid URL (e.g. https://example.com).');
      return;
    }

    const title = urlTitle.trim() || url;

    setError(null);
    setUploading(true);
    try {
      const res = await chatbotApi.addKnowledgeUrl(chatbotId, {
        source_type: 'url',
        url,
        title,
      });
      setItems((prev) => [res.data, ...prev]);
      setUrlValue('');
      setUrlTitle('');
      setShowUrlInput(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to add URL. Please try again.',
      );
    } finally {
      setUploading(false);
    }
  }, [chatbotId, urlValue, urlTitle]);

  // ── Delete handler ───────────────────────────────────────────────────

  const handleDelete = useCallback(
    async (knowledgeId: string) => {
      setDeletingIds((prev) => new Set(prev).add(knowledgeId));
      try {
        await chatbotApi.deleteKnowledge(chatbotId, knowledgeId);
        setItems((prev) => prev.filter((item) => item.id !== knowledgeId));
      } catch {
        setError('Failed to delete item. Please try again.');
      } finally {
        setDeletingIds((prev) => {
          const next = new Set(prev);
          next.delete(knowledgeId);
          return next;
        });
      }
    },
    [chatbotId],
  );

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      {/* ── Auto-Ingested Sources (read-only) ──────────────────────────── */}
      {autoItems.length > 0 && (
        <div className="rounded-xl border border-teal-200/60 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-teal-50 to-teal-50/30 border-b border-teal-100">
            <div className="flex items-center gap-2.5">
              <div className="h-7 w-7 rounded-lg bg-teal-100 flex items-center justify-center">
                <BookOpen className="h-3.5 w-3.5 text-teal-600" aria-hidden="true" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-800">
                  Course Content
                </h3>
                <p className="text-[11px] text-gray-400 leading-tight">
                  Auto-synced from assigned sections
                </p>
              </div>
              <span className="rounded-full bg-teal-100 px-2 py-0.5 text-[10px] font-bold text-teal-700">
                {autoItems.length}
              </span>
            </div>
            <button
              type="button"
              onClick={handleRefreshSources}
              disabled={refreshing}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium',
                'text-teal-600 hover:bg-teal-100/60 active:bg-teal-100',
                'disabled:opacity-50 transition-all duration-200',
              )}
              title="Re-sync course content sources"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} aria-hidden="true" />
              {refreshing ? 'Syncing...' : 'Re-sync'}
            </button>
          </div>
          <ul className="divide-y divide-teal-50 bg-white">
            {autoItems.map((item) => (
              <KnowledgeItem
                key={item.id}
                item={item}
                isDeleting={false}
              />
            ))}
          </ul>
        </div>
      )}

      {/* ── Supplementary Sources (manual) ─────────────────────────────── */}
      <div>
        {autoItems.length > 0 && (
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Supplementary Sources
          </h3>
        )}

        {/* Drag-and-drop zone */}
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          role="button"
          tabIndex={0}
          aria-label="Upload knowledge file"
          className={cn(
            'flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-8 cursor-pointer transition-all duration-200',
            uploading && 'pointer-events-none opacity-60',
            isDragOver
              ? 'border-indigo-400 bg-indigo-50/80 scale-[1.01] shadow-sm shadow-indigo-100'
              : 'border-gray-200 bg-gray-50/50 hover:border-indigo-300 hover:bg-indigo-50/30',
          )}
        >
          <div className={cn(
            'h-12 w-12 rounded-xl flex items-center justify-center transition-colors duration-200',
            isDragOver ? 'bg-indigo-100' : 'bg-gray-100',
          )}>
            {uploading ? (
              <Loader2 className="h-6 w-6 text-indigo-500 animate-spin" aria-hidden="true" />
            ) : (
              <Upload className={cn(
                'h-6 w-6 transition-colors duration-200',
                isDragOver ? 'text-indigo-500' : 'text-gray-400',
              )} aria-hidden="true" />
            )}
          </div>
          <div className="text-center">
            <p className="text-sm text-gray-600">
              <span className="font-semibold text-indigo-600">Click to upload</span> or drag
              and drop
            </p>
            <p className="text-xs text-gray-400 mt-1">PDF, TXT, MD, DOCX — max 10 MB</p>
          </div>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.md,.docx"
          onChange={handleInputChange}
          className="hidden"
          aria-hidden="true"
        />

        {/* Add Text / Add URL toggles */}
        <div className="flex items-center gap-4 mt-3">
          {!showTextInput && (
            <button
              type="button"
              onClick={() => { setShowTextInput(true); setShowUrlInput(false); }}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-700 transition-colors"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add Text
            </button>
          )}
          {!showUrlInput && (
            <button
              type="button"
              onClick={() => { setShowUrlInput(true); setShowTextInput(false); }}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-700 transition-colors"
            >
              <Link className="h-4 w-4" aria-hidden="true" />
              Add URL
            </button>
          )}
        </div>

        {/* Text input section */}
        {showTextInput && (
          <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3 mt-3">
            <input
              type="text"
              value={textTitle}
              onChange={(e) => setTextTitle(e.target.value)}
              placeholder="Title (optional)"
              className={cn(
                'block w-full rounded-lg border border-gray-300 bg-white px-3 py-2',
                'text-sm text-gray-900 placeholder-gray-400',
                'focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500',
              )}
            />
            <textarea
              value={textContent}
              onChange={(e) => setTextContent(e.target.value)}
              placeholder="Paste your knowledge text here..."
              rows={5}
              className={cn(
                'block w-full rounded-lg border border-gray-300 bg-white px-3 py-2',
                'text-sm text-gray-900 placeholder-gray-400',
                'focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500',
                'resize-y',
              )}
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleAddText}
                disabled={uploading || !textContent.trim()}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-white transition-colors',
                  'bg-indigo-600 hover:bg-indigo-700',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                {uploading ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Plus className="h-4 w-4" aria-hidden="true" />
                )}
                Add
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowTextInput(false);
                  setTextTitle('');
                  setTextContent('');
                }}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* URL input section */}
        {showUrlInput && (
          <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3 mt-3">
            <input
              type="text"
              value={urlTitle}
              onChange={(e) => setUrlTitle(e.target.value)}
              placeholder="Title (optional)"
              className={cn(
                'block w-full rounded-lg border border-gray-300 bg-white px-3 py-2',
                'text-sm text-gray-900 placeholder-gray-400',
                'focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500',
              )}
            />
            <input
              type="url"
              value={urlValue}
              onChange={(e) => setUrlValue(e.target.value)}
              placeholder="https://example.com/article"
              className={cn(
                'block w-full rounded-lg border border-gray-300 bg-white px-3 py-2',
                'text-sm text-gray-900 placeholder-gray-400',
                'focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500',
              )}
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleAddUrl}
                disabled={uploading || !urlValue.trim()}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-white transition-colors',
                  'bg-indigo-600 hover:bg-indigo-700',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                {uploading ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Link className="h-4 w-4" aria-hidden="true" />
                )}
                Add URL
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowUrlInput(false);
                  setUrlValue('');
                  setUrlTitle('');
                }}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2.5 rounded-xl border border-red-200/80 bg-gradient-to-r from-red-50 to-red-50/30 px-4 py-3 shadow-sm">
          <div className="shrink-0 h-6 w-6 rounded-lg bg-red-100 flex items-center justify-center">
            <AlertCircle className="h-3.5 w-3.5 text-red-500" aria-hidden="true" />
          </div>
          <p className="text-sm text-red-700 flex-1">{error}</p>
          <button
            type="button"
            onClick={() => setError(null)}
            className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-red-500 hover:bg-red-100 transition-colors"
            aria-label="Dismiss error"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Manual knowledge items list */}
      {manualItems.length > 0 && (
        <ul className="divide-y divide-gray-100 rounded-xl border border-gray-200/80 bg-white shadow-sm overflow-hidden">
          {manualItems.map((item) => (
            <KnowledgeItem
              key={item.id}
              item={item}
              isDeleting={deletingIds.has(item.id)}
              onDelete={handleDelete}
            />
          ))}
        </ul>
      )}

      {/* Empty state */}
      {items.length === 0 && !uploading && (
        <div className="text-center py-8">
          <div className="mx-auto h-12 w-12 rounded-xl bg-gray-100 flex items-center justify-center mb-3">
            <BookOpen className="h-6 w-6 text-gray-400" />
          </div>
          <p className="text-sm font-medium text-gray-500">No knowledge sources yet</p>
          <p className="text-xs text-gray-400 mt-1">
            Upload files, add text, or assign sections to auto-ingest course content.
          </p>
        </div>
      )}
    </div>
  );
}
