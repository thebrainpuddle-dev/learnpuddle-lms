import React, { useEffect, useMemo, useRef, useState } from 'react';
import Hls from 'hls.js';
import DOMPurify from 'dompurify';
import { PlayIcon, DocumentTextIcon, LinkIcon, CheckCircleIcon } from '@heroicons/react/24/solid';
import {
  ArrowRightIcon,
  ArrowTopRightOnSquareIcon,
  FlagIcon,
  HandThumbDownIcon,
  HandThumbUpIcon,
} from '@heroicons/react/24/outline';
import { teacherService } from '../../services/teacherService';
import { getAccessToken } from '../../utils/authSession';

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
  initialProgress?: number;
  isCompleted?: boolean;
  onComplete?: () => void;
  onProgressUpdate?: (seconds: number) => void;
  onNextItem?: () => void;
  nextItemLabel?: string;
}

export const ContentPlayer: React.FC<ContentPlayerProps> = ({
  content,
  initialProgress = 0,
  isCompleted = false,
  onComplete,
  onProgressUpdate,
  onNextItem,
  nextItemLabel,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [maxWatched, setMaxWatched] = useState(initialProgress);
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<null | {
    full_text: string;
    segments: Array<{ start: number; end: number; text: string }>;
  }>(null);

  const videoSrc = useMemo(() => content.hls_url || content.file_url || '', [content.hls_url, content.file_url]);

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

  useEffect(() => {
    setMaxWatched(initialProgress);
  }, [content.id, initialProgress]);

  useEffect(() => {
    if (content.content_type !== 'VIDEO') return;
    const video = videoRef.current;
    if (!video || !videoSrc) return;

    const isHls = videoSrc.endsWith('.m3u8') || videoSrc.includes('.m3u8');

    if (isHls && Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        xhrSetup: (xhr) => {
          const token = getAccessToken();
          if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        },
      });
      hls.loadSource(videoSrc);
      hls.attachMedia(video);
      return () => {
        hls.destroy();
      };
    }

    video.src = videoSrc;
  }, [content.content_type, videoSrc]);

  useEffect(() => {
    setTranscript(null);
    setTranscriptError(null);
    setTranscriptLoading(false);
  }, [content.id]);

  useEffect(() => {
    if (content.content_type !== 'VIDEO') return;
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
  }, [content.content_type, content.has_transcript, content.id, transcript, transcriptLoading]);

  const renderNextItemCta = () => {
    if (!onNextItem || !nextItemLabel) return null;
    return (
      <button
        type="button"
        onClick={onNextItem}
        className="inline-flex items-center gap-2 rounded-xl border border-blue-600 px-4 py-2 text-sm font-semibold text-blue-600 hover:bg-blue-50"
      >
        {nextItemLabel}
        <ArrowRightIcon className="h-4 w-4" />
      </button>
    );
  };

  if (content.content_type === 'VIDEO') {
    return (
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="relative aspect-video w-full bg-black">
          {videoSrc ? (
            <video
              ref={videoRef}
              className="h-full w-full"
              controls
              poster={content.thumbnail_url || undefined}
              onLoadedMetadata={(event) => {
                const video = event.currentTarget;
                if (initialProgress > 0 && video.duration > initialProgress) {
                  video.currentTime = initialProgress;
                }
              }}
              onTimeUpdate={(event) => {
                const video = event.currentTarget;
                const current = Math.floor(video.currentTime);
                setMaxWatched((prev) => Math.max(prev, current));
                onProgressUpdate?.(current);
              }}
              onSeeking={(event) => {
                const video = event.currentTarget;
                if (video.currentTime > maxWatched + 2) {
                  video.currentTime = maxWatched;
                }
              }}
              onEnded={() => onComplete?.()}
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
            <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-300">
              <PlayIcon className="mb-4 h-16 w-16 animate-pulse" />
              <p className="font-medium">Video is being processed</p>
              <p className="mt-1 text-sm">Streaming will be available shortly.</p>
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-3xl font-semibold text-slate-900">{content.title}</h2>
              <p className="mt-1 text-sm text-slate-500">
                {content.duration ? `Video • ${formatDuration(content.duration)}` : 'Video'}
              </p>
            </div>
            {isCompleted && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-3 py-1 text-sm font-semibold text-emerald-700">
                <CheckCircleIcon className="h-4 w-4" />
                Completed
              </span>
            )}
          </div>

          <div className="mt-5 border-b border-slate-200 pb-2">
            <div className="flex items-center gap-6 text-sm font-medium">
              <span className="border-b-2 border-slate-900 pb-2 text-slate-900">Transcript</span>
              <span className="pb-2 text-slate-400">Notes</span>
              <span className="pb-2 text-slate-400">Downloads</span>
            </div>
          </div>

          <div className="mt-3 max-h-64 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-4">
            {transcriptLoading ? (
              <p className="text-sm text-slate-500">Loading transcript...</p>
            ) : transcriptError ? (
              <p className="text-sm text-rose-600">{transcriptError}</p>
            ) : transcript ? (
              transcript.segments.length > 0 ? (
                <div className="space-y-2">
                  {transcript.segments.map((segment, index) => (
                    <button
                      key={index}
                      type="button"
                      className="w-full rounded-lg px-3 py-2 text-left hover:bg-white"
                      onClick={() => {
                        const video = videoRef.current;
                        if (!video) return;
                        video.currentTime = segment.start;
                        video.play().catch(() => undefined);
                      }}
                    >
                      <p className="text-xs text-slate-500">{formatTime(segment.start)}</p>
                      <p className="text-sm text-slate-800">{segment.text}</p>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="whitespace-pre-wrap text-sm text-slate-700">{transcript.full_text}</p>
              )
            ) : (
              <p className="text-sm text-slate-500">Transcript not ready yet.</p>
            )}
          </div>

          <div className="mt-4 flex items-center justify-between">
            <button type="button" className="text-sm font-semibold text-blue-600 hover:text-blue-700">
              Save note
            </button>
            {renderNextItemCta()}
          </div>
        </div>
      </section>
    );
  }

  const readingLabel = content.content_type === 'LINK' ? 'External Resource' : 'Reading';
  const readingIcon = content.content_type === 'LINK' ? (
    <LinkIcon className="h-8 w-8 text-blue-600" />
  ) : (
    <DocumentTextIcon className="h-8 w-8 text-blue-600" />
  );

  const defaultReadingText =
    content.content_type === 'LINK'
      ? 'Open this resource and complete the related task.'
      : 'Review this material and mark it complete once done.';

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="p-8">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="rounded-xl bg-blue-50 p-3">{readingIcon}</div>
            <div>
              <p className="text-sm font-semibold text-blue-600">{readingLabel}</p>
              <h2 className="text-4xl font-semibold text-slate-900">{content.title}</h2>
            </div>
          </div>
          {isCompleted && (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-3 py-1 text-sm font-semibold text-emerald-700">
              <CheckCircleIcon className="h-4 w-4" />
              Completed
            </span>
          )}
        </div>

        <div className="max-w-4xl text-lg leading-8 text-slate-700">
          {content.text_content ? (
            <div
              className="prose prose-lg max-w-none prose-slate"
              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(content.text_content) }}
            />
          ) : (
            <p>{defaultReadingText}</p>
          )}
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          {content.file_url && (
            <a
              href={content.file_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
            >
              Open resource
              <ArrowTopRightOnSquareIcon className="h-4 w-4" />
            </a>
          )}

          {!isCompleted && onComplete && (
            <button
              type="button"
              onClick={onComplete}
              className="inline-flex items-center rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
            >
              Mark as completed
            </button>
          )}
        </div>

        <div className="mt-10 border-t border-slate-200 pt-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-6 text-blue-600">
              <button type="button" className="inline-flex items-center gap-2 text-sm font-semibold">
                <HandThumbUpIcon className="h-5 w-5" />
                Like
              </button>
              <button type="button" className="inline-flex items-center gap-2 text-sm font-semibold">
                <HandThumbDownIcon className="h-5 w-5" />
                Dislike
              </button>
              <button type="button" className="inline-flex items-center gap-2 text-sm font-semibold">
                <FlagIcon className="h-5 w-5" />
                Report an issue
              </button>
            </div>

            {renderNextItemCta()}
          </div>
        </div>
      </div>
    </section>
  );
};
