// course-editor/useCourseEditor.ts
//
// Orchestrator hook that composes the sub-hooks into a single
// CourseEditorState object.  Downstream components are unaffected —
// the public return type is unchanged.

import { useCallback, useEffect, useRef } from 'react';
import { useCourseForm } from './useCourseForm';
import { useModuleState } from './useModuleState';
import { useContentState } from './useContentState';
import { useAssignmentState } from './useAssignmentState';
import { useCourseAudience } from './useCourseAudience';
import * as courseApi from './api';
import type { Module } from './types';

export { buildEmptyQuestion } from './useAssignmentState';

export function useCourseEditor() {
  // ── 1. Course form (identity, tabs, editor mode, form data, thumbnail, publish) ──
  const form = useCourseForm();

  // ── 2. Content state (content CRUD, video upload/polling, media library) ──
  const content = useContentState({
    courseId: form.courseId,
    course: form.course,
    toast: form.toast,
  });

  // ── 3. Module state (module CRUD, expand/collapse, description editing) ──
  const modules = useModuleState({
    courseId: form.courseId,
    courseModules: form.course?.modules,
    toast: form.toast,
    onModuleCreated: useCallback(
      (newModule: Module) => {
        content.bootstrapModuleTextContent(newModule.id);
      },
      [content.bootstrapModuleTextContent],
    ),
    onModuleDeleted: useCallback(
      (moduleId: string) => {
        content.handlePollingModuleDeleted(moduleId);
      },
      [content.handlePollingModuleDeleted],
    ),
  });

  // Bridge: expand all modules when course data first arrives.
  // The original monolith did this inside the "populate form" useEffect.
  const hasExpandedModules = useRef(false);
  useEffect(() => {
    if (form.course?.modules && !hasExpandedModules.current) {
      modules.expandAllModules(form.course.modules);
      hasExpandedModules.current = true;
    }
  }, [form.course, modules.expandAllModules]);

  // ── 4. Assignment state ──
  const assignments = useAssignmentState({
    courseId: form.courseId,
    isEditing: form.isEditing,
    canManageAssignments: form.canManageAssignments,
    course: form.course,
    toast: form.toast,
  });

  // ── 5. Audience state (teachers, groups) ──
  const audience = useCourseAudience({
    canManageAssignments: form.canManageAssignments,
  });

  // ── Compose the full return object ────────────────────────────────
  return {
    // ── Identity / navigation ───────────────────────────────────────
    courseId: form.courseId,
    isEditing: form.isEditing,
    isTeacherAuthoring: form.isTeacherAuthoring,
    canManageAssignments: form.canManageAssignments,
    canUploadVideo: form.canUploadVideo,
    courseListPath: form.courseListPath,
    navigate: form.navigate,

    // ── Tab ─────────────────────────────────────────────────────────
    activeTab: form.activeTab,
    setActiveTab: form.setActiveTab,

    // ── Editor mode ─────────────────────────────────────────────────
    editorMode: form.editorMode,
    setEditorMode: form.setEditorMode,
    showEditorChooser: form.showEditorChooser,
    setShowEditorChooser: form.setShowEditorChooser,
    rememberEditorMode: form.rememberEditorMode,
    setRememberEditorMode: form.setRememberEditorMode,
    handleEditorModeChange: form.handleEditorModeChange,
    handleSaveEditorChoice: form.handleSaveEditorChoice,
    handleModeWarning: form.handleModeWarning,

    // ── Course data ─────────────────────────────────────────────────
    course: form.course,
    courseLoading: form.courseLoading,
    formData: form.formData,
    setFormData: form.setFormData,
    handleInputChange: form.handleInputChange,
    handleSaveCourse: form.handleSaveCourse,
    courseMutationPending: form.courseMutationPending,

    // ── Thumbnail ───────────────────────────────────────────────────
    thumbnailPreview: form.thumbnailPreview,
    thumbnailFile: form.thumbnailFile,
    thumbnailInputRef: form.thumbnailInputRef,
    handleThumbnailChange: form.handleThumbnailChange,

    // ── Publish ─────────────────────────────────────────────────────
    publishMutation: form.publishMutation,

    // ── Module state ────────────────────────────────────────────────
    expandedModules: modules.expandedModules,
    toggleModule: modules.toggleModule,
    editingModule: modules.editingModule,
    setEditingModule: modules.setEditingModule,
    newModuleTitle: modules.newModuleTitle,
    setNewModuleTitle: modules.setNewModuleTitle,
    handleAddModule: modules.handleAddModule,
    moduleMutation: modules.moduleMutation,
    updateModuleMutation: modules.updateModuleMutation,
    deleteModuleMutation: modules.deleteModuleMutation,
    editingModuleDescriptionId: modules.editingModuleDescriptionId,
    moduleDescriptionDrafts: modules.moduleDescriptionDrafts,
    setModuleDescriptionDrafts: modules.setModuleDescriptionDrafts,
    startModuleDescriptionEdit: modules.startModuleDescriptionEdit,
    saveModuleDescription: modules.saveModuleDescription,
    cancelModuleDescriptionEdit: modules.cancelModuleDescriptionEdit,

    // ── Content state ───────────────────────────────────────────────
    addingContentToModule: content.addingContentToModule,
    setAddingContentToModule: content.setAddingContentToModule,
    newContentData: content.newContentData,
    setNewContentData: content.setNewContentData,
    contentFile: content.contentFile,
    setContentFile: content.setContentFile,
    contentFileInputRef: content.contentFileInputRef,
    contentMutation: content.contentMutation,
    updateContentMutation: content.updateContentMutation,
    deleteContentMutation: content.deleteContentMutation,
    handleAddContent: content.handleAddContent,
    editingTextContentId: content.editingTextContentId,
    editingTextModuleId: content.editingTextModuleId,
    textContentDraft: content.textContentDraft,
    setTextContentDraft: content.setTextContentDraft,
    showEditingTextPreview: content.showEditingTextPreview,
    setShowEditingTextPreview: content.setShowEditingTextPreview,
    showNewTextPreview: content.showNewTextPreview,
    setShowNewTextPreview: content.setShowNewTextPreview,
    startTextContentEdit: content.startTextContentEdit,
    saveTextContent: content.saveTextContent,
    cancelTextContentEdit: content.cancelTextContentEdit,

    // ── Upload ──────────────────────────────────────────────────────
    uploadPhase: content.uploadPhase,
    setUploadPhase: content.setUploadPhase,
    uploadProgress: content.uploadProgress,

    // ── Preview ─────────────────────────────────────────────────────
    previewContent: content.previewContent,
    setPreviewContent: content.setPreviewContent,

    // ── Media library ───────────────────────────────────────────────
    libraryOpen: content.libraryOpen,
    setLibraryOpen: content.setLibraryOpen,
    librarySearch: content.librarySearch,
    setLibrarySearch: content.setLibrarySearch,
    libraryFilter: content.libraryFilter,
    setLibraryFilter: content.setLibraryFilter,
    libraryAssets: content.libraryAssets,
    fetchLibraryAssets: content.fetchLibraryAssets,
    openLibraryPicker: content.openLibraryPicker,

    // ── Confirm delete ──────────────────────────────────────────────
    confirmDelete: form.confirmDelete,
    setConfirmDelete: form.setConfirmDelete,

    // ── Teachers / Groups ───────────────────────────────────────────
    teachers: audience.teachers,
    groups: audience.groups,
    createGroupOpen: audience.createGroupOpen,
    setCreateGroupOpen: audience.setCreateGroupOpen,
    createGroupForm: audience.createGroupForm,
    setCreateGroupForm: audience.setCreateGroupForm,
    createGroupMutation: audience.createGroupMutation,

    // ── Assignments ─────────────────────────────────────────────────
    assignmentScopeFilter: assignments.assignmentScopeFilter,
    setAssignmentScopeFilter: assignments.setAssignmentScopeFilter,
    assignmentList: assignments.assignmentList,
    assignmentListLoading: assignments.assignmentListLoading,
    selectedAssignmentId: assignments.selectedAssignmentId,
    setSelectedAssignmentId: assignments.setSelectedAssignmentId,
    selectedAssignment: assignments.selectedAssignment,
    selectedAssignmentLoading: assignments.selectedAssignmentLoading,
    isCreatingNewAssignment: assignments.isCreatingNewAssignment,
    setIsCreatingNewAssignment: assignments.setIsCreatingNewAssignment,
    assignmentForm: assignments.assignmentForm,
    setAssignmentForm: assignments.setAssignmentForm,
    aiQuestionCount: assignments.aiQuestionCount,
    setAiQuestionCount: assignments.setAiQuestionCount,
    aiIncludeShortAnswer: assignments.aiIncludeShortAnswer,
    setAiIncludeShortAnswer: assignments.setAiIncludeShortAnswer,
    aiTitleHint: assignments.aiTitleHint,
    setAiTitleHint: assignments.setAiTitleHint,
    aiModelLabel: assignments.aiModelLabel,
    aiSourceState: assignments.aiSourceState,
    createAssignmentMutation: assignments.createAssignmentMutation,
    updateAssignmentMutation: assignments.updateAssignmentMutation,
    deleteAssignmentMutation: assignments.deleteAssignmentMutation,
    aiGenerateMutation: assignments.aiGenerateMutation,
    resetAssignmentBuilder: assignments.resetAssignmentBuilder,
    updateAssignmentQuestion: assignments.updateAssignmentQuestion,
    addAssignmentQuestion: assignments.addAssignmentQuestion,
    removeAssignmentQuestion: assignments.removeAssignmentQuestion,
    handleSaveAssignmentBuilder: assignments.handleSaveAssignmentBuilder,

    // ── Helpers (re-exported for sub-components) ────────────────────
    toast: form.toast,
    uploadEditorImage: courseApi.uploadEditorImage,
  };
}

export type CourseEditorState = ReturnType<typeof useCourseEditor>;
