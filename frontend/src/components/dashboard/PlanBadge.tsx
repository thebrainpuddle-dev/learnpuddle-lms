// src/components/dashboard/PlanBadge.tsx
//
// Compact plan badge that opens a modal with full plan details, usage bars,
// and a link to billing. Replaces the large plan card on the dashboard.

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { CreditCard, X, Zap } from 'lucide-react';
import { Badge, Button, cn } from '../../design-system';
import { useTenantStore, TenantUsage } from '../../stores/tenantStore';

// ─── Types ───────────────────────────────────────────────────────────────────

interface PlanInfo {
  name: string;
  description: string;
}

const PLAN_INFO: Record<string, PlanInfo> = {
  FREE: { name: 'Free', description: 'Basic features for small schools getting started.' },
  STARTER: { name: 'Starter', description: 'Essential tools for growing schools.' },
  PRO: { name: 'Pro', description: 'Advanced features for established institutions.' },
  ENTERPRISE: { name: 'Enterprise', description: 'Full-featured plan with unlimited capacity and priority support.' },
};

// ─── Usage Bar (modal version) ───────────────────────────────────────────────

function ModalUsageBar({ label, used, limit, unit, color }: {
  label: string;
  used: number;
  limit: number;
  unit?: string;
  color: string;
}) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const isNearLimit = pct >= 80;

  return (
    <div>
      <div className="flex justify-between text-xs font-medium mb-1.5">
        <span className="text-content-secondary">{label}</span>
        <span className={cn('tabular-nums', isNearLimit ? 'text-danger' : 'text-content-muted')}>
          {used}{unit ? ` ${unit}` : ''} / {limit}{unit ? ` ${unit}` : ''}
        </span>
      </div>
      <div className="h-2 bg-surface rounded-full overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500',
            isNearLimit ? 'bg-danger' : color,
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export const PlanBadge: React.FC = () => {
  const navigate = useNavigate();
  const { plan, usage, limits } = useTenantStore();
  const [isOpen, setIsOpen] = useState(false);

  const planInfo = PLAN_INFO[plan.toUpperCase()] || { name: plan, description: 'Your current plan.' };

  // Close modal on Escape key
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setIsOpen(false);
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [isOpen]);

  return (
    <>
      {/* Compact Badge */}
      <button
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-1.5 group"
        title="Click to view plan details and usage"
      >
        <Badge
          variant={plan.toUpperCase() === 'FREE' ? 'neutral' : 'default'}
          size="lg"
          className="cursor-pointer group-hover:shadow-sm transition-shadow"
        >
          <CreditCard className="h-3 w-3" />
          {planInfo.name}
          <Zap className="h-3 w-3 opacity-60" />
        </Badge>
      </button>

      {/* Modal Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={() => setIsOpen(false)}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />

          {/* Modal Card */}
          <div
            className="relative bg-surface-card rounded-2xl border border-surface-border shadow-xl w-full max-w-md animate-in fade-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-5 border-b border-surface-border">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-accent-50 flex items-center justify-center">
                  <CreditCard className="h-5 w-5 text-accent" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-content">{planInfo.name} Plan</h3>
                  <p className="text-xs text-content-secondary">{planInfo.description}</p>
                </div>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1.5 rounded-lg hover:bg-surface transition-colors"
                title="Close"
              >
                <X className="h-4 w-4 text-content-muted" />
              </button>
            </div>

            {/* Usage Bars */}
            <div className="p-5 space-y-4">
              {usage && limits ? (
                <>
                  <ModalUsageBar
                    label="Teachers"
                    used={usage.teachers.used}
                    limit={usage.teachers.limit}
                    color="bg-accent"
                  />
                  <ModalUsageBar
                    label="Courses"
                    used={usage.courses.used}
                    limit={usage.courses.limit}
                    color="bg-success"
                  />
                  <ModalUsageBar
                    label="Storage"
                    used={usage.storage_mb.used}
                    limit={usage.storage_mb.limit}
                    unit="MB"
                    color="bg-warning"
                  />
                </>
              ) : (
                <p className="text-sm text-content-muted text-center py-4">
                  Usage information unavailable
                </p>
              )}
            </div>

            {/* Footer */}
            <div className="p-5 pt-0">
              <Button
                variant="primary"
                className="w-full"
                onClick={() => {
                  setIsOpen(false);
                  navigate('/admin/billing');
                }}
                icon={<CreditCard className="h-4 w-4" />}
              >
                {plan.toUpperCase() === 'FREE' ? 'Upgrade Plan' : 'Manage Plan'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
