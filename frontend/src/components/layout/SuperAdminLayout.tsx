import React from 'react';
import { Outlet } from 'react-router-dom';
import { SuperAdminSidebar } from './SuperAdminSidebar';

export const SuperAdminLayout: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-50">
      <SuperAdminSidebar />
      <main className="ml-64 p-8">
        <Outlet />
      </main>
    </div>
  );
};
