// src/components/teacher/CertificateButton.tsx

import React, { useState } from 'react';
import { DocumentArrowDownIcon, CheckBadgeIcon } from '@heroicons/react/24/outline';
import api from '../../config/api';

interface CertificateButtonProps {
  courseId: string;
  courseName?: string;
  isCompleted: boolean;
  disabled?: boolean;
  variant?: 'button' | 'link' | 'icon';
  className?: string;
}

export const CertificateButton: React.FC<CertificateButtonProps> = ({
  courseId,
  courseName,
  isCompleted,
  disabled = false,
  variant = 'button',
  className = '',
}) => {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!isCompleted || disabled || isDownloading) return;

    setIsDownloading(true);
    setError(null);

    try {
      const response = await api.get(`/teacher/courses/${courseId}/certificate/`, {
        responseType: 'blob',
      });

      // Create download link
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      // Extract filename from content-disposition header or use default
      const contentDisposition = response.headers['content-disposition'];
      let filename = `certificate_${courseName?.replace(/\s+/g, '_') || courseId}.pdf`;
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
        if (filenameMatch) {
          filename = filenameMatch[1];
        }
      }
      
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      const errorMessage = err.response?.data?.error || 'Failed to download certificate';
      setError(errorMessage);
      console.error('Certificate download error:', err);
    } finally {
      setIsDownloading(false);
    }
  };

  if (!isCompleted) {
    return null;
  }

  if (variant === 'icon') {
    return (
      <button
        onClick={handleDownload}
        disabled={disabled || isDownloading}
        className={`p-2 rounded-full hover:bg-emerald-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
        title="Download Certificate"
      >
        {isDownloading ? (
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
        ) : (
          <CheckBadgeIcon className="h-5 w-5 text-emerald-600" />
        )}
      </button>
    );
  }

  if (variant === 'link') {
    return (
      <button
        onClick={handleDownload}
        disabled={disabled || isDownloading}
        className={`inline-flex items-center gap-1 text-emerald-600 hover:text-emerald-700 font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
      >
        {isDownloading ? (
          <>
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
            Downloading...
          </>
        ) : (
          <>
            <CheckBadgeIcon className="h-4 w-4" />
            Download Certificate
          </>
        )}
      </button>
    );
  }

  return (
    <div className="space-y-2">
      <button
        onClick={handleDownload}
        disabled={disabled || isDownloading}
        className={`inline-flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium ${className}`}
      >
        {isDownloading ? (
          <>
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
            Generating...
          </>
        ) : (
          <>
            <DocumentArrowDownIcon className="h-5 w-5" />
            Download Certificate
          </>
        )}
      </button>
      {error && (
        <p className="text-sm text-red-600">{error}</p>
      )}
    </div>
  );
};
