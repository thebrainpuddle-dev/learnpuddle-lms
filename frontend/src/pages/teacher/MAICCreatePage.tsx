// src/pages/teacher/MAICCreatePage.tsx
//
// Full-page wrapper for the GenerationWizard.
// On completion, navigates to the AI Classroom player.

import React, { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePageTitle } from '../../hooks/usePageTitle';
import { GenerationWizard } from '../../components/maic/GenerationWizard';

const ArrowLeftIcon = () => (
  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
  </svg>
);

export const MAICCreatePage: React.FC = () => {
  usePageTitle('New AI Classroom');
  const navigate = useNavigate();

  const handleComplete = useCallback(
    (classroomId: string) => {
      navigate(`/teacher/ai-classroom/${classroomId}`);
    },
    [navigate],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/teacher/ai-classroom')}
          className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
        >
          <ArrowLeftIcon />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">New AI Classroom</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Configure and generate an AI-powered interactive classroom
          </p>
        </div>
      </div>

      {/* Wizard */}
      <GenerationWizard onComplete={handleComplete} />
    </div>
  );
};
