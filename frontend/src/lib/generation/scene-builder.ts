/**
 * Standalone scene building and element normalization.
 * Does NOT depend on store — returns complete MAICScene objects.
 *
 * Adapted from upstream OpenMAIC scene-builder.ts for client-side use.
 */

import { nanoid } from 'nanoid';
import type { MAICAction } from '../../types/maic-actions';
import type { MAICScene, MAICSceneType } from '../../types/maic-scenes';
import type { MAICOutlineScene, MAICSlideElement } from '../../types/maic';
import type { AgentInfo, AICallFn, SceneGenerationContext } from './types';
import { buildLanguageText } from './prompt-formatters';
import { parseJsonResponse } from './json-repair';

const log = {
  debug: (...args: unknown[]) => {
    if (import.meta.env.DEV) console.debug('[Generation]', ...args);
  },
  info: (...args: unknown[]) => console.info('[Generation]', ...args),
  warn: (...args: unknown[]) => console.warn('[Generation]', ...args),
  error: (...args: unknown[]) => console.error('[Generation]', ...args),
};

// ─── Content types returned by AI generation ─────────────────────────────────

interface GeneratedSlideContent {
  elements: MAICSlideElement[];
  background?: string;
  speakerScript?: string;
}

interface GeneratedQuizContent {
  questions: Array<{
    id: string;
    type: 'single' | 'multiple' | 'short_answer';
    question: string;
    options?: { label: string; value: string }[];
    answer?: string[];
    analysis?: string;
    commentPrompt?: string;
    points?: number;
  }>;
}

interface GeneratedInteractiveContent {
  html: string;
  url?: string;
}

interface GeneratedPBLContent {
  projectTitle: string;
  description: string;
  roles: { id: string; name: string; description: string }[];
  milestones: { id: string; title: string; description: string; order: number }[];
  deliverables: string[];
}

type GeneratedContent =
  | GeneratedSlideContent
  | GeneratedQuizContent
  | GeneratedInteractiveContent
  | GeneratedPBLContent;

// ─── Media ID uniquification ─────────────────────────────────────────────────

/** Outline media generation entry */
interface MediaGeneration {
  elementId: string;
  type: 'image' | 'video';
  prompt?: string;
}

/** Extended outline that may carry mediaGenerations */
interface OutlineWithMedia extends MAICOutlineScene {
  mediaGenerations?: MediaGeneration[];
}

/**
 * Replace sequential gen_img_N / gen_vid_N IDs in outlines with globally unique IDs.
 *
 * The LLM generates sequential placeholder IDs (gen_img_1, gen_img_2, ...) which are
 * only unique within a single course. Using nanoid-based IDs ensures global uniqueness,
 * avoiding thumbnail contamination across courses that share a media store.
 */
export function uniquifyMediaElementIds(outlines: OutlineWithMedia[]): OutlineWithMedia[] {
  const idMap = new Map<string, string>();

  // First pass: collect all sequential media IDs and assign unique replacements
  for (const outline of outlines) {
    if (!outline.mediaGenerations) continue;
    for (const mg of outline.mediaGenerations) {
      if (!idMap.has(mg.elementId)) {
        const prefix = mg.type === 'video' ? 'gen_vid_' : 'gen_img_';
        idMap.set(mg.elementId, `${prefix}${nanoid(8)}`);
      }
    }
  }

  if (idMap.size === 0) return outlines;

  // Second pass: replace IDs in mediaGenerations
  return outlines.map((outline) => {
    if (!outline.mediaGenerations) return outline;
    return {
      ...outline,
      mediaGenerations: outline.mediaGenerations.map((mg) => ({
        ...mg,
        elementId: idMap.get(mg.elementId) || mg.elementId,
      })),
    };
  });
}

/**
 * Map an outline scene type to a MAICSceneType.
 * Upstream outline uses broader types ('introduction', 'lecture', etc.)
 * while MAICSceneType is constrained to 'slide' | 'quiz' | 'interactive' | 'pbl'.
 */
