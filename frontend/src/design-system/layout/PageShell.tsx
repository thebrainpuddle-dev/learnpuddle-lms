import React from 'react';
import { Outlet } from 'react-router-dom';
import { TopNav } from './TopNav';

export function PageShell() {
  return (
    <div className="flex flex-col h-screen overflow-hidden bg-surface">
      <TopNav />
      <main className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="max-w-[1440px] mx-auto px-4 lg:px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
