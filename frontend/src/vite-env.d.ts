/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_PLATFORM_DOMAIN: string;
  readonly VITE_WS_URL: string;
  readonly VITE_ENABLE_PWA: string;
  readonly VITE_SENTRY_DSN: string;
  // CRA compat
  readonly REACT_APP_API_URL: string;
  readonly REACT_APP_PLATFORM_DOMAIN: string;
  readonly REACT_APP_WS_URL: string;
  readonly REACT_APP_ENABLE_PWA: string;
  readonly REACT_APP_ENABLE_PWA_IN_PROD: string;
  readonly REACT_APP_BOOK_DEMO_URL: string;
  readonly REACT_APP_BOOK_DEMO_CAL_LINK: string;
  readonly REACT_APP_BOOK_DEMO_MODE: string;
  readonly REACT_APP_IDLE_TIMEOUT_MINUTES: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
