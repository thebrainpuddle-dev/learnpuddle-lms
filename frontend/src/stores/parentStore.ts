import { create } from 'zustand';
import type { ParentChild } from '../types/parent';

interface ParentState {
  isAuthenticated: boolean;
  parentEmail: string | null;
  sessionToken: string | null;
  refreshToken: string | null;
  expiresAt: string | null;
  children: ParentChild[];
  selectedChildId: string | null;

  setSession: (data: {
    session_token: string;
    refresh_token: string;
    expires_at: string;
    children: ParentChild[];
    email: string;
  }) => void;
  setSelectedChild: (childId: string) => void;
  clearSession: () => void;
}

export const useParentStore = create<ParentState>((set) => ({
  isAuthenticated: !!sessionStorage.getItem('parent_session_token'),
  parentEmail: sessionStorage.getItem('parent_email'),
  sessionToken: sessionStorage.getItem('parent_session_token'),
  refreshToken: sessionStorage.getItem('parent_refresh_token'),
  expiresAt: sessionStorage.getItem('parent_expires_at'),
  children: JSON.parse(sessionStorage.getItem('parent_children') || '[]'),
  selectedChildId: sessionStorage.getItem('parent_selected_child'),

  setSession: ({ session_token, refresh_token, expires_at, children, email }) => {
    sessionStorage.setItem('parent_session_token', session_token);
    sessionStorage.setItem('parent_refresh_token', refresh_token);
    sessionStorage.setItem('parent_expires_at', expires_at);
    sessionStorage.setItem('parent_children', JSON.stringify(children));
    sessionStorage.setItem('parent_email', email);
    if (children.length > 0 && !sessionStorage.getItem('parent_selected_child')) {
      sessionStorage.setItem('parent_selected_child', children[0].id);
    }
    set({
      isAuthenticated: true,
      sessionToken: session_token,
      refreshToken: refresh_token,
      expiresAt: expires_at,
      children,
      parentEmail: email,
      selectedChildId:
        sessionStorage.getItem('parent_selected_child') ||
        (children[0]?.id ?? null),
    });
  },

  setSelectedChild: (childId) => {
    sessionStorage.setItem('parent_selected_child', childId);
    set({ selectedChildId: childId });
  },

  clearSession: () => {
    sessionStorage.removeItem('parent_session_token');
    sessionStorage.removeItem('parent_refresh_token');
    sessionStorage.removeItem('parent_expires_at');
    sessionStorage.removeItem('parent_children');
    sessionStorage.removeItem('parent_email');
    sessionStorage.removeItem('parent_selected_child');
    set({
      isAuthenticated: false,
      sessionToken: null,
      refreshToken: null,
      expiresAt: null,
      children: [],
      parentEmail: null,
      selectedChildId: null,
    });
  },
}));
