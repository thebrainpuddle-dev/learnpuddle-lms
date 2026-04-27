// src/hooks/useDocumentPiP.ts
//
// Document Picture-in-Picture support for the MAIC Classroom stage.
//
// The Document PiP API (Chrome / Edge 116+) lets the page pop an arbitrary
// DOM tree into a dedicated always-on-top browser window. Unlike the
// `HTMLVideoElement.requestPictureInPicture` API (which only accepts a
// <video> element), Document PiP can host the whole classroom stage —
// scene renderer, overlays, speech bubble, agent strip — and keeps the
// React tree (and audio) alive while the user works in another tab.
//
// Approach:
//   1. `open(stageRef)` calls `window.documentPictureInPicture.requestWindow`.
//   2. We remember the original parent of the stage DOM node and its next
//      sibling so we can put it back when the PiP window closes.
//   3. We move the stage node into the PiP window's <body>. Because the
//      React tree was rendered by React DOM and its fibers don't care
//      which document a DOM node lives in, the component stays mounted
//      and keeps running. Audio elements created with `new Audio()` are
//      document-agnostic so playback is uninterrupted.
//   4. We clone every <link rel="stylesheet"> and <style> tag from the
//      main document into the PiP document so Tailwind + custom CSS
//      apply. New stylesheets added later aren't synchronised — PiP is
//      expected to be a short-lived window so this is acceptable.
//   5. When the `pagehide` event fires on the PiP window (user hits the
//      close button or the tab tears down) we portal the stage back to
//      its original position.
//
// Feature detection:
//   - `isSupported` is true only when `window.documentPictureInPicture`
//     exists. We intentionally do NOT expose video-element PiP here —
//     callers handle that fallback themselves with a "video only" hint.
//   - Mobile Chromium does not ship Document PiP; `documentPictureInPicture`
//     is simply undefined there, so `isSupported` is false and consumers
//     can hide the button.

