// src/components/common/Loading.tsx

import React from 'react';

interface LoadingProps {
  fullScreen?: boolean;
  message?: string;
}

export const Loading: React.FC<LoadingProps> = ({
  fullScreen = false,
  message = 'Loading...',
}) => {
  const content = (
    <div className="flex flex-col items-center justify-center">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      {message && <p className="mt-4 text-gray-600">{message}</p>}
    </div>
  );
  
  if (fullScreen) {
    return <div className="min-h-screen flex items-center justify-center">{content}</div>;
  }
  
  return <div className="p-8">{content}</div>;
};
