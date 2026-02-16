// src/components/layout/AdminHeader.tsx

import React from 'react';
import { Bars3Icon, BellIcon } from '@heroicons/react/24/outline';
import { SearchBar } from './SearchBar';

interface AdminHeaderProps {
  onMenuClick: () => void;
}

export const AdminHeader: React.FC<AdminHeaderProps> = ({ onMenuClick }) => {
  return (
    <div className="sticky top-0 z-10 flex h-16 flex-shrink-0 bg-white border-b border-gray-200">
      {/* Mobile menu button */}
      <button
        type="button"
        className="px-4 text-gray-500 focus:outline-none lg:hidden"
        onClick={onMenuClick}
      >
        <Bars3Icon className="h-6 w-6" />
      </button>
      
      <div className="flex flex-1 justify-between px-4 sm:px-6 lg:px-8">
        {/* Search */}
        <div className="flex flex-1 items-center max-w-lg">
          <SearchBar className="w-full" isAdmin={true} />
        </div>
        
        {/* Right side */}
        <div className="ml-4 flex items-center md:ml-6">
          {/* Notifications */}
          <button
            type="button"
            className="rounded-full bg-white p-1 text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
          >
            <BellIcon className="h-6 w-6" />
          </button>
        </div>
      </div>
    </div>
  );
};
