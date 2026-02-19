import React, { Fragment, useRef } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';

interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning';
  loading?: boolean;
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  loading = false,
}) => {
  const cancelRef = useRef<HTMLButtonElement>(null);

  const iconBg = variant === 'danger' ? 'bg-red-100' : 'bg-amber-100';
  const iconColor = variant === 'danger' ? 'text-red-600' : 'text-amber-600';
  const confirmBg =
    variant === 'danger'
      ? 'bg-red-600 hover:bg-red-700 focus-visible:outline-red-600'
      : 'bg-amber-600 hover:bg-amber-700 focus-visible:outline-amber-600';

  return (
    <Transition show={isOpen} as={Fragment}>
      <Dialog
        as="div"
        className="relative z-50"
        initialFocus={cancelRef}
        onClose={onClose}
      >
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/40" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-white p-6 shadow-xl transition-all">
                <div className="flex items-start gap-4">
                  <div className={`flex-shrink-0 p-2 rounded-full ${iconBg}`}>
                    <ExclamationTriangleIcon className={`h-6 w-6 ${iconColor}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <Dialog.Title className="text-lg font-semibold text-gray-900">
                      {title}
                    </Dialog.Title>
                    <p className="mt-2 text-sm text-gray-500">{message}</p>
                  </div>
                </div>

                <div className="mt-6 flex justify-end gap-3">
                  <button
                    ref={cancelRef}
                    type="button"
                    onClick={onClose}
                    disabled={loading}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-400"
                  >
                    {cancelLabel}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      onConfirm();
                      onClose();
                    }}
                    disabled={loading}
                    className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors focus:outline-none focus-visible:ring-2 ${confirmBg} ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    {loading ? 'Processing...' : confirmLabel}
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
};
