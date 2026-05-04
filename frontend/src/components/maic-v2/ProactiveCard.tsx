/**
 * ProactiveCard — UI surface that asks the user to join a discussion.
 *
 * Triggered by the engine's `onProactiveShow` callback (3 s after a
 * `discussion` action enters the playback stream). The user can:
 *   - Click Join → engine.confirmDiscussion() → mode 'live' (parent
 *     wires the action via the manager's onJoin prop)
 *   - Click Skip → engine.skipDiscussion() → continues lecture
 *
 * Source convention: a bridged port of upstream
 * `components/chat/proactive-card.tsx` (248 lines, framer-motion-heavy).
 * We keep only the parts on the Phase 3 acceptance list:
 *   - topic + optional prompt
 *   - Join + Skip buttons
 *   - Entry animation (fade + slide-up 4px, 300ms) — CSS keyframes,
 *     no `motion` dep (per Phase 2 hard rule + plan)
 *
 * Out of scope (DEFERRED to Phase 5+ polish):
 *   - Auto-dismiss progress bar (upstream has 50ms tick)
 *   - Avatar / agent identity chrome
 *   - Backdrop blur, drop-shadow tier
 *   - Animated dismiss
 */
import type { TriggerEvent } from '../../lib/maic-v2/playback-types';


export interface ProactiveCardProps {
  trigger: TriggerEvent;
  onJoin: () => void;
  onSkip: () => void;
}


export function ProactiveCard({
  trigger,
  onJoin,
  onSkip,
}: ProactiveCardProps) {
  return (
    <>
      <style>{PROACTIVE_CARD_STYLES}</style>
      <div
        data-testid="maic-v2-proactive-card"
        data-trigger-id={trigger.id}
        className="proactive-card-enter rounded-xl border bg-card p-4 shadow-sm flex flex-col gap-3"
      >
        <div className="flex flex-col gap-1">
          <p
            data-testid="maic-v2-proactive-card-question"
            className="text-base font-semibold leading-snug"
          >
            {trigger.question}
          </p>
          {trigger.prompt && (
            <p
              data-testid="maic-v2-proactive-card-prompt"
              className="text-sm text-muted-foreground leading-snug"
            >
              {trigger.prompt}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 justify-end">
          <button
            type="button"
            data-testid="maic-v2-proactive-card-skip"
            onClick={onSkip}
            className="px-3 py-1.5 rounded-md border bg-background text-sm font-medium hover:bg-accent transition-colors"
          >
            Skip
          </button>
          <button
            type="button"
            data-testid="maic-v2-proactive-card-join"
            onClick={onJoin}
            className="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Join
          </button>
        </div>
      </div>
    </>
  );
}


// Inline keyframe so the animation is scoped to this component without
// touching the global tailwind.config.cjs. 300ms entry: fade in + slide
// up 4 px. `prefers-reduced-motion: reduce` short-circuits both for
// users who've opted out of motion at the OS level.
const PROACTIVE_CARD_STYLES = `
@keyframes maic-proactive-card-enter {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.proactive-card-enter {
  animation: maic-proactive-card-enter 300ms ease-out;
}
@media (prefers-reduced-motion: reduce) {
  .proactive-card-enter {
    animation: none;
  }
}
`;
