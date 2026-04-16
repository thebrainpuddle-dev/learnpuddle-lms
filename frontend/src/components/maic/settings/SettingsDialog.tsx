// src/components/maic/settings/SettingsDialog.tsx
//
// Unified settings modal for the MAIC AI Classroom.
// Left sidebar with tabs, right content area. Uses motion/react for animation.

import React, { useState, useEffect, useCallback } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  X,
  Settings2,
  Volume2,
  Zap,
  Keyboard,
} from 'lucide-react';
import { cn } from '../../../lib/utils';
import { GeneralSettings } from './GeneralSettings';
import { AudioSettings } from './AudioSettings';

interface SettingsDialogProps {
  open: boolean;
  onClose: () => void;
}

type SettingsTab = 'general' | 'audio' | 'providers' | 'shortcuts';

const TABS: Array<{ id: SettingsTab; label: string; icon: React.ElementType }> = [
  { id: 'general', label: 'General', icon: Settings2 },
  { id: 'audio', label: 'Audio', icon: Volume2 },
  { id: 'providers', label: 'Providers', icon: Zap },
  { id: 'shortcuts', label: 'Keyboard Shortcuts', icon: Keyboard },
];

const SHORTCUTS: Array<{ key: string; description: string }> = [
  { key: 'Space', description: 'Play / Pause' },
  { key: 'Arrow Right', description: 'Next scene' },
  { key: 'Arrow Left', description: 'Previous scene' },
  { key: 'F', description: 'Toggle fullscreen' },
  { key: 'C', description: 'Toggle chat panel' },
  { key: 'W', description: 'Toggle whiteboard' },
  { key: 'S', description: 'Toggle scene sidebar' },
  { key: 'D', description: 'Toggle discussion' },
  { key: 'N', description: 'Toggle notes' },
  { key: '+ / -', description: 'Volume up / down' },
  { key: 'M', description: 'Mute / unmute' },
];

export const SettingsDialog = React.memo<SettingsDialogProps>(function SettingsDialog({
  open,
  onClose,
}) {
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');

  // ── Close on Escape ────────────────────────────────────────────────
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    },
    [onClose],
  );

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [open, handleKeyDown]);

  // ── Render tab content ─────────────────────────────────────────────
  function renderTabContent() {
    switch (activeTab) {
      case 'general':
        return <GeneralSettings />;
      case 'audio':
        return <AudioSettings />;
      case 'providers':
        return (
          <div className="flex items-center justify-center h-48">
            <div className="text-center">
              <Zap className="h-10 w-10 text-gray-300 mx-auto mb-3" />
              <p className="text-sm text-gray-500">
                Configure AI providers via your school admin settings.
              </p>
            </div>
          </div>
        );
      case 'shortcuts':
        return (
          <div>
            <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-4">
              Keyboard Shortcuts
            </h3>
            <div className="border border-gray-200 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left px-4 py-2 font-medium text-gray-600">Key</th>
                    <th className="text-left px-4 py-2 font-medium text-gray-600">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {SHORTCUTS.map((shortcut, i) => (
                    <tr
                      key={shortcut.key}
                      className={cn(
                        i < SHORTCUTS.length - 1 && 'border-b border-gray-100',
                      )}
                    >
                      <td className="px-4 py-2">
                        <kbd className="inline-flex items-center px-2 py-0.5 rounded bg-gray-100 border border-gray-200 text-xs font-mono text-gray-700">
                          {shortcut.key}
                        </kbd>
                      </td>
                      <td className="px-4 py-2 text-gray-600">{shortcut.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      default:
        return null;
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Dialog */}
          <motion.div
            className="relative w-full max-w-3xl max-h-[85vh] bg-white rounded-xl shadow-2xl overflow-hidden flex"
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            role="dialog"
            aria-modal="true"
            aria-label="Settings"
          >
            {/* Left sidebar */}
            <div className="w-52 flex-shrink-0 bg-gray-50 border-r border-gray-200 py-6 px-3">
              <h2 className="text-lg font-semibold text-gray-800 px-3 mb-4">Settings</h2>
              <nav className="space-y-1" aria-label="Settings tabs">
                {TABS.map((tab) => {
                  const Icon = tab.icon;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setActiveTab(tab.id)}
                      className={cn(
                        'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors text-left',
                        'focus:outline-none focus:ring-2 focus:ring-primary-500',
                        activeTab === tab.id
                          ? 'bg-primary-100 text-primary-700'
                          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-800',
                      )}
                      aria-current={activeTab === tab.id ? 'page' : undefined}
                    >
                      <Icon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                      {tab.label}
                    </button>
                  );
                })}
              </nav>
            </div>

            {/* Right content area */}
            <div className="flex-1 flex flex-col min-h-0">
              {/* Header with close button */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                <h3 className="text-base font-semibold text-gray-800">
                  {TABS.find((t) => t.id === activeTab)?.label}
                </h3>
                <button
                  type="button"
                  onClick={onClose}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
                  aria-label="Close settings"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Scrollable content */}
              <div className="flex-1 overflow-y-auto px-6 py-5">
                {renderTabContent()}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
});
