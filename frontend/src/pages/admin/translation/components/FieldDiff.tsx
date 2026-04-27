// src/pages/admin/translation/components/FieldDiff.tsx
// Side-by-side source vs translated field with Approve / Reject / Edit actions.
// Per-field review state is local (no backend approve/reject endpoints exist).

import React, { useState } from 'react';
import {
  CheckCircleIcon,
  XCircleIcon,
  PencilSquareIcon,
  CheckIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import type { FieldReviewStatus } from '../../../../stores/translationStore';

interface FieldDiffProps {
  fieldKey: string;
  fieldLabel: string;
  sourceText: string;
  translatedText: string;
  reviewStatus: FieldReviewStatus;
  editedText: string | null;
  onApprove: () => void;
  onReject: () => void;
  onSaveEdit: (text: string) => void;
}

export const FieldDiff: React.FC<FieldDiffProps> = ({
  fieldKey,
  fieldLabel,
  sourceText,
  translatedText,
  reviewStatus,
  editedText,
  onApprove,
  onReject,
  onSaveEdit,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [draftText, setDraftText] = useState('');

  const displayText = editedText !== null ? editedText : translatedText;

  const handleEditStart = () => {
    setDraftText(displayText);
    setIsEditing(true);
  };

  const handleEditSave = () => {
    onSaveEdit(draftText);
    setIsEditing(false);
  };

  const handleEditCancel = () => {
    setIsEditing(false);
    setDraftText('');
  };

  const statusColors = {
    pending: 'bg-white border-gray-200',
    approved: 'bg-emerald-50 border-emerald-200',
    rejected: 'bg-red-50 border-red-200',
  };

  return (
    <div
      data-testid={`field-diff-${fieldKey}`}
      className={`rounded-lg border p-4 transition-colors ${statusColors[reviewStatus]}`}
    >
      {/* Field header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          {fieldLabel}
        </h3>
        <div className="flex items-center gap-1.5">
          {reviewStatus === 'approved' && (
            <span
              data-testid={`status-approved-${fieldKey}`}
              className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600"
            >
              <CheckCircleIcon className="h-4 w-4" />
              Approved
            </span>
          )}
          {reviewStatus === 'rejected' && (
            <span
              data-testid={`status-rejected-${fieldKey}`}
              className="inline-flex items-center gap-1 text-xs font-medium text-red-600"
            >
              <XCircleIcon className="h-4 w-4" />
              Rejected
            </span>
          )}
        </div>
      </div>

      {/* Two-column source / translated */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        {/* Source */}
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">
            Source (English)
          </p>
          <div
            data-testid={`source-text-${fieldKey}`}
            className="rounded bg-gray-50 border border-gray-200 p-2 text-sm text-gray-700 whitespace-pre-wrap min-h-[3rem]"
          >
            {sourceText || <span className="text-gray-400 italic">Empty</span>}
          </div>
        </div>

        {/* Translated */}
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">
            Translated
          </p>
          {isEditing ? (
            <textarea
              data-testid={`edit-textarea-${fieldKey}`}
              value={draftText}
              onChange={(e) => setDraftText(e.target.value)}
              className="w-full rounded border border-primary-400 p-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-primary-500 resize-y min-h-[3rem]"
              autoFocus
            />
          ) : (
            <div
              data-testid={`translated-text-${fieldKey}`}
              className="rounded bg-gray-50 border border-gray-200 p-2 text-sm text-gray-700 whitespace-pre-wrap min-h-[3rem]"
            >
              {displayText || (
                <span className="text-gray-400 italic">No translation</span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {isEditing ? (
          <>
            <button
              type="button"
              data-testid={`save-edit-btn-${fieldKey}`}
              onClick={handleEditSave}
              className="cursor-pointer inline-flex items-center gap-1 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <CheckIcon className="h-3.5 w-3.5" />
              Save
            </button>
            <button
              type="button"
              data-testid={`cancel-edit-btn-${fieldKey}`}
              onClick={handleEditCancel}
              className="cursor-pointer inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-400"
            >
              <XMarkIcon className="h-3.5 w-3.5" />
              Cancel
            </button>
          </>
        ) : (
          <>
            {reviewStatus !== 'approved' && (
              <button
                type="button"
                data-testid={`approve-btn-${fieldKey}`}
                onClick={onApprove}
                className="cursor-pointer inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              >
                <CheckCircleIcon className="h-3.5 w-3.5" />
                Approve
              </button>
            )}
            {reviewStatus !== 'rejected' && (
              <button
                type="button"
                data-testid={`reject-btn-${fieldKey}`}
                onClick={onReject}
                className="cursor-pointer inline-flex items-center gap-1 rounded-lg border border-red-300 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500"
              >
                <XCircleIcon className="h-3.5 w-3.5" />
                Reject
              </button>
            )}
            <button
              type="button"
              data-testid={`edit-btn-${fieldKey}`}
              onClick={handleEditStart}
              className="cursor-pointer inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-400"
            >
              <PencilSquareIcon className="h-3.5 w-3.5" />
              Edit
            </button>
          </>
        )}
      </div>
    </div>
  );
};
