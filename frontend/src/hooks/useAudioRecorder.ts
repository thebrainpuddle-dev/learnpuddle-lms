// hooks/useAudioRecorder.ts — Audio recording with MediaRecorder and Web Speech recognition
//
// Used in roundtable discussions for student voice input. Records audio via
// getUserMedia and provides real-time transcription via the Web Speech API.

import { useState, useRef, useCallback, useEffect } from 'react';

// ─── Types ───────────────────────────────────────────────────────────────────

interface UseAudioRecorderOptions {
  onTranscription?: (text: string) => void;
  onError?: (error: string) => void;
  language?: string; // default: 'en-US'
}

interface UseAudioRecorderReturn {
  isRecording: boolean;
  isProcessing: boolean;
  recordingTime: number; // seconds
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<string | null>; // returns transcription
  cancelRecording: () => void;
}

// ─── Web Speech API types (not in standard lib) ─────────────────────────────

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognitionInstance;
    webkitSpeechRecognition: new () => SpeechRecognitionInstance;
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getSpeechRecognitionConstructor(): (new () => SpeechRecognitionInstance) | null {
  if (typeof window === 'undefined') return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function formatPermissionError(err: unknown): string {
  if (err instanceof DOMException) {
    switch (err.name) {
      case 'NotAllowedError':
        return 'Microphone access denied. Please allow microphone permissions in your browser settings.';
      case 'NotFoundError':
        return 'No microphone found. Please connect a microphone and try again.';
      case 'NotReadableError':
        return 'Microphone is in use by another application.';
      default:
        return `Microphone error: ${err.message}`;
    }
  }
  return err instanceof Error ? err.message : 'Failed to access microphone.';
}

// ─── Hook ────────────────────────────────────────────────────────────────────

export function useAudioRecorder(options: UseAudioRecorderOptions = {}): UseAudioRecorderReturn {
  const { onTranscription, onError, language = 'en-US' } = options;

  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const transcriptRef = useRef<string>('');
  const resolveStopRef = useRef<((text: string | null) => void) | null>(null);

  // ─── Cleanup helpers ────────────────────────────────────────────────

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const releaseMediaStream = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  const stopRecognition = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {
        // Ignore — recognition may already be stopped
      }
      recognitionRef.current = null;
    }
  }, []);

  const cleanupAll = useCallback(() => {
    stopTimer();
    releaseMediaStream();
    stopRecognition();

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // Already stopped
      }
    }
    mediaRecorderRef.current = null;
  }, [stopTimer, releaseMediaStream, stopRecognition]);

  // ─── Start recording ───────────────────────────────────────────────

  const startRecording = useCallback(async () => {
    if (isRecording) return;

    // Reset state
    transcriptRef.current = '';
    setRecordingTime(0);
    setIsProcessing(false);

    // Acquire microphone
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      const message = formatPermissionError(err);
      onError?.(message);
      return;
    }

    mediaStreamRef.current = stream;

    // Set up MediaRecorder (for potential future use with audio blobs)
    try {
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.start();
    } catch (err) {
      releaseMediaStream();
      onError?.('Failed to start audio recording.');
      return;
    }

    // Set up Web Speech recognition
    const SpeechRecognitionCtor = getSpeechRecognitionConstructor();
    if (SpeechRecognitionCtor) {
      const recognition = new SpeechRecognitionCtor();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = language;

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) {
            finalTranscript += result[0].transcript;
          } else {
            interimTranscript += result[0].transcript;
          }
        }

        if (finalTranscript) {
          transcriptRef.current += (transcriptRef.current ? ' ' : '') + finalTranscript.trim();
        }

        // Report interim results for real-time feedback
        const currentText = transcriptRef.current + (interimTranscript ? ' ' + interimTranscript : '');
        if (currentText.trim()) {
          onTranscription?.(currentText.trim());
        }
      };

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        // 'no-speech' and 'aborted' are non-critical
        if (event.error !== 'no-speech' && event.error !== 'aborted') {
          onError?.(`Speech recognition error: ${event.error}`);
        }
      };

      recognition.onend = () => {
        // If still recording, recognition ended unexpectedly — restart it
        if (isRecording && recognitionRef.current) {
          try {
            recognition.start();
          } catch {
            // Ignore — may already be starting
          }
        }
      };

      try {
        recognition.start();
      } catch {
        // Speech recognition not available — continue without it
      }
      recognitionRef.current = recognition;
    }

    // Start recording timer (1s interval)
    timerRef.current = setInterval(() => {
      setRecordingTime((prev) => prev + 1);
    }, 1000);

    setIsRecording(true);
  }, [isRecording, language, onError, onTranscription, releaseMediaStream]);

  // ─── Stop recording ────────────────────────────────────────────────

  const stopRecording = useCallback(async (): Promise<string | null> => {
    if (!isRecording) return null;

    setIsRecording(false);
    setIsProcessing(true);
    stopTimer();

    // Stop speech recognition gracefully to capture final results
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // Already stopped
      }
    }

    // Wait briefly for final recognition results
    const transcript = await new Promise<string | null>((resolve) => {
      resolveStopRef.current = resolve;

      // Give speech recognition a moment to finalize
      setTimeout(() => {
        const text = transcriptRef.current.trim() || null;
        resolveStopRef.current = null;
        resolve(text);
      }, 500);
    });

    // Stop MediaRecorder and release stream
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // Already stopped
      }
    }
    mediaRecorderRef.current = null;

    releaseMediaStream();
    stopRecognition();

    setIsProcessing(false);

    if (transcript) {
      onTranscription?.(transcript);
    }

    return transcript;
  }, [isRecording, stopTimer, releaseMediaStream, stopRecognition, onTranscription]);

  // ─── Cancel recording ──────────────────────────────────────────────

  const cancelRecording = useCallback(() => {
    setIsRecording(false);
    setIsProcessing(false);
    setRecordingTime(0);
    transcriptRef.current = '';
    cleanupAll();
  }, [cleanupAll]);

  // ─── Cleanup on unmount ────────────────────────────────────────────

  useEffect(() => {
    return () => {
      cleanupAll();
    };
  }, [cleanupAll]);

  return {
    isRecording,
    isProcessing,
    recordingTime,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}
