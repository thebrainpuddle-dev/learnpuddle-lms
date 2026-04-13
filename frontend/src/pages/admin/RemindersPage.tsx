import React, { useState, useCallback } from 'react';
import { usePageTitle } from '../../hooks/usePageTitle';
import { RulesSection } from '../../components/reminders/RulesSection';
import { ManualSendSection } from '../../components/reminders/ManualSendSection';
import { HistorySection } from '../../components/reminders/HistorySection';
import {
  CpuChipIcon,
  PaperAirplaneIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';

// ─── Types ──────────────────────────────────────────────────────────────────

type Tab = 'rules' | 'manual' | 'history';

interface TabConfig {
  id: Tab;
  label: string;
  icon: React.ElementType;
}

const TABS: TabConfig[] = [
  { id: 'rules', label: 'Rules', icon: CpuChipIcon },
  { id: 'manual', label: 'Manual Send', icon: PaperAirplaneIcon },
  { id: 'history', label: 'History', icon: ClockIcon },
];

// ─── Component ──────────────────────────────────────────────────────────────

export const RemindersPage: React.FC = () => {
  usePageTitle('Reminders');
  const [activeTab, setActiveTab] = useState<Tab>('rules');
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  const handleReminderSent = useCallback(() => {
    // Bump the key so HistorySection refetches when user switches to History tab
    setHistoryRefreshKey((k) => k + 1);
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Reminders</h1>
        <p className="mt-1 text-sm text-gray-500">
          Configure automated reminder rules, send manual reminders, and review history.
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-6" aria-label="Reminder sections">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                  isActive
                    ? 'border-primary-600 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === 'rules' && <RulesSection />}
      {activeTab === 'manual' && <ManualSendSection onSent={handleReminderSent} />}
      {activeTab === 'history' && <HistorySection refreshKey={historyRefreshKey} />}
    </div>
  );
};
