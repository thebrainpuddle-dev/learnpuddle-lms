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

const MAX_TOOLTIP_WIDTH = 360;
const EDGE = 16;
const GAP = 14;
const MOBILE_BREAKPOINT = 768;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function getTooltipMetrics(viewportWidth: number, viewportHeight: number) {
  const width = Math.min(MAX_TOOLTIP_WIDTH, viewportWidth - EDGE * 2);
  const estimatedHeight = viewportWidth < MOBILE_BREAKPOINT ? 300 : 230;
  return {
    width,
    height: Math.min(estimatedHeight, viewportHeight - EDGE * 2),
    compact: viewportWidth < MOBILE_BREAKPOINT,
  };
}

function getTooltipPosition(targetRect: DOMRect | null, placement: TourPlacement = 'bottom') {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const metrics = getTooltipMetrics(viewportWidth, viewportHeight);

  if (!targetRect || placement === 'center') {
    return {
      left: clamp((viewportWidth - metrics.width) / 2, EDGE, viewportWidth - metrics.width - EDGE),
      top: clamp((viewportHeight - metrics.height) / 2, EDGE, viewportHeight - metrics.height - EDGE),
      width: metrics.width,
    };
  }

  const centerX = targetRect.left + targetRect.width / 2;
  const centerY = targetRect.top + targetRect.height / 2;
  const minTop = EDGE;
  const maxTop = viewportHeight - metrics.height - EDGE;
  const minLeft = EDGE;
  const maxLeft = viewportWidth - metrics.width - EDGE;

  if (metrics.compact) {
    const placeAbove = targetRect.bottom + GAP + metrics.height > viewportHeight - EDGE;
    return {
      left: minLeft,
      top: clamp(
        placeAbove ? targetRect.top - metrics.height - GAP : targetRect.bottom + GAP,
        minTop,
        maxTop
      ),
      width: metrics.width,
    };
  }

  if (placement === 'top') {
    return {
      left: clamp(centerX - metrics.width / 2, minLeft, maxLeft),
      top: clamp(targetRect.top - metrics.height - GAP, minTop, maxTop),
      width: metrics.width,
    };
  }

  if (placement === 'left') {
    return {
      left: clamp(targetRect.left - metrics.width - GAP, minLeft, maxLeft),
      top: clamp(centerY - metrics.height / 2, minTop, maxTop),
      width: metrics.width,
    };
  }

  if (placement === 'right') {
    return {
      left: clamp(targetRect.right + GAP, minLeft, maxLeft),
      top: clamp(centerY - metrics.height / 2, minTop, maxTop),
      width: metrics.width,
    };
  }

  return {
    left: clamp(centerX - metrics.width / 2, minLeft, maxLeft),
    top: clamp(targetRect.bottom + GAP, minTop, maxTop),
    width: metrics.width,
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
        className="absolute max-h-[calc(100vh-2rem)] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl sm:p-5"
        style={{ left: tooltipPosition.left, top: tooltipPosition.top, width: tooltipPosition.width }}
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
