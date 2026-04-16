/**
 * Top-level pipeline orchestration.
 * Creates sessions and runs the full generation pipeline.
 *
 * Adapted from upstream OpenMAIC pipeline-runner.ts for client-side use.
 * Talks to the Django backend via the provided AICallFn.
 */

import { nanoid } from 'nanoid';
import type {
  AgentInfo,
  AICallFn,
  GenerationResult,
  GenerationCallbacks,
  GenerationProgress,
} from './types';
import type { MAICScene } from '../../types/maic-scenes';
import type { MAICSlide, MAICOutlineScene } from '../../types/maic';
import { buildCompleteScene, buildSceneFromOutline, uniquifyMediaElementIds } from './scene-builder';
import { postProcessInteractiveHtml } from './interactive-post-processor';
import { parseJsonResponse } from './json-repair';

const log = {
  debug: (...args: unknown[]) => {
    if (import.meta.env.DEV) console.debug('[Pipeline]', ...args);
  },
  info: (...args: unknown[]) => console.info('[Pipeline]', ...args),
  warn: (...args: unknown[]) => console.warn('[Pipeline]', ...args),
  error: (...args: unknown[]) => console.error('[Pipeline]', ...args),
};

// ─── Session Type ────────────────────────────────────────────────────────────

export interface GenerationSession {
  id: string;
  topic: string;
  language: string;
  agents: AgentInfo[];
  sceneCount: number;
  status: 'idle' | 'generating' | 'complete' | 'error';
  progress: GenerationProgress;
}

// ─── Session Factory ─────────────────────────────────────────────────────────

export function createGenerationSession(config: {
  topic: string;
  language: string;
  agents: AgentInfo[];
  sceneCount?: number;
}): GenerationSession {
  return {
    id: nanoid(),
    topic: config.topic,
    language: config.language,
    agents: config.agents,
    sceneCount: config.sceneCount ?? 5,
    status: 'idle',
    progress: {
      stage: 'idle',
      current: 0,
      total: 0,
      message: 'Initializing...',
    },
  };
}

// ─── Pipeline Runner ─────────────────────────────────────────────────────────

/**
 * Run the full generation pipeline:
 *  1. Validate inputs
 *  2. Generate outline (via aiCall)
 *  3. Apply outline fallbacks
 *  4. For each scene in outline:
 *     a. Generate content (via aiCall)
 *     b. Generate actions (via aiCall)
 *     c. Build complete scene
 *     d. Post-process interactive HTML if applicable
 *     e. Report progress
 *  5. Return assembled scenes and slides
 */
