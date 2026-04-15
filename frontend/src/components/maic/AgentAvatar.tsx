// src/components/maic/AgentAvatar.tsx
//
// Circular avatar for MAIC agents. Shows agent initial or image with a
// colored ring. When speaking, displays a sound wave animation (3 bars)
// below the avatar and a subtle glow effect around the circle.

import React from 'react';
import type { MAICAgent } from '../../types/maic';
import { cn } from '../../lib/utils';

interface AgentAvatarProps {
  agent: MAICAgent;
  isSpeaking?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const sizeMap = {
  sm: { container: 'h-8 w-8', text: 'text-xs', ring: 'ring-2', wave: 'h-3' },
  md: { container: 'h-10 w-10', text: 'text-sm', ring: 'ring-2', wave: 'h-4' },
  lg: { container: 'h-14 w-14', text: 'text-lg', ring: 'ring-[3px]', wave: 'h-5' },
} as const;

export const AgentAvatar = React.memo<AgentAvatarProps>(function AgentAvatar({
  agent,
  isSpeaking = false,
  size = 'md',
}) {
  const s = sizeMap[size];
  const initial = agent.name.charAt(0).toUpperCase();
  const isImageUrl = agent.avatar && (agent.avatar.startsWith('http') || agent.avatar.startsWith('/'));

  return (
    <div className="relative inline-flex flex-col items-center" role="img" aria-label={agent.name}>
      {/* Avatar circle with glow when speaking */}
      <div
        className={cn(
          'relative rounded-full flex items-center justify-center overflow-hidden font-semibold transition-shadow duration-300',
          s.container,
          s.ring,
          isSpeaking && 'ring-offset-2',
        )}
        style={{
          '--tw-ring-color': agent.color,
          borderColor: agent.color,
          boxShadow: isSpeaking
            ? `0 0 0 ${size === 'lg' ? '3px' : '2px'} ${agent.color}, 0 0 12px ${agent.color}66`
            : `0 0 0 ${size === 'lg' ? '3px' : '2px'} ${agent.color}`,
        } as React.CSSProperties}
      >
        {isImageUrl ? (
          <img
            src={agent.avatar}
            alt={agent.name}
            className="h-full w-full object-cover"
          />
        ) : (
          <div
            className={cn('h-full w-full flex items-center justify-center text-white', s.text)}
            style={{ backgroundColor: agent.color }}
          >
            {initial}
          </div>
        )}
      </div>

      {/* Sound wave animation when speaking */}
      {isSpeaking && (
        <div
          className={cn('flex items-end gap-[2px] mt-1', s.wave)}
          aria-hidden="true"
          style={{ color: agent.color }}
        >
          <span
            className="w-[3px] bg-current rounded-full"
            style={{
              animation: 'maicSoundWave 0.4s ease-in-out infinite',
              animationDelay: '0ms',
              height: '4px',
            }}
          />
          <span
            className="w-[3px] bg-current rounded-full"
            style={{
              animation: 'maicSoundWave 0.4s ease-in-out infinite',
              animationDelay: '150ms',
              height: '4px',
            }}
          />
          <span
            className="w-[3px] bg-current rounded-full"
            style={{
              animation: 'maicSoundWave 0.4s ease-in-out infinite',
              animationDelay: '300ms',
              height: '4px',
            }}
          />
        </div>
      )}

      {/* Inject keyframes via style tag (scoped via unique animation name) */}
      {isSpeaking && (
        <style>{`
          @keyframes maicSoundWave {
            0%, 100% { height: 4px; }
            50% { height: 12px; }
          }
        `}</style>
      )}
    </div>
  );
});
