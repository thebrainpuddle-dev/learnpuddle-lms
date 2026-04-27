// src/hooks/useSpeechInput.ts
//
// Thin wrapper around the browser Web Speech API
// (`webkitSpeechRecognition` / `SpeechRecognition`) so the MAIC chat
// panel can offer a microphone button without pulling in a heavy
// dependency. No backend involved — the recognition happens in the
// browser (Chrome, Edge, Safari). Firefox has no implementation; we
// surface `isSupported=false` so the caller hides the button.
//
// Behavior:
//   - start(): begin continuous recognition. `interim` updates every
//     few hundred ms with the partial hypothesis; `final` fires once
//     the utterance stabilizes.
//   - stop(): end the session cleanly.
//   - cancel(): abort without emitting a final transcript.
//   - listening: true while the mic is open.
//
// Caveats callers should know:
//   - The *browser* requests mic permission on first start(); if the
//     user denies, `error` is set and listening returns to false.
//   - Language is configurable (`lang`) but defaults to en-US. Could
//     be wired to the classroom language in a follow-up.
//   - No offline fallback. If the user's browser blocks speech, we
//     report unsupported rather than silently failing.

import { useCallback, useEffect, useRef, useState } from 'react';

// The Web Speech API types aren't shipped with lib.dom in every
// TypeScript version, so keep a minimal local typing surface.
type SpeechRecognitionResult = {
  isFinal: boolean;
  0: { transcript: string };
};

type SpeechRecognitionResultList = {
  length: number;
  [index: number]: SpeechRecognitionResult;
};

interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEventLike extends Event {
  error: string;
  message?: string;
}

interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export interface UseSpeechInputOptions {
  /** BCP-47 language tag, e.g. "en-US", "hi-IN". */
  lang?: string;
  /** Called whenever the interim hypothesis updates. */
  onInterim?: (text: string) => void;
  /** Called once the utterance is final. */
  onFinal?: (text: string) => void;
}

export interface UseSpeechInputReturn {
  isSupported: boolean;
  listening: boolean;
  interim: string;
  error: string | null;
  start: () => void;
  stop: () => void;
  cancel: () => void;
}

export function useSpeechInput(opts: UseSpeechInputOptions = {}): UseSpeechInputReturn {
  const { lang = 'en-US', onInterim, onFinal } = opts;
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const cancelledRef = useRef(false);

  const Ctor = getRecognitionCtor();
  const isSupported = Ctor !== null;

  const ensure = useCallback(() => {
    if (!Ctor) return null;
    if (recRef.current) return recRef.current;
    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.onstart = () => {
      setListening(true);
      setError(null);
    };
    rec.onend = () => {
      setListening(false);
      setInterim('');
    };
    rec.onerror = (e) => {
      // "no-speech" and "aborted" are routine, not failures worth
      // surfacing to the user. Everything else lands in state.
      if (e.error === 'no-speech' || e.error === 'aborted') {
        setError(null);
      } else {
        setError(e.error || 'speech-recognition-failed');
      }
      setListening(false);
    };
    rec.onresult = (e) => {
      let finalChunk = '';
      let interimChunk = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        const text = res[0]?.transcript || '';
        if (res.isFinal) finalChunk += text;
        else interimChunk += text;
      }
      if (interimChunk) {
        setInterim(interimChunk);
        onInterim?.(interimChunk);
      }
      if (finalChunk && !cancelledRef.current) {
        setInterim('');
        onFinal?.(finalChunk.trim());
      }
    };
    recRef.current = rec;
    return rec;
  }, [Ctor, lang, onInterim, onFinal]);

  const start = useCallback(() => {
    const rec = ensure();
    if (!rec) return;
    cancelledRef.current = false;
    try {
      rec.start();
    } catch {
      // Calling start() twice throws; ignore.
    }
  }, [ensure]);

  const stop = useCallback(() => {
    const rec = recRef.current;
    if (!rec) return;
    try {
      rec.stop();
    } catch {
      /* idempotent */
    }
  }, []);

  const cancel = useCallback(() => {
    const rec = recRef.current;
    if (!rec) return;
    cancelledRef.current = true;
    try {
      rec.abort();
    } catch {
      /* idempotent */
    }
    setInterim('');
  }, []);

  useEffect(() => {
    return () => {
      const rec = recRef.current;
      if (rec) {
        try {
          rec.abort();
        } catch {
          /* unmounting — silent */
        }
      }
    };
  }, []);

  return { isSupported, listening, interim, error, start, stop, cancel };
}
