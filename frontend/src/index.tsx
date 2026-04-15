import React from 'react';
import ReactDOM from 'react-dom/client';
import * as Sentry from '@sentry/react';
import App from './App';

// ---------------------------------------------------------------------------
// Sentry error tracking (initialise before anything else so we capture
// errors that happen during React bootstrap).
// Set VITE_SENTRY_DSN in your .env to enable.
// ---------------------------------------------------------------------------
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.MODE,
    integrations: [
      Sentry.browserTracingIntegration(),
    ],
    tracesSampleRate: import.meta.env.PROD ? 0.1 : 1.0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: import.meta.env.PROD ? 1.0 : 0,
  });
}

// Global error handlers — catch unhandled promise rejections and uncaught errors
// before React mounts so nothing slips through during initialization.
window.addEventListener('unhandledrejection', (event) => {
  console.error('[Unhandled Promise Rejection]', event.reason);
  // Prevent default browser logging
  event.preventDefault();
});

window.addEventListener('error', (event) => {
  console.error('[Uncaught Error]', event.error);
});

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
