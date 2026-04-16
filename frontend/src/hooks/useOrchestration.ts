// hooks/useOrchestration.ts — React hook wrapping the DirectorGraph
//
// Provides a convenient interface for components to start/stop multi-agent
// orchestration. Wires DirectorGraph callbacks to update the maicStageStore
// (speaking agent, speech text) and manages cleanup on unmount.

import { useState, useCallback, useRef, useEffect } from 'react';
import { DirectorGraph } from '../lib/orchestration/director';
import { useMAICStageStore } from '../stores/maicStageStore';
import type { AgentConfig, OrchestrationCallbacks } from '../lib/orchestration/types';
import type { MAICRole } from '../lib/maic/endpoints';

// ─── Hook Options ────────────────────────────────────────────────────────────

interface UseOrchestrationOptions {
  onAgentStart?: (agentId: string, agentName: string) => void;
  onTextDelta?: (text: string, agentId: string) => void;
  onAgentEnd?: (agentId: string) => void;
  onComplete?: () => void;
  onError?: (message: string) => void;
  onThinking?: (stage: string, agentId?: string) => void;
  /**
   * Player role — decides which chat endpoint the underlying DirectorGraph
   * hits. Defaults to 'teacher' for backward compatibility.
   */
  role?: MAICRole;
}

// ─── Hook Return ─────────────────────────────────────────────────────────────

interface UseOrchestrationReturn {
  isRunning: boolean;
  currentAgentId: string | null;
  turnCount: number;
  startOrchestration: (
    agents: AgentConfig[],
    options?: {
      discussionTopic?: string;
      discussionPrompt?: string;
      triggerAgentId?: string;
      maxTurns?: number;
      slideContext?: {
        currentSceneTitle?: string;
        slideContent?: string;
        previousMessages?: Array<{ role: string; content: string; agentId?: string }>;
      };
    },
  ) => void;
  stopOrchestration: () => void;
}

// ─── Hook Implementation ─────────────────────────────────────────────────────

export function useOrchestration(
  options?: UseOrchestrationOptions,
): UseOrchestrationReturn {
  const [isRunning, setIsRunning] = useState(false);
  const [currentAgentId, setCurrentAgentId] = useState<string | null>(null);
  const [turnCount, setTurnCount] = useState(0);

  const directorRef = useRef<DirectorGraph | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Stage store actions
  const setSpeakingAgent = useMAICStageStore((s) => s.setSpeakingAgent);
  const setSpeechText = useMAICStageStore((s) => s.setSpeechText);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      directorRef.current?.stop();
      directorRef.current = null;
    };
  }, []);

  const stopOrchestration = useCallback(() => {
    directorRef.current?.stop();
    directorRef.current = null;
    setIsRunning(false);
    setCurrentAgentId(null);
    setSpeakingAgent(null);
    setSpeechText(null);
  }, [setSpeakingAgent, setSpeechText]);

  const startOrchestration = useCallback(
    (
      agents: AgentConfig[],
      startOptions?: {
        discussionTopic?: string;
        discussionPrompt?: string;
        triggerAgentId?: string;
        maxTurns?: number;
        slideContext?: {
          currentSceneTitle?: string;
          slideContent?: string;
          previousMessages?: Array<{ role: string; content: string; agentId?: string }>;
        };
      },
    ) => {
      // Stop any existing orchestration
      if (directorRef.current) {
        directorRef.current.stop();
      }

      setIsRunning(true);
      setTurnCount(0);
      setCurrentAgentId(null);

      // Build callbacks that bridge to React state and optional external handlers
      const callbacks: OrchestrationCallbacks = {
        onAgentStart: (agentId, agentName) => {
          setCurrentAgentId(agentId);
          setSpeakingAgent(agentId);
          optionsRef.current?.onAgentStart?.(agentId, agentName);
        },
        onTextDelta: (text, agentId) => {
          setSpeechText(text);
          optionsRef.current?.onTextDelta?.(text, agentId);
        },
        onActionEmit: () => {
          // Actions are handled by the action engine, not orchestration
        },
        onAgentEnd: (agentId) => {
          setSpeakingAgent(null);
          setSpeechText(null);
          optionsRef.current?.onAgentEnd?.(agentId);
        },
        onThinking: (stage, agentId) => {
          optionsRef.current?.onThinking?.(stage, agentId);
        },
        onCueUser: () => {
          setIsRunning(false);
          setCurrentAgentId(null);
          setSpeakingAgent(null);
          setSpeechText(null);
          optionsRef.current?.onComplete?.();
        },
        onError: (message) => {
          optionsRef.current?.onError?.(message);
        },
      };

      // Create the director graph
      const director = new DirectorGraph(agents, callbacks, {
        maxTurns: startOptions?.maxTurns,
        discussionContext: startOptions?.discussionTopic
          ? {
              topic: startOptions.discussionTopic,
              prompt: startOptions.discussionPrompt,
            }
          : undefined,
        triggerAgentId: startOptions?.triggerAgentId,
        slideContext: startOptions?.slideContext,
        role: optionsRef.current?.role,
      });

      directorRef.current = director;

      // Start the orchestration loop (async, runs in background)
      director.start().then(() => {
        // Update turn count from final state
        const finalState = director.getState();
        setTurnCount(finalState.turnCount);
      }).catch((err) => {
        const message = err instanceof Error ? err.message : 'Orchestration failed';
        optionsRef.current?.onError?.(message);
        setIsRunning(false);
      });
    },
    [setSpeakingAgent, setSpeechText],
  );

  return {
    isRunning,
    currentAgentId,
    turnCount,
    startOrchestration,
    stopOrchestration,
  };
}
