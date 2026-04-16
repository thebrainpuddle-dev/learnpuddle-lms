/**
 * TTS Utilities
 *
 * Text splitting utilities for TTS providers with text length limits.
 * Used by both client-side and action engine to chunk long text before
 * sending to TTS providers.
 *
 * Adapted from OpenMAIC upstream for LearnPuddle LMS.
 */

import type { TTSProviderId } from './types';

/**
 * Provider-specific max text length limits.
 * Providers not listed here have no known limit (or a very large one).
 */
export const TTS_MAX_TEXT_LENGTH: Partial<Record<TTSProviderId, number>> = {
  // Most providers support large text, but some have stricter limits.
  // Add entries here as needed.
};

/**
 * Split long text into chunks that respect sentence boundaries.
 *
 * Tries splitting at sentence-ending punctuation first, then clause-level
 * punctuation, and finally hard-splits at maxLength as a last resort.
 *
 * @param text - The text to split
 * @param maxLength - Maximum length per chunk
 * @returns Array of text chunks, each at most maxLength characters
 */
export function splitLongSpeechText(text: string, maxLength: number): string[] {
  const normalized = text.trim();
  if (!normalized || normalized.length <= maxLength) return [normalized];

  // Split at sentence boundaries
  const units = normalized
    .split(/(?<=[.!?;:\n])/u)
    .map((part) => part.trim())
    .filter(Boolean);

  const chunks: string[] = [];
  let current = '';

  const pushChunk = (value: string) => {
    const trimmed = value.trim();
    if (trimmed) chunks.push(trimmed);
  };

  const appendUnit = (unit: string) => {
    if (!current) {
      current = unit;
      return;
    }
    if ((current + ' ' + unit).length <= maxLength) {
      current += ' ' + unit;
      return;
    }
    pushChunk(current);
    current = unit;
  };

  const hardSplitUnit = (unit: string) => {
    // Try splitting at commas first
    const parts = unit.split(/(?<=[,])\s*/u).filter(Boolean);
    if (parts.length > 1) {
      for (const part of parts) {
        if (part.length <= maxLength) appendUnit(part);
        else hardSplitUnit(part);
      }
      return;
    }

    // Last resort: hard split at maxLength
    let start = 0;
    while (start < unit.length) {
      appendUnit(unit.slice(start, start + maxLength));
      start += maxLength;
    }
  };

  for (const unit of units.length > 0 ? units : [normalized]) {
    if (unit.length <= maxLength) appendUnit(unit);
    else hardSplitUnit(unit);
  }

  pushChunk(current);
  return chunks;
}

/**
 * Split long speech text based on the provider's text length limit.
 *
 * Returns the original text array unchanged if the provider has no limit
 * or all texts are within the limit.
 *
 * @param texts - Array of text strings to check and potentially split
 * @param providerId - The TTS provider ID to check limits for
 * @returns Array of text strings, split if needed
 */
export function splitTextsForProvider(texts: string[], providerId: TTSProviderId): string[] {
  const maxLength = TTS_MAX_TEXT_LENGTH[providerId];
  if (!maxLength) return texts;

  return texts.flatMap((text) => {
    if (text.length <= maxLength) return [text];
    return splitLongSpeechText(text, maxLength);
  });
}
