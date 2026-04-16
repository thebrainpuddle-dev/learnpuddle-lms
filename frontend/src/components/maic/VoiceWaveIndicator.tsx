// src/components/maic/VoiceWaveIndicator.tsx
//
// Animated voice wave bars showing audio activity. Used alongside speaking
// agent avatars and during microphone recording in roundtable discussions.

import React from 'react';
import { cn } from '../../lib/utils';

interface VoiceWaveIndicatorProps {
  active: boolean;
  color?: string;
  barCount?: number;
  size?: 'sm' | 'md' | 'lg';
}

const SIZE_CONFIG = {
  sm: { height: 12, barWidth: 2, gap: 1, minHeight: 2, maxHeight: 10 },
  md: { height: 20, barWidth: 3, gap: 2, minHeight: 3, maxHeight: 16 },
  lg: { height: 28, barWidth: 3, gap: 2, minHeight: 4, maxHeight: 24 },
} as const;

export const VoiceWaveIndicator = React.memo<VoiceWaveIndicatorProps>(
  function VoiceWaveIndicator({ active, color = '#6366f1', barCount = 5, size = 'md' }) {
    const config = SIZE_CONFIG[size];

    return (
      <>
        <div
          className={cn('flex items-center justify-center')}
          style={{ height: config.height, gap: config.gap }}
          role="presentation"
          aria-label={active ? 'Audio active' : 'Audio inactive'}
        >
          {Array.from({ length: barCount }, (_, i) => (
            <span
              key={i}
              className="rounded-full"
              style={{
                width: config.barWidth,
                height: active ? undefined : config.minHeight,
                minHeight: config.minHeight,
                backgroundColor: color,
                animation: active
                  ? `voiceWaveBar 0.6s ease-in-out infinite`
                  : 'none',
                animationDelay: active ? `${i * 0.1}s` : undefined,
                transition: 'height 0.2s ease',
              }}
            />
          ))}
        </div>

        {/* Inject keyframes — only rendered when active to avoid duplicate styles */}
        {active && (
          <style>{`
            @keyframes voiceWaveBar {
              0%, 100% { height: ${config.minHeight}px; }
              50% { height: ${config.maxHeight}px; }
            }
          `}</style>
        )}
      </>
    );
  },
);
