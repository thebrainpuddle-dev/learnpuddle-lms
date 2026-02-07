// src/components/teacher/ContentPlayer.tsx

import React, { useEffect, useMemo, useRef, useState } from 'react';
import Hls from 'hls.js';
import DOMPurify from 'dompurify';
import {
  PlayIcon,
  DocumentTextIcon,
  LinkIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/solid';
import { ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline';
import { teacherService } from '../../services/teacherService';

interface ContentPlayerProps {
  content: {
    id: string;
    title: string;
    content_type: 'VIDEO' | 'DOCUMENT' | 'LINK' | 'TEXT';
    file_url?: string;
    hls_url?: string;
    thumbnail_url?: string;
    text_content?: string;
    duration?: number;
    has_transcript?: boolean;
    transcript_vtt_url?: string;
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
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const [activeTab, setActiveTab] = useState<'video' | 'transcript'>('video');
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<null | {
    full_text: string;
    segments: Array<{ start: number; end: number; text: string }>;
  }>(null);

  const videoSrc = useMemo(() => {
    return content.hls_url || content.file_url || '';
  }, [content.hls_url, content.file_url]);
  
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Attach HLS source when needed
  useEffect(() => {
    if (content.content_type !== 'VIDEO') return;
    const video = videoRef.current;
    if (!video) return;
    if (!videoSrc) return;

    // Native HLS (Safari) or MP4 fallback
    if (!videoSrc.endsWith('.m3u8') || video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = videoSrc;
      return;
    }

    if (!Hls.isSupported()) {
      video.src = videoSrc;
      return;
    }

    const hls = new Hls({ enableWorker: true });
    hls.loadSource(videoSrc);
    hls.attachMedia(video);
    return () => {
      hls.destroy();
    };
  }, [content.content_type, content.id, videoSrc]);

  // Reset transcript state when content changes
  useEffect(() => {
    setTranscript(null);
    setTranscriptError(null);
    setTranscriptLoading(false);
    setActiveTab('video');
  }, [content.id]);

  useEffect(() => {
    if (content.content_type !== 'VIDEO') return;
    if (activeTab !== 'transcript') return;
    if (!content.has_transcript) return;
    if (transcript || transcriptLoading) return;

    setTranscriptLoading(true);
    setTranscriptError(null);
    teacherService
      .getVideoTranscript(content.id)
      .then((data) => {
        setTranscript({ full_text: data.full_text, segments: data.segments || [] });
      })
      .catch(() => setTranscriptError('Could not load transcript.'))
      .finally(() => setTranscriptLoading(false));
  }, [activeTab, content.content_type, content.has_transcript, content.id, transcript, transcriptLoading]);
  
  // Video player
  if (content.content_type === 'VIDEO') {
    return (
      <div className="bg-slate-900 rounded-xl overflow-hidden">
        {/* Tabs */}
        <div className="flex border-b border-slate-800">
          <button
            onClick={() => setActiveTab('video')}
            className={`px-4 py-2 text-sm font-medium ${
              activeTab === 'video' ? 'text-white bg-slate-800' : 'text-slate-300 hover:text-white'
            }`}
          >
            Video
          </button>
          <button
            onClick={() => setActiveTab('transcript')}
            disabled={!content.has_transcript}
            className={`px-4 py-2 text-sm font-medium ${
              !content.has_transcript
                ? 'text-slate-600 cursor-not-allowed'
                : activeTab === 'transcript'
                ? 'text-white bg-slate-800'
                : 'text-slate-300 hover:text-white'
            }`}
            title={content.has_transcript ? 'View transcript' : 'Transcript not ready yet'}
          >
            Transcript
          </button>
        </div>

        {/* Video container — always mounted so videoRef stays valid for transcript seek */}
        <div className={`relative aspect-video bg-black ${activeTab !== 'video' ? 'hidden' : ''}`}>
          {videoSrc ? (
            <video
              ref={videoRef}
              className="w-full h-full"
              controls
              poster={content.thumbnail_url || undefined}
              onTimeUpdate={(e) => {
                const video = e.currentTarget;
                setCurrentTime(Math.floor(video.currentTime));
                onProgressUpdate?.(Math.floor(video.currentTime));
              }}
              onEnded={() => onComplete?.()}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
            >
              {content.transcript_vtt_url && (
                <track
                  kind="captions"
                  src={content.transcript_vtt_url}
                  srcLang="en"
                  label="Captions"
                  default
                />
              )}
            </video>
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400">
              <div className="animate-pulse">
                <PlayIcon className="h-16 w-16 mb-4 mx-auto" />
              </div>
              <p className="font-medium">Video is being processed</p>
              <p className="text-sm mt-1">HLS streaming will be available shortly. Please check back in a few minutes.</p>
            </div>
          )}
        </div>

        {/* Transcript panel */}
        {activeTab === 'transcript' && (
          <div className="bg-slate-950 max-h-[28rem] overflow-y-auto p-4">
            {transcriptLoading ? (
              <p className="text-slate-300 text-sm">Loading transcript...</p>
            ) : transcriptError ? (
              <p className="text-red-300 text-sm">{transcriptError}</p>
            ) : transcript ? (
              <div className="space-y-3">
                {transcript.segments.length > 0 ? (
                  transcript.segments.map((seg, idx) => (
                    <button
                      key={idx}
                      className="w-full text-left rounded-lg p-3 hover:bg-slate-900 transition-colors"
                      onClick={() => {
                        const v = videoRef.current;
                        if (v) {
                          v.currentTime = seg.start;
                          v.play().catch(() => undefined);
                          setActiveTab('video');
                        }
                      }}
                    >
                      <div className="text-xs text-slate-400 mb-1">
                        {formatTime(seg.start)} - {formatTime(seg.end)}
                      </div>
                      <div className="text-sm text-slate-100">{seg.text}</div>
                    </button>
                  ))
                ) : (
                  <p className="text-slate-300 text-sm whitespace-pre-wrap">{transcript.full_text}</p>
                )}
              </div>
            ) : (
              <p className="text-slate-300 text-sm">Transcript not available.</p>
            )}
          </div>
        )}
        
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
          <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(content.text_content || '') }} />
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
