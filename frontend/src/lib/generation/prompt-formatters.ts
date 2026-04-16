/**
 * Prompt and context building utilities for the generation pipeline.
 * Adapted from upstream OpenMAIC prompt-formatters.ts for client-side use.
 */

import type { AgentInfo, SceneGenerationContext } from './types';

/**
 * Build a course context string for injection into action prompts.
 * Includes course outline, position markers, and transition guidance.
 */
export function buildCourseContext(
  topic: string,
  description?: string,
  language?: string,
): string {
  const lines: string[] = [];

  lines.push(`Course Topic: ${topic}`);
  if (description) {
    lines.push(`Description: ${description}`);
  }
  if (language) {
    lines.push(`Language: ${language}`);
  }

  return lines.join('\n');
}

/**
 * Build a detailed course context from a SceneGenerationContext.
 * Includes outline, position, and transition reference information.
 */
export function buildCourseContextFromScene(ctx?: SceneGenerationContext): string {
  if (!ctx) return '';

  const lines: string[] = [];

  // Course outline with position marker
  lines.push('Course Outline:');
  ctx.allTitles.forEach((t, i) => {
    const marker = i === ctx.pageIndex - 1 ? ' <- current' : '';
    lines.push(`  ${i + 1}. ${t}${marker}`);
  });

  // Position information
  lines.push('');
  lines.push(
    'IMPORTANT: All pages belong to the SAME class session. Do NOT greet again after the first page. When referencing content from earlier pages, say "we just covered" or "as mentioned on page N" — NEVER say "last class" or "previous session" because there is no previous session.',
  );
  lines.push('');
  if (ctx.pageIndex === 1) {
    lines.push('Position: This is the FIRST page. Open with a greeting and course introduction.');
  } else if (ctx.pageIndex === ctx.totalPages) {
    lines.push('Position: This is the LAST page. Conclude the course with a summary and closing.');
    lines.push(
      'Transition: Continue naturally from the previous page. Do NOT greet or re-introduce.',
    );
  } else {
    lines.push(`Position: Page ${ctx.pageIndex} of ${ctx.totalPages} (middle of the course).`);
    lines.push(
      'Transition: Continue naturally from the previous page. Do NOT greet or re-introduce.',
    );
  }

  // Previous page speech for transition reference
  if (ctx.previousSpeeches.length > 0) {
    lines.push('');
    lines.push('Previous page speech (for transition reference):');
    const lastSpeech = ctx.previousSpeeches[ctx.previousSpeeches.length - 1];
    lines.push(`  "...${lastSpeech.slice(-150)}"`);
  }

  return lines.join('\n');
}

/** Format agent list for injection into action prompts */
export function formatAgentsForPrompt(agents?: AgentInfo[]): string {
  if (!agents || agents.length === 0) return '';

  const lines = ['Classroom Agents:'];
  for (const a of agents) {
    const personaPart = a.persona ? ` — ${a.persona}` : '';
    lines.push(`- id: "${a.id}", name: "${a.name}", role: ${a.role}${personaPart}`);
  }
  return lines.join('\n');
}

/**
 * Format an image description for prompt inclusion.
 * Includes dimension/aspect-ratio info when available.
 */
export function formatImageDescription(image: { id: string; description?: string }): string {
  const desc = image.description ? ` | ${image.description}` : '';
  return `- **${image.id}**${desc}`;
}

/**
 * Format a short image placeholder for vision mode.
 * Only ID is shown since the model can see the actual image.
 */
export function formatImagePlaceholder(imageId: string): string {
  return `- **${imageId}**: [see attached image]`;
}

/**
 * Build language instruction text from course-level directive and optional per-scene note.
 * Used by scene content and action generators to inject into prompt templates.
 */
export function buildLanguageText(languageDirective?: string, languageNote?: string): string {
  if (!languageDirective && !languageNote) return '';
  let text = languageDirective || '';
  if (languageNote) {
    text += (text ? '\n\n' : '') + `Additional language note for this scene: ${languageNote}`;
  }
  return text;
}
