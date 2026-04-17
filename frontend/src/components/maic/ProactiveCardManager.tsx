// src/components/maic/ProactiveCardManager.tsx
//
// Manager component that generates and displays proactive suggestion cards
// based on playback state. Shows contextual prompts at natural break points
// (scene transitions, pauses, speech completions) to encourage student
// engagement. Tracks which scenes have already shown cards to avoid repeats.

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { ProactiveCard } from './ProactiveCard';
import type { ProactiveCardType } from './ProactiveCard';
import type { MAICEngineMode } from '../../types/maic-scenes';

// ─── Types ──────────────────────────────────────────────────────────────────

interface ProactiveCardManagerProps {
  enabled: boolean;
}

interface Suggestion {
  text: string;
  type: ProactiveCardType;
  agentName?: string;
  agentColor?: string;
}

// ─── Suggestion Templates ───────────────────────────────────────────────────

const SUGGESTION_TEMPLATES: { type: ProactiveCardType; template: (title: string) => string }[] = [
  {
    type: 'question',
    template: (title) => `What are the key implications of ${title}?`,
  },
  {
    type: 'discussion',
    template: (title) => `How does this concept apply in real-world scenarios?`,
  },
  {
    type: 'activity',
    template: (title) => `Can you think of examples related to ${title}?`,
  },
  {
    type: 'reflection',
    template: (title) => `What questions do you have about ${title}?`,
  },
  {
    type: 'question',
    template: (title) => `What would happen if the assumptions about ${title} were different?`,
  },
  {
    type: 'discussion',
    template: (title) => `How would you explain ${title} to someone unfamiliar with it?`,
  },
  {
    type: 'reflection',
    template: (title) => `What surprised you the most about ${title}?`,
  },
  {
    type: 'activity',
    template: (title) => `Try to connect ${title} with something you already know.`,
  },
];

// ─── Component ──────────────────────────────────────────────────────────────

export const ProactiveCardManager: React.FC<ProactiveCardManagerProps> = ({ enabled }) => {
  const scenes = useMAICStageStore((s) => s.scenes);
  const currentSceneIndex = useMAICStageStore((s) => s.currentSceneIndex);
  const engineMode = useMAICStageStore((s) => s.engineMode);
  const agents = useMAICStageStore((s) => s.agents);
  const setDiscussionMode = useMAICStageStore((s) => s.setDiscussionMode);

  const [activeSuggestion, setActiveSuggestion] = useState<Suggestion | null>(null);
  const [cardVisible, setCardVisible] = useState(false);

  // Track which scenes have already shown a card (by scene index)
  const shownScenesRef = useRef<Set<number>>(new Set());
  // Track previous engine mode to detect transitions
  const prevEngineModeRef = useRef<MAICEngineMode>(engineMode);
  // Rotation counter for cycling through suggestion types
  const rotationRef = useRef(0);
  // Track consecutive speech actions without user interaction
  const speechCountRef = useRef(0);
  // Track previous scene index
  const prevSceneIndexRef = useRef(currentSceneIndex);

  // Generate a suggestion for a given scene title
  const generateSuggestion = useCallback(
    (sceneIndex: number): Suggestion | null => {
      const scene = scenes[sceneIndex];
      if (!scene) return null;

      const title = scene.title || 'this topic';
      const templateIndex = rotationRef.current % SUGGESTION_TEMPLATES.length;
      const template = SUGGESTION_TEMPLATES[templateIndex];
      rotationRef.current += 1;

      // Optionally attribute the suggestion to an agent from the scene
      let agentName: string | undefined;
      let agentColor: string | undefined;
      if (scene.multiAgent?.agentIds?.length) {
        const suggestingAgentId = scene.multiAgent.agentIds[0];
        const agent = agents.find((a) => a.id === suggestingAgentId);
        if (agent) {
          agentName = agent.name;
          agentColor = agent.color;
        }
      }

      return {
        text: template.template(title),
        type: template.type,
        agentName,
        agentColor,
      };
    },
    [scenes, agents],
  );

  // Show a new proactive card for the current scene
  const showCard = useCallback(
    (sceneIndex: number) => {
      if (!enabled) return;
      if (shownScenesRef.current.has(sceneIndex)) return;

      const suggestion = generateSuggestion(sceneIndex);
      if (!suggestion) return;

      shownScenesRef.current.add(sceneIndex);
      setActiveSuggestion(suggestion);
      setCardVisible(true);
    },
    [enabled, generateSuggestion],
  );

  // ─── Trigger: Engine mode transitions (playing -> paused/idle) ─────────
  useEffect(() => {
    const prevMode = prevEngineModeRef.current;
    prevEngineModeRef.current = engineMode;

    if (!enabled) return;

    // Natural break: engine transitioned from playing to paused or idle
    if (prevMode === 'playing' && (engineMode === 'paused' || engineMode === 'idle')) {
      showCard(currentSceneIndex);
    }
  }, [engineMode, enabled, currentSceneIndex, showCard]);

  // ─── Trigger: Scene change ────────────────────────────────────────────
  useEffect(() => {
    const prevScene = prevSceneIndexRef.current;
    prevSceneIndexRef.current = currentSceneIndex;

    if (!enabled) return;

    // Scene completed (index moved forward)
    if (currentSceneIndex !== prevScene && currentSceneIndex > 0) {
      // Show card for the scene that just completed
      showCard(prevScene);
    }

    // Reset speech counter on scene change
    speechCountRef.current = 0;
  }, [currentSceneIndex, enabled, showCard]);

  // ─── Trigger: Speech count (3+ consecutive without interaction) ────────
  const speechText = useMAICStageStore((s) => s.speechText);

  useEffect(() => {
    if (!enabled) return;
    if (!speechText) return;

    speechCountRef.current += 1;

    if (speechCountRef.current >= 3 && !cardVisible) {
      showCard(currentSceneIndex);
    }
  }, [speechText, enabled, cardVisible, currentSceneIndex, showCard]);

  // ─── Handlers ─────────────────────────────────────────────────────────
  const handleAccept = useCallback(() => {
    setCardVisible(false);
    setActiveSuggestion(null);
    speechCountRef.current = 0;
    // Trigger discussion mode
    setDiscussionMode('qa');
  }, [setDiscussionMode]);

  const handleDismiss = useCallback(() => {
    setCardVisible(false);
    setActiveSuggestion(null);
    speechCountRef.current = 0;
  }, []);

  // Reset shown scenes when scenes array changes (new classroom loaded)
  useEffect(() => {
    shownScenesRef.current.clear();
    rotationRef.current = 0;
    speechCountRef.current = 0;
  }, [scenes]);

  // ─── Render ───────────────────────────────────────────────────────────
  // Wrapper is just a flex container — the caller (Stage.tsx) is
  // responsible for placement. Rendering the card here inside an absolute
  // overlay keeps the card bounded to the stage viewport.
  if (!enabled || !activeSuggestion) return null;

  return (
    <ProactiveCard
      suggestion={activeSuggestion.text}
      type={activeSuggestion.type}
      agentName={activeSuggestion.agentName}
      agentColor={activeSuggestion.agentColor}
      onAccept={handleAccept}
      onDismiss={handleDismiss}
      visible={cardVisible}
    />
  );
};
