// src/components/maic/AgentAvatar.tsx
//
// Circular avatar for MAIC agents. Shows agent initial or image with a
// colored ring. Pulsing animation indicates the agent is currently speaking.

import React from 'react';
import type { MAICAgent } from '../../types/maic';
import { cn } from '../../lib/utils';

interface AgentAvatarProps {
  agent: MAICAgent;
  isSpeaking?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const sizeMap = {
  sm: { container: 'h-8 w-8', text: 'text-xs', ring: 'ring-2', pulse: 'h-10 w-10' },
  md: { container: 'h-10 w-10', text: 'text-sm', ring: 'ring-2', pulse: 'h-12 w-12' },
  lg: { container: 'h-14 w-14', text: 'text-lg', ring: 'ring-[3px]', pulse: 'h-16 w-16' },
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
    <div className="relative inline-flex items-center justify-center" role="img" aria-label={agent.name}>
      {/* Pulsing ring when speaking */}
      {isSpeaking && (
        <span
          className={cn(
            'absolute inset-0 rounded-full animate-ping opacity-30',
            s.pulse,
          )}
          style={{ backgroundColor: agent.color }}
          aria-hidden="true"
        />
      )}

      {/* Avatar circle */}
      <div
        className={cn(
          'relative rounded-full flex items-center justify-center overflow-hidden font-semibold',
          s.container,
          s.ring,
          isSpeaking && 'ring-offset-2',
        )}
        style={{
          '--tw-ring-color': agent.color,
          borderColor: agent.color,
          boxShadow: `0 0 0 ${size === 'lg' ? '3px' : '2px'} ${agent.color}`,
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
    </div>
  );
});
