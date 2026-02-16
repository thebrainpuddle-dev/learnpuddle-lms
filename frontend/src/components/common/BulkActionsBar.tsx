// src/components/common/BulkActionsBar.tsx

import React, { useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import {
  XMarkIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

export interface BulkAction {
  id: string;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  variant?: 'default' | 'danger' | 'success';
  requiresConfirmation?: boolean;
  confirmationMessage?: string;
}

interface BulkActionsBarProps {
  selectedCount: number;
  actions: BulkAction[];
  onAction: (actionId: string) => void;
  onClearSelection: () => void;
  isLoading?: boolean;
}

export const BulkActionsBar: React.FC<BulkActionsBarProps> = ({
  selectedCount,
  actions,
  onAction,
  onClearSelection,
  isLoading = false,
}) => {
  const [confirmAction, setConfirmAction] = useState<BulkAction | null>(null);

  if (selectedCount === 0) {
    return null;
  }

  const handleActionClick = (action: BulkAction) => {
    if (action.requiresConfirmation) {
      setConfirmAction(action);
    } else {
      onAction(action.id);
    }
  };

  const handleConfirm = () => {
    if (confirmAction) {
      onAction(confirmAction.id);
      setConfirmAction(null);
    }
  };

  const getButtonClasses = (variant: BulkAction['variant'] = 'default') => {
    const base =
      'inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
    switch (variant) {
      case 'danger':
        return `${base} bg-red-100 text-red-700 hover:bg-red-200`;
      case 'success':
        return `${base} bg-emerald-100 text-emerald-700 hover:bg-emerald-200`;
      default:
        return `${base} bg-gray-100 text-gray-700 hover:bg-gray-200`;
    }
  };

  return (
    <>
      {/* Bulk Actions Bar */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40">
        <div className="bg-white rounded-xl shadow-lg border border-gray-200 px-4 py-3 flex items-center gap-4">
          {/* Selection Count */}
          <div className="flex items-center gap-2">
            <span className="bg-emerald-100 text-emerald-700 font-semibold px-2.5 py-1 rounded-lg text-sm">
              {selectedCount}
            </span>
            <span className="text-sm text-gray-600">selected</span>
          </div>

          {/* Divider */}
          <div className="h-6 w-px bg-gray-200" />

          {/* Actions */}
          <div className="flex items-center gap-2">
            {actions.map((action) => {
              const Icon = action.icon;
              return (
                <button
                  key={action.id}
                  onClick={() => handleActionClick(action)}
                  disabled={isLoading}
                  className={getButtonClasses(action.variant)}
                >
                  {Icon && <Icon className="h-4 w-4" />}
                  {action.label}
                </button>
              );
            })}
          </div>

          {/* Divider */}
          <div className="h-6 w-px bg-gray-200" />

          {/* Clear Selection */}
          <button
            onClick={onClearSelection}
            disabled={isLoading}
            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            title="Clear selection"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Confirmation Dialog */}
      <Transition show={!!confirmAction} as={React.Fragment}>
        <Dialog
          as="div"
          className="relative z-50"
          onClose={() => setConfirmAction(null)}
        >
          <Transition.Child
            as={React.Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black bg-opacity-25" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4 text-center">
              <Transition.Child
                as={React.Fragment}
                enter="ease-out duration-300"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-200"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-white p-6 text-left align-middle shadow-xl transition-all">
                  <div className="flex items-center gap-3 mb-4">
                    <div className={`p-2 rounded-full ${
                      confirmAction?.variant === 'danger' 
                        ? 'bg-red-100' 
                        : 'bg-amber-100'
                    }`}>
                      <ExclamationTriangleIcon className={`h-6 w-6 ${
                        confirmAction?.variant === 'danger'
                          ? 'text-red-600'
                          : 'text-amber-600'
                      }`} />
                    </div>
                    <Dialog.Title
                      as="h3"
                      className="text-lg font-semibold text-gray-900"
                    >
                      Confirm Action
                    </Dialog.Title>
                  </div>

                  <p className="text-sm text-gray-500 mb-6">
                    {confirmAction?.confirmationMessage ||
                      `Are you sure you want to ${confirmAction?.label?.toLowerCase()} ${selectedCount} selected item${selectedCount > 1 ? 's' : ''}?`}
                  </p>

                  <div className="flex justify-end gap-3">
                    <button
                      type="button"
                      onClick={() => setConfirmAction(null)}
                      className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleConfirm}
                      className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
                        confirmAction?.variant === 'danger'
                          ? 'bg-red-600 hover:bg-red-700'
                          : 'bg-emerald-600 hover:bg-emerald-700'
                      }`}
                    >
                      {confirmAction?.label}
                    </button>
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>
    </>
  );
};
