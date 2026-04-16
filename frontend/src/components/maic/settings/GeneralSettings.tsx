// src/components/maic/settings/GeneralSettings.tsx
//
// General classroom settings panel for the MAIC AI Classroom.
// Covers playback, display, and data management preferences.

import React, { useState, useEffect, useCallback } from 'react';
import {
  PlayCircle,
  Monitor,
  Database,
  AlertTriangle,
} from 'lucide-react';
import { cn } from '../../../lib/utils';
import { useMAICSettingsStore } from '../../../stores/maicSettingsStore';
import type { MAICSlideTransition } from '../../../types/maic';

interface GeneralSettingsProps {
  className?: string;
}

const PLAYBACK_SPEEDS = [
  { value: 0.5, label: '0.5x' },
  { value: 0.75, label: '0.75x' },
  { value: 1, label: '1x' },
  { value: 1.25, label: '1.25x' },
  { value: 1.5, label: '1.5x' },
  { value: 2, label: '2x' },
];

const SLIDE_TRANSITIONS: { value: MAICSlideTransition; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'fade', label: 'Fade' },
  { value: 'slideLeft', label: 'Slide Left' },
  { value: 'slideRight', label: 'Slide Right' },
  { value: 'slideUp', label: 'Slide Up' },
  { value: 'slideDown', label: 'Slide Down' },
  { value: 'zoom', label: 'Zoom' },
  { value: 'flip', label: 'Flip' },
];

const FONT_SIZES: Array<{ value: 'small' | 'medium' | 'large'; label: string }> = [
  { value: 'small', label: 'Small' },
  { value: 'medium', label: 'Medium' },
  { value: 'large', label: 'Large' },
];

/* ------------------------------------------------------------------ */
/*  Reusable toggles                                                  */
/* ------------------------------------------------------------------ */

function ToggleSwitch({
  checked,
  onChange,
  label,
  id,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  id: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <label htmlFor={id} className="text-sm font-medium text-gray-700 cursor-pointer">
        {label}
      </label>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
          checked ? 'bg-primary-600' : 'bg-gray-200',
        )}
      >
        <span
          className={cn(
            'inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform shadow-sm',
            checked ? 'translate-x-[18px]' : 'translate-x-[3px]',
          )}
        />
      </button>
    </div>
  );
}

