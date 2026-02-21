// src/components/layout/TeacherLayout.tsx

import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { TeacherSidebar } from './TeacherSidebar';
import { TeacherHeader } from './TeacherHeader';

export const TeacherLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Mobile sidebar */}
      <TeacherSidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      
      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
        <TeacherSidebar open={true} />
      </div>
      
      {/* Main content */}
      <div className="lg:pl-64 flex min-w-0 flex-1 flex-col">
        <TeacherHeader onMenuClick={() => setSidebarOpen(true)} />
        
        <main className="flex-1 min-w-0">
          <div className="py-6">
            <div className="mx-auto max-w-7xl px-4 sm:px-6 md:px-8">
              <Outlet />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
