// src/components/maic/NotesPanel.tsx
//
// Side panel that shows auto-generated notes from speakerScripts + user annotations.
// Notes are grouped by scene with scene title headers, searchable, and exportable.

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import type { MAICNote } from '../../types/maic-scenes';
import { cn } from '../../lib/utils';

// ─── Internal Types ─────────────────────────────────────────────────────────

interface NotesEntry extends MAICNote {
  type: 'auto' | 'user' | 'quiz';
  agentName?: string;
}

// ─── Component ──────────────────────────────────────────────────────────────

export const NotesPanel: React.FC = () => {
  const scenes = useMAICStageStore((s) => s.scenes);
  const slides = useMAICStageStore((s) => s.slides);
  const currentSlideIndex = useMAICStageStore((s) => s.currentSlideIndex);
  const currentSceneIndex = useMAICStageStore((s) => s.currentSceneIndex);
  const notes = useMAICStageStore((s) => s.notes);
  const addNote = useMAICStageStore((s) => s.addNote);
  const agents = useMAICStageStore((s) => s.agents);
  const speakingAgentId = useMAICStageStore((s) => s.speakingAgentId);

  const [localEntries, setLocalEntries] = useState<NotesEntry[]>([]);
  const [userInput, setUserInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [copyFeedback, setCopyFeedback] = useState(false);
  const [userScrolled, setUserScrolled] = useState(false);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const notedSlidesRef = useRef<Set<number>>(new Set());
  // Entry DOM refs by slide index so we can scroll the active note into view
  // whenever the learner (or engine) moves to a new slide — OpenMAIC parity.
  const entryRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  // ─── Auto-note on slide change ──────────────────────────────────────

  useEffect(() => {
    if (notedSlidesRef.current.has(currentSlideIndex)) return;

    let speakerScript: string | undefined;
    let agentName: string | undefined;

    // Try scene-based speakerScript first
    const currentScene = scenes[currentSceneIndex];
    if (currentScene?.content?.type === 'slide') {
      speakerScript = (currentScene.content as { speakerScript?: string }).speakerScript;
    }

    // Fall back to flat slides
    if (!speakerScript) {
      const slide = slides[currentSlideIndex];
      speakerScript = slide?.speakerScript;
    }

    if (!speakerScript) return;

    // Identify which agent is speaking
    if (speakingAgentId) {
      const agent = agents.find((a) => a.id === speakingAgentId);
      if (agent) agentName = agent.name;
    }

    notedSlidesRef.current.add(currentSlideIndex);

    const entry: NotesEntry = {
      sceneIdx: currentSceneIndex,
      slideIdx: currentSlideIndex,
      text: speakerScript,
      timestamp: Date.now(),
      type: 'auto',
      agentName,
    };

    setLocalEntries((prev) => [...prev, entry]);
  }, [currentSlideIndex, currentSceneIndex, scenes, slides, agents, speakingAgentId]);

  // ─── Merge store notes with local entries ───────────────────────────

  const allEntries = useMemo(() => {
    // Store notes don't have 'type' — treat as user notes
    const storeEntries: NotesEntry[] = notes.map((n) => ({
      ...n,
      type: 'user' as const,
    }));

    // Combine and deduplicate by timestamp
    const combined = [...localEntries, ...storeEntries];
    const seen = new Set<number>();
    const deduped: NotesEntry[] = [];
    for (const entry of combined) {
      if (!seen.has(entry.timestamp)) {
        seen.add(entry.timestamp);
        deduped.push(entry);
      }
    }

    return deduped.sort((a, b) => a.timestamp - b.timestamp);
  }, [localEntries, notes]);

  // ─── Filtered entries ───────────────────────────────────────────────

  const filteredEntries = useMemo(() => {
    if (!searchQuery.trim()) return allEntries;
    const q = searchQuery.toLowerCase();
    return allEntries.filter(
      (e) =>
        e.text.toLowerCase().includes(q) ||
        (e.agentName && e.agentName.toLowerCase().includes(q)),
    );
  }, [allEntries, searchQuery]);

  // ─── Group by scene ─────────────────────────────────────────────────

  const groupedByScene = useMemo(() => {
    const groups: Map<number, NotesEntry[]> = new Map();
    for (const entry of filteredEntries) {
      const arr = groups.get(entry.sceneIdx) || [];
      arr.push(entry);
      groups.set(entry.sceneIdx, arr);
    }
    return groups;
  }, [filteredEntries]);

  // ─── Auto-scroll ────────────────────────────────────────────────────

  // When new entries arrive and the user hasn't scrolled away, keep the list
  // pinned to the bottom (catches newly-generated notes during autoplay).
  useEffect(() => {
    if (!userScrolled) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [allEntries.length, userScrolled]);

  // Scroll the active slide's entry into view on slide change. Overrides
  // user-scrolled sticky so clicking a thumbnail always reveals its note.
  useEffect(() => {
    const el = entryRefs.current.get(currentSlideIndex);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setUserScrolled(false);
    }
  }, [currentSlideIndex]);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setUserScrolled(!atBottom);
  }, []);

  // ─── Add user note ──────────────────────────────────────────────────

  const handleAddNote = useCallback(() => {
    const trimmed = userInput.trim();
    if (!trimmed) return;

    const note: MAICNote = {
      sceneIdx: currentSceneIndex,
      slideIdx: currentSlideIndex,
      text: trimmed,
      timestamp: Date.now(),
    };

    addNote(note);

    const entry: NotesEntry = {
      ...note,
      type: 'user',
    };
    setLocalEntries((prev) => [...prev, entry]);
    setUserInput('');
    setUserScrolled(false);
  }, [userInput, currentSceneIndex, currentSlideIndex, addNote]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        handleAddNote();
      }
    },
    [handleAddNote],
  );

  // ─── Export as markdown ─────────────────────────────────────────────

  const handleCopy = useCallback(async () => {
    const lines: string[] = ['# Classroom Notes\n'];

    for (const [sceneIdx, entries] of groupedByScene) {
      const scene = scenes[sceneIdx];
      const title = scene?.title || `Scene ${sceneIdx + 1}`;
      lines.push(`## ${title}\n`);

      for (const entry of entries) {
        const prefix = entry.type === 'user' ? '[My Note]' : entry.agentName ? `[${entry.agentName}]` : '';
        const slideLabel = `Slide ${entry.slideIdx + 1}`;
        lines.push(`- **${slideLabel}** ${prefix}: ${entry.text}`);
      }
      lines.push('');
    }

    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 2000);
    } catch {
      // Fallback: create a textarea and copy
      const textarea = document.createElement('textarea');
      textarea.value = lines.join('\n');
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 2000);
    }
  }, [groupedByScene, scenes]);

  // ─── Render ─────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full bg-white border-l border-gray-200 w-80 shrink-0">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <svg
            className="h-4 w-4 text-amber-500"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
            />
          </svg>
          <h3 className="text-sm font-semibold text-gray-900">Notes</h3>
          <span className="text-[10px] text-gray-400 tabular-nums">
            {allEntries.length}
          </span>
        </div>

        <button
          type="button"
          onClick={handleCopy}
          className={cn(
            'text-[10px] px-2 py-1 rounded-md font-medium transition-colors',
            copyFeedback
              ? 'bg-green-50 text-green-600'
              : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600',
          )}
          title="Copy notes as markdown"
        >
          {copyFeedback ? 'Copied!' : 'Copy'}
        </button>
      </div>

      {/* Search */}
      <div className="shrink-0 px-3 py-2 border-b border-gray-50">
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"
            />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search notes..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-gray-50 border border-gray-200 rounded-lg placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-400/50 focus:border-transparent"
          />
        </div>
      </div>

      {/* Notes list */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-3 py-3 space-y-4"
      >
        {filteredEntries.length === 0 && (
          <div className="text-center py-8">
            <svg
              className="h-8 w-8 text-gray-200 mx-auto mb-2"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
              />
            </svg>
            <p className="text-xs text-gray-400">
              {searchQuery ? 'No matching notes' : 'Notes will appear as the class plays'}
            </p>
          </div>
        )}

        {Array.from(groupedByScene.entries()).map(([sceneIdx, entries]) => {
          const scene = scenes[sceneIdx];
          const sceneTitle = scene?.title || `Scene ${sceneIdx + 1}`;

          return (
            <div key={sceneIdx}>
              {/* Scene header */}
              <div className="flex items-center gap-1.5 mb-2">
                <div className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" />
                <h4 className="text-[11px] font-semibold text-gray-700 truncate">
                  {sceneTitle}
                </h4>
              </div>

              {/* Scene notes */}
              <div className="space-y-1.5 ml-3 border-l-2 border-gray-100 pl-3">
                {entries.map((entry, idx) => {
                  const isCurrent = entry.slideIdx === currentSlideIndex;
                  return (
                    <div
                      key={`${entry.timestamp}-${idx}`}
                      ref={(el) => {
                        if (el && isCurrent) entryRefs.current.set(entry.slideIdx, el);
                      }}
                      className={cn(
                        'text-xs leading-relaxed rounded-lg px-2.5 py-2 transition-all',
                        isCurrent
                          ? 'bg-primary-50 border-2 border-primary-400 text-gray-900 shadow-sm'
                          : entry.type === 'user'
                            ? 'bg-amber-50 border border-amber-200 text-amber-900'
                            : entry.type === 'quiz'
                              ? 'bg-violet-50 border border-violet-200 text-violet-900'
                              : 'bg-gray-50 border border-transparent text-gray-700',
                      )}
                    >
                      {/* Meta line */}
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span
                          className={cn(
                            'text-[10px] tabular-nums',
                            isCurrent ? 'font-semibold text-primary-700' : 'text-gray-400',
                          )}
                        >
                          Slide {entry.slideIdx + 1}
                        </span>
                        {isCurrent && (
                          <span className="text-[10px] font-semibold uppercase tracking-wide text-primary-600 bg-primary-100 px-1.5 py-0.5 rounded">
                            Current
                          </span>
                        )}
                        {entry.type === 'user' && !isCurrent && (
                          <span className="text-[10px] font-medium text-amber-500">My Note</span>
                        )}
                        {entry.type === 'quiz' && (
                          <span className="text-[10px] font-medium text-violet-500">Quiz</span>
                        )}
                        {entry.agentName && entry.type === 'auto' && (
                          <span className="text-[10px] font-medium text-gray-500">
                            {entry.agentName}
                          </span>
                        )}
                      </div>
                      <p className="line-clamp-none">{entry.text}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        <div ref={bottomRef} />
      </div>

      {/* User note input */}
      <div className="shrink-0 px-3 py-3 border-t border-gray-100 bg-gray-50">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Add a note..."
            className="flex-1 text-xs px-3 py-2 bg-white border border-gray-200 rounded-lg placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-400/50 focus:border-transparent"
          />
          <button
            type="button"
            onClick={handleAddNote}
            disabled={!userInput.trim()}
            className={cn(
              'shrink-0 h-8 w-8 rounded-lg flex items-center justify-center transition-colors',
              userInput.trim()
                ? 'bg-amber-500 text-white hover:bg-amber-600'
                : 'bg-gray-100 text-gray-300 cursor-not-allowed',
            )}
            title="Add note"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
};
