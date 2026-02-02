// src/components/teacher/ContentPlayer.tsx

import React, { useState } from 'react';
import {
  PlayIcon,
  DocumentTextIcon,
  LinkIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/solid';
import { ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline';

interface ContentPlayerProps {
  content: {
    id: string;
    title: string;
    content_type: 'VIDEO' | 'DOCUMENT' | 'LINK' | 'TEXT';
    file_url?: string;
    text_content?: string;
    duration?: number;
  };
  isCompleted?: boolean;
  onComplete?: () => void;
  onProgressUpdate?: (seconds: number) => void;
}

export const ContentPlayer: React.FC<ContentPlayerProps> = ({
  content,
  isCompleted = false,
  onComplete,
  onProgressUpdate,
}) => {
  const [, setIsPlaying] = useState(false);
  const [, setCurrentTime] = useState(0);
  
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };
  
  // Video player
  if (content.content_type === 'VIDEO') {
    return (
      <div className="bg-slate-900 rounded-xl overflow-hidden">
        {/* Video container */}
        <div className="relative aspect-video bg-black">
          {content.file_url ? (
            <video
              className="w-full h-full"
              src={content.file_url}
              controls
              onTimeUpdate={(e) => {
                const video = e.currentTarget;
                setCurrentTime(Math.floor(video.currentTime));
                onProgressUpdate?.(Math.floor(video.currentTime));
              }}
              onEnded={() => onComplete?.()}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
            />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400">
              <PlayIcon className="h-16 w-16 mb-4" />
              <p>Video unavailable</p>
            </div>
          )}
        </div>
        
        {/* Video info */}
        <div className="p-4 flex items-center justify-between">
          <div>
            <h3 className="text-white font-medium">{content.title}</h3>
            <p className="text-slate-400 text-sm">
              {content.duration ? formatDuration(content.duration) : 'Duration unknown'}
            </p>
          </div>
          
          {isCompleted && (
            <div className="flex items-center text-emerald-400">
              <CheckCircleIcon className="h-5 w-5 mr-1" />
              <span className="text-sm">Completed</span>
            </div>
          )}
        </div>
      </div>
    );
  }
  
  // Document viewer
  if (content.content_type === 'DOCUMENT') {
    return (
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="p-6">
          <div className="flex items-start">
            <div className="p-3 bg-blue-100 rounded-lg mr-4">
              <DocumentTextIcon className="h-8 w-8 text-blue-600" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-gray-900 mb-1">{content.title}</h3>
              <p className="text-sm text-gray-500 mb-4">PDF Document</p>
              
              <div className="flex items-center space-x-3">
                {content.file_url && (
                  <a
                    href={content.file_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                    onClick={() => onComplete?.()}
                  >
                    <ArrowTopRightOnSquareIcon className="h-4 w-4 mr-2" />
                    Open Document
                  </a>
                )}
                
                {isCompleted && (
                  <span className="flex items-center text-emerald-600">
                    <CheckCircleIcon className="h-5 w-5 mr-1" />
                    Completed
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
        
        {/* Document preview iframe */}
        {content.file_url && (
          <div className="border-t border-gray-200">
            <iframe
              src={content.file_url}
              className="w-full h-96"
              title={content.title}
            />
          </div>
        )}
      </div>
    );
  }
  
  // External link
  if (content.content_type === 'LINK') {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-start">
          <div className="p-3 bg-purple-100 rounded-lg mr-4">
            <LinkIcon className="h-8 w-8 text-purple-600" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-gray-900 mb-1">{content.title}</h3>
            <p className="text-sm text-gray-500 mb-4">External Resource</p>
            
            <div className="flex items-center space-x-3">
              {content.file_url && (
                <a
                  href={content.file_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
                  onClick={() => onComplete?.()}
                >
                  <ArrowTopRightOnSquareIcon className="h-4 w-4 mr-2" />
                  Open Link
                </a>
              )}
              
              {isCompleted && (
                <span className="flex items-center text-emerald-600">
                  <CheckCircleIcon className="h-5 w-5 mr-1" />
                  Completed
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }
  
  // Text content
  if (content.content_type === 'TEXT') {
    return (
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="p-6 border-b border-gray-200 flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">{content.title}</h3>
          {isCompleted && (
            <span className="flex items-center text-emerald-600">
              <CheckCircleIcon className="h-5 w-5 mr-1" />
              Completed
            </span>
          )}
        </div>
        
        <div className="p-6 prose prose-slate max-w-none">
          <div dangerouslySetInnerHTML={{ __html: content.text_content || '' }} />
        </div>
        
        {!isCompleted && onComplete && (
          <div className="p-4 border-t border-gray-200 bg-gray-50">
            <button
              onClick={onComplete}
              className="w-full py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors"
            >
              Mark as Complete
            </button>
          </div>
        )}
      </div>
    );
  }
  
  return null;
};
