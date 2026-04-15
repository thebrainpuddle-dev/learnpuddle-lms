// src/pages/student/SettingsPage.tsx

import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePageTitle } from '../../hooks/usePageTitle';
import api from '../../config/api';
import {
  ShieldCheckIcon,
  BellIcon,
  InformationCircleIcon,
  ChevronRightIcon,
  EnvelopeIcon,
  ChatBubbleLeftIcon,
} from '@heroicons/react/24/outline';

/** Keys accepted by the backend preferences_view (apps/users/views.py). */
type PrefKey =
  | 'email_courses'
  | 'email_assignments'
  | 'email_reminders'
  | 'email_announcements'
  | 'in_app_courses'
  | 'in_app_assignments'
  | 'in_app_reminders'
  | 'in_app_announcements';

type NotificationPrefs = Partial<Record<PrefKey, boolean>>;

interface ToggleConfig {
  key: PrefKey;
  label: string;
  description: string;
  icon: React.ForwardRefExoticComponent<
    React.SVGProps<SVGSVGElement> & { title?: string; titleId?: string }
  >;
}

const notificationToggles: ToggleConfig[] = [
  {
    key: 'email_courses',
    label: 'Course Updates',
    description: 'Get notified when new courses or content are available',
    icon: EnvelopeIcon,
  },
  {
    key: 'email_assignments',
    label: 'Assignment Reminders',
    description: 'Receive reminders for upcoming assignments and deadlines',
    icon: ChatBubbleLeftIcon,
  },
  {
    key: 'email_reminders',
    label: 'General Reminders',
    description: 'Get notified about general reminders and updates',
    icon: BellIcon,
  },
];

export const SettingsPage: React.FC = () => {
  usePageTitle('Settings');
  const navigate = useNavigate();

  const [prefs, setPrefs] = useState<NotificationPrefs>({});
  const [loading, setLoading] = useState(true);
  /** Tracks which keys are currently being saved so we can show per-toggle feedback. */
  const [saving, setSaving] = useState<Set<PrefKey>>(new Set());

  // Fetch current preferences on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get('/users/auth/preferences/');
        if (!cancelled) {
          setPrefs(res.data ?? {});
        }
      } catch {
        // If the endpoint is unreachable fall back to empty prefs — toggles
        // will default to "off" (false) and the user can still flip them.
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleToggle = useCallback(
    async (key: PrefKey) => {
      const newValue = !prefs[key];

      // Optimistic update.
      setPrefs((prev) => ({ ...prev, [key]: newValue }));
      setSaving((prev) => new Set(prev).add(key));

      try {
        const res = await api.patch('/users/auth/preferences/', { [key]: newValue });
        // Reconcile with server response to keep state accurate.
        setPrefs(res.data ?? {});
      } catch {
        // Revert on failure.
        setPrefs((prev) => ({ ...prev, [key]: !newValue }));
      } finally {
        setSaving((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    },
    [prefs],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Settings</h1>
        <p className="mt-1 text-[13px] text-slate-500">
          Manage your account security, notification preferences, and more
        </p>
      </div>

      <div className="max-w-2xl space-y-6">
        {/* Security Section */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
          <div className="px-5 py-4 sm:px-6">
            <h2 className="text-[15px] font-semibold text-slate-900 flex items-center gap-2">
              <ShieldCheckIcon className="h-5 w-5 text-indigo-600" />
              Security
            </h2>
            <p className="text-[13px] text-slate-500 mt-0.5">
              Manage your password and account security settings
            </p>
          </div>

          <div className="border-t border-slate-100">
            <button
              onClick={() => navigate('/student/settings/security')}
              className="w-full flex items-center justify-between px-5 py-4 sm:px-6 hover:bg-slate-50 transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-indigo-50 flex items-center justify-center">
                  <ShieldCheckIcon className="h-5 w-5 text-indigo-600" />
                </div>
                <div className="text-left">
                  <p className="text-[13px] font-medium text-slate-900">
                    Password & Authentication
                  </p>
                  <p className="text-[12px] text-slate-500">
                    Change your password, enable two-factor authentication
                  </p>
                </div>
              </div>
              <ChevronRightIcon className="h-5 w-5 text-slate-400 group-hover:text-indigo-600 transition-colors" />
            </button>
          </div>
        </div>

        {/* Notifications Section */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
          <div className="px-5 py-4 sm:px-6">
            <h2 className="text-[15px] font-semibold text-slate-900 flex items-center gap-2">
              <BellIcon className="h-5 w-5 text-indigo-600" />
              Notifications
            </h2>
            <p className="text-[13px] text-slate-500 mt-0.5">
              Choose what notifications you would like to receive
            </p>
          </div>

          <div className="border-t border-slate-100 divide-y divide-slate-100">
            {loading ? (
              <div className="px-5 py-6 sm:px-6 text-center">
                <div className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
                <p className="mt-2 text-[12px] text-slate-400">Loading preferences...</p>
              </div>
            ) : (
              notificationToggles.map((item) => {
                const checked = !!prefs[item.key];
                const isSaving = saving.has(item.key);

                return (
                  <div
                    key={item.key}
                    className="flex flex-col gap-3 px-5 py-4 sm:px-6 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-shrink-0 h-10 w-10 rounded-lg bg-slate-50 flex items-center justify-center mt-0.5">
                        <item.icon className="h-5 w-5 text-slate-400" />
                      </div>
                      <div>
                        <p className="text-[13px] font-medium text-slate-900">{item.label}</p>
                        <p className="text-[12px] text-slate-500">{item.description}</p>
                      </div>
                    </div>

                    {/* Functional toggle */}
                    <div className="flex-shrink-0">
                      <button
                        type="button"
                        role="switch"
                        aria-checked={checked}
                        disabled={isSaving}
                        onClick={() => handleToggle(item.key)}
                        className={`
                          relative inline-flex h-6 w-11 items-center rounded-full
                          transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2
                          ${checked ? 'bg-indigo-600' : 'bg-slate-200'}
                          ${isSaving ? 'opacity-60 cursor-wait' : 'cursor-pointer'}
                        `}
                      >
                        <span
                          className={`
                            inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-1 ring-slate-200/50
                            transition-transform duration-200 ease-in-out
                            ${checked ? 'translate-x-[22px]' : 'translate-x-[2px]'}
                          `}
                        />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* About Section */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
          <div className="px-5 py-4 sm:px-6">
            <h2 className="text-[15px] font-semibold text-slate-900 flex items-center gap-2">
              <InformationCircleIcon className="h-5 w-5 text-indigo-600" />
              About
            </h2>
          </div>

          <div className="border-t border-slate-100 divide-y divide-slate-100">
            <div className="flex items-center justify-between px-5 py-3.5 sm:px-6">
              <span className="text-[13px] text-slate-600">App Version</span>
              <span className="text-[13px] font-medium text-slate-900">1.0.0</span>
            </div>
            <div className="flex items-center justify-between px-5 py-3.5 sm:px-6">
              <span className="text-[13px] text-slate-600">Platform</span>
              <span className="text-[13px] font-medium text-slate-900">LearnPuddle LMS</span>
            </div>
            <div className="flex items-center justify-between px-5 py-3.5 sm:px-6">
              <span className="text-[13px] text-slate-600">Support</span>
              <a
                href="mailto:support@learnpuddle.com"
                className="text-[13px] font-medium text-indigo-600 hover:text-indigo-700 transition-colors"
              >
                support@learnpuddle.com
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
