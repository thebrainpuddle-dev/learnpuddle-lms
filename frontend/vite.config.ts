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
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-react': ['react', 'react-dom', 'react-router-dom'],
            'vendor-ui': ['@headlessui/react', 'lucide-react', 'clsx', 'tailwind-merge'],
            'vendor-charts': ['recharts'],
            'vendor-query': ['@tanstack/react-query'],
            'vendor-state': ['zustand', 'dexie'],
            'vendor-utils': ['date-fns', 'axios', 'dompurify'],
            'vendor-sentry': ['@sentry/react'],
            'vendor-pdf': ['pdfjs-dist'],
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
