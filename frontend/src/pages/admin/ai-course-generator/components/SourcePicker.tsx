// src/pages/admin/ai-course-generator/components/SourcePicker.tsx
// Renders file-upload UI or URL-input UI based on source type selection.

import React, { useRef } from 'react';
import {
  DocumentTextIcon,
  LinkIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import type { SourceType } from '../../../../services/aiCourseGeneratorService';
import { MAX_FILE_BYTES, validateUrlHost } from '../../../../services/aiCourseGeneratorService';

export const FILE_SOURCE_TYPES: SourceType[] = ['pdf', 'docx', 'text'];
export const URL_SOURCE_TYPES: SourceType[] = ['youtube', 'vimeo'];

const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  pdf: 'PDF',
  docx: 'Word (DOCX)',
  text: 'Plain Text',
  youtube: 'YouTube',
  vimeo: 'Vimeo',
};

const ACCEPT_MAP: Record<string, string> = {
  pdf: '.pdf,application/pdf',
  docx: '.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  text: '.txt,text/plain',
};

interface SourcePickerProps {
  sourceType: SourceType;
  onSourceTypeChange: (type: SourceType) => void;
  file: File | null;
  onFileChange: (file: File | null) => void;
  url: string;
  onUrlChange: (url: string) => void;
  fileError: string | null;
  urlError: string | null;
}

export const SourcePicker: React.FC<SourcePickerProps> = ({
  sourceType,
  onSourceTypeChange,
  file,
  onFileChange,
  url,
  onUrlChange,
  fileError,
  urlError,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isFileType = FILE_SOURCE_TYPES.includes(sourceType);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    onFileChange(selected);
    // Reset input so same file can be re-selected after clear
    e.target.value = '';
  };

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-4">
      {/* Source type tab bar */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Source Type
        </label>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Source type">
          {(Object.keys(SOURCE_TYPE_LABELS) as SourceType[]).map((type) => (
            <button
              key={type}
              type="button"
              data-testid={`source-type-${type}`}
              onClick={() => {
                onSourceTypeChange(type);
                onFileChange(null);
                onUrlChange('');
              }}
              className={`cursor-pointer rounded-full px-4 py-1.5 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 ${
                sourceType === type
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {SOURCE_TYPE_LABELS[type]}
            </button>
          ))}
        </div>
      </div>

      {/* File upload UI */}
      {isFileType && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            File <span className="text-gray-400 font-normal">(max 20 MB)</span>
          </label>
          {file ? (
            <div
              data-testid="file-preview"
              className={`flex items-center gap-3 rounded-lg border px-4 py-3 ${
                fileError
                  ? 'border-red-300 bg-red-50'
                  : 'border-gray-200 bg-gray-50'
              }`}
            >
              <DocumentTextIcon className="h-5 w-5 flex-shrink-0 text-gray-400" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-gray-900">
                  {file.name}
                </p>
                <p
                  data-testid="file-size"
                  className={`text-xs ${
                    file.size > MAX_FILE_BYTES ? 'text-red-600' : 'text-gray-500'
                  }`}
                >
                  {formatBytes(file.size)}
                  {file.size > MAX_FILE_BYTES && ' — exceeds 20 MB limit'}
                </p>
              </div>
              <button
                type="button"
                aria-label="Remove file"
                onClick={() => onFileChange(null)}
                className="cursor-pointer text-gray-400 hover:text-gray-600"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>
          ) : (
            <div
              data-testid="file-drop-zone"
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              role="button"
              tabIndex={0}
              aria-label="Choose file"
              className="cursor-pointer rounded-lg border-2 border-dashed border-gray-300 px-6 py-8 text-center transition-colors hover:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1"
            >
              <DocumentTextIcon className="mx-auto h-8 w-8 text-gray-400 mb-2" />
              <p className="text-sm text-gray-600">
                Click to choose a file
              </p>
              <p className="mt-1 text-xs text-gray-400">
                {SOURCE_TYPE_LABELS[sourceType]} up to 20 MB
              </p>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            data-testid="file-input"
            accept={ACCEPT_MAP[sourceType] ?? ''}
            onChange={handleFileChange}
            className="sr-only"
          />
          {fileError && (
            <p
              data-testid="file-error"
              role="alert"
              className="mt-1.5 text-sm text-red-600"
            >
              {fileError}
            </p>
          )}
        </div>
      )}

      {/* URL input UI */}
      {!isFileType && (
        <div>
          <label
            htmlFor="source-url"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            {SOURCE_TYPE_LABELS[sourceType]} URL
          </label>
          <div className="relative">
            <LinkIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              id="source-url"
              data-testid="url-input"
              type="url"
              value={url}
              onChange={(e) => onUrlChange(e.target.value)}
              placeholder={
                sourceType === 'youtube'
                  ? 'https://www.youtube.com/watch?v=...'
                  : 'https://vimeo.com/...'
              }
              className={`block w-full rounded-lg border pl-10 pr-3 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
                urlError
                  ? 'border-red-300 focus:ring-red-400'
                  : 'border-gray-300'
              }`}
            />
          </div>
          {urlError && (
            <p
              data-testid="url-error"
              role="alert"
              className="mt-1.5 text-sm text-red-600"
            >
              {urlError}
            </p>
          )}
        </div>
      )}
    </div>
  );
};