import { useCallback, useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';

// Minimal shape of the Document Picture-in-Picture API. Typescript's DOM
// lib doesn't ship types for it yet (Chrome-only as of mid-2026) so we
// declare the bits we touch locally.
interface DocumentPictureInPictureWindow extends Window {
  addEventListener(type: 'pagehide', listener: (ev: Event) => void): void;
  removeEventListener(type: 'pagehide', listener: (ev: Event) => void): void;
}

interface DocumentPictureInPictureRequest {
  width?: number;
  height?: number;
  disallowReturnToOpener?: boolean;
  preferInitialWindowPlacement?: boolean;
}

interface DocumentPictureInPictureAPI {
  requestWindow: (
    options?: DocumentPictureInPictureRequest,
  ) => Promise<DocumentPictureInPictureWindow>;
  window?: DocumentPictureInPictureWindow | null;
}

type WindowWithDocPiP = Window & {
  documentPictureInPicture?: DocumentPictureInPictureAPI;
};

export interface UseDocumentPiPReturn {
  isSupported: boolean;
  isOpen: boolean;
  open: (stageRef: RefObject<HTMLDivElement | null>) => Promise<void>;
  close: () => void;
}

/** Copy stylesheets from main document into the PiP window. */
function cloneStyles(srcDoc: Document, pipWin: Window): void {
  const targetDoc = pipWin.document;
  const sources = Array.from(
    srcDoc.querySelectorAll<HTMLLinkElement | HTMLStyleElement>(
      'link[rel="stylesheet"], style',
    ),
  );
  for (const node of sources) {
    if (node instanceof HTMLLinkElement) {
      const link = targetDoc.createElement('link');
      link.rel = 'stylesheet';
      link.href = node.href;
      if (node.media) link.media = node.media;
      targetDoc.head.appendChild(link);
    } else if (node instanceof HTMLStyleElement) {
      const style = targetDoc.createElement('style');
      style.textContent = node.textContent;
      targetDoc.head.appendChild(style);
    }
  }

  // Try to copy constructed stylesheets too (Tailwind via some tooling
  // uses them). Silently skip if the browser can't serialise them.
  try {
    const adopted = (srcDoc as Document & {
      adoptedStyleSheets?: readonly CSSStyleSheet[];
    }).adoptedStyleSheets;
    if (adopted && adopted.length > 0) {
      (targetDoc as Document & {
        adoptedStyleSheets?: readonly CSSStyleSheet[];
      }).adoptedStyleSheets = adopted;
    }
  } catch {
    /* ignore — cross-document adoption may throw on older builds */
  }
}

function detectSupport(): boolean {
  if (typeof window === 'undefined') return false;
  return typeof (window as WindowWithDocPiP).documentPictureInPicture !== 'undefined';
}

export function useDocumentPiP(): UseDocumentPiPReturn {
  const [isSupported] = useState<boolean>(detectSupport);
  const [isOpen, setIsOpen] = useState<boolean>(false);

  // Snapshot of where the stage lives in the main document so we can
  // restore it when the PiP window closes.
  const placeholderRef = useRef<HTMLDivElement | null>(null);
  const pipWindowRef = useRef<DocumentPictureInPictureWindow | null>(null);
  const stageNodeRef = useRef<HTMLDivElement | null>(null);

  const restoreStage = useCallback(() => {
    const stage = stageNodeRef.current;
    const placeholder = placeholderRef.current;
    if (stage && placeholder && placeholder.parentNode) {
      placeholder.parentNode.replaceChild(stage, placeholder);
    }
    placeholderRef.current = null;
    stageNodeRef.current = null;
    pipWindowRef.current = null;
    setIsOpen(false);
  }, []);

  const open = useCallback(
    async (stageRef: RefObject<HTMLDivElement | null>) => {
      if (!isSupported) {
        throw new Error('Document Picture-in-Picture is not supported');
      }
      const stage = stageRef.current;
      if (!stage) {
        throw new Error('Stage ref is not attached');
      }
      if (pipWindowRef.current) {
        // Already open — focus existing.
        pipWindowRef.current.focus?.();
        return;
      }

      const api = (window as WindowWithDocPiP).documentPictureInPicture!;
      const pipWin = await api.requestWindow({
        width: Math.max(480, Math.round(stage.clientWidth * 0.6)),
        height: Math.max(270, Math.round(stage.clientHeight * 0.6)),
      });

      // Copy stylesheets so Tailwind utilities work in the PiP window.
      cloneStyles(document, pipWin);

      // Inherit the <html> class list so dark mode + theming propagate.
      try {
        pipWin.document.documentElement.className = document.documentElement.className;
        pipWin.document.body.className = document.body.className;
      } catch {
        /* ignore assignment errors on exotic documents */
      }

      // Set up a placeholder that preserves the stage's position in the
      // main DOM so we can swap it back later.
      const placeholder = document.createElement('div');
      placeholder.setAttribute('data-pip-placeholder', 'true');
      placeholder.style.width = '100%';
      placeholder.style.height = '100%';
      placeholder.style.display = 'flex';
      placeholder.style.alignItems = 'center';
      placeholder.style.justifyContent = 'center';
      placeholder.style.background = '#111827';
      placeholder.style.color = '#9ca3af';
      placeholder.style.fontSize = '13px';
      placeholder.textContent = 'Playing in floating window — close it to resume here.';

      stage.parentNode?.replaceChild(placeholder, stage);
      pipWin.document.body.style.margin = '0';
      pipWin.document.body.style.background = '#111827';
      pipWin.document.body.appendChild(stage);

      placeholderRef.current = placeholder;
      stageNodeRef.current = stage;
      pipWindowRef.current = pipWin;
      setIsOpen(true);

      const onClose = () => {
        restoreStage();
      };
      pipWin.addEventListener('pagehide', onClose);
    },
    [isSupported, restoreStage],
  );

  const close = useCallback(() => {
    const pipWin = pipWindowRef.current;
    if (!pipWin) return;
    try {
      pipWin.close();
    } catch {
      /* ignore */
    }
    // pagehide will fire → restoreStage. Guard in case it doesn't:
    setTimeout(() => {
      if (pipWindowRef.current === pipWin) {
        restoreStage();
      }
    }, 100);
  }, [restoreStage]);

  // Clean up on unmount: if the host component unmounts while PiP is
  // open, close the window so we don't leak a detached DOM tree.
  useEffect(() => {
    return () => {
      const pipWin = pipWindowRef.current;
      if (pipWin) {
        try {
          pipWin.close();
        } catch {
          /* ignore */
        }
      }
    };
  }, []);

  return { isSupported, isOpen, open, close };
}
