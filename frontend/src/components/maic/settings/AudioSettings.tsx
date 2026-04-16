// src/components/maic/settings/AudioSettings.tsx
//
// TTS and ASR provider configuration panel for the MAIC AI Classroom.
// Wired to useMAICSettingsStore for persistent user preferences.

import React, { useState, useMemo, useCallback } from 'react';
import {
  Volume2,
  Mic,
  Eye,
  EyeOff,
  Play,
  Square,
  ChevronDown,
} from 'lucide-react';
import { cn } from '../../../lib/utils';
import { useMAICSettingsStore } from '../../../stores/maicSettingsStore';
import { useTTSPreview } from '../../../hooks/useTTSPreview';
import {
  TTS_PROVIDERS,
  ASR_PROVIDERS,
  getAllTTSProviders,
  getAllASRProviders,
  getTTSProvider,
  getASRProvider,
} from '../../../lib/audio/constants';
import type {
  TTSProviderId,
  ASRProviderId,
  BuiltInTTSProviderId,
  BuiltInASRProviderId,
} from '../../../lib/audio/types';

interface AudioSettingsProps {
  className?: string;
}

const PREVIEW_TEXT = 'Hello! This is a preview of the selected voice for your AI classroom.';

/* ------------------------------------------------------------------ */
/*  Reusable small components                                         */
/* ------------------------------------------------------------------ */