function mapSceneType(outlineType: string): MAICSceneType {
  switch (outlineType) {
    case 'quiz':
      return 'quiz';
    case 'interactive':
      return 'interactive';
    case 'pbl':
      return 'pbl';
    default:
      // introduction, lecture, discussion, activity, summary -> slide
      return 'slide';
  }
}

/**
 * Build a complete MAICScene object from outline, content, and actions.
 * This function does NOT depend on any store.
 */
export function buildCompleteScene(
  outline: MAICOutlineScene,
  content: GeneratedContent,
  actions: MAICAction[],
  classroomId: string,
): MAICScene | null {
  const sceneId = nanoid();
  const sceneType = mapSceneType(outline.type);

  if (sceneType === 'slide' && 'elements' in content) {
    const slideContent = content as GeneratedSlideContent;
    return {
      id: sceneId,
      type: 'slide',
      title: outline.title,
      order: outline.estimatedMinutes, // Use as ordering proxy
      content: {
        type: 'slide',
        elements: slideContent.elements,
        background: slideContent.background,
        speakerScript: slideContent.speakerScript,
      },
      actions,
    };
  }

  if (sceneType === 'quiz' && 'questions' in content) {
    const quizContent = content as GeneratedQuizContent;
    return {
      id: sceneId,
      type: 'quiz',
      title: outline.title,
      order: outline.estimatedMinutes,
      content: {
        type: 'quiz',
        questions: quizContent.questions,
      },
      actions,
    };
  }

  if (sceneType === 'interactive' && 'html' in content) {
    const interactiveContent = content as GeneratedInteractiveContent;
    return {
      id: sceneId,
      type: 'interactive',
      title: outline.title,
      order: outline.estimatedMinutes,
      content: {
        type: 'interactive',
        html: interactiveContent.html,
        url: interactiveContent.url,
      },
      actions,
    };
  }

  if (sceneType === 'pbl' && 'projectTitle' in content) {
    const pblContent = content as GeneratedPBLContent;
    return {
      id: sceneId,
      type: 'pbl',
      title: outline.title,
      order: outline.estimatedMinutes,
      content: {
        type: 'pbl',
        projectTitle: pblContent.projectTitle,
        description: pblContent.description,
        roles: pblContent.roles,
        milestones: pblContent.milestones,
        deliverables: pblContent.deliverables,
      },
      actions,
    };
  }

  log.warn(`Could not build scene for type "${outline.type}" with given content`);
  return null;
}

/**
 * Full pipeline: generate content -> generate actions -> build scene.
 * Uses the provided aiCall function to talk to the backend.
 */
export async function buildSceneFromOutline(
  outline: MAICOutlineScene,
  aiCall: AICallFn,
  classroomId: string,
  options?: {
    ctx?: SceneGenerationContext;
    agents?: AgentInfo[];
    languageDirective?: string;
    onPhaseChange?: (phase: 'content' | 'actions') => void;
  },
): Promise<MAICScene | null> {
  const langText = buildLanguageText(options?.languageDirective);
  const sceneType = mapSceneType(outline.type);

  // Step 1: Generate content
  options?.onPhaseChange?.('content');
  log.debug(`Step 1: Generating content for: ${outline.title}`);

  const contentPrompt = buildContentPrompt(outline, sceneType, langText, options?.agents);
  let contentResponse: string;
  try {
    contentResponse = await aiCall(
      `You are a course content generator. Generate ${sceneType} content in JSON format.`,
      contentPrompt,
    );
  } catch (e) {
    log.error(`Failed to generate content for: ${outline.title}`, e);
    return null;
  }

  const content = parseContentResponse(contentResponse, sceneType);
  if (!content) {
    log.error(`Failed to parse content for: ${outline.title}`);
    return null;
  }

  // Step 2: Generate actions
  options?.onPhaseChange?.('actions');
  log.debug(`Step 2: Generating actions for: ${outline.title}`);

  const actionsPrompt = buildActionsPrompt(outline, sceneType, langText, options?.agents, options?.ctx);
  let actionsResponse: string;
  try {
    actionsResponse = await aiCall(
      'You are a classroom action choreographer. Generate actions in JSON array format.',
      actionsPrompt,
    );
  } catch (e) {
    log.error(`Failed to generate actions for: ${outline.title}`, e);
    // Return scene with no actions rather than failing entirely
    return buildCompleteScene(outline, content, [], classroomId);
  }

  const { parseActionsFromStructuredOutput } = await import('./action-parser');
  const actions = parseActionsFromStructuredOutput(actionsResponse, sceneType);
  log.debug(`Generated ${actions.length} actions for: ${outline.title}`);

  return buildCompleteScene(outline, content, actions, classroomId);
}

