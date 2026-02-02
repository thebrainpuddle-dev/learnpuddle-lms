// src/components/admin/StatsCard.tsx

import React from 'react';
import { clsx } from 'clsx';

interface StatsCardProps {
  title: string;
  value: string | number;
  change?: {
    value: number;
    positive: boolean;
  };
  icon: React.ReactNode;
  loading?: boolean;
}

export const StatsCard: React.FC<StatsCardProps> = ({
  title,
  value,
  change,
  icon,
  loading,
}) => {
  if (loading) {
    return (
      <div className="card">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/2 mb-4"></div>
          <div className="h-8 bg-gray-200 rounded w-3/4"></div>
        </div>
      </div>
    );
  }
  
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className="mt-2 text-3xl font-semibold text-gray-900">{value}</p>
          
          {change && (
            <p className="mt-2 flex items-center text-sm">
              <span
                className={clsx(
                  change.positive ? 'text-green-600' : 'text-red-600'
                )}
              >
                {change.positive ? '↑' : '↓'} {Math.abs(change.value)}%
              </span>
              <span className="ml-2 text-gray-500">vs last month</span>
            </p>
          )}
        </div>
        
        <div className="flex-shrink-0">
          <div className="p-3 bg-primary-100 rounded-lg">
            <div className="text-primary-600">{icon}</div>
          </div>
        </div>
      </div>
    </div>
  );
};
