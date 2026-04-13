// course-editor/api.ts — API functions used by the Course Editor

import api from '../../../config/api';
import type { Course, Module, Content } from './types';

export const fetchCourse = async (id: string): Promise<Course> => {
  const response = await api.get(`/courses/${id}/`);
  return response.data;
};

export const fetchTeachers = async () => {
  const response = await api.get('/teachers/');
  return response.data.results ?? response.data;
};

export const fetchGroups = async () => {
  const response = await api.get('/teacher-groups/');
  return response.data.results ?? response.data;
};

export const createCourse = async (data: FormData): Promise<Course> => {
  const response = await api.post('/courses/', data);
  return response.data;
};

export const updateCourse = async ({
  id,
  data,
}: {
  id: string;
  data: FormData;
}): Promise<Course> => {
  const response = await api.patch(`/courses/${id}/`, data);
  return response.data;
};

export const createModule = async ({
  courseId,
  data,
}: {
  courseId: string;
  data: Record<string, unknown>;
}): Promise<Module> => {
  const response = await api.post(`/courses/${courseId}/modules/`, data);
  return response.data;
};

export const updateModule = async ({
  courseId,
  moduleId,
  data,
}: {
  courseId: string;
  moduleId: string;
  data: Record<string, unknown>;
}): Promise<Module> => {
  const response = await api.patch(
    `/courses/${courseId}/modules/${moduleId}/`,
    data,
  );
  return response.data;
};

export const deleteModule = async ({
  courseId,
  moduleId,
}: {
  courseId: string;
  moduleId: string;
}): Promise<void> => {
  await api.delete(`/courses/${courseId}/modules/${moduleId}/`);
};

export const createContent = async ({
  courseId,
  moduleId,
  data,
}: {
  courseId: string;
  moduleId: string;
  data: FormData;
}): Promise<Content> => {
  const response = await api.post(
    `/courses/${courseId}/modules/${moduleId}/contents/`,
    data,
  );
  return response.data;
};

export const updateContent = async ({
  courseId,
  moduleId,
  contentId,
  data,
}: {
  courseId: string;
  moduleId: string;
  contentId: string;
  data: Record<string, unknown>;
}): Promise<Content> => {
  const response = await api.patch(
    `/courses/${courseId}/modules/${moduleId}/contents/${contentId}/`,
    data,
  );
  return response.data;
};

export const deleteContent = async ({
  courseId,
  moduleId,
  contentId,
}: {
  courseId: string;
  moduleId: string;
  contentId: string;
}): Promise<void> => {
  await api.delete(
    `/courses/${courseId}/modules/${moduleId}/contents/${contentId}/`,
  );
};

export const uploadFile = async (
  file: File,
  type: 'thumbnail' | 'content',
): Promise<string> => {
  const formData = new FormData();
  formData.append('file', file);
  const endpoint =
    type === 'thumbnail'
      ? '/uploads/course-thumbnail/'
      : '/uploads/content-file/';
  const response = await api.post(endpoint, formData);
  return response.data.url;
};

export const uploadEditorImage = async (
  file: File,
): Promise<{ src: string; imageId: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/uploads/editor-image/', formData);
  return {
    src: response.data.preview_url,
    imageId: response.data.asset_id,
  };
};
