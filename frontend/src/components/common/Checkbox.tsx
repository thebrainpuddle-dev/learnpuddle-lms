// src/components/common/Checkbox.tsx

import React from 'react';
import { clsx } from 'clsx';

interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export const Checkbox: React.FC<CheckboxProps> = ({
  label,
  className,
  ...props
}) => {
  return (
    <div className="flex items-center">
      <input
        type="checkbox"
        className={clsx(
          'h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded',
          className
        )}
        {...props}
      />
      {label && (
        <label htmlFor={props.id} className="ml-2 block text-sm text-gray-700">
          {label}
        </label>
      )}
    </div>
  );
};
