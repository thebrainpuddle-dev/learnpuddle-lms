// src/components/common/LanguageSelector.tsx
/**
 * Language selector dropdown component.
 * Allows users to switch the UI language.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Menu, MenuButton, MenuItem, MenuItems, Transition } from '@headlessui/react';
import { LanguageIcon, ChevronDownIcon } from '@heroicons/react/24/outline';
import { languages, type LanguageCode } from '../../i18n';
import { clsx } from 'clsx';

interface LanguageSelectorProps {
  /** Display style variant */
  variant?: 'dropdown' | 'inline';
  /** Size of the selector */
  size?: 'sm' | 'md';
  /** Additional class names */
  className?: string;
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  variant = 'dropdown',
  size = 'md',
  className,
}) => {
  const { i18n } = useTranslation();
  const currentLang = i18n.language as LanguageCode;
  const currentLanguage = languages[currentLang] || languages.en;

  const changeLanguage = (langCode: LanguageCode) => {
    i18n.changeLanguage(langCode);
  };

  if (variant === 'inline') {
    return (
      <div className={clsx('flex space-x-2', className)}>
        {Object.entries(languages).map(([code, lang]) => (
          <button
            key={code}
            onClick={() => changeLanguage(code as LanguageCode)}
            className={clsx(
              'px-3 py-1 rounded-md text-sm font-medium transition-colors',
              currentLang === code
                ? 'bg-primary-100 text-primary-700'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
            )}
          >
            {lang.nativeName}
          </button>
        ))}
      </div>
    );
  }

  return (
    <Menu as="div" className={clsx('relative', className)}>
      <MenuButton
        className={clsx(
          'flex items-center rounded-md border border-gray-300 bg-white shadow-sm',
          'hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary-500',
          size === 'sm' ? 'px-2 py-1 text-sm' : 'px-3 py-2'
        )}
      >
        <LanguageIcon
          className={clsx(
            'text-gray-500',
            size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'
          )}
        />
        <span className="ml-2 text-gray-700">{currentLanguage.nativeName}</span>
        <ChevronDownIcon
          className={clsx(
            'ml-2 text-gray-400',
            size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'
          )}
        />
      </MenuButton>

      <Transition
        enter="transition ease-out duration-100"
        enterFrom="transform opacity-0 scale-95"
        enterTo="transform opacity-100 scale-100"
        leave="transition ease-in duration-75"
        leaveFrom="transform opacity-100 scale-100"
        leaveTo="transform opacity-0 scale-95"
      >
        <MenuItems className="absolute right-0 z-10 mt-2 w-40 origin-top-right rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none">
          <div className="py-1">
            {Object.entries(languages).map(([code, lang]) => (
              <MenuItem key={code}>
                {({ active }) => (
                  <button
                    onClick={() => changeLanguage(code as LanguageCode)}
                    className={clsx(
                      'block w-full px-4 py-2 text-left text-sm',
                      active ? 'bg-gray-100 text-gray-900' : 'text-gray-700',
                      currentLang === code && 'font-medium text-primary-600'
                    )}
                  >
                    <span className="block">{lang.nativeName}</span>
                    <span className="block text-xs text-gray-500">
                      {lang.name}
                    </span>
                  </button>
                )}
              </MenuItem>
            ))}
          </div>
        </MenuItems>
      </Transition>
    </Menu>
  );
};

export default LanguageSelector;
