// course-editor/contentUtils.tsx
//
// Pure utility functions for content items (no state, no hooks).

import React from 'react';
import {
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
} from '@heroicons/react/24/outline';
import type { Content } from './types';

export const getContentIcon = (type: Content['content_type']) => {
  switch (type) {
    case 'VIDEO':
      return <PlayCircleIcon className="h-5 w-5 text-blue-500" />;
    case 'DOCUMENT':
      return <DocumentTextIcon className="h-5 w-5 text-orange-500" />;
    case 'LINK':
      return <LinkIcon className="h-5 w-5 text-purple-500" />;
    case 'AI_CLASSROOM':
      return <PlayCircleIcon className="h-5 w-5 text-indigo-500" />;
    case 'CHATBOT':
      return <DocumentTextIcon className="h-5 w-5 text-emerald-500" />;
    default:
      return <DocumentTextIcon className="h-5 w-5 text-gray-500" />;
  }
};
