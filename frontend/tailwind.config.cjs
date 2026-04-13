/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ─── Sidebar (kept for backward compat) ──────────────────────
        sidebar: {
          DEFAULT: '#1A1A1A',
          hover: '#2A2A2A',
          active: '#333333',
          text: '#9B9B9B',
          'text-active': '#FFFFFF',
          border: '#2A2A2A',
          accent: '#D4A843',
          'accent-glow': '#E8C76B',
        },

        // ─── Teacher Portal — light white + orange ────────────────
        tp: {
          bg: '#F9FAFB',
          sidebar: '#FFFFFF',
          'sidebar-hover': '#FFF7ED',
          'sidebar-active': '#FFEDD5',
          'sidebar-border': '#F3F4F6',
          card: '#FFFFFF',
          'card-hover': '#FFFBF5',
          'card-border': '#E5E7EB',
          accent: '#F97316',
          'accent-light': '#FB923C',
          'accent-dark': '#EA580C',
          'accent-glow': 'rgba(249, 115, 22, 0.2)',
          text: '#111827',
          'text-secondary': '#6B7280',
          'text-muted': '#9CA3AF',
        },

        // ─── Surface (warm cream canvas) ─────────────────────────────
        surface: {
          DEFAULT: '#FAF7F2',
          card: '#FFFFFF',
          'card-hover': '#F5F0E8',
          border: '#EDE8DF',
          'border-subtle': '#F5F0E8',
        },

        // ─── Content text ────────────────────────────────────────────
        content: {
          DEFAULT: '#1A1A1A',
          secondary: '#6B6B6B',
          muted: '#9B9B9B',
          inverse: '#FFFFFF',
        },

        // ─── Accent / golden amber ───────────────────────────────────
        accent: {
          DEFAULT: '#D4A843',
          light: '#E8C76B',
          dark: '#B8892B',
          foreground: '#FFFFFF',
          50: '#FDF8EB',
          100: '#FAF0D5',
          200: '#F5E1AB',
          300: '#F0D281',
          400: '#EBC357',
          500: '#D4A843',
          600: '#B8892B',
          700: '#9C6E1F',
          800: '#805617',
          900: '#644312',
        },

        // ─── Status ──────────────────────────────────────────────────
        success: { DEFAULT: '#28A745', light: '#48C764', dark: '#1E8E3A', bg: '#F0FFF4' },
        warning: { DEFAULT: '#F5A623', light: '#F7BD4F', dark: '#D4901A', bg: '#FFFCF0' },
        danger:  { DEFAULT: '#DC3545', light: '#E25D6A', dark: '#BD2130', bg: '#FFF5F5' },
        info:    { DEFAULT: '#4A90D9', light: '#6DA8E5', dark: '#3378C0', bg: '#F0F7FF' },

        // ─── Tenant brand (CSS custom properties) ────────────────────
        brand: {
          50:  'var(--color-brand-50)',
          100: 'var(--color-brand-100)',
          200: 'var(--color-brand-200)',
          300: 'var(--color-brand-300)',
          400: 'var(--color-brand-400)',
          500: 'var(--color-brand-500)',
          600: 'var(--color-brand-600)',
          700: 'var(--color-brand-700)',
          800: 'var(--color-brand-800)',
          900: 'var(--color-brand-900)',
        },

        // ─── Backward compat (existing code uses primary-*) ─────────
        primary: {
          50:  'var(--color-primary-50)',
          100: 'var(--color-primary-100)',
          200: 'var(--color-primary-200)',
          300: 'var(--color-primary-300)',
          400: 'var(--color-primary-400)',
          500: 'var(--color-primary-500)',
          600: 'var(--color-primary-600)',
          700: 'var(--color-primary-700)',
          800: 'var(--color-primary-800)',
          900: 'var(--color-primary-900)',
        },
        secondary: {
          50:  'var(--color-secondary-50)',
          100: 'var(--color-secondary-100)',
          200: 'var(--color-secondary-200)',
          300: 'var(--color-secondary-300)',
          400: 'var(--color-secondary-400)',
          500: 'var(--color-secondary-500)',
          600: 'var(--color-secondary-600)',
          700: 'var(--color-secondary-700)',
          800: 'var(--color-secondary-800)',
          900: 'var(--color-secondary-900)',
        },
        destructive: { DEFAULT: '#DC3545', foreground: '#FFFFFF' },
        muted: { DEFAULT: '#F5F0E8', foreground: '#6B6B6B' },
      },

      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },

      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },

      boxShadow: {
        card: '0 1px 3px 0 rgb(0 0 0 / 0.04), 0 1px 2px -1px rgb(0 0 0 / 0.03)',
        'card-hover': '0 4px 12px -2px rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.04)',
        nav: '0 1px 3px 0 rgb(0 0 0 / 0.05)',
        glass: '0 8px 32px 0 rgba(0, 0, 0, 0.06)',
        'glow-accent': '0 0 20px rgba(212, 168, 67, 0.25)',
        'glow-success': '0 0 20px rgba(40, 167, 69, 0.25)',
        dropdown: '0 10px 40px -4px rgba(0, 0, 0, 0.1), 0 4px 12px -2px rgba(0, 0, 0, 0.05)',
      },

      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height, auto)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height, auto)' },
          to: { height: '0' },
        },
        'slide-up': {
          from: { transform: 'translateY(100%)' },
          to: { transform: 'translateY(0)' },
        },
        'slide-in-right': {
          from: { transform: 'translateX(100%)', opacity: '0' },
          to: { transform: 'translateX(0)', opacity: '1' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'scale-in': {
          from: { transform: 'scale(0.95)', opacity: '0' },
          to: { transform: 'scale(1)', opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'pulse-ring': {
          '0%, 100%': { transform: 'scale(1)', opacity: '0.3' },
          '50%': { transform: 'scale(1.15)', opacity: '0.1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-4px)' },
        },
        'bounce-dot': {
          '0%, 80%, 100%': { transform: 'translateY(0)' },
          '40%': { transform: 'translateY(-3px)' },
        },
      },

      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'slide-up': 'slide-up 0.3s ease-out',
        'slide-in-right': 'slide-in-right 0.3s ease-out',
        'fade-in': 'fade-in 0.2s ease-out',
        'scale-in': 'scale-in 0.2s ease-out',
        shimmer: 'shimmer 2s linear infinite',
      },
    },
  },
  plugins: [require('@tailwindcss/forms')],
};
