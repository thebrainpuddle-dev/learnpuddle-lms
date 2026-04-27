// course-editor/ContentPreviewModal.tsx
//
// Modal that previews any content item (VIDEO, DOCUMENT, LINK, TEXT).

import React from 'react';
import DOMPurify from 'dompurify';
import { HlsVideoPlayer } from '../../../components/common';
import { Button } from '../../../components/common';
import {
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
  XMarkIcon,
  ArrowPathIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import type { Content } from './types';
import { getContentIcon } from './contentUtils';

interface ContentPreviewModalProps {
  content: Content;
  onClose: () => void;
}

const resolveUrl = (u: string | null): string => {
  if (!u) return '';
  const backendOrigin = (process.env.REACT_APP_API_URL || `http://${window.location.hostname}:8000/api`).replace(/\/api\/?$/, '');
  if (u.startsWith('http')) {
    try {
      const parsed = new URL(u);
      return `${backendOrigin}${parsed.pathname}${parsed.search}`;
    } catch {
      return u;
    }
  }
  return `${backendOrigin}${u.startsWith('/') ? '' : '/'}${u}`;
};

export const ContentPreviewModal: React.FC<ContentPreviewModalProps> = ({ content: c, onClose }) => (
  <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
    <div className="bg-white rounded-xl max-w-3xl w-full mx-4 max-h-[85vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center justify-between p-4 border-b border-gray-200">
        <div className="flex items-center gap-2">
          {getContentIcon(c.content_type)}
          <h3 className="text-lg font-semibold text-gray-900 truncate">{c.title}</h3>
          <span className="text-xs text-gray-500 uppercase">{c.content_type}</span>
        </div>
        <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
          <XMarkIcon className="h-5 w-5" />
        </button>
      </div>

      <div className="p-6 overflow-y-auto flex-1">
        {c.content_type === 'VIDEO' ? (
          c.video_status === 'READY' && c.file_url ? (
            <HlsVideoPlayer src={resolveUrl(c.file_url)} className="w-full rounded-lg bg-black aspect-video" />
          ) : c.video_status === 'PROCESSING' ? (
            <div className="flex flex-col items-center justify-center py-16 text-amber-600">
              <ArrowPathIcon className="h-12 w-12 animate-spin mb-3" />
              <p className="font-medium">Video is still processing...</p>
              <p className="text-sm text-gray-500 mt-1">HLS transcoding, transcript, and assignments are being generated.</p>
            </div>
          ) : c.video_status === 'FAILED' ? (
            <div className="flex flex-col items-center justify-center py-16 text-red-600">
              <ExclamationCircleIcon className="h-12 w-12 mb-3" />
              <p className="font-medium">Video processing failed</p>
              <p className="text-sm text-gray-500 mt-1">Try re-uploading the video.</p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-gray-400">
              <PlayCircleIcon className="h-12 w-12 mb-3" />
              <p className="text-sm">Video uploaded, waiting for processing...</p>
            </div>
          )
        ) : c.content_type === 'DOCUMENT' ? (
          c.file_url ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-3">
              <DocumentTextIcon className="h-12 w-12 text-orange-400" />
              <p className="font-medium text-gray-900">{c.title}</p>
              <a href={c.file_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700">
                Open document in new tab
              </a>
            </div>
          ) : (
            <p className="text-gray-400 text-center py-8">No file uploaded</p>
          )
        ) : c.content_type === 'LINK' ? (
          c.file_url ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-4">
              <div className="w-20 h-20 bg-gradient-to-br from-purple-50 to-purple-100 rounded-full flex items-center justify-center shadow-sm border border-purple-200">
                <LinkIcon className="h-10 w-10 text-purple-500" />
              </div>
              <p className="font-medium text-gray-900">{c.title}</p>
              <p className="text-sm text-gray-500 break-all max-w-md text-center">{c.file_url}</p>
              <a
                href={c.file_url.startsWith('http') ? c.file_url : `https://${c.file_url}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700"
              >
                Open link in new tab
              </a>
            </div>
          ) : (
            <p className="text-gray-400 text-center py-8">No URL provided</p>
          )
        ) : c.content_type === 'TEXT' ? (
          <div className="prose prose-sm max-w-none">
            {c.text_content ? (
              <div className="p-4 bg-gray-50 rounded-lg text-gray-700 leading-relaxed" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(c.text_content) }} />
            ) : (
              <div className="p-4 bg-gray-50 rounded-lg text-gray-500">No text content</div>
            )}
          </div>
        ) : (
          <p className="text-gray-400 text-center py-8">Preview not available for this content type</p>
        )}
      </div>

      <div className="p-4 border-t border-gray-200 flex justify-end">
        <Button variant="outline" onClick={onClose}>Close</Button>
      </div>
    </div>
  </div>
);
