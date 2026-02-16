// src/services/adminMediaService.ts

import api from '../config/api';

export interface MediaAsset {
  id: string;
  title: string;
  media_type: 'VIDEO' | 'DOCUMENT' | 'LINK';
  file_url: string;
  file_name: string;
  file_size: number | null;
  mime_type: string;
  duration: number | null;
  thumbnail_url: string;
  tags: string[];
  is_active: boolean;
  uploaded_by: string | null;
  uploaded_by_name: string;
  created_at: string;
  updated_at: string;
}

export interface MediaListResponse {
  results: MediaAsset[];
  count: number;
  next: string | null;
  previous: string | null;
}

export interface MediaStats {
  VIDEO?: number;
  DOCUMENT?: number;
  LINK?: number;
  total: number;
}

export const adminMediaService = {
  async listMedia(params?: {
    media_type?: string;
    search?: string;
    page?: number;
    page_size?: number;
  }): Promise<MediaListResponse> {
    const res = await api.get('/media/', { params });
    // If backend returns paginated response
    if (res.data.results) return res.data;
    // Fallback for unpaginated
    return { results: res.data, count: res.data.length, next: null, previous: null };
  },

  async uploadMedia(payload: {
    file?: File;
    title: string;
    media_type: string;
    file_url?: string;
  }): Promise<MediaAsset> {
    const fd = new FormData();
    fd.append('title', payload.title);
    fd.append('media_type', payload.media_type);
    if (payload.file) {
      fd.append('file', payload.file);
    }
    if (payload.file_url) {
      fd.append('file_url', payload.file_url);
    }
    const res = await api.post('/media/', fd);
    return res.data;
  },

  async getMedia(id: string): Promise<MediaAsset> {
    const res = await api.get(`/media/${id}/`);
    return res.data;
  },

  async updateMedia(id: string, data: { title?: string; tags?: string[] }): Promise<MediaAsset> {
    const res = await api.patch(`/media/${id}/`, data);
    return res.data;
  },

  async deleteMedia(id: string): Promise<void> {
    await api.delete(`/media/${id}/`);
  },

  async getStats(): Promise<MediaStats> {
    const res = await api.get('/media/stats/');
    return res.data;
  },
};
