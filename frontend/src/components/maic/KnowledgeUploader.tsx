// src/components/maic/KnowledgeUploader.tsx
//
// Knowledge source upload component for AI chatbot. Supports drag-and-drop
// file upload (PDF, TXT, MD, DOCX) and raw text input. Displays knowledge
// items with embedding status badges and polls for status updates.

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
  { label: string; classes: string }
> = {
  pending: { label: 'Pending', classes: 'bg-yellow-100 text-yellow-700' },
  processing: {
    label: 'Processing',
    classes: 'bg-blue-100 text-blue-700 animate-pulse',
  },
  ready: { label: 'Ready', classes: 'bg-green-100 text-green-700' },
  failed: { label: 'Failed', classes: 'bg-red-100 text-red-700' },
};

const sourceTypeBadge: Record<string, { label: string; classes: string }> = {
  pdf: { label: 'PDF', classes: 'bg-red-50 text-red-600' },
  text: { label: 'Text', classes: 'bg-gray-100 text-gray-600' },
  document: { label: 'Doc', classes: 'bg-blue-50 text-blue-600' },
  url: { label: 'URL', classes: 'bg-purple-50 text-purple-600' },
};

export function KnowledgeUploader({ chatbotId }: { chatbotId: string }) {
  const [items, setItems] = useState<AIChatbotKnowledge[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
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
    <div className="space-y-4">
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
          'flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 cursor-pointer transition-colors',
          uploading && 'pointer-events-none opacity-60',
          isDragOver
            ? 'border-primary-500 bg-primary-50'
            : 'border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-gray-100',
        )}
      >
        {uploading ? (
          <Loader2 className="h-8 w-8 text-primary-500 animate-spin" aria-hidden="true" />
        ) : (
          <Upload className="h-8 w-8 text-gray-400" aria-hidden="true" />
        )}
        <p className="text-sm text-gray-600 text-center">
          <span className="font-medium text-primary-600">Click to upload</span> or drag
          and drop
        </p>
        <p className="text-xs text-gray-400">PDF, TXT, MD, DOCX — max 10 MB</p>
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
      <div className="flex items-center gap-4">
        {!showTextInput && (
          <button
            type="button"
            onClick={() => { setShowTextInput(true); setShowUrlInput(false); }}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-primary-600 hover:text-primary-700 transition-colors"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add Text
          </button>
        )}
        {!showUrlInput && (
          <button
            type="button"
            onClick={() => { setShowUrlInput(true); setShowTextInput(false); }}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-primary-600 hover:text-primary-700 transition-colors"
          >
            <Link className="h-4 w-4" aria-hidden="true" />
            Add URL
          </button>
        )}
      </div>

      {/* Text input section */}
      {showTextInput && (
        <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
          <input
            type="text"
            value={textTitle}
            onChange={(e) => setTextTitle(e.target.value)}
            placeholder="Title (optional)"
            className={cn(
              'block w-full rounded-lg border border-gray-300 bg-white px-3 py-2',
              'text-sm text-gray-900 placeholder-gray-400',
              'focus:border-primary-500 focus:ring-1 focus:ring-primary-500',
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
              'focus:border-primary-500 focus:ring-1 focus:ring-primary-500',
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
                'bg-primary-600 hover:bg-primary-700',
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
        <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
          <input
            type="text"
            value={urlTitle}
            onChange={(e) => setUrlTitle(e.target.value)}
            placeholder="Title (optional)"
            className={cn(
              'block w-full rounded-lg border border-gray-300 bg-white px-3 py-2',
              'text-sm text-gray-900 placeholder-gray-400',
              'focus:border-primary-500 focus:ring-1 focus:ring-primary-500',
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
              'focus:border-primary-500 focus:ring-1 focus:ring-primary-500',
            )}
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleAddUrl}
              disabled={uploading || !urlValue.trim()}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-white transition-colors',
                'bg-primary-600 hover:bg-primary-700',
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

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <AlertCircle className="h-4 w-4 text-red-500 shrink-0" aria-hidden="true" />
          <p className="text-sm text-red-700">{error}</p>
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-auto text-xs text-red-400 hover:text-red-600 transition-colors"
            aria-label="Dismiss error"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Knowledge items list */}
      {items.length > 0 && (
        <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
          {items.map((item) => {
            const status = statusConfig[item.embedding_status] || statusConfig.pending;
            const sourceType = sourceTypeBadge[item.source_type] || sourceTypeBadge.text;
            const isDeleting = deletingIds.has(item.id);

            return (
              <li
                key={item.id}
                className={cn(
                  'flex items-center gap-3 px-4 py-3',
                  isDeleting && 'opacity-50',
                )}
              >
                {/* Icon */}
                {item.embedding_status === 'ready' ? (
                  <CheckCircle
                    className="h-5 w-5 text-green-500 shrink-0"
                    aria-hidden="true"
                  />
                ) : item.embedding_status === 'failed' ? (
                  <AlertCircle
                    className="h-5 w-5 text-red-500 shrink-0"
                    aria-hidden="true"
                  />
                ) : item.embedding_status === 'processing' ? (
                  <Loader2
                    className="h-5 w-5 text-blue-500 shrink-0 animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <FileText
                    className="h-5 w-5 text-gray-400 shrink-0"
                    aria-hidden="true"
                  />
                )}

                {/* Info */}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {item.title}
                  </p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span
                      className={cn(
                        'inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                        sourceType.classes,
                      )}
                    >
                      {sourceType.label}
                    </span>
                    <span
                      className={cn(
                        'inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                        status.classes,
                      )}
                    >
                      {status.label}
                    </span>
                    {item.chunk_count > 0 && (
                      <span className="text-[10px] text-gray-400">
                        {item.chunk_count} chunk{item.chunk_count !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                  {item.embedding_status === 'failed' && item.error_message && (
                    <p className="text-xs text-red-500 mt-0.5 truncate">
                      {item.error_message}
                    </p>
                  )}
                </div>

                {/* Delete button */}
                <button
                  type="button"
                  onClick={() => handleDelete(item.id)}
                  disabled={isDeleting}
                  className="shrink-0 p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors disabled:cursor-not-allowed"
                  aria-label={`Delete ${item.title}`}
                >
                  {isDeleting ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {/* Empty state */}
      {items.length === 0 && !uploading && (
        <p className="text-center text-sm text-gray-400 py-4">
          No knowledge sources yet. Upload files or add text to get started.
        </p>
      )}
    </div>
  );
}
