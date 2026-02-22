import React from 'react';

interface GlassBadgeIconProps {
  level: 1 | 2 | 3 | 4 | 5;
  className?: string;
}

const baseClass = 'h-24 w-24';

export const GlassBadgeIcon: React.FC<GlassBadgeIconProps> = ({ level, className = '' }) => {
  const cls = `${baseClass} ${className}`.trim();

  if (level === 1) {
    return (
      <svg className={cls} viewBox="0 0 140 140" fill="none">
        <defs>
          <radialGradient id="g1bg" cx="0.3" cy="0.25" r="0.8">
            <stop stopColor="#1a3d3a" />
            <stop offset="1" stopColor="#0a1a18" />
          </radialGradient>
          <radialGradient id="g1hi" cx="0.3" cy="0.15" r="0.5">
            <stop stopColor="rgba(78,205,196,0.35)" />
            <stop offset="1" stopColor="transparent" />
          </radialGradient>
          <linearGradient id="g1bord" x1="20" y1="20" x2="120" y2="120">
            <stop stopColor="rgba(78,205,196,0.6)" />
            <stop offset="0.5" stopColor="rgba(78,205,196,0.1)" />
            <stop offset="1" stopColor="rgba(78,205,196,0.4)" />
          </linearGradient>
        </defs>
        <ellipse cx="70" cy="126" rx="36" ry="6" fill="rgba(78,205,196,0.08)" />
        <circle cx="70" cy="66" r="52" fill="url(#g1bg)" />
        <circle cx="70" cy="66" r="52" fill="url(#g1hi)" />
        <circle cx="70" cy="66" r="51" stroke="url(#g1bord)" strokeWidth="1.5" />
        <ellipse cx="56" cy="40" rx="22" ry="10" fill="rgba(255,255,255,0.06)" transform="rotate(-20 56 40)" />
        <path d="M70 34C70 34 54 50 54 60C54 69 61 76 70 76C79 76 86 69 86 60C86 50 70 34 70 34Z" fill="rgba(78,205,196,0.2)" stroke="#4ECDC4" strokeWidth="1.5" />
        <path d="M70 38C70 38 58 51 58 59C58 65 63 71 70 71" stroke="rgba(255,255,255,0.2)" strokeWidth="1" fill="none" strokeLinecap="round" />
        <ellipse cx="70" cy="90" rx="20" ry="5" stroke="#4ECDC4" strokeWidth="0.8" opacity="0.3" />
        <ellipse cx="70" cy="96" rx="28" ry="6" stroke="#4ECDC4" strokeWidth="0.5" opacity="0.15" />
      </svg>
    );
  }

  if (level === 2) {
    return (
      <svg className={cls} viewBox="0 0 140 140" fill="none">
        <defs>
          <radialGradient id="g2bg" cx="0.3" cy="0.25" r="0.8">
            <stop stopColor="#152e3d" />
            <stop offset="1" stopColor="#091820" />
          </radialGradient>
          <radialGradient id="g2hi" cx="0.3" cy="0.15" r="0.5">
            <stop stopColor="rgba(69,183,209,0.35)" />
            <stop offset="1" stopColor="transparent" />
          </radialGradient>
          <linearGradient id="g2bord" x1="20" y1="10" x2="120" y2="130">
            <stop stopColor="rgba(69,183,209,0.6)" />
            <stop offset="0.5" stopColor="rgba(69,183,209,0.08)" />
            <stop offset="1" stopColor="rgba(69,183,209,0.4)" />
          </linearGradient>
        </defs>
        <ellipse cx="70" cy="128" rx="34" ry="6" fill="rgba(69,183,209,0.08)" />
        <path d="M70 10L110 32V76C110 102 70 130 70 130C70 130 30 102 30 76V32L70 10Z" fill="url(#g2bg)" stroke="url(#g2bord)" strokeWidth="1.5" />
        <path d="M70 10L110 32V76C110 102 70 130 70 130" fill="url(#g2hi)" opacity="0.6" />
        <ellipse cx="54" cy="30" rx="20" ry="8" fill="rgba(255,255,255,0.05)" transform="rotate(-15 54 30)" />
        <polyline points="52,68 64,80 88,56" stroke="#45B7D1" strokeWidth="3.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points="52,68 64,80 88,56" stroke="rgba(255,255,255,0.15)" strokeWidth="5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points="52,68 64,80 88,56" stroke="#45B7D1" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  if (level === 3) {
    return (
      <svg className={cls} viewBox="0 0 140 140" fill="none">
        <defs>
          <radialGradient id="g3bg" cx="0.3" cy="0.25" r="0.8">
            <stop stopColor="#1a1840" />
            <stop offset="1" stopColor="#0c0b22" />
          </radialGradient>
          <radialGradient id="g3hi" cx="0.35" cy="0.2" r="0.5">
            <stop stopColor="rgba(108,99,255,0.3)" />
            <stop offset="1" stopColor="transparent" />
          </radialGradient>
        </defs>
        <ellipse cx="70" cy="128" rx="38" ry="6" fill="rgba(108,99,255,0.06)" />
        <path d="M70 8L118 34V90L70 132L22 90V34L70 8Z" fill="url(#g3bg)" stroke="rgba(108,99,255,0.35)" strokeWidth="1.5" />
        <path d="M70 8L118 34V90L70 132" fill="url(#g3hi)" opacity="0.5" />
        <ellipse cx="50" cy="28" rx="24" ry="10" fill="rgba(255,255,255,0.04)" transform="rotate(-20 50 28)" />
        <rect x="48" y="52" width="44" height="32" rx="3" fill="rgba(108,99,255,0.15)" stroke="#6C63FF" strokeWidth="2" />
        <line x1="70" y1="52" x2="70" y2="84" stroke="#6C63FF" strokeWidth="1" opacity="0.5" />
        <path d="M48 52C48 52 58 48 70 48C82 48 92 52 92 52" stroke="#6C63FF" strokeWidth="1.5" fill="none" />
        <circle cx="60" cy="100" r="3" fill="#6C63FF" opacity="0.4" />
        <circle cx="70" cy="104" r="4" fill="#6C63FF" opacity="0.5" />
        <circle cx="80" cy="100" r="3" fill="#6C63FF" opacity="0.4" />
      </svg>
    );
  }

  if (level === 4) {
    return (
      <svg className={cls} viewBox="0 0 140 140" fill="none">
        <defs>
          <radialGradient id="g4bg" cx="0.3" cy="0.25" r="0.8">
            <stop stopColor="#2d2510" />
            <stop offset="1" stopColor="#151005" />
          </radialGradient>
          <radialGradient id="g4hi" cx="0.3" cy="0.15" r="0.5">
            <stop stopColor="rgba(247,183,49,0.3)" />
            <stop offset="1" stopColor="transparent" />
          </radialGradient>
        </defs>
        <ellipse cx="70" cy="128" rx="38" ry="6" fill="rgba(247,183,49,0.06)" />
        <circle cx="70" cy="66" r="52" fill="url(#g4bg)" stroke="rgba(247,183,49,0.35)" strokeWidth="1.5" />
        <circle cx="70" cy="66" r="52" fill="url(#g4hi)" />
        <circle cx="70" cy="66" r="47" stroke="rgba(247,183,49,0.1)" strokeWidth="1" strokeDasharray="3 5" />
        <ellipse cx="52" cy="38" rx="22" ry="10" fill="rgba(255,255,255,0.05)" transform="rotate(-20 52 38)" />
        <circle cx="70" cy="62" r="20" stroke="#F7B731" strokeWidth="2" fill="rgba(247,183,49,0.08)" />
        <polygon points="70,44 74,60 70,54 66,60" fill="#F7B731" opacity="0.9" />
        <polygon points="70,80 66,64 70,70 74,64" fill="rgba(247,183,49,0.3)" />
        <polygon points="52,62 68,58 62,62 68,66" fill="rgba(247,183,49,0.3)" />
        <polygon points="88,62 72,66 78,62 72,58" fill="#F7B731" opacity="0.9" />
        <circle cx="70" cy="62" r="4" fill="rgba(247,183,49,0.4)" stroke="#F7B731" strokeWidth="1" />
        <circle cx="48" cy="98" r="3" fill="#F7B731" opacity="0.3" />
        <circle cx="58" cy="104" r="3.5" fill="#F7B731" opacity="0.4" />
        <circle cx="82" cy="104" r="3.5" fill="#F7B731" opacity="0.4" />
        <circle cx="92" cy="98" r="3" fill="#F7B731" opacity="0.3" />
      </svg>
    );
  }

  return (
    <svg className={cls} viewBox="0 0 140 140" fill="none">
      <defs>
        <radialGradient id="g5bg" cx="0.3" cy="0.25" r="0.8">
          <stop stopColor="#2d1515" />
          <stop offset="1" stopColor="#150808" />
        </radialGradient>
        <radialGradient id="g5hi" cx="0.3" cy="0.15" r="0.5">
          <stop stopColor="rgba(255,107,107,0.35)" />
          <stop offset="1" stopColor="transparent" />
        </radialGradient>
      </defs>
      <ellipse cx="70" cy="130" rx="40" ry="6" fill="rgba(255,107,107,0.06)" />
      <circle cx="70" cy="66" r="56" stroke="rgba(255,107,107,0.15)" strokeWidth="1" />
      <circle cx="70" cy="66" r="52" fill="url(#g5bg)" stroke="rgba(255,107,107,0.4)" strokeWidth="2" />
      <circle cx="70" cy="66" r="52" fill="url(#g5hi)" />
      <circle cx="70" cy="66" r="47" stroke="rgba(255,107,107,0.08)" strokeWidth="1" />
      <ellipse cx="50" cy="36" rx="24" ry="10" fill="rgba(255,255,255,0.06)" transform="rotate(-20 50 36)" />
      <path d="M42 76L50 54L62 66L70 44L78 66L90 54L98 76Z" fill="rgba(255,107,107,0.25)" stroke="#FF6B6B" strokeWidth="2" strokeLinejoin="round" />
      <rect x="42" y="76" width="56" height="12" rx="3" fill="rgba(255,107,107,0.2)" stroke="#FF6B6B" strokeWidth="1.5" />
      <circle cx="56" cy="82" r="2.5" fill="rgba(255,180,180,0.5)" />
      <circle cx="70" cy="82" r="3" fill="rgba(255,200,200,0.6)" stroke="rgba(255,255,255,0.1)" strokeWidth="0.5" />
      <circle cx="84" cy="82" r="2.5" fill="rgba(255,180,180,0.5)" />
      <circle cx="40" cy="100" r="2.5" fill="#FF6B6B" opacity="0.25" />
      <circle cx="50" cy="106" r="3" fill="#FF6B6B" opacity="0.35" />
      <circle cx="70" cy="110" r="3.5" fill="#FF6B6B" opacity="0.45" />
      <circle cx="90" cy="106" r="3" fill="#FF6B6B" opacity="0.35" />
      <circle cx="100" cy="100" r="2.5" fill="#FF6B6B" opacity="0.25" />
    </svg>
  );
};
