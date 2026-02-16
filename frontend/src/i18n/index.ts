// src/i18n/index.ts
/**
 * i18n configuration using react-i18next.
 * 
 * Features:
 * - Automatic language detection from browser
 * - Fallback to English
 * - Lazy loading of translations
 * - TypeScript support
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// Import translations
import en from './locales/en.json';
import hi from './locales/hi.json';

// Available languages
export const languages = {
  en: { name: 'English', nativeName: 'English' },
  hi: { name: 'Hindi', nativeName: 'हिन्दी' },
} as const;

export type LanguageCode = keyof typeof languages;

// Resources
const resources = {
  en: { translation: en },
  hi: { translation: hi },
};

i18n
  // Detect user language
  .use(LanguageDetector)
  // Pass i18n instance to react-i18next
  .use(initReactI18next)
  // Initialize
  .init({
    resources,
    fallbackLng: 'en',
    debug: process.env.NODE_ENV === 'development',
    
    interpolation: {
      escapeValue: false, // React already escapes values
    },
    
    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      lookupLocalStorage: 'i18nextLng',
      caches: ['localStorage'],
    },
  });

export default i18n;

// Type-safe translation keys
export type TranslationKey = keyof typeof en;