// ─── Internal prompt builders ────────────────────────────────────────────────

function buildContentPrompt(
  outline: MAICOutlineScene,
  sceneType: MAICSceneType,
  langText: string,
  agents?: AgentInfo[],
): string {
  const parts: string[] = [
    `Generate content for a ${sceneType} scene titled "${outline.title}".`,
    `Description: ${outline.description}`,
  ];

  if (langText) parts.push(`Language: ${langText}`);
  if (agents && agents.length > 0) {
    parts.push(`Agents: ${agents.map((a) => `${a.name} (${a.role})`).join(', ')}`);
  }

  if (sceneType === 'slide') {
    parts.push('Return a JSON object with "elements" array and optional "background" and "speakerScript".');
    parts.push('Each element: { type, id, x, y, width, height, content, style? }');
  } else if (sceneType === 'quiz') {
    parts.push('Return a JSON object with "questions" array.');
    parts.push('Each question: { id, type, question, options?, answer?, analysis?, points? }');
  } else if (sceneType === 'interactive') {
    parts.push('Return a JSON object with "html" (complete HTML page) and optional "url".');
  } else if (sceneType === 'pbl') {
    parts.push('Return a JSON object with "projectTitle", "description", "roles", "milestones", "deliverables".');
  }

  return parts.join('\n');
}

function buildActionsPrompt(
  outline: MAICOutlineScene,
  sceneType: MAICSceneType,
  langText: string,
  agents?: AgentInfo[],
  ctx?: SceneGenerationContext,
): string {
  const parts: string[] = [
    `Generate classroom actions for the scene "${outline.title}" (type: ${sceneType}).`,
    `Description: ${outline.description}`,
  ];

  if (langText) parts.push(`Language: ${langText}`);
  if (agents && agents.length > 0) {
    parts.push(`Agents: ${agents.map((a) => `${a.name} (${a.role})`).join(', ')}`);
  }
  if (ctx) {
    parts.push(`Page ${ctx.pageIndex} of ${ctx.totalPages}.`);
  }

  parts.push('Return a JSON array of actions.');
  parts.push('Text: {"type":"text","content":"speech text"}');
  parts.push('Action: {"type":"action","name":"spotlight|laser|highlight|pause|discussion|transition","params":{...}}');

  return parts.join('\n');
}

// ─── Content response parser ─────────────────────────────────────────────────

function parseContentResponse(response: string, sceneType: MAICSceneType): GeneratedContent | null {
  if (sceneType === 'slide') {
    return parseJsonResponse<GeneratedSlideContent>(response);
  } else if (sceneType === 'quiz') {
    return parseJsonResponse<GeneratedQuizContent>(response);
  } else if (sceneType === 'interactive') {
    return parseJsonResponse<GeneratedInteractiveContent>(response);
  } else if (sceneType === 'pbl') {
    return parseJsonResponse<GeneratedPBLContent>(response);
  }

  return null;
}
