import React from 'react';
import './FishEvolutionWidget.css';

export interface FishStage {
  key: 'PUDDLE' | 'POND' | 'LAKE' | 'RIVER' | 'OCEAN';
  label: string;
  minPoints: number;
  maxPoints: number | null;
  color: string;
  depth: string;
}

const FISH_STAGES: FishStage[] = [
  { key: 'PUDDLE', label: 'Puddle', minPoints: 0, maxPoints: 199, color: '#7DD3C8', depth: '#5AADA5' },
  { key: 'POND', label: 'Pond', minPoints: 200, maxPoints: 599, color: '#4ECDC4', depth: '#34A89F' },
  { key: 'LAKE', label: 'Lake', minPoints: 600, maxPoints: 1199, color: '#3BA4D4', depth: '#2680A8' },
  { key: 'RIVER', label: 'River', minPoints: 1200, maxPoints: 2499, color: '#7B6CFF', depth: '#5A4ED4' },
  { key: 'OCEAN', label: 'Ocean', minPoints: 2500, maxPoints: null, color: '#2B6FE8', depth: '#1A4EB8' },
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

function getStageIndexFromSlider(sliderValue: number): number {
  if (sliderValue >= 100) return 4;
  if (sliderValue >= 75) return 3;
  if (sliderValue >= 50) return 2;
  if (sliderValue >= 25) return 1;
  return 0;
}

function lerpColor(a: string, b: string, t: number): string {
  const ah = parseInt(a.slice(1), 16);
  const bh = parseInt(b.slice(1), 16);
  const ar = (ah >> 16) & 0xff;
  const ag = (ah >> 8) & 0xff;
  const ab = ah & 0xff;
  const br = (bh >> 16) & 0xff;
  const bg = (bh >> 8) & 0xff;
  const bb = bh & 0xff;
  return `rgb(${Math.round(ar + (br - ar) * t)},${Math.round(ag + (bg - ag) * t)},${Math.round(
    ab + (bb - ab) * t,
  )})`;
}

interface FishEvolutionWidgetProps {
  pointsTotal: number;
}

function getStageRangeLabel(stage: FishStage): string {
  return stage.maxPoints == null ? `${stage.minPoints}+ RP` : `${stage.minPoints}-${stage.maxPoints} RP`;
}

export const FishEvolutionWidget: React.FC<FishEvolutionWidgetProps> = ({ pointsTotal }) => {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const [reducedMotion, setReducedMotion] = React.useState(false);
  const [isPlaying, setIsPlaying] = React.useState(false);
  const [previewMode, setPreviewMode] = React.useState(false);

  const liveStage = React.useMemo(() => getFishStageFromPoints(pointsTotal), [pointsTotal]);
  const liveStageIndex = React.useMemo(
    () => FISH_STAGES.findIndex((stage) => stage.key === liveStage.key),
    [liveStage.key],
  );
  const liveSlider = React.useMemo(() => getSliderFromPoints(pointsTotal), [pointsTotal]);
  const [sliderValue, setSliderValue] = React.useState(liveSlider);

  React.useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      setReducedMotion(false);
      return undefined;
    }
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const syncMotion = () => setReducedMotion(mediaQuery.matches);
    syncMotion();
    mediaQuery.addEventListener('change', syncMotion);
    return () => mediaQuery.removeEventListener('change', syncMotion);
  }, []);

  React.useEffect(() => {
    if (!previewMode && !isPlaying) {
      setSliderValue(liveSlider);
    }
  }, [liveSlider, previewMode, isPlaying]);

  React.useEffect(() => {
    if (!isPlaying || reducedMotion) return undefined;
    const timer = window.setInterval(() => {
      setSliderValue((current) => {
        const next = Math.min(100, current + 0.9);
        if (next >= 100) setIsPlaying(false);
        return next;
      });
    }, 32);
    return () => window.clearInterval(timer);
  }, [isPlaying, reducedMotion]);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    if (typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent || '')) {
      return undefined;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;

    let raf = 0;
    let stageWidth = 0;
    let stageHeight = 0;
    let t = 0;

    const resize = () => {
      if (!canvas.parentElement) return;
      const rect = canvas.parentElement.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      stageWidth = rect.width;
      stageHeight = rect.height;
    };

    const drawPuddle = (cx: number, cy: number, sx: number, sy: number, color: string, deep: string) => {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.scale(sx, sy);

      ctx.beginPath();
      ctx.ellipse(4, 10, 105, 32, 0, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(0,0,0,0.12)';
      ctx.fill();

      ctx.beginPath();
      ctx.moveTo(-85, -8 + Math.sin(t * 1.2) * 2);
      ctx.bezierCurveTo(-95, -28, -55, -38 + Math.sin(t * 0.8) * 3, -25, -33);
      ctx.bezierCurveTo(-5, -40, 15, -36 + Math.sin(t * 1.5) * 2, 45, -32);
      ctx.bezierCurveTo(72, -28, 92, -22 + Math.sin(t * 0.9) * 3, 96, -5);
      ctx.bezierCurveTo(100, 10, 82, 24 + Math.sin(t * 1.1) * 2, 52, 28);
      ctx.bezierCurveTo(28, 32, 8, 26 + Math.sin(t * 1.3) * 2, -18, 30);
      ctx.bezierCurveTo(-48, 34, -72, 28, -88, 16);
      ctx.bezierCurveTo(-102, 4, -98, -3, -85, -8 + Math.sin(t * 1.2) * 2);
      ctx.closePath();

      const gradient = ctx.createLinearGradient(-100, -40, 100, 40);
      gradient.addColorStop(0, color);
      gradient.addColorStop(1, deep);
      ctx.fillStyle = gradient;
      ctx.fill();
      ctx.strokeStyle = deep;
      ctx.lineWidth = 2.5;
      ctx.stroke();

      ctx.beginPath();
      ctx.ellipse(-15, -16, 45, 10, -0.2, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,255,255,0.18)';
      ctx.fill();

      ctx.beginPath();
      ctx.ellipse(30, -10, 22, 5, 0.1, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,255,255,0.1)';
      ctx.fill();

      ctx.restore();
    };

    const drawRipples = (cx: number, cy: number, sx: number, sy: number, color: string, count: number) => {
      ctx.save();
      ctx.translate(cx, cy);
      for (let i = 0; i < count; i += 1) {
        const phase = (t * 0.8 + i * 1.5) % 4;
        const ripple = phase / 4;
        const alpha = (1 - ripple) * 0.25;
        ctx.beginPath();
        ctx.ellipse(0, 0, (55 + ripple * 80) * sx, (18 + ripple * 25) * sy, 0, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.globalAlpha = alpha;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      ctx.restore();
      ctx.globalAlpha = 1;
    };

    const drawBubbles = (cx: number, cy: number, count: number, spread: number, color: string) => {
      for (let i = 0; i < count; i += 1) {
        const phase = (t * 0.6 + i * 2.3) % 5;
        const y = cy - phase * 16;
        const x = cx + Math.sin(t + i * 1.7) * spread;
        const r = 2 + Math.sin(i * 3) * 1.5;
        const alpha = Math.max(0, 0.3 - phase * 0.06);
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.globalAlpha = alpha;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    };

    const drawFish = (x: number, y: number, size: number, energy: number, happy: number) => {
      ctx.save();
      ctx.translate(x, y);

      const speedFactor = 1.5 + energy * 3;
      const bodyAngle = Math.sin(t * speedFactor) * energy * 0.15 + (1 - energy) * 0.45;
      ctx.rotate(bodyAngle);

      ctx.globalAlpha = 0.12;
      ctx.beginPath();
      ctx.ellipse(0, size * 0.55, size * 0.62, size * 0.14, 0, 0, Math.PI * 2);
      ctx.fillStyle = '#000';
      ctx.fill();
      ctx.globalAlpha = 1;

      ctx.beginPath();
      ctx.ellipse(0, 0, size * 0.65, size * 0.35, 0, 0, Math.PI * 2);
      const bodyGradient = ctx.createRadialGradient(-size * 0.12, -size * 0.08, 0, 0, 0, size * 0.65);
      bodyGradient.addColorStop(0, '#FF9B4E');
      bodyGradient.addColorStop(0.6, '#FF7B2E');
      bodyGradient.addColorStop(1, '#E85D1A');
      ctx.fillStyle = bodyGradient;
      ctx.fill();
      ctx.strokeStyle = '#D4500F';
      ctx.lineWidth = 1.4;
      ctx.stroke();

      const tailSwing = Math.sin(t * speedFactor * 1.5) * (5 + energy * 18);
      ctx.save();
      ctx.translate(size * 0.55, 0);
      ctx.rotate((tailSwing * Math.PI) / 180);
      ctx.beginPath();
      ctx.moveTo(0, -size * 0.08);
      ctx.quadraticCurveTo(size * 0.32, -size * 0.38, size * 0.38, -size * 0.32);
      ctx.lineTo(size * 0.14, 0);
      ctx.lineTo(size * 0.38, size * 0.32);
      ctx.quadraticCurveTo(size * 0.32, size * 0.38, 0, size * 0.08);
      ctx.closePath();
      ctx.fillStyle = '#FF8533';
      ctx.fill();
      ctx.strokeStyle = '#D4500F';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.restore();

      const eyeX = -size * 0.3;
      const eyeY = -size * 0.05;
      const eyeR = size * 0.12;
      ctx.beginPath();
      ctx.arc(eyeX, eyeY, eyeR, 0, Math.PI * 2);
      ctx.fillStyle = 'white';
      ctx.fill();
      ctx.strokeStyle = '#D4500F';
      ctx.lineWidth = 0.8;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(eyeX + (energy * 2 - 1) * 2, eyeY, eyeR * 0.58, 0, Math.PI * 2);
      ctx.fillStyle = '#1a1a2e';
      ctx.fill();

      const mouthX = -size * 0.45;
      const mouthY = size * 0.06;
      ctx.beginPath();
      if (happy < 0.3) {
        const gasp = 2 + Math.sin(t * 4) * 1.3;
        ctx.ellipse(mouthX, mouthY, gasp, gasp * 1.2, 0, 0, Math.PI * 2);
        ctx.fillStyle = '#B8400A';
        ctx.fill();
      } else if (happy < 0.65) {
        ctx.moveTo(mouthX - 4, mouthY);
        ctx.lineTo(mouthX + 2, mouthY);
        ctx.strokeStyle = '#B8400A';
        ctx.lineWidth = 1.4;
        ctx.lineCap = 'round';
        ctx.stroke();
      } else {
        ctx.arc(mouthX + 2, mouthY - 2, 4 + happy * 3.8, 0.2, Math.PI - 0.2);
        ctx.strokeStyle = '#B8400A';
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.stroke();
      }

      ctx.restore();
    };

    const draw = () => {
      t += reducedMotion ? 0.002 : 0.016;
      ctx.clearRect(0, 0, stageWidth, stageHeight);

      const v = clamp(sliderValue / 100, 0, 1);
      const colorBand = Math.min(3, Math.floor(v * 4));
      const bandT = v * 4 - colorBand;

      const color = lerpColor(FISH_STAGES[colorBand].color, FISH_STAGES[Math.min(4, colorBand + 1)].color, bandT);
      const depth = lerpColor(FISH_STAGES[colorBand].depth, FISH_STAGES[Math.min(4, colorBand + 1)].depth, bandT);

      const scaleX = 0.4 + v * 1.8;
      const scaleY = 0.3 + v * 1.2;
      const centerX = stageWidth / 2;
      const centerY = stageHeight * 0.64 + (1 - v) * 24;

      drawRipples(centerX, centerY + 5, scaleX * 0.9, scaleY * 0.6, color, Math.max(1, Math.floor(1 + v * 4)));
      drawPuddle(centerX, centerY, scaleX, scaleY, color, depth);

      if (v > 0.2) {
        drawBubbles(centerX - 40 * scaleX, centerY - 20 * scaleY, Math.floor((v - 0.2) * 12), 26 * scaleX, color);
      }

      const energy = Math.min(1, v * 1.3);
      const happy = Math.min(1, v * 1.2);
      const fishSize = 18 + v * 24;
      const swimRadius = v * 55 * scaleX;
      const baseX = centerX - 15;
      const baseY = centerY - 12 * scaleY;
      const fishX = baseX + Math.sin(t * (0.3 + energy * 1.2)) * swimRadius;
      const fishY = baseY + Math.cos(t * (0.2 + energy * 0.8)) * swimRadius * 0.3 + (1 - energy) * 15;

      drawFish(fishX, fishY, fishSize, energy, happy);

      raf = window.requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener('resize', resize);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
    };
  }, [reducedMotion, sliderValue]);

  const previewStageIndex = getStageIndexFromSlider(sliderValue);

  return (
    <section className="lp-fish-widget-v2" aria-label="Learning state fish">
      <div className="lp-fish-canvas-shell">
        <canvas ref={canvasRef} className="lp-fish-canvas" role="img" aria-label="Live fish and puddle animation" />
      </div>

      <div className="lp-fish-controls-v2">
        <div className="lp-fish-level-strip">
          <p className="lp-fish-current-level">
            Current Level: <span>{liveStage.label}</span>
          </p>
          {previewMode && previewStageIndex !== liveStageIndex && (
            <p className="lp-fish-preview-level">Preview: {FISH_STAGES[previewStageIndex].label}</p>
          )}
        </div>

        <label htmlFor="fish-state-slider" className="sr-only">
          Preview fish state
        </label>
        <input
          id="fish-state-slider"
          type="range"
          min={0}
          max={100}
          step={1}
          value={Math.round(sliderValue)}
          onChange={(event) => {
            setPreviewMode(true);
            setIsPlaying(false);
            setSliderValue(Number(event.target.value));
          }}
          aria-label="Preview fish state"
          aria-valuetext={FISH_STAGES[previewStageIndex].label}
        />

        <div className="lp-fish-state-dots" role="list" aria-label="Progress states">
          {FISH_STAGES.map((stage, index) => {
            const isCurrent = index === liveStageIndex;
            const isPreview = index === previewStageIndex;
            return (
              <button
                key={stage.key}
                type="button"
                role="listitem"
                className={`lp-fish-dot ${isCurrent ? 'is-current' : 'is-muted'} ${isPreview ? 'is-preview' : ''}`}
                style={isCurrent ? { backgroundColor: stage.color, borderColor: stage.color } : undefined}
                onClick={() => {
                  setPreviewMode(true);
                  setIsPlaying(false);
                  setSliderValue(index * 25);
                }}
                aria-label={`${stage.label} state`}
              />
            );
          })}
        </div>

        <div className="lp-fish-stage-labels" aria-hidden="true">
          {FISH_STAGES.map((stage, index) => {
            const isCurrent = index === liveStageIndex;
            return (
              <div key={stage.key} className={`lp-fish-stage-label ${isCurrent ? 'is-current' : 'is-muted'}`}>
                <span className="lp-fish-stage-name">{stage.label}</span>
                <span className="lp-fish-stage-range">{getStageRangeLabel(stage)}</span>
              </div>
            );
          })}
        </div>

        <div className="lp-fish-actions-v2">
          <button
            type="button"
            onClick={() => {
              if (reducedMotion) return;
              setPreviewMode(true);
              setIsPlaying((prev) => !prev);
            }}
            disabled={reducedMotion}
            aria-label={isPlaying ? 'Pause animation' : 'Play animation'}
          >
            {reducedMotion ? 'Animation Off' : isPlaying ? 'Pause' : 'Play'}
          </button>
          <button
            type="button"
            onClick={() => {
              setIsPlaying(false);
              setPreviewMode(false);
              setSliderValue(liveSlider);
            }}
          >
            Live
          </button>
        </div>
      </div>
    </section>
  );
};