function SectionHeader({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="h-4 w-4 text-gray-500" aria-hidden="true" />
      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">{label}</h3>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                    */
/* ------------------------------------------------------------------ */

export const GeneralSettings = React.memo<GeneralSettingsProps>(function GeneralSettings({ className }) {
  // ── Store bindings ────────────────────────────────────────────────
  const autoPlay = useMAICSettingsStore((s) => s.autoPlay);
  const setAutoPlay = useMAICSettingsStore((s) => s.setAutoPlay);
  const playbackSpeed = useMAICSettingsStore((s) => s.playbackSpeed);
  const setPlaybackSpeed = useMAICSettingsStore((s) => s.setPlaybackSpeed);
  const slideTransition = useMAICSettingsStore((s) => s.slideTransition);
  const setSlideTransition = useMAICSettingsStore((s) => s.setSlideTransition);
  const fontSize = useMAICSettingsStore((s) => s.fontSize);
  const setFontSize = useMAICSettingsStore((s) => s.setFontSize);
  const showChatPanel = useMAICSettingsStore((s) => s.showChatPanel);
  const setShowChatPanel = useMAICSettingsStore((s) => s.setShowChatPanel);
  const showWhiteboard = useMAICSettingsStore((s) => s.showWhiteboard);
  const setShowWhiteboard = useMAICSettingsStore((s) => s.setShowWhiteboard);
  const browserTTSEnabled = useMAICSettingsStore((s) => s.browserTTSEnabled);
  const setBrowserTTSEnabled = useMAICSettingsStore((s) => s.setBrowserTTSEnabled);

  // ── Cache management ──────────────────────────────────────────────
  const [cacheSize, setCacheSize] = useState<string>('Calculating...');
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearInput, setClearInput] = useState('');
  const [clearSuccess, setClearSuccess] = useState(false);

  useEffect(() => {
    if (typeof navigator !== 'undefined' && 'storage' in navigator && navigator.storage.estimate) {
      navigator.storage.estimate().then((estimate) => {
        const usageBytes = estimate.usage ?? 0;
        if (usageBytes < 1024) {
          setCacheSize(`${usageBytes} B`);
        } else if (usageBytes < 1024 * 1024) {
          setCacheSize(`${(usageBytes / 1024).toFixed(1)} KB`);
        } else {
          setCacheSize(`${(usageBytes / (1024 * 1024)).toFixed(1)} MB`);
        }
      }).catch(() => {
        setCacheSize('Unknown');
      });
    } else {
      setCacheSize('Unknown');
    }
  }, []);

  const handleClearCache = useCallback(async () => {
    if (clearInput !== 'CLEAR') return;
    try {
      // Clear IndexedDB databases
      if (typeof indexedDB !== 'undefined') {
        const dbs = await indexedDB.databases();
        for (const db of dbs) {
          if (db.name) {
            indexedDB.deleteDatabase(db.name);
          }
        }
      }
      // Clear caches
      if ('caches' in window) {
        const cacheNames = await caches.keys();
        for (const name of cacheNames) {
          await caches.delete(name);
        }
      }
      setClearSuccess(true);
      setCacheSize('0 B');
      setTimeout(() => {
        setShowClearConfirm(false);
        setClearInput('');
        setClearSuccess(false);
      }, 2000);
    } catch {
      // Silently handle errors
    }
  }, [clearInput]);

  return (
    <div className={cn('space-y-8', className)}>
      {/* ── Playback Section ─────────────────────────────────────────── */}
      <section>
        <SectionHeader icon={PlayCircle} label="Playback" />

        <div className="space-y-4">
          <ToggleSwitch
            id="auto-play-toggle"
            checked={autoPlay}
            onChange={setAutoPlay}
            label="Auto-play slides"
          />

          {/* Default playback speed */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Default Playback Speed
            </label>
            <div className="flex items-center gap-1">
              {PLAYBACK_SPEEDS.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => setPlaybackSpeed(s.value)}
                  className={cn(
                    'flex-1 text-xs py-1.5 rounded-lg transition-colors font-medium',
                    'focus:outline-none focus:ring-2 focus:ring-primary-500',
                    playbackSpeed === s.value
                      ? 'bg-primary-100 text-primary-700'
                      : 'text-gray-500 hover:bg-gray-100',
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Slide transition */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Slide Transition
            </label>
            <div className="relative">
              <select
                value={slideTransition}
                onChange={(e) => setSlideTransition(e.target.value as MAICSlideTransition)}
                className="w-full appearance-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm pr-8 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                {SLIDE_TRANSITIONS.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              <svg
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
              </svg>
            </div>
          </div>
        </div>
      </section>

      {/* ── Display Section ──────────────────────────────────────────── */}
      <section>
        <SectionHeader icon={Monitor} label="Display" />

        <div className="space-y-4">
          {/* Font size */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Font Size</label>
            <div className="flex items-center gap-1">
              {FONT_SIZES.map((f) => (
                <button
                  key={f.value}
                  type="button"
                  onClick={() => setFontSize(f.value)}
                  className={cn(
                    'flex-1 text-xs py-1.5 rounded-lg transition-colors font-medium',
                    'focus:outline-none focus:ring-2 focus:ring-primary-500',
                    fontSize === f.value
                      ? 'bg-primary-100 text-primary-700'
                      : 'text-gray-500 hover:bg-gray-100',
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          <ToggleSwitch
            id="chat-panel-toggle"
            checked={showChatPanel}
            onChange={setShowChatPanel}
            label="Show chat panel"
          />

          <ToggleSwitch
            id="whiteboard-toggle"
            checked={showWhiteboard}
            onChange={setShowWhiteboard}
            label="Show whiteboard"
          />

          <ToggleSwitch
            id="browser-tts-toggle"
            checked={browserTTSEnabled}
            onChange={setBrowserTTSEnabled}
            label="Browser TTS fallback"
          />
        </div>
      </section>

      {/* ── Data Management Section ──────────────────────────────────── */}
      <section>
        <SectionHeader icon={Database} label="Data Management" />

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600">Estimated cache size</span>
            <span className="text-sm font-medium text-gray-700 tabular-nums">{cacheSize}</span>
          </div>

          {!showClearConfirm ? (
            <button
              type="button"
              onClick={() => setShowClearConfirm(true)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium text-red-600 bg-red-50 hover:bg-red-100 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500"
            >
              Clear cached data
            </button>
          ) : (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 space-y-2">
              <div className="flex items-center gap-2 text-red-700 text-sm font-medium">
                <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                <span>This will delete all cached classroom data.</span>
              </div>
              <p className="text-xs text-red-600">
                Type <strong>CLEAR</strong> to confirm.
              </p>
              <input
                type="text"
                value={clearInput}
                onChange={(e) => setClearInput(e.target.value)}
                placeholder="Type CLEAR"
                className="w-full rounded-lg border border-red-300 px-3 py-1.5 text-sm focus:ring-2 focus:ring-red-500 focus:border-red-500"
                autoFocus
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleClearCache}
                  disabled={clearInput !== 'CLEAR'}
                  className={cn(
                    'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                    clearInput === 'CLEAR'
                      ? 'bg-red-600 text-white hover:bg-red-700'
                      : 'bg-gray-200 text-gray-400 cursor-not-allowed',
                  )}
                >
                  {clearSuccess ? 'Cleared!' : 'Confirm Clear'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowClearConfirm(false);
                    setClearInput('');
                  }}
                  className="px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
});
