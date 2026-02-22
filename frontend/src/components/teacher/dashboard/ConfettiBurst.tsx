import React from 'react';

interface ConfettiBurstProps {
  active: boolean;
}

const COLORS = ['#4ECDC4', '#45B7D1', '#6C63FF', '#F7B731', '#FF6B6B'];

export const ConfettiBurst: React.FC<ConfettiBurstProps> = ({ active }) => {
  if (!active) return null;

  return (
    <div className="pointer-events-none fixed inset-0 z-[90] overflow-hidden">
      {Array.from({ length: 42 }).map((_, index) => {
        const left = 10 + Math.random() * 80;
        const delay = Math.random() * 120;
        const duration = 900 + Math.random() * 700;
        const color = COLORS[index % COLORS.length];
        const size = 6 + Math.random() * 7;
        return (
          <span
            key={index}
            className="absolute rounded-sm"
            style={{
              left: `${left}%`,
              top: '-16px',
              width: `${size}px`,
              height: `${size * 0.55}px`,
              background: color,
              transform: `rotate(${Math.random() * 360}deg)`,
              animation: `lp-confetti-fall ${duration}ms ease-out ${delay}ms forwards`,
            }}
          />
        );
      })}
      <style>{`
        @keyframes lp-confetti-fall {
          0% { opacity: 1; transform: translate3d(0, 0, 0) rotate(0deg); }
          100% { opacity: 0; transform: translate3d(-20px, 95vh, 0) rotate(420deg); }
        }
      `}</style>
    </div>
  );
};