function SectionHeader({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="h-4 w-4 text-gray-500" aria-hidden="true" />
      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">{label}</h3>
    </div>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="block text-sm font-medium text-gray-700 mb-1">{children}</label>;
}

function PasswordInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [show, setShow] = useState(false);

  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm pr-10 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
      />
      <button
        type="button"
        onClick={() => setShow((v) => !v)}
        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600"
        aria-label={show ? 'Hide API key' : 'Show API key'}
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                    */
/* ------------------------------------------------------------------ */

export const AudioSettings = React.memo<AudioSettingsProps>(function AudioSettings({ className }) {
  // ── Store bindings ────────────────────────────────────────────────
  const ttsProviderId = useMAICSettingsStore((s) => s.ttsProviderId);
  const setTTSProviderId = useMAICSettingsStore((s) => s.setTTSProviderId);
  const ttsVoice = useMAICSettingsStore((s) => s.ttsVoice);
  const setTTSVoice = useMAICSettingsStore((s) => s.setTTSVoice);
  const ttsSpeed = useMAICSettingsStore((s) => s.ttsSpeed);
  const setTTSSpeed = useMAICSettingsStore((s) => s.setTTSSpeed);
  const ttsModelId = useMAICSettingsStore((s) => s.ttsModelId);
  const setTTSModelId = useMAICSettingsStore((s) => s.setTTSModelId);
  const ttsProvidersConfig = useMAICSettingsStore((s) => s.ttsProvidersConfig);
  const setTTSProvidersConfig = useMAICSettingsStore((s) => s.setTTSProvidersConfig);

  const asrProviderId = useMAICSettingsStore((s) => s.asrProviderId);
  const setASRProviderId = useMAICSettingsStore((s) => s.setASRProviderId);
  const asrLanguage = useMAICSettingsStore((s) => s.asrLanguage);
  const setASRLanguage = useMAICSettingsStore((s) => s.setASRLanguage);
  const asrProvidersConfig = useMAICSettingsStore((s) => s.asrProvidersConfig);
  const setASRProvidersConfig = useMAICSettingsStore((s) => s.setASRProvidersConfig);

  // ── TTS Preview ────────────────────────────────────────────────────
  const { previewing, startPreview, stopPreview } = useTTSPreview();

  // ── Derived data ──────────────────────────────────────────────────
  const allTTSProviders = useMemo(() => getAllTTSProviders(), []);
  const allASRProviders = useMemo(() => getAllASRProviders(), []);

  const currentTTSProvider = useMemo(
    () => getTTSProvider(ttsProviderId),
    [ttsProviderId],
  );

  const currentASRProvider = useMemo(
    () => getASRProvider(asrProviderId),
    [asrProviderId],
  );

  const speedRange = currentTTSProvider?.speedRange ?? { min: 0.25, max: 4.0, default: 1.0 };

  const ttsApiKey = ttsProvidersConfig[ttsProviderId]?.apiKey ?? '';
  const asrApiKey = asrProvidersConfig[asrProviderId]?.apiKey ?? '';

  // ── Handlers ──────────────────────────────────────────────────────

  const handleTTSProviderChange = useCallback(
    (id: string) => {
      const newId = id as TTSProviderId;
      setTTSProviderId(newId);
      // Reset voice and model to provider defaults
      const provider = getTTSProvider(newId);
      if (provider) {
        setTTSVoice(provider.voices[0]?.id ?? 'default');
        setTTSModelId(provider.defaultModelId);
        setTTSSpeed(provider.speedRange?.default ?? 1.0);
      }
    },
    [setTTSProviderId, setTTSVoice, setTTSModelId, setTTSSpeed],
  );

  const handleASRProviderChange = useCallback(
    (id: string) => {
      const newId = id as ASRProviderId;
      setASRProviderId(newId);
      const provider = getASRProvider(newId);
      if (provider) {
        setASRLanguage(provider.supportedLanguages[0] ?? 'en');
      }
    },
    [setASRProviderId, setASRLanguage],
  );

  const handleTTSApiKeyChange = useCallback(
    (value: string) => {
      setTTSProvidersConfig({
        ...ttsProvidersConfig,
        [ttsProviderId]: { ...ttsProvidersConfig[ttsProviderId], apiKey: value },
      });
    },
    [ttsProviderId, ttsProvidersConfig, setTTSProvidersConfig],
  );

  const handleASRApiKeyChange = useCallback(
    (value: string) => {
      setASRProvidersConfig({
        ...asrProvidersConfig,
        [asrProviderId]: { ...asrProvidersConfig[asrProviderId], apiKey: value },
      });
    },
    [asrProviderId, asrProvidersConfig, setASRProvidersConfig],
  );

  const handleTestVoice = useCallback(async () => {
    if (previewing) {
      stopPreview();
      return;
    }
    try {
      await startPreview({
        text: PREVIEW_TEXT,
        providerId: ttsProviderId,
        modelId: ttsModelId || undefined,
        voice: ttsVoice,
        speed: ttsSpeed,
        apiKey: ttsApiKey || undefined,
      });
    } catch {
      // Error is handled by the preview hook; ignore here.
    }
  }, [previewing, stopPreview, startPreview, ttsProviderId, ttsModelId, ttsVoice, ttsSpeed, ttsApiKey]);

  // ── Render ────────────────────────────────────────────────────────

  return (
    <div className={cn('space-y-8', className)}>
      {/* ── TTS Section ──────────────────────────────────────────────── */}
      <section>
        <SectionHeader icon={Volume2} label="Text-to-Speech" />

        <div className="space-y-4">
          {/* Provider selector */}
          <div>
            <FieldLabel>Provider</FieldLabel>
            <div className="relative">
              <select
                value={ttsProviderId}
                onChange={(e) => handleTTSProviderChange(e.target.value)}
                className="w-full appearance-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm pr-8 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                {allTTSProviders.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            </div>
          </div>

          {/* Voice selector */}
          {currentTTSProvider && currentTTSProvider.voices.length > 0 && (
            <div>
              <FieldLabel>Voice</FieldLabel>
              <div className="relative">
                <select
                  value={ttsVoice}
                  onChange={(e) => setTTSVoice(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm pr-8 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                >
                  {currentTTSProvider.voices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                      {v.gender ? ` (${v.gender})` : ''}
                      {v.description ? ` - ${v.description}` : ''}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              </div>
            </div>
          )}

          {/* Model selector (only for providers with models) */}
          {currentTTSProvider && currentTTSProvider.models.length > 0 && (
            <div>
              <FieldLabel>Model</FieldLabel>
              <div className="relative">
                <select
                  value={ttsModelId}
                  onChange={(e) => setTTSModelId(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm pr-8 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                >
                  {currentTTSProvider.models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              </div>
            </div>
          )}

          {/* Speed slider */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <FieldLabel>Speed</FieldLabel>
              <span className="text-xs text-gray-500 tabular-nums">{ttsSpeed.toFixed(2)}x</span>
            </div>
            <input
              type="range"
              min={speedRange.min}
              max={speedRange.max}
              step={0.05}
              value={ttsSpeed}
              onChange={(e) => setTTSSpeed(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-primary-600"
              aria-label="TTS playback speed"
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
              <span>{speedRange.min}x</span>
              <span>{speedRange.max}x</span>
            </div>
          </div>

          {/* API key (only if provider requires it) */}
          {currentTTSProvider?.requiresApiKey && (
            <div>
              <FieldLabel>API Key</FieldLabel>
              <PasswordInput
                value={ttsApiKey}
                onChange={handleTTSApiKeyChange}
                placeholder={`Enter ${currentTTSProvider.name} API key`}
              />
              <p className="text-xs text-gray-400 mt-1">
                Your API key is stored locally in the browser and never sent to LearnPuddle servers.
              </p>
            </div>
          )}

          {/* Test Voice button */}
          <div>
            <button
              type="button"
              onClick={handleTestVoice}
              className={cn(
                'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-primary-500',
                previewing
                  ? 'bg-red-50 text-red-600 hover:bg-red-100'
                  : 'bg-primary-50 text-primary-600 hover:bg-primary-100',
              )}
            >
              {previewing ? (
                <>
                  <Square className="h-3.5 w-3.5" />
                  Stop Preview
                </>
              ) : (
                <>
                  <Play className="h-3.5 w-3.5" />
                  Test Voice
                </>
              )}
            </button>
          </div>
        </div>
      </section>

      {/* ── ASR Section ──────────────────────────────────────────────── */}
      <section>
        <SectionHeader icon={Mic} label="Speech Recognition" />

        <div className="space-y-4">
          {/* Provider selector */}
          <div>
            <FieldLabel>Provider</FieldLabel>
            <div className="relative">
              <select
                value={asrProviderId}
                onChange={(e) => handleASRProviderChange(e.target.value)}
                className="w-full appearance-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm pr-8 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                {allASRProviders.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            </div>
          </div>

          {/* Language selector */}
          {currentASRProvider && currentASRProvider.supportedLanguages.length > 0 && (
            <div>
              <FieldLabel>Language</FieldLabel>
              <div className="relative">
                <select
                  value={asrLanguage}
                  onChange={(e) => setASRLanguage(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm pr-8 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                >
                  {currentASRProvider.supportedLanguages.map((lang) => (
                    <option key={lang} value={lang}>
                      {lang}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              </div>
            </div>
          )}

          {/* API key (only if provider requires it) */}
          {currentASRProvider?.requiresApiKey && (
            <div>
              <FieldLabel>API Key</FieldLabel>
              <PasswordInput
                value={asrApiKey}
                onChange={handleASRApiKeyChange}
                placeholder={`Enter ${currentASRProvider.name} API key`}
              />
              <p className="text-xs text-gray-400 mt-1">
                Your API key is stored locally in the browser and never sent to LearnPuddle servers.
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
});
