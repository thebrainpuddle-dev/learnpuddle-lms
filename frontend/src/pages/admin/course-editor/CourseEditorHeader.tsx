// course-editor/CourseEditorHeader.tsx
//
// Top bar with back navigation, title, publish toggle, and save button.

import React from 'react';
import { Button } from '../../../components/common';
import {
  ArrowLeftIcon,
  EyeIcon,
  GlobeAltIcon,
} from '@heroicons/react/24/outline';
import type { CourseEditorState } from './useCourseEditor';

interface CourseEditorHeaderProps {
  state: CourseEditorState;
}

export const CourseEditorHeader: React.FC<CourseEditorHeaderProps> = ({
  state,
}) => {
  const {
    isEditing,
    isTeacherAuthoring,
    canManageAssignments,
    courseListPath,
    navigate,
    course,
    handleSaveCourse,
    courseMutationPending,
    publishMutation,
  } = state;

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center">
        <button
          onClick={() => navigate(courseListPath)}
          className="mr-4 p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
          aria-label="Back to course list"
        >
          <ArrowLeftIcon className="h-5 w-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {isTeacherAuthoring
              ? isEditing
                ? 'Edit Authored Course'
                : 'Create Authored Course'
              : isEditing
              ? 'Edit Course'
              : 'Create Course'}
          </h1>
          <p className="mt-1 text-gray-500">
            {isTeacherAuthoring
              ? isEditing
                ? 'Update your draft course content'
                : 'Create a draft course with modules and rich lessons'
              : isEditing
              ? 'Update course details and content'
              : 'Set up a new training course'}
          </p>
        </div>
      </div>

      <div className="flex items-center space-x-3">
        {isEditing && canManageAssignments && (
          <>
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                course?.is_published
                  ? 'bg-green-100 text-green-800'
                  : 'bg-yellow-100 text-yellow-800'
              }`}
            >
              {course?.is_published ? 'Published' : 'Draft'}
            </span>
            <Button
              variant="outline"
              onClick={() =>
                publishMutation.mutate(!course?.is_published)
              }
              loading={publishMutation.isPending}
            >
              {course?.is_published ? (
                <>
                  <EyeIcon className="h-4 w-4 mr-1.5" /> Unpublish
                </>
              ) : (
                <>
                  <GlobeAltIcon className="h-4 w-4 mr-1.5" /> Publish
                </>
              )}
            </Button>
          </>
        )}
        <Button
          variant="primary"
          onClick={handleSaveCourse}
          loading={courseMutationPending}
        >
          {isEditing ? 'Save Changes' : 'Create Course'}
        </Button>
      </div>
    </div>
  );
};
