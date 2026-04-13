// course-editor/CourseSettings.tsx
//
// Audience tab: assign-to-all toggle, group selection, individual teacher
// selection, and inline group creation modal.

import React from 'react';
import { Button, Input } from '../../../components/common';
import {
  UsersIcon,
  UserGroupIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import type { CourseEditorState } from './useCourseEditor';

interface CourseSettingsProps {
  state: CourseEditorState;
}

export const CourseSettings: React.FC<CourseSettingsProps> = ({ state }) => {
  const {
    formData,
    setFormData,
    handleInputChange,
    teachers,
    groups,
    createGroupOpen,
    setCreateGroupOpen,
    createGroupForm,
    setCreateGroupForm,
    createGroupMutation,
  } = state;

  return (
    <div
      data-tour="admin-course-assignment-panel"
      className="bg-white rounded-xl border border-gray-200 p-6 space-y-6"
    >
      <h2 className="text-lg font-semibold text-gray-900">
        Course Audience
      </h2>

      {/* Assign to All */}
      <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
        <div className="flex items-center">
          <UsersIcon className="h-6 w-6 text-primary-600 mr-3" />
          <div>
            <p className="font-medium text-gray-900">
              Assign to All Teachers
            </p>
            <p className="text-sm text-gray-500">
              All current and future teachers will have access
            </p>
          </div>
        </div>
        <label className="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            name="assigned_to_all"
            checked={formData.assigned_to_all}
            onChange={handleInputChange}
            className="sr-only peer"
          />
          <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
        </label>
      </div>

      {/* Specific Audience */}
      {!formData.assigned_to_all && (
        <>
          {/* Groups */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="flex items-center text-sm font-medium text-gray-700">
                <UserGroupIcon className="h-5 w-5 mr-2 text-gray-400" />
                Assign to Groups
              </label>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCreateGroupOpen(true)}
              >
                + Create group
              </Button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {groups?.map((group) => (
                <label
                  key={group.id}
                  className={`flex items-center p-3 border rounded-lg cursor-pointer transition-colors ${
                    formData.assigned_groups.includes(group.id)
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={formData.assigned_groups.includes(
                      group.id,
                    )}
                    onChange={(e) => {
                      setFormData((prev) => ({
                        ...prev,
                        assigned_groups: e.target.checked
                          ? [...prev.assigned_groups, group.id]
                          : prev.assigned_groups.filter(
                              (id) => id !== group.id,
                            ),
                      }));
                    }}
                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                  />
                  <span className="ml-2 text-sm text-gray-900">
                    {group.name}
                  </span>
                </label>
              ))}
            </div>
            {groups?.length === 0 && (
              <p className="text-sm text-gray-500">
                No groups created yet
              </p>
            )}
          </div>

          {/* Individual Teachers */}
          <div>
            <label className="flex items-center text-sm font-medium text-gray-700 mb-2">
              <UsersIcon className="h-5 w-5 mr-2 text-gray-400" />
              Assign to Individual Teachers
            </label>
            <div className="max-h-60 overflow-y-auto border border-gray-200 rounded-lg">
              {teachers?.map((teacher) => (
                <label
                  key={teacher.id}
                  className={`flex items-center p-3 border-b last:border-b-0 cursor-pointer hover:bg-gray-50 ${
                    formData.assigned_teachers.includes(teacher.id)
                      ? 'bg-primary-50'
                      : ''
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={formData.assigned_teachers.includes(
                      teacher.id,
                    )}
                    onChange={(e) => {
                      setFormData((prev) => ({
                        ...prev,
                        assigned_teachers: e.target.checked
                          ? [
                              ...prev.assigned_teachers,
                              teacher.id,
                            ]
                          : prev.assigned_teachers.filter(
                              (id) => id !== teacher.id,
                            ),
                      }));
                    }}
                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                  />
                  <div className="ml-3">
                    <p className="text-sm font-medium text-gray-900">
                      {teacher.first_name} {teacher.last_name}
                    </p>
                    <p className="text-xs text-gray-500">
                      {teacher.email}
                    </p>
                  </div>
                </label>
              ))}
            </div>
            {teachers?.length === 0 && (
              <p className="text-sm text-gray-500">No teachers found</p>
            )}
          </div>
        </>
      )}

      {/* Summary */}
      <div className="p-4 bg-blue-50 rounded-lg">
        <p className="text-sm text-blue-800">
          <strong>Audience Summary:</strong>{' '}
          {formData.assigned_to_all
            ? 'All teachers in your school will have access to this course.'
            : `${formData.assigned_groups.length} group(s) and ${formData.assigned_teachers.length} individual teacher(s) selected.`}
        </p>
      </div>

      {/* Inline Create Group Modal */}
      {createGroupOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-lg w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">
                Create Group
              </h3>
              <button
                onClick={() => setCreateGroupOpen(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <div className="space-y-4">
              <Input
                label="Group name"
                name="group_name"
                value={createGroupForm.name}
                onChange={(e) =>
                  setCreateGroupForm({
                    ...createGroupForm,
                    name: e.target.value,
                  })
                }
                placeholder="e.g., Grade 9, Math Teachers"
              />
              <Input
                label="Description"
                name="group_description"
                value={createGroupForm.description}
                onChange={(e) =>
                  setCreateGroupForm({
                    ...createGroupForm,
                    description: e.target.value,
                  })
                }
                placeholder="Optional"
              />
              <div>
                <label
                  htmlFor="group-type"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Type
                </label>
                <select
                  id="group-type"
                  name="group_type"
                  value={createGroupForm.group_type}
                  onChange={(e) =>
                    setCreateGroupForm({
                      ...createGroupForm,
                      group_type: e.target.value,
                    })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                >
                  <option value="CUSTOM">Custom</option>
                  <option value="SUBJECT">Subject</option>
                  <option value="GRADE">Grade</option>
                  <option value="DEPARTMENT">Department</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 mt-6">
              <Button
                variant="outline"
                onClick={() => setCreateGroupOpen(false)}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() =>
                  createGroupMutation.mutate({
                    name: createGroupForm.name,
                    description: createGroupForm.description,
                    group_type: createGroupForm.group_type,
                  })
                }
                disabled={!createGroupForm.name.trim()}
                loading={createGroupMutation.isPending}
              >
                Create
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
