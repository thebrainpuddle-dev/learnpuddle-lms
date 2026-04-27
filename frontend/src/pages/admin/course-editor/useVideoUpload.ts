// course-editor/useVideoUpload.ts
//
// Sub-hook: video upload state machine and server-side polling.
// Handles the full lifecycle: idle → uploading → processing → done/failed.

import { useState, useRef, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { adminService } from '../../../services/adminService';
import type { UploadPhase } from './types';

export interface UseVideoUploadParams {
  courseId: string | undefined;
  toast: {
    success: (title: string, message: string) => void;
    error: (title: string, message: string) => void;
  };
}

export function useVideoUpload({ courseId, toast }: UseVideoUploadParams) {
  const queryClient = useQueryClient();

  const [uploadPhase, setUploadPhase] = useState<UploadPhase>('idle');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [pollingContentId, setPollingContentId] = useState<string | null>(null);
  const [pollingModuleId, setPollingModuleId] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setPollingContentId(null);
  }, []);

  const pollErrorCount = useRef(0);

  useEffect(() => {
    if (!pollingContentId || !pollingModuleId || !courseId) return;
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    pollErrorCount.current = 0;

    pollingRef.current = setInterval(async () => {
      try {
        const data = await adminService.getVideoStatus(
          courseId,
          pollingModuleId,
          pollingContentId,
        );
        pollErrorCount.current = 0;
        const st = data.video_asset?.status;
        if (st === 'READY') {
          stopPolling();
          setUploadPhase('done');
          toast.success(
            'Video ready!',
            'HLS streaming, transcript, and assignments have been created.',
          );
          queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
          setTimeout(() => setUploadPhase('idle'), 3000);
        } else if (st === 'FAILED') {
          stopPolling();
          setUploadPhase('idle');
          toast.error(
            'Video processing failed',
            data.video_asset?.error_message || 'Unknown error',
          );
          queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
        }
      } catch {
        pollErrorCount.current += 1;
        if (pollErrorCount.current >= 5) {
          stopPolling();
          setUploadPhase('idle');
          toast.error(
            'Status check failed',
            'Could not reach the server. Please refresh the page.',
          );
        }
      }
    }, 5000);

    return () => stopPolling();
  }, [pollingContentId, pollingModuleId, courseId, stopPolling, toast, queryClient]);

  /** Start polling an in-progress video upload. */
  const startPolling = useCallback(
    (contentId: string, moduleId: string) => {
      setPollingContentId(contentId);
      setPollingModuleId(moduleId);
    },
    [],
  );

  /** Called when the module that was being polled is deleted. */
  const handlePollingModuleDeleted = useCallback(
    (moduleId: string) => {
      if (pollingModuleId === moduleId) {
        stopPolling();
        setPollingContentId(null);
        setPollingModuleId(null);
      }
      setUploadPhase('idle');
      setUploadProgress(0);
    },
    [pollingModuleId, stopPolling],
  );

  return {
    uploadPhase,
    setUploadPhase,
    uploadProgress,
    setUploadProgress,
    pollingContentId,
    setPollingContentId,
    pollingModuleId,
    setPollingModuleId,
    stopPolling,
    startPolling,
    handlePollingModuleDeleted,
  };
}