export async function runGenerationPipeline(
  session: GenerationSession,
  aiCall: AICallFn,
  callbacks: GenerationCallbacks,
): Promise<GenerationResult<{ scenes: MAICScene[]; slides: MAICSlide[] }>> {
  try {
    session.status = 'generating';

    // ── Step 1: Validate inputs ──
    if (!session.topic.trim()) {
      throw new Error('Topic is required');
    }
    if (session.agents.length === 0) {
      throw new Error('At least one agent is required');
    }

    // ── Step 2: Generate outline ──
    callbacks.onProgress?.({
      stage: 'outline',
      current: 0,
      total: session.sceneCount,
      message: 'Generating course outline...',
    });

    const outlinePrompt = buildOutlinePrompt(session);
    const outlineResponse = await aiCall(
      'You are a curriculum designer. Generate a course outline in JSON format.',
      outlinePrompt,
    );

    const outlineResult = parseJsonResponse<{ scenes: MAICOutlineScene[] }>(outlineResponse);
    if (!outlineResult?.scenes || outlineResult.scenes.length === 0) {
      throw new Error('Failed to generate course outline');
    }

    // ── Step 3: Apply outline fallbacks ──
    let outlines = applyOutlineFallbacks(outlineResult.scenes);
    outlines = uniquifyMediaElementIds(outlines) as MAICOutlineScene[];

    callbacks.onStageComplete?.(1, outlines);

    const totalScenes = outlines.length;
    const classroomId = session.id;

    // ── Step 4: Generate each scene ──
    const scenes: MAICScene[] = [];
    const slides: MAICSlide[] = [];

    for (let i = 0; i < totalScenes; i++) {
      const outline = outlines[i];

      callbacks.onProgress?.({
        stage: 'scenes',
        current: i + 1,
        total: totalScenes,
        message: `Generating scene ${i + 1}/${totalScenes}: ${outline.title}`,
      });

      const scene = await buildSceneFromOutline(outline, aiCall, classroomId, {
        ctx: {
          pageIndex: i + 1,
          totalPages: totalScenes,
          allTitles: outlines.map((o) => o.title),
          previousSpeeches: collectPreviousSpeeches(scenes),
        },
        agents: session.agents,
        languageDirective: session.language !== 'en' ? `Respond in ${session.language}` : undefined,
        onPhaseChange: (phase) => {
          log.debug(`Scene ${i + 1} phase: ${phase}`);
        },
      });

      if (scene) {
        // Post-process interactive HTML if applicable
        if (scene.type === 'interactive' && scene.content.type === 'interactive' && scene.content.html) {
          scene.content.html = postProcessInteractiveHtml(scene.content.html);
        }

        // Set correct order
        scene.order = i;

        scenes.push(scene);

        // Extract slide data from slide-type scenes
        if (scene.type === 'slide' && scene.content.type === 'slide') {
          slides.push({
            id: scene.id,
            title: scene.title,
            elements: scene.content.elements,
            background: scene.content.background,
            speakerScript: scene.content.speakerScript,
          });
        }

        callbacks.onStageComplete?.(2, scene);
      } else {
        log.warn(`Scene ${i + 1} (${outline.title}) generation failed, skipping`);
      }
    }

    if (scenes.length === 0) {
      throw new Error('No scenes were generated successfully');
    }

    // ── Step 5: Complete ──
    session.status = 'complete';
    session.progress = {
      stage: 'complete',
      current: totalScenes,
      total: totalScenes,
      message: 'Generation complete!',
    };

    callbacks.onProgress?.(session.progress);

    return { success: true, data: { scenes, slides } };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    session.status = 'error';
    session.progress = {
      stage: 'error',
      current: 0,
      total: 0,
      message: errorMessage,
    };
    callbacks.onError?.(errorMessage);
    log.error('Pipeline failed:', errorMessage);
    return { success: false, error: errorMessage };
  }
}

// ─── Internal Helpers ────────────────────────────────────────────────────────

function buildOutlinePrompt(session: GenerationSession): string {
  const parts: string[] = [
    `Generate a course outline for: "${session.topic}"`,
    `Number of scenes: ${session.sceneCount}`,
    `Language: ${session.language}`,
    '',
    'Agents available:',
    ...session.agents.map((a) => `- ${a.name} (${a.role})${a.persona ? ': ' + a.persona : ''}`),
    '',
    'Return a JSON object with a "scenes" array. Each scene should have:',
    '- id: unique identifier',
    '- title: scene title',
    '- description: what the scene covers',
    '- type: one of "introduction", "lecture", "discussion", "quiz", "activity", "summary"',
    '- estimatedMinutes: estimated duration',
    '- agentIds: array of agent IDs involved',
  ];

  return parts.join('\n');
}

/**
 * Apply sensible defaults to outline scenes that may be missing fields.
 */
function applyOutlineFallbacks(outlines: MAICOutlineScene[]): MAICOutlineScene[] {
  return outlines.map((outline, index) => ({
    ...outline,
    id: outline.id || nanoid(),
    title: outline.title || `Scene ${index + 1}`,
    description: outline.description || '',
    type: outline.type || 'lecture',
    estimatedMinutes: outline.estimatedMinutes || 5,
    agentIds: outline.agentIds || [],
  }));
}

/**
 * Collect speech texts from previously generated scenes for transition context.
 */
function collectPreviousSpeeches(scenes: MAICScene[]): string[] {
  if (scenes.length === 0) return [];
  const lastScene = scenes[scenes.length - 1];
  if (!lastScene.actions) return [];

  return lastScene.actions
    .filter((a): a is Extract<typeof a, { type: 'speech' }> => a.type === 'speech')
    .map((a) => a.text);
}
