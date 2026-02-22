import React from 'react';
import './FishEvolutionWidget.css';

export interface FishStage {
  key: 'PUDDLE' | 'POND' | 'LAKE' | 'RIVER' | 'OCEAN';
  label: string;
  subtitle: string;
  rippleRange: string;
  minPoints: number;
  maxPoints: number | null;
  color: string;
  fishEmoji: string;
}

const FISH_STAGES: FishStage[] = [
  {
    key: 'PUDDLE',
    label: 'Puddle',
    subtitle: 'Associate Educator',
    rippleRange: '0-200 RP',
    minPoints: 0,
    maxPoints: 199,
    color: '#7DD3C8',
    fishEmoji: '🐟',
  },
  {
    key: 'POND',
    label: 'Pond',
    subtitle: 'Certified Teacher',
    rippleRange: '200-600 RP',
    minPoints: 200,
    maxPoints: 599,
    color: '#4ECDC4',
    fishEmoji: '🐠',
  },
  {
    key: 'LAKE',
    label: 'Lake',
    subtitle: 'Senior Educator',
    rippleRange: '600-1,200 RP',
    minPoints: 600,
    maxPoints: 1199,
    color: '#3BA4D4',
    fishEmoji: '🐡',
  },
  {
    key: 'RIVER',
    label: 'River',
    subtitle: 'Lead Academic Mentor',
    rippleRange: '1,200-2,500 RP',
    minPoints: 1200,
    maxPoints: 2499,
    color: '#7B6CFF',
    fishEmoji: '🐬',
  },
  {
    key: 'OCEAN',
    label: 'Ocean',
    subtitle: 'Master Faculty',
    rippleRange: '2,500+ RP',
    minPoints: 2500,
    maxPoints: null,
    color: '#2B6FE8',
    fishEmoji: '🐋',
  },
];

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

export function getFishStageFromPoints(pointsTotal: number): FishStage {
  const points = Number.isFinite(pointsTotal) ? pointsTotal : 0;
  return (
    FISH_STAGES.find((stage) =>
      stage.maxPoints == null
        ? points >= stage.minPoints
        : points >= stage.minPoints && points <= stage.maxPoints,
    ) || FISH_STAGES[0]
  );
}

export function getSliderFromPoints(pointsTotal: number): number {
  const points = Number.isFinite(pointsTotal) ? pointsTotal : 0;
  if (points >= 2500) return 100;
  if (points >= 1200) return 75 + ((points - 1200) / 1300) * 24;
  if (points >= 600) return 50 + ((points - 600) / 600) * 24;
  if (points >= 200) return 25 + ((points - 200) / 400) * 24;
  return (points / 200) * 24;
}

function getStageFromSlider(sliderValue: number): FishStage {
  if (sliderValue >= 100) return FISH_STAGES[4];
  if (sliderValue >= 75) return FISH_STAGES[3];
  if (sliderValue >= 50) return FISH_STAGES[2];
  if (sliderValue >= 25) return FISH_STAGES[1];
  return FISH_STAGES[0];
}

function getProgressToNextStage(pointsTotal: number): number {
  const current = getFishStageFromPoints(pointsTotal);
  if (current.maxPoints == null) return 100;
  const span = Math.max(1, current.maxPoints - current.minPoints + 1);
  const currentPoints = clamp(pointsTotal - current.minPoints + 1, 0, span);
  return Math.round((currentPoints / span) * 100);
}

interface FishEvolutionWidgetProps {
  pointsTotal: number;
}

