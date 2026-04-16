/**
 * Generation pipeline — barrel exports.
 * Re-exports all public symbols from sub-modules.
 */

// Types
export type {
  AgentInfo,
  SceneGenerationContext,
  GeneratedSlideData,
  GenerationResult,
  GenerationCallbacks,
  AICallFn,
  GenerationProgress,
} from './types';

// JSON repair
export { parseJsonResponse, tryParseJson } from './json-repair';

// Action parser
export { parseActionsFromStructuredOutput } from './action-parser';

// Scene builder
export { buildCompleteScene, buildSceneFromOutline, uniquifyMediaElementIds } from './scene-builder';

// Interactive post-processor
export { postProcessInteractiveHtml } from './interactive-post-processor';

// Prompt formatters
export {
  buildCourseContext,
  buildCourseContextFromScene,
  formatAgentsForPrompt,
  formatImageDescription,
  formatImagePlaceholder,
  buildLanguageText,
} from './prompt-formatters';

// Pipeline runner
export { createGenerationSession, runGenerationPipeline } from './pipeline-runner';
export type { GenerationSession } from './pipeline-runner';
