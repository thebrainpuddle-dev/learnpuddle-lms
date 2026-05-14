/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), ['VITE_', 'REACT_APP_']);

  // Polyfill process.env.REACT_APP_* for CRA backward compatibility
  const processEnvDefines: Record<string, string> = {
    'process.env.NODE_ENV': JSON.stringify(mode),
  };
  for (const [key, val] of Object.entries(env)) {
    if (key.startsWith('REACT_APP_')) {
      processEnvDefines[`process.env.${key}`] = JSON.stringify(val);
    }
  }

  return {
    plugins: [react()],
    define: processEnvDefines,
    envPrefix: ['VITE_', 'REACT_APP_'],
    server: {
      port: 3000,
      host: true,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/media': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/ws': {
          target: 'ws://localhost:8000',
          ws: true,
          changeOrigin: true,
        },
      },
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    build: {
      outDir: 'build',
      sourcemap: true,
      chunkSizeWarningLimit: 1200,
      rollupOptions: {
        output: {
          manualChunks(id) {
            const moduleId = id.replace(/\\/g, '/');
            if (!moduleId.includes('node_modules')) return undefined;

            if (
              moduleId.includes('/node_modules/react/') ||
              moduleId.includes('/node_modules/react-dom/') ||
              moduleId.includes('/node_modules/react-router') ||
              moduleId.includes('/node_modules/@remix-run/router/') ||
              moduleId.includes('/node_modules/@headlessui/react/') ||
              moduleId.includes('/node_modules/recharts/') ||
              moduleId.includes('/node_modules/lucide-react/') ||
              moduleId.includes('/node_modules/clsx/') ||
              moduleId.includes('/node_modules/tailwind-merge/')
            ) {
              return 'vendor-ui-react';
            }
            if (moduleId.includes('/node_modules/@tanstack/react-query/')) {
              return 'vendor-query';
            }
            if (moduleId.includes('/node_modules/zustand/') || moduleId.includes('/node_modules/dexie/')) {
              return 'vendor-state';
            }
            if (
              moduleId.includes('/node_modules/date-fns/') ||
              moduleId.includes('/node_modules/axios/') ||
              moduleId.includes('/node_modules/dompurify/')
            ) {
              return 'vendor-utils';
            }
            if (moduleId.includes('/node_modules/@sentry/react/')) {
              return 'vendor-sentry';
            }
            if (moduleId.includes('/node_modules/pdfjs-dist/')) {
              return 'vendor-pdf';
            }
            if (moduleId.includes('/node_modules/hls.js/')) {
              return 'vendor-media';
            }
            if (
              moduleId.includes('/node_modules/katex/') ||
              moduleId.includes('/node_modules/lowlight/') ||
              moduleId.includes('/node_modules/highlight.js/')
            ) {
              return 'vendor-rendering';
            }
            if (moduleId.includes('/node_modules/pptxgenjs/') || moduleId.includes('/node_modules/jszip/')) {
              return 'vendor-office';
            }
            if (
              moduleId.includes('/node_modules/zod/') ||
              moduleId.includes('/node_modules/react-hook-form/') ||
              moduleId.includes('/node_modules/i18next/') ||
              moduleId.includes('/node_modules/i18next-browser-languagedetector/')
            ) {
              return 'vendor-forms-i18n';
            }
            return undefined;
          },
        },
      },
    },
    test: {
      globals: true,
      environment: 'happy-dom',
      setupFiles: ['./src/setupTests.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
    },
  };
});
