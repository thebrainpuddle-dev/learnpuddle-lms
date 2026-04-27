// src/components/templates/BlueprintTreeView.tsx
//
// Read-only tree visualization for a course blueprint (module/content tree).
// Built standalone — does NOT depend on JsonDiffView from TASK-050.

import React, { useState } from 'react';
import {
  ChevronRightIcon,
  ChevronDownIcon,
  FolderIcon,
  FolderOpenIcon,
  DocumentTextIcon,
  VideoCameraIcon,
  QuestionMarkCircleIcon,
  PresentationChartBarIcon,
} from '@heroicons/react/24/outline';
import type { BlueprintJson, BlueprintModule, BlueprintContent } from '../../services/courseTemplatesService';

interface BlueprintTreeViewProps {
  blueprint: BlueprintJson;
  className?: string;
}

const CONTENT_TYPE_ICONS: Record<string, React.ElementType> = {
  VIDEO: VideoCameraIcon,
  QUIZ: QuestionMarkCircleIcon,
  SCORM: PresentationChartBarIcon,
};

function getContentIcon(contentType: string): React.ElementType {
  return CONTENT_TYPE_ICONS[contentType] ?? DocumentTextIcon;
}

function ContentRow({ content }: { content: BlueprintContent }) {
  const Icon = getContentIcon(content.content_type);
  const isPlaceholder =
    typeof content.meta_json === 'object' &&
    content.meta_json !== null &&
    (content.meta_json as Record<string, unknown>).is_placeholder === true;

  return (
    <li className="flex items-center gap-2 py-1 pl-8 text-sm text-gray-700">
      <Icon className="h-4 w-4 flex-shrink-0 text-gray-400" />
      <span className="truncate">{content.title}</span>
      <span className="ml-1 text-xs text-gray-400 uppercase">{content.content_type}</span>
      {isPlaceholder && (
        <span className="ml-1 rounded-sm bg-amber-100 px-1 text-[11px] font-medium text-amber-700">
          placeholder
        </span>
      )}
      {content.is_mandatory && (
        <span className="ml-1 rounded-sm bg-blue-100 px-1 text-[11px] font-medium text-blue-700">
          required
        </span>
      )}
    </li>
  );
}

function ModuleRow({ module: mod }: { module: BlueprintModule }) {
  const [open, setOpen] = useState(true);
  const ChevronIcon = open ? ChevronDownIcon : ChevronRightIcon;
  const FolderIconComp = open ? FolderOpenIcon : FolderIcon;
  const contentCount = mod.contents?.length ?? 0;

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm font-medium text-gray-800 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 transition-colors"
        aria-expanded={open}
      >
        <ChevronIcon className="h-4 w-4 flex-shrink-0 text-gray-400" />
        <FolderIconComp className="h-4 w-4 flex-shrink-0 text-primary-500" />
        <span className="truncate">{mod.title}</span>
        <span className="ml-auto text-xs text-gray-400">{contentCount} item{contentCount !== 1 ? 's' : ''}</span>
      </button>
      {open && contentCount > 0 && (
        <ul className="mt-0.5" role="list">
          {mod.contents.map((content, idx) => (
            <ContentRow key={idx} content={content} />
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * Renders a read-only module/content tree from a blueprint JSON object.
 *
 * @example
 * <BlueprintTreeView blueprint={template.blueprint_json} />
 */
export const BlueprintTreeView: React.FC<BlueprintTreeViewProps> = ({
  blueprint,
  className = '',
}) => {
  const modules = blueprint?.modules ?? [];
  const totalContents = modules.reduce(
    (sum, mod) => sum + (mod.contents?.length ?? 0),
    0,
  );

  if (modules.length === 0) {
    return (
      <div className={`rounded-lg border border-gray-200 bg-gray-50 p-4 text-center text-sm text-gray-500 ${className}`}>
        No modules defined in this blueprint.
      </div>
    );
  }

  return (
    <div className={`rounded-lg border border-gray-200 bg-white ${className}`}>
      <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Blueprint Structure
        </span>
        <span className="text-xs text-gray-400">
          {modules.length} module{modules.length !== 1 ? 's' : ''} · {totalContents} item{totalContents !== 1 ? 's' : ''}
        </span>
      </div>
      <ul className="p-2 space-y-0.5" role="tree">
        {modules.map((mod, idx) => (
          <ModuleRow key={idx} module={mod} />
        ))}
      </ul>
    </div>
  );
};
