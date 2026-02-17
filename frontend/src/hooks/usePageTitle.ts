import { useEffect } from 'react';
import { useTenantStore } from '../stores/tenantStore';

export const usePageTitle = (title: string) => {
  const themeName = useTenantStore((state) => state.theme.name);

  useEffect(() => {
    document.title = `${title} - ${themeName} LMS`;
  }, [title, themeName]);
};
