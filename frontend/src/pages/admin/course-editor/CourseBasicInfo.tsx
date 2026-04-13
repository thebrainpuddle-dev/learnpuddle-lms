// course-editor/CourseBasicInfo.tsx
//
// Details tab: title, description, estimated hours, deadline, mandatory flag,
// and thumbnail upload.

import React from 'react';
import { Input } from '../../../components/common';
import { PhotoIcon } from '@heroicons/react/24/outline';
import type { CourseEditorState } from './useCourseEditor';

interface CourseBasicInfoProps {
  state: CourseEditorState;
}

export const CourseBasicInfo: React.FC<CourseBasicInfoProps> = ({ state }) => {
  const {
    formData,
    handleInputChange,
    thumbnailPreview,
    thumbnailInputRef,
    handleThumbnailChange,
  } = state;

  return (
    <div data-tour="admin-course-details-panel" className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Basic Information
          </h2>

          <div className="space-y-4">
            <Input
              label="Course Title"
              name="title"
              value={formData.title}
              onChange={handleInputChange}
              placeholder="e.g., Classroom Management 101"
              required
            />

            <div>
              <label
                htmlFor="course-description"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Description
              </label>
              <textarea
                id="course-description"
                name="description"
                value={formData.description}
                onChange={handleInputChange}
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                placeholder="Describe what teachers will learn..."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Estimated Hours"
                name="estimated_hours"
                type="number"
                min="0"
                step="0.5"
                value={formData.estimated_hours}
                onChange={handleInputChange}
              />

              <Input
                label="Deadline (Optional)"
                name="deadline"
                type="date"
                value={formData.deadline}
                onChange={handleInputChange}
              />
            </div>

            <div className="flex items-center">
              <input
                type="checkbox"
                id="is_mandatory"
                name="is_mandatory"
                checked={formData.is_mandatory}
                onChange={handleInputChange}
                className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
              />
              <label
                htmlFor="is_mandatory"
                className="ml-2 text-sm text-gray-700"
              >
                This is a mandatory course for assigned teachers
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* Thumbnail */}
      <div className="lg:col-span-1">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Thumbnail
          </h2>

          <div
            className="aspect-video border-2 border-dashed border-gray-300 rounded-lg flex items-center justify-center overflow-hidden bg-gray-50 cursor-pointer hover:border-primary-500 transition-colors"
            role="button"
            tabIndex={0}
            aria-label="Upload course thumbnail"
            onClick={() => thumbnailInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                thumbnailInputRef.current?.click();
              }
            }}
          >
            {thumbnailPreview ? (
              <img
                src={thumbnailPreview}
                alt="Thumbnail preview"
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="text-center">
                <PhotoIcon className="h-12 w-12 mx-auto text-gray-400 mb-2" />
                <p className="text-sm text-gray-500">Click to upload</p>
                <p className="text-xs text-gray-400">
                  PNG, JPG up to 2MB
                </p>
              </div>
            )}
          </div>
          <input
            ref={thumbnailInputRef}
            id="course-thumbnail-upload"
            name="course_thumbnail"
            type="file"
            accept="image/png,image/jpeg,image/jpg"
            onChange={handleThumbnailChange}
            className="hidden"
          />
        </div>
      </div>
    </div>
  );
};
