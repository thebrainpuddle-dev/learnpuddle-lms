// src/hooks/useKeyboardShortcuts.ts
//
// Keyboard shortcuts for the MAIC stage, matching OpenMAIC's key bindings.
// Only active when enabled and focus is not inside an input/textarea.

import { useEffect, useCallback } from 'react';

interface UseKeyboardShortcutsOptions {
  onPlayPause: () => void;
  onNextScene: () => void;
  onPrevScene: () => void;
  onToggleFullscreen: () => void;
  onToggleChat: () => void;
  onToggleWhiteboard: () => void;
  onVolumeUp: () => void;
  onVolumeDown: () => void;
  onMute: () => void;
  onToggleSceneSidebar?: () => void;
  onToggleDiscussion?: () => void;
  onToggleNotes?: () => void;
  enabled?: boolean;
}

function isInputFocused(): boolean {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
  if ((el as HTMLElement).isContentEditable) return true;
  return false;
}

export function useKeyboardShortcuts(opts: UseKeyboardShortcutsOptions): void {
  const {
    onPlayPause,
    onNextScene,
    onPrevScene,
    onToggleFullscreen,
    onToggleChat,
    onToggleWhiteboard,
    onVolumeUp,
    onVolumeDown,
    onMute,
    onToggleSceneSidebar,
    onToggleDiscussion,
    onToggleNotes,
    enabled = true,
  } = opts;

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return;
      if (isInputFocused()) return;

      // Avoid conflicts with browser default behaviors when modifiers are held
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      switch (e.key) {
        case ' ':
          e.preventDefault();
          onPlayPause();
          break;

        case 'ArrowRight':
          e.preventDefault();
          onNextScene();
          break;

        case 'ArrowLeft':
          e.preventDefault();
          onPrevScene();
          break;

        case 'ArrowUp':
          e.preventDefault();
          onVolumeUp();
          break;

        case 'ArrowDown':
          e.preventDefault();
          onVolumeDown();
          break;

        case 'F11':
          e.preventDefault();
          onToggleFullscreen();
          break;

        case 'Escape':
          // Only exit fullscreen if currently in fullscreen
          if (document.fullscreenElement) {
            e.preventDefault();
            onToggleFullscreen();
          }
          break;

        case 'c':
        case 'C':
          e.preventDefault();
          onToggleChat();
          break;

        case 'w':
        case 'W':
          e.preventDefault();
          onToggleWhiteboard();
          break;

        case 'm':
        case 'M':
          e.preventDefault();
          onMute();
          break;

        case 's':
        case 'S':
          e.preventDefault();
          onToggleSceneSidebar?.();
          break;

        case 't':
        case 'T':
          e.preventDefault();
          onToggleDiscussion?.();
          break;

        case 'n':
        case 'N':
          e.preventDefault();
          onToggleNotes?.();
          break;

        default:
          break;
      }
    },
    [
      enabled,
      onPlayPause,
      onNextScene,
      onPrevScene,
      onToggleFullscreen,
      onToggleChat,
      onToggleWhiteboard,
      onVolumeUp,
      onVolumeDown,
      onMute,
      onToggleSceneSidebar,
      onToggleDiscussion,
      onToggleNotes,
    ],
  );

  useEffect(() => {
    if (!enabled) return;

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [enabled, handleKeyDown]);
}
