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
  onToggleWhiteboard?: () => void;
  onVolumeUp: () => void;
  onVolumeDown: () => void;
  onMute: () => void;
  onToggleSceneSidebar?: () => void;
  onToggleDiscussion?: () => void;
  onToggleNotes?: () => void;
  /** Sprint 4 · B.13 — show the keyboard shortcut help overlay (bound to ?). */
  onShowHelp?: () => void;
  /** Toggle Document Picture-in-Picture (bound to 'P'). */
  onTogglePiP?: () => void;
  enabled?: boolean;
}

/** Display list of shortcuts, shared between the hook and the help
 *  overlay. Keeping the key/label pairs in one place means the help
 *  modal can't drift out of sync with the handler. */
export const KEYBOARD_SHORTCUTS: { keys: string; label: string }[] = [
  { keys: 'Space', label: 'Play / Pause' },
  { keys: '→', label: 'Next scene' },
  { keys: '←', label: 'Previous scene' },
  { keys: '↑ / ↓', label: 'Volume up / down' },
  { keys: 'M', label: 'Mute / unmute' },
  { keys: 'C', label: 'Toggle chat panel' },
  { keys: 'W', label: 'Toggle whiteboard' },
  { keys: 'S', label: 'Toggle scene sidebar' },
  { keys: 'T', label: 'Toggle discussion' },
  { keys: 'N', label: 'Toggle notes' },
  { keys: 'F11 / Esc', label: 'Toggle fullscreen' },
  { keys: 'P', label: 'Toggle floating player (PiP)' },
  { keys: '?', label: 'Show this help' },
];

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
    onShowHelp,
    onTogglePiP,
    enabled = true,
  } = opts;

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return;
      if (isInputFocused()) return;

      // Avoid conflicts with browser default behaviors when modifiers are held
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      // Sprint 4 · B.13 — shift+/ (? on US layouts) opens the shortcut
      // help overlay. Handled before the switch so a layout that reports
      // key="?" vs code="Slash" still works.
      if (e.key === '?' && onShowHelp) {
        e.preventDefault();
        onShowHelp();
        return;
      }

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
          if (onToggleWhiteboard) {
            e.preventDefault();
            onToggleWhiteboard();
          }
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

        case 'p':
        case 'P':
          if (onTogglePiP) {
            e.preventDefault();
            onTogglePiP();
          }
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
      onShowHelp,
      onTogglePiP,
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
