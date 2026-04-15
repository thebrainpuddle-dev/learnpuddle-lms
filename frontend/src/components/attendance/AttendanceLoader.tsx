// src/components/attendance/AttendanceLoader.tsx
//
// Branded loading state for attendance pages — tenant logo spins,
// then content fades in once data is ready.

import React from 'react';
import { useTenantStore } from '../../stores/tenantStore';

export const AttendanceLoader: React.FC = () => {
  const { theme } = useTenantStore();
  const tenantName = theme?.name || 'LearnPuddle';
  const tenantInitial = tenantName.charAt(0).toUpperCase();

  return (
    <div className="flex flex-col items-center justify-center py-28">
      {/* Outer ring */}
      <div className="relative h-20 w-20">
        {/* Spinning ring */}
        <div className="absolute inset-0 rounded-full border-[3px] border-slate-100" />
        <div className="absolute inset-0 rounded-full border-[3px] border-transparent border-t-indigo-500 animate-spin" />

        {/* Logo center */}
        <div className="absolute inset-[6px] rounded-full bg-white shadow-sm flex items-center justify-center overflow-hidden">
          {theme?.logo ? (
            <img
              src={theme.logo}
              alt={tenantName}
              className="h-10 w-10 rounded-full object-cover animate-pulse"
            />
          ) : (
            <div className="h-10 w-10 rounded-full bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center animate-pulse">
              <span className="text-white font-bold text-lg">{tenantInitial}</span>
            </div>
          )}
        </div>
      </div>

      {/* Text */}
      <p className="mt-5 text-sm font-medium text-slate-400 animate-pulse">
        Loading attendance...
      </p>
    </div>
  );
};
