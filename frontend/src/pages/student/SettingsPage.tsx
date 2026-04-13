// src/pages/student/SettingsPage.tsx

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  ShieldCheckIcon,
  BellIcon,
  InformationCircleIcon,
  ChevronRightIcon,
  EnvelopeIcon,
  ChatBubbleLeftIcon,
} from '@heroicons/react/24/outline';

export const SettingsPage: React.FC = () => {
  usePageTitle('Settings');
  const navigate = useNavigate();

  const notificationToggles = [
    {
      key: 'email_course_updates',
      label: 'Course Updates',
      description: 'Get notified when new courses or content are available',
      icon: EnvelopeIcon,
    },
    {
      key: 'email_assignment_reminders',
      label: 'Assignment Reminders',
      description: 'Receive reminders for upcoming assignments and deadlines',
      icon: ChatBubbleLeftIcon,
    },
    {
      key: 'email_grade_notifications',
      label: 'Grade Notifications',
      description: 'Get notified when your assignments are graded',
      icon: BellIcon,
    },
  ];

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
            {notificationToggles.map((item) => (
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

                {/* Visually disabled toggle with "Coming soon" tooltip */}
                <div className="relative group flex-shrink-0">
                  <label className="relative inline-flex items-center cursor-not-allowed">
                    <input
                      type="checkbox"
                      checked={false}
                      readOnly
                      disabled
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-200 rounded-full opacity-50 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all" />
                  </label>
                  {/* Tooltip */}
                  <div className="absolute bottom-full right-0 mb-2 hidden group-hover:block z-10">
                    <div className="bg-slate-800 text-white text-[11px] font-medium px-2.5 py-1.5 rounded-lg whitespace-nowrap shadow-lg">
                      Coming soon
                      <div className="absolute top-full right-4 -mt-px">
                        <div className="border-4 border-transparent border-t-slate-800" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
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
