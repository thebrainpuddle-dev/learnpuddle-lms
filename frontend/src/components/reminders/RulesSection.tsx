import React, { useState, useCallback } from 'react';
import {
  ClockIcon,
  BellAlertIcon,
  AcademicCapIcon,
  ShieldCheckIcon,
  ClipboardDocumentListIcon,
  PlusIcon,
  PencilIcon,
  CheckIcon,
} from '@heroicons/react/24/outline';

// ─── Types ──────────────────────────────────────────────────────────────────

type RuleType =
  | 'DEADLINE_APPROACHING'
  | 'COURSE_INCOMPLETE'
  | 'CERT_EXPIRING'
  | 'ASSIGNMENT_OVERDUE';

interface ReminderRule {
  id: string;
  type: RuleType;
  description: string;
  triggerDays: number;
  triggerLabel: string;
  isActive: boolean;
}

// ─── Default rules ──────────────────────────────────────────────────────────

const DEFAULT_RULES: ReminderRule[] = [
  {
    id: 'rule-deadline-3d',
    type: 'DEADLINE_APPROACHING',
    description: 'Course deadline approaching',
    triggerDays: 3,
    triggerLabel: '3 days before deadline',
    isActive: true,
  },
  {
    id: 'rule-deadline-1d',
    type: 'DEADLINE_APPROACHING',
    description: 'Course deadline imminent',
    triggerDays: 1,
    triggerLabel: '1 day before deadline',
    isActive: true,
  },
  {
    id: 'rule-incomplete-weekly',
    type: 'COURSE_INCOMPLETE',
    description: 'Weekly digest for incomplete courses',
    triggerDays: 7,
    triggerLabel: 'Every 7 days',
    isActive: true,
  },
  {
    id: 'rule-cert-30d',
    type: 'CERT_EXPIRING',
    description: 'Certification expiry warning',
    triggerDays: 30,
    triggerLabel: '30 days before expiry',
    isActive: true,
  },
  {
    id: 'rule-cert-7d',
    type: 'CERT_EXPIRING',
    description: 'Certification expiry urgent',
    triggerDays: 7,
    triggerLabel: '7 days before expiry',
    isActive: true,
  },
  {
    id: 'rule-overdue-1d',
    type: 'ASSIGNMENT_OVERDUE',
    description: 'Assignment overdue notification',
    triggerDays: 1,
    triggerLabel: '1 day after due date',
    isActive: false,
  },
];

// ─── Helpers ────────────────────────────────────────────────────────────────

const RULE_META: Record<RuleType, { icon: React.ElementType; color: string; bg: string }> = {
  DEADLINE_APPROACHING: { icon: ClockIcon, color: 'text-orange-600', bg: 'bg-orange-100' },
  COURSE_INCOMPLETE: { icon: AcademicCapIcon, color: 'text-blue-600', bg: 'bg-blue-100' },
  CERT_EXPIRING: { icon: ShieldCheckIcon, color: 'text-purple-600', bg: 'bg-purple-100' },
  ASSIGNMENT_OVERDUE: { icon: ClipboardDocumentListIcon, color: 'text-red-600', bg: 'bg-red-100' },
};

// ─── Component ──────────────────────────────────────────────────────────────

export const RulesSection: React.FC = () => {
  const [rules, setRules] = useState<ReminderRule[]>(DEFAULT_RULES);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDays, setEditDays] = useState<string>('');

  const toggleRule = useCallback((id: string) => {
    // TODO: Call API to toggle rule active state
    setRules((prev) =>
      prev.map((r) => (r.id === id ? { ...r, isActive: !r.isActive } : r))
    );
  }, []);

  const startEdit = useCallback((rule: ReminderRule) => {
    setEditingId(rule.id);
    setEditDays(String(rule.triggerDays));
  }, []);

  const saveEdit = useCallback(
    (id: string) => {
      const days = parseInt(editDays, 10);
      if (isNaN(days) || days < 1) return;
      // TODO: Call API to update trigger days
      setRules((prev) =>
        prev.map((r) => {
          if (r.id !== id) return r;
          const unit =
            r.type === 'COURSE_INCOMPLETE'
              ? `Every ${days} days`
              : r.type === 'ASSIGNMENT_OVERDUE'
              ? `${days} day${days > 1 ? 's' : ''} after due date`
              : `${days} day${days > 1 ? 's' : ''} before ${
                  r.type === 'CERT_EXPIRING' ? 'expiry' : 'deadline'
                }`;
          return { ...r, triggerDays: days, triggerLabel: unit };
        })
      );
      setEditingId(null);
    },
    [editDays]
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Automated Rules</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Configure when reminders are automatically sent.
          </p>
        </div>
        <button
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-primary-700 bg-primary-50 rounded-lg hover:bg-primary-100 transition-colors"
          onClick={() => {
            // TODO: Open a modal to create a custom rule
          }}
        >
          <PlusIcon className="h-4 w-4" />
          Add Custom Rule
        </button>
      </div>

      <div className="divide-y divide-gray-100 border border-gray-200 rounded-xl bg-white">
        {rules.map((rule) => {
          const meta = RULE_META[rule.type];
          const Icon = meta.icon;
          const isEditing = editingId === rule.id;

          return (
            <div
              key={rule.id}
              className="flex items-center gap-4 px-4 py-3.5 hover:bg-gray-50/50 transition-colors"
            >
              {/* Icon */}
              <div className={`flex-shrink-0 p-2 rounded-lg ${meta.bg}`}>
                <Icon className={`h-5 w-5 ${meta.color}`} />
              </div>

              {/* Description */}
              <div className="flex-1 min-w-0">
                <div className="font-medium text-gray-900 text-sm">{rule.description}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  {isEditing ? (
                    <div className="flex items-center gap-1.5">
                      <input
                        type="number"
                        min={1}
                        value={editDays}
                        onChange={(e) => setEditDays(e.target.value)}
                        className="w-16 px-2 py-0.5 text-xs border border-gray-300 rounded focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveEdit(rule.id);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        autoFocus
                      />
                      <span className="text-xs text-gray-500">days</span>
                      <button
                        onClick={() => saveEdit(rule.id)}
                        className="p-0.5 text-green-600 hover:text-green-700"
                      >
                        <CheckIcon className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <BellAlertIcon className="h-3.5 w-3.5 text-gray-400" />
                      <span className="text-xs text-gray-500">{rule.triggerLabel}</span>
                      <button
                        onClick={() => startEdit(rule)}
                        className="p-0.5 text-gray-400 hover:text-gray-600"
                        title="Edit trigger days"
                      >
                        <PencilIcon className="h-3 w-3" />
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Toggle */}
              <button
                role="switch"
                aria-checked={rule.isActive}
                onClick={() => toggleRule(rule.id)}
                className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 ${
                  rule.isActive ? 'bg-primary-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    rule.isActive ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};
