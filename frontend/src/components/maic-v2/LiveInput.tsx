/**
 * LiveInput — text input + Send + End Discussion controls visible
 * during `live` mode (MAIC-411.3).
 *
 * Visible only when Stage's `engineMode === 'live'`. Stage owns the
 * mount/unmount.
 *
 * Wiring on Send:
 *   1. Stage calls `engine.sendUserMessage(text)` (fires
 *      `onLiveUserMessage` callback locally)
 *   2. Stage calls `send({action:'user_message', data:{text}})` over
 *      the WS to backend MAIC-110.5
 *
 * Wiring on End Discussion:
 *   1. Stage calls `engine.handleEndDiscussion()` (restores cursor,
 *      sets mode 'idle')
 *   2. Stage calls `engine.continuePlayback()` so the lecture resumes
 *      from the saved cursor without re-running the WS Start path
 *   3. Stage calls `send({action:'resume'})` so the backend
 *      relinquishes its live-mode budget and resumes director
 *      decisions for any future turns
 *
 * UX choices (locked in the Session 4 prep doc, defaults):
 *   - single-line input (multi-line deferred to Phase 5+)
 *   - plain Enter submits (no shift+Enter for newline)
 *   - Send is disabled when input is empty or whitespace-only
 *   - End Discussion always enabled — user can bail at any time
 */
import { useState } from 'react';


export interface LiveInputProps {
  onSend: (text: string) => void;
  onEnd: () => void;
}


export function LiveInput({ onSend, onEnd }: LiveInputProps) {
  const [text, setText] = useState('');

  const trimmed = text.trim();
  const canSend = trimmed.length > 0;

  const handleSend = () => {
    if (!canSend) return;
    onSend(trimmed);
    setText('');
  };

  return (
    <div
      data-testid="maic-v2-live-input"
      className="flex items-center gap-2 rounded-xl border bg-card p-3"
    >
      <input
        data-testid="maic-v2-live-input-text"
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        placeholder="Type your message..."
        className="flex-1 rounded-md border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
        autoFocus
      />
      <button
        type="button"
        data-testid="maic-v2-live-input-send"
        onClick={handleSend}
        disabled={!canSend}
        className="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
      >
        Send
      </button>
      <button
        type="button"
        data-testid="maic-v2-live-input-end"
        onClick={onEnd}
        className="px-3 py-1.5 rounded-md border bg-background text-sm font-medium hover:bg-accent transition-colors"
      >
        End Discussion
      </button>
    </div>
  );
}
