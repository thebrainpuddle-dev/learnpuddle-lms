// course-editor/ModuleContentEditor.tsx
//
// Content editing within a single module: composes ModuleDescription,
// ContentItemRow, AddContentForm, and the Module History accordion.

import React, { useState } from 'react';
import { ClockIcon, ChevronDownIcon } from '@heroicons/react/24/outline';
import type { Module } from './types';
import type { CourseEditorState } from './useCourseEditor';
import { RevisionHistoryPanel } from '../../../components/versioning/RevisionHistoryPanel';
import { ModuleDescription } from './ModuleDescription';
import { ContentItemRow } from './ContentItemRow';
import { AddContentForm } from './AddContentForm';

// Re-export for backward compatibility (index.tsx and other modules use this)
export { getContentIcon } from './contentUtils';

interface ModuleContentEditorProps {
  state: CourseEditorState;
  module: Module;
  moduleIndex: number;
}

export const ModuleContentEditor: React.FC<ModuleContentEditorProps> = ({
  state,
  module,
  moduleIndex: _moduleIndex,
}) => {
  const [historyOpen, setHistoryOpen] = useState(false);

  return (
    <div className="p-4 space-y-3">
      {/* Module Description */}
      <ModuleDescription state={state} module={module} />

      {/* Content Items */}
      {module.contents?.map((content) => (
        <ContentItemRow key={content.id} state={state} module={module} content={content} />
      ))}

      {/* Add Content Form / Trigger */}
      <AddContentForm state={state} module={module} />

      {/* Module Revision History */}
      <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
        <button
          type="button"
          onClick={() => setHistoryOpen((o) => !o)}
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
          aria-expanded={historyOpen}
        >
          <span className="flex items-center gap-2">
            <ClockIcon className="h-4 w-4 text-gray-400" />
            Module History
          </span>
          <ChevronDownIcon className={`h-4 w-4 text-gray-400 transition-transform ${historyOpen ? 'rotate-180' : ''}`} />
        </button>
        {historyOpen && (
          <div className="border-t border-gray-100 p-4">
            <RevisionHistoryPanel kind="module" objectId={module.id} />
          </div>
        )}
      </div>
    </div>
  );
};
