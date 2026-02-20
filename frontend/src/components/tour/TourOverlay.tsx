import React from 'react';
import type { TourPlacement, TourStep } from './types';

interface TourOverlayProps {
  step: TourStep;
  stepNumber: number;
  totalSteps: number;
  targetRect: DOMRect | null;
  isResolving: boolean;
  onBack: () => void;
  onNext: () => void;
  onSkip: () => void;
}

const TOOLTIP_WIDTH = 360;
const EDGE = 16;
const GAP = 14;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function getTooltipPosition(targetRect: DOMRect | null, placement: TourPlacement = 'bottom') {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;

  if (!targetRect || placement === 'center') {
    return {
      left: clamp((viewportWidth - TOOLTIP_WIDTH) / 2, EDGE, viewportWidth - TOOLTIP_WIDTH - EDGE),
      top: clamp((viewportHeight - 220) / 2, EDGE, viewportHeight - 220 - EDGE),
    };
  }

  const centerX = targetRect.left + targetRect.width / 2;
  const centerY = targetRect.top + targetRect.height / 2;

  if (placement === 'top') {
    return {
      left: clamp(centerX - TOOLTIP_WIDTH / 2, EDGE, viewportWidth - TOOLTIP_WIDTH - EDGE),
      top: clamp(targetRect.top - 220 - GAP, EDGE, viewportHeight - 220 - EDGE),
    };
  }

  if (placement === 'left') {
    return {
      left: clamp(targetRect.left - TOOLTIP_WIDTH - GAP, EDGE, viewportWidth - TOOLTIP_WIDTH - EDGE),
      top: clamp(centerY - 100, EDGE, viewportHeight - 220 - EDGE),
    };
  }

  if (placement === 'right') {
    return {
      left: clamp(targetRect.right + GAP, EDGE, viewportWidth - TOOLTIP_WIDTH - EDGE),
      top: clamp(centerY - 100, EDGE, viewportHeight - 220 - EDGE),
    };
  }

  return {
    left: clamp(centerX - TOOLTIP_WIDTH / 2, EDGE, viewportWidth - TOOLTIP_WIDTH - EDGE),
    top: clamp(targetRect.bottom + GAP, EDGE, viewportHeight - 220 - EDGE),
  };
}

export const TourOverlay: React.FC<TourOverlayProps> = ({
  step,
  stepNumber,
  totalSteps,
  targetRect,
  isResolving,
  onBack,
  onNext,
  onSkip,
}) => {
  const tooltipPosition = getTooltipPosition(targetRect, step.placement);
  const isLast = stepNumber >= totalSteps;

  return (
    <div className="fixed inset-0 z-[130]">
      <div className={`absolute inset-0 ${targetRect ? 'bg-transparent' : 'bg-slate-950/65'}`} />

      {targetRect && (
        <div
          className="pointer-events-none absolute rounded-xl border-2 border-emerald-400/90 shadow-[0_0_0_9999px_rgba(2,6,23,0.65)] transition-all duration-200"
          style={{
            left: Math.max(targetRect.left - 6, 0),
            top: Math.max(targetRect.top - 6, 0),
            width: targetRect.width + 12,
            height: targetRect.height + 12,
          }}
        />
      )}

      <section
        data-tour-overlay="true"
        className="absolute w-[360px] max-w-[calc(100vw-2rem)] rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl"
        style={{ left: tooltipPosition.left, top: tooltipPosition.top }}
      >
        <div className="mb-3 flex items-center justify-between">
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
            Step {stepNumber} of {totalSteps}
          </span>
          <button
            type="button"
            onClick={onSkip}
            className="text-xs font-medium text-slate-500 hover:text-slate-700"
          >
            Skip tour
          </button>
        </div>

        <h3 data-tour-overlay-title="true" className="text-base font-semibold text-slate-900">{step.title}</h3>
        <p className="mt-2 text-sm leading-6 text-slate-600">{step.description}</p>

        {isResolving && (
          <p className="mt-3 text-xs text-slate-500">Positioning this step...</p>
        )}

        <div className="mt-5 flex items-center justify-between">
          <button
            type="button"
            onClick={onBack}
            disabled={stepNumber === 1}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Back
          </button>
          <button
            type="button"
            onClick={onNext}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
          >
            {isLast ? 'Finish' : 'Next'}
          </button>
        </div>
      </section>
    </div>
  );
};
