// course-editor/useModuleState.ts
//
// Sub-hook: module CRUD, expand/collapse, description editing, reordering.

import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { Module } from './types';
import * as courseApi from './api';

export interface UseModuleStateParams {
  courseId: string | undefined;
  courseModules: Module[] | undefined;
  toast: {
    success: (title: string, message: string) => void;
    error: (title: string, message: string) => void;
  };
  /** Callbacks so the module hook can drive content-level side-effects */
  onModuleCreated?: (newModule: Module) => void;
  /** Called when a module delete removes a module whose content was being polled */
  onModuleDeleted?: (moduleId: string) => void;
}

export function useModuleState({
  courseId,
  courseModules,
  toast,
  onModuleCreated,
  onModuleDeleted,
}: UseModuleStateParams) {
  const queryClient = useQueryClient();

  // ── UI state ────────────────────────────────────────────────────────
  const [expandedModules, setExpandedModules] = useState<string[]>([]);
  const [editingModule, setEditingModule] = useState<string | null>(null);
  const [newModuleTitle, setNewModuleTitle] = useState('');

  // ── Module description editing ──────────────────────────────────────
  const [editingModuleDescriptionId, setEditingModuleDescriptionId] =
    useState<string | null>(null);
  const [moduleDescriptionDrafts, setModuleDescriptionDrafts] = useState<
    Record<string, string>
  >({});

  // ── Expand / collapse ───────────────────────────────────────────────
  const toggleModule = useCallback((moduleId: string) => {
    setExpandedModules((prev) =>
      prev.includes(moduleId)
        ? prev.filter((id) => id !== moduleId)
        : [...prev, moduleId],
    );
  }, []);

  const expandAllModules = useCallback((modules: Module[]) => {
    setExpandedModules(modules.map((m) => m.id));
  }, []);

  // ── Module mutations ────────────────────────────────────────────────
  const moduleMutation = useMutation({
    mutationFn: courseApi.createModule,
    onSuccess: async (newModule) => {
      if (!courseId) return;
      setNewModuleTitle('');
      setExpandedModules((prev) =>
        prev.includes(newModule.id) ? prev : [...prev, newModule.id],
      );
      setEditingModule(newModule.id);

      onModuleCreated?.(newModule);

      await queryClient.invalidateQueries({
        queryKey: ['adminCourse', courseId],
      });
      toast.success(
        'Module added',
        'Module is ready with a default text editor.',
      );
    },
    onError: () => {
      toast.error('Failed to add module', 'Please try again.');
    },
  });

  const updateModuleMutation = useMutation({
    mutationFn: courseApi.updateModule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      setEditingModule(null);
      toast.success('Module updated', 'Changes saved.');
    },
    onError: () => {
      toast.error('Failed to update module', 'Please try again.');
    },
  });

  const deleteModuleMutation = useMutation({
    mutationFn: courseApi.deleteModule,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      onModuleDeleted?.(variables.moduleId);
      toast.success(
        'Module deleted',
        'Module and its content have been removed.',
      );
    },
    onError: () => {
      toast.error('Failed to delete module', 'Please try again.');
    },
  });

  // ── Handlers ────────────────────────────────────────────────────────
  const handleAddModule = useCallback(() => {
    if (!courseId) return;
    const nextOrder = (courseModules?.length || 0) + 1;
    const nextTitle =
      newModuleTitle.trim() || `Untitled Module ${nextOrder}`;
    moduleMutation.mutate({
      courseId,
      data: { title: nextTitle, description: '', order: nextOrder },
    });
  }, [courseId, courseModules, newModuleTitle, moduleMutation]);

  const startModuleDescriptionEdit = useCallback((module: Module) => {
    setEditingModuleDescriptionId(module.id);
    setModuleDescriptionDrafts((prev) => ({
      ...prev,
      [module.id]: module.description || '',
    }));
  }, []);

  const saveModuleDescription = useCallback(
    (moduleId: string) => {
      if (!courseId) return;
      updateModuleMutation.mutate(
        {
          courseId,
          moduleId,
          data: { description: moduleDescriptionDrafts[moduleId] || '' },
        },
        {
          onSuccess: () => {
            setEditingModuleDescriptionId(null);
          },
        },
      );
    },
    [courseId, moduleDescriptionDrafts, updateModuleMutation],
  );

  const cancelModuleDescriptionEdit = useCallback((moduleId: string) => {
    setEditingModuleDescriptionId(null);
    setModuleDescriptionDrafts((prev) => {
      const next = { ...prev };
      delete next[moduleId];
      return next;
    });
  }, []);

  return {
    // UI state
    expandedModules,
    setExpandedModules,
    toggleModule,
    expandAllModules,
    editingModule,
    setEditingModule,
    newModuleTitle,
    setNewModuleTitle,

    // Description editing
    editingModuleDescriptionId,
    moduleDescriptionDrafts,
    setModuleDescriptionDrafts,
    startModuleDescriptionEdit,
    saveModuleDescription,
    cancelModuleDescriptionEdit,

    // Mutations
    moduleMutation,
    updateModuleMutation,
    deleteModuleMutation,

    // Handlers
    handleAddModule,
  };
}
