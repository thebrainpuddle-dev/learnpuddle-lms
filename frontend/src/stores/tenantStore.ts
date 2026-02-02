import { create } from 'zustand';

import type { TenantTheme } from '../config/theme';
import { DEFAULT_THEME } from '../config/theme';

interface TenantState {
  theme: TenantTheme;
  setTheme: (theme: TenantTheme) => void;
}

export const useTenantStore = create<TenantState>((set) => ({
  theme: DEFAULT_THEME,
  setTheme: (theme) => set({ theme }),
}));

