// src/pages/student/StudentMAICCreatePage.tsx
//
// Student AI Classroom creation page — same wizard flow as teacher
// but with guardrail validation on topic/PDF before generation.
//
// The wizard itself owns the step state; the "Meet your classroom" agent
// picker (WS-C) is inserted between Topic/Config and Review-Outline inside
// StudentGenerationWizard with role="student". This page stays a thin
// wrapper so non-wizard pages can reuse StudentGenerationWizard as-is.

import React, { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePageTitle } from '../../hooks/usePageTitle';
import { StudentGenerationWizard } from '../../components/maic/StudentGenerationWizard';

const ArrowLeftIcon = () => (
  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
  </svg>
);

export const StudentMAICCreatePage: React.FC = () => {
  usePageTitle('New AI Classroom');
  const navigate = useNavigate();

  const handleComplete = useCallback(
    (classroomId: string) => {
      navigate(`/student/ai-classroom/${classroomId}`);
    },
    [navigate],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/student/ai-classroom')}
          className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
        >
          <ArrowLeftIcon />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">New AI Classroom</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Generate an interactive AI classroom from any educational topic
          </p>
        </div>
      </div>

      <StudentGenerationWizard onComplete={handleComplete} />
    </div>
  );
};
