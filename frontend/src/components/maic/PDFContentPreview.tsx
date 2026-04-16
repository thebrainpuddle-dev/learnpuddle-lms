// src/components/maic/PDFContentPreview.tsx
//
// Preview component for parsed PDF content. Displays extracted text,
// images, tables, and metadata from backend PDF parsing results.

import React, { useState, useCallback } from 'react';
import { FileText, Image, Table2, X, ChevronDown, ChevronUp } from 'lucide-react';
import type { ParsedPdfContent } from '../../lib/pdf/types';
import { cn } from '../../lib/utils';

interface PDFContentPreviewProps {
  content: ParsedPdfContent;
  onUseContent: (text: string, images: string[]) => void;
  onClose: () => void;
}

const TEXT_PREVIEW_LENGTH = 500;

export const PDFContentPreview: React.FC<PDFContentPreviewProps> = ({
  content,
  onUseContent,
  onClose,
}) => {
  const [showFullText, setShowFullText] = useState(false);
  const [activeTab, setActiveTab] = useState<'text' | 'images' | 'tables'>('text');

  const textPreview = showFullText
    ? content.text
    : content.text.slice(0, TEXT_PREVIEW_LENGTH);
  const hasMoreText = content.text.length > TEXT_PREVIEW_LENGTH;

  const handleUseContent = useCallback(() => {
    onUseContent(content.text, content.images);
  }, [content.text, content.images, onUseContent]);

  const imageCount = content.images.length;
  const tableCount = content.tables?.length ?? 0;
  const pageCount = content.metadata?.pageCount ?? 0;
  const parserName = content.metadata?.parser ?? 'Standard';

  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-indigo-500" aria-hidden="true" />
          <h3 className="text-sm font-medium text-gray-800">PDF Content Preview</h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600"
          aria-label="Close preview"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Metadata bar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-50 border-b border-gray-100 text-xs text-gray-500">
        {pageCount > 0 && (
          <span className="inline-flex items-center gap-1">
            <FileText className="h-3 w-3" aria-hidden="true" />
            {pageCount} page{pageCount !== 1 ? 's' : ''}
          </span>
        )}
        {imageCount > 0 && (
          <span className="inline-flex items-center gap-1">
            <Image className="h-3 w-3" aria-hidden="true" />
            {imageCount} image{imageCount !== 1 ? 's' : ''}
          </span>
        )}
        {tableCount > 0 && (
          <span className="inline-flex items-center gap-1">
            <Table2 className="h-3 w-3" aria-hidden="true" />
            {tableCount} table{tableCount !== 1 ? 's' : ''}
          </span>
        )}
        <span className="ml-auto text-gray-400">Parser: {parserName}</span>
      </div>

      {/* Tab navigation */}
      <div className="flex border-b border-gray-100">
        <button
          type="button"
          onClick={() => setActiveTab('text')}
          className={cn(
            'flex-1 px-4 py-2 text-xs font-medium transition-colors',
            activeTab === 'text'
              ? 'text-indigo-600 border-b-2 border-indigo-600 bg-indigo-50/50'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50',
          )}
        >
          Text
        </button>
        {imageCount > 0 && (
          <button
            type="button"
            onClick={() => setActiveTab('images')}
            className={cn(
              'flex-1 px-4 py-2 text-xs font-medium transition-colors',
              activeTab === 'images'
                ? 'text-indigo-600 border-b-2 border-indigo-600 bg-indigo-50/50'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50',
            )}
          >
            Images
          </button>
        )}
        {tableCount > 0 && (
          <button
            type="button"
            onClick={() => setActiveTab('tables')}
            className={cn(
              'flex-1 px-4 py-2 text-xs font-medium transition-colors',
              activeTab === 'tables'
                ? 'text-indigo-600 border-b-2 border-indigo-600 bg-indigo-50/50'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50',
            )}
          >
            Tables
          </button>
        )}
      </div>

      {/* Tab content */}
      <div className="p-4 max-h-64 overflow-y-auto">
        {/* Text tab */}
        {activeTab === 'text' && (
          <div>
            <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
              {textPreview}
              {!showFullText && hasMoreText && '...'}
            </p>
            {hasMoreText && (
              <button
                type="button"
                onClick={() => setShowFullText(!showFullText)}
                className="inline-flex items-center gap-1 mt-2 text-xs text-indigo-600 hover:text-indigo-800 transition-colors"
              >
                {showFullText ? (
                  <>
                    <ChevronUp className="h-3 w-3" /> Show less
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-3 w-3" /> Show more
                  </>
                )}
              </button>
            )}
          </div>
        )}

        {/* Images tab */}
        {activeTab === 'images' && imageCount > 0 && (
          <div className="grid grid-cols-3 gap-2">
            {content.images.map((src, idx) => (
              <div
                key={idx}
                className="aspect-square rounded border border-gray-200 overflow-hidden bg-gray-100"
              >
                <img
                  src={src}
                  alt={`Extracted image ${idx + 1}`}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        )}

        {/* Tables tab */}
        {activeTab === 'tables' && content.tables && content.tables.length > 0 && (
          <div className="space-y-3">
            {content.tables.map((table, idx) => (
              <div key={idx} className="overflow-x-auto">
                {table.caption && (
                  <p className="text-xs font-medium text-gray-600 mb-1">
                    {table.caption} (Page {table.page})
                  </p>
                )}
                <table className="min-w-full text-xs border border-gray-200">
                  <tbody>
                    {table.data.map((row, rIdx) => (
                      <tr key={rIdx} className={rIdx === 0 ? 'bg-gray-100 font-medium' : ''}>
                        {row.map((cell, cIdx) => (
                          <td key={cIdx} className="border border-gray-200 px-2 py-1 text-gray-700">
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-gray-100 bg-gray-50/50">
        <button
          type="button"
          onClick={onClose}
          className={cn(
            'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            'text-gray-600 hover:bg-gray-100 border border-gray-200',
            'focus:outline-none focus:ring-2 focus:ring-gray-400',
          )}
        >
          Close
        </button>
        <button
          type="button"
          onClick={handleUseContent}
          className={cn(
            'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            'bg-indigo-600 text-white hover:bg-indigo-700',
            'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
          )}
        >
          Use this content
        </button>
      </div>
    </div>
  );
};
