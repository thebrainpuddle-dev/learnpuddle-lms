// src/components/maic/ai-elements/Artifact.tsx
//
// Container for code/design preview artifacts with toolbar actions.
// Compound component pattern for flexible layout composition.

import React from 'react';
import { X } from 'lucide-react';
import { cn } from '../../../lib/utils';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ArtifactProps {
  className?: string;
  children: React.ReactNode;
}

interface ArtifactHeaderProps {
  className?: string;
  children: React.ReactNode;
}

interface ArtifactContentProps {
  className?: string;
  children: React.ReactNode;
}

interface ArtifactCloseProps {
  onClick?: () => void;
}

interface ArtifactToolbarProps {
  className?: string;
  children: React.ReactNode;
}

interface ArtifactToolbarButtonProps {
  icon: React.ElementType;
  label: string;
  onClick?: () => void;
  active?: boolean;
}

// ─── Components ───────────────────────────────────────────────────────────────

export const Artifact: React.FC<ArtifactProps> = ({ className, children }) => (
  <div
    className={cn(
      'rounded-lg border border-gray-200 shadow-sm bg-white overflow-hidden',
      className,
    )}
  >
    {children}
  </div>
);

export const ArtifactHeader: React.FC<ArtifactHeaderProps> = ({ className, children }) => (
  <div
    className={cn(
      'flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200',
      className,
    )}
  >
    {children}
  </div>
);

export const ArtifactContent: React.FC<ArtifactContentProps> = ({ className, children }) => (
  <div className={cn('overflow-auto max-h-96', className)}>
    {children}
  </div>
);

export const ArtifactClose: React.FC<ArtifactCloseProps> = ({ onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-200 transition-colors"
    aria-label="Close artifact"
  >
    <X className="h-4 w-4" />
  </button>
);

export const ArtifactToolbar: React.FC<ArtifactToolbarProps> = ({ className, children }) => (
  <div
    className={cn(
      'flex items-center gap-1 px-2 py-1.5 bg-gray-50 border-t border-gray-200',
      className,
    )}
  >
    {children}
  </div>
);

export const ArtifactToolbarButton: React.FC<ArtifactToolbarButtonProps> = ({
  icon: Icon,
  label,
  onClick,
  active = false,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
      active
        ? 'bg-primary-100 text-primary-700'
        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100',
    )}
    aria-label={label}
  >
    <Icon className="h-3.5 w-3.5" />
    <span>{label}</span>
  </button>
);