export const FishEvolutionWidget: React.FC<FishEvolutionWidgetProps> = ({ pointsTotal }) => {
  const [reducedMotion, setReducedMotion] = React.useState(false);
  const [isPlaying, setIsPlaying] = React.useState(false);
  const liveSlider = React.useMemo(() => getSliderFromPoints(pointsTotal), [pointsTotal]);
  const [sliderValue, setSliderValue] = React.useState(liveSlider);

  React.useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      setReducedMotion(false);
      return undefined;
    }
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = () => setReducedMotion(mediaQuery.matches);
    updatePreference();
    mediaQuery.addEventListener('change', updatePreference);
    return () => mediaQuery.removeEventListener('change', updatePreference);
  }, []);

  React.useEffect(() => {
    setSliderValue((current) => (isPlaying ? current : liveSlider));
  }, [liveSlider, isPlaying]);

  React.useEffect(() => {
    if (!isPlaying || reducedMotion) return undefined;
    const timer = window.setInterval(() => {
      setSliderValue((current) => {
        if (current >= 100) {
          setIsPlaying(false);
          return 100;
        }
        return Math.min(100, current + 1.5);
      });
    }, 70);
    return () => window.clearInterval(timer);
  }, [isPlaying, reducedMotion]);

  const activeStage = getStageFromSlider(sliderValue);
  const liveStage = getFishStageFromPoints(pointsTotal);
  const stageProgress = getProgressToNextStage(pointsTotal);

  const handlePlayToggle = () => {
    if (reducedMotion) return;
    setIsPlaying((prev) => !prev);
  };

  return (
    <section className="lp-fish-widget" aria-label="Puddle fish evolution">
      <div className="lp-fish-header">
        <div>
          <h3>The Puddle Fish Journey</h3>
          <p>Play with your level path while your live progress stays in sync.</p>
        </div>
        <div className="lp-fish-live-pill" style={{ borderColor: `${liveStage.color}66`, color: liveStage.color }}>
          Live Stage: {liveStage.label}
        </div>
      </div>

      <div className={`lp-fish-stage lp-fish-stage-${activeStage.key.toLowerCase()}`}>
        <div className="lp-fish-level-copy">
          <p className="lp-fish-level-name" style={{ color: activeStage.color }}>
            {activeStage.label}
          </p>
          <p className="lp-fish-level-subtitle">{activeStage.subtitle}</p>
          <p className="lp-fish-level-range">{activeStage.rippleRange}</p>
        </div>

        <div className="lp-fish-waterline" aria-hidden="true" />
        <div
          className={`lp-fish-avatar ${reducedMotion ? 'lp-fish-static' : ''}`}
          style={{ left: `calc(${sliderValue}% - 1.1rem)` }}
          aria-hidden="true"
        >
          {activeStage.fishEmoji}
        </div>
        <div className="lp-fish-bubbles" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </div>

      <div className="lp-fish-controls">
        <label htmlFor="fish-evolution-slider" className="lp-fish-slider-label">
          Evolution Preview
        </label>
        <input
          id="fish-evolution-slider"
          type="range"
          min={0}
          max={100}
          step={1}
          value={Math.round(sliderValue)}
          onChange={(event) => {
            setIsPlaying(false);
            setSliderValue(Number(event.target.value));
          }}
          aria-valuetext={`${activeStage.label} stage`}
        />
        <div className="lp-fish-stage-labels">
          {FISH_STAGES.map((stage, index) => (
            <button
              key={stage.key}
              type="button"
              onClick={() => {
                setIsPlaying(false);
                setSliderValue(index * 25);
              }}
              className={activeStage.key === stage.key ? 'active' : ''}
              style={{ color: activeStage.key === stage.key ? stage.color : undefined }}
            >
              {stage.label}
            </button>
          ))}
        </div>
      </div>

      <div className="lp-fish-footer">
        <div>
          <p className="lp-fish-points">Live Points: {pointsTotal}</p>
          <p className="lp-fish-progress">
            Stage progress: {stageProgress}% {liveStage.maxPoints == null ? '(max stage)' : 'towards next level'}
          </p>
        </div>
        <div className="lp-fish-actions">
          <button
            type="button"
            onClick={handlePlayToggle}
            disabled={reducedMotion}
            aria-label={isPlaying ? 'Pause evolution animation' : 'Play evolution animation'}
          >
            {reducedMotion ? 'Animation Off' : isPlaying ? 'Pause Evolution' : 'Play Evolution'}
          </button>
          <button
            type="button"
            onClick={() => {
              setIsPlaying(false);
              setSliderValue(liveSlider);
            }}
          >
            Reset to Live
          </button>
        </div>
      </div>
    </section>
  );
};
