// src/components/maic/AccessCodeGuard.tsx
//
// Wrapper component that conditionally shows the AccessCodeModal before granting
// access to child content. Caches successful access in sessionStorage per
// classroom so users are not repeatedly prompted during the same browser session.

import React, { useState, useCallback } from 'react';
import { AccessCodeModal } from './AccessCodeModal';
import { api } from '../../config/api';

interface AccessCodeGuardProps {
  /** Whether access code is required */
  requireCode: boolean;
  /** Classroom ID for validation */
  classroomId: string;
  /** Classroom title */
  classroomTitle?: string;
  /** Children to render when access is granted */
  children: React.ReactNode;
}

/** Session-storage key for caching a valid access per classroom */
function cacheKey(classroomId: string): string {
  return `maic-access-${classroomId}`;
}

/** Check whether access has already been granted in this session */
function hasCachedAccess(classroomId: string): boolean {
  try {
    return sessionStorage.getItem(cacheKey(classroomId)) === 'true';
  } catch {
    return false;
  }
}

/** Persist granted access for this session */
function setCachedAccess(classroomId: string): void {
  try {
    sessionStorage.setItem(cacheKey(classroomId), 'true');
  } catch {
    // sessionStorage may be unavailable in some contexts; silently ignore.
  }
}

export const AccessCodeGuard: React.FC<AccessCodeGuardProps> = ({
  requireCode,
  classroomId,
  classroomTitle,
  children,
}) => {
  const [granted, setGranted] = useState(() => !requireCode || hasCachedAccess(classroomId));
  const [modalOpen, setModalOpen] = useState(() => requireCode && !hasCachedAccess(classroomId));

  const handleSubmit = useCallback(
    async (code: string): Promise<boolean> => {
      try {
        await api.post(
          `/v1/teacher/maic/classrooms/${classroomId}/verify-access/`,
          { code },
        );
        // Successful verification
        setCachedAccess(classroomId);
        setGranted(true);
        setModalOpen(false);
        return true;
      } catch {
        return false;
      }
    },
    [classroomId],
  );

  const handleClose = useCallback(() => {
    setModalOpen(false);
  }, []);

  // If no code required or access granted, render children directly
  if (granted) {
    return <>{children}</>;
  }

  return (
    <>
      {/* Show a locked placeholder behind the modal */}
      <div className="flex items-center justify-center h-full bg-gray-50 text-gray-400">
        <p className="text-sm">This classroom requires an access code.</p>
      </div>

      <AccessCodeModal
        isOpen={modalOpen}
        classroomTitle={classroomTitle}
        onSubmit={handleSubmit}
        onClose={handleClose}
      />
    </>
  );
};
