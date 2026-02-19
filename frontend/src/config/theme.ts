// src/config/theme.ts

export interface TenantTheme {
  name: string;
  subdomain: string;
  logo?: string; // absolute URL
  primaryColor: string;
  secondaryColor?: string;
  fontFamily?: string;
  tenantFound: boolean;
  tenantErrorReason?: 'not_found' | 'trial_expired' | 'deactivated';
  tenantErrorMessage?: string;
}

// Default theme (fallback)
export const DEFAULT_THEME: TenantTheme = {
  name: 'Default School',
  subdomain: 'demo',
  primaryColor: '#1F4788',
  secondaryColor: '#2E5C8A',
  fontFamily: 'Inter',
  tenantFound: true,
};

/**
 * Convert hex to RGB values
 */
function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
      }
    : null;
}

/**
 * Convert RGB to hex
 */
function rgbToHex(r: number, g: number, b: number): string {
  return '#' + [r, g, b].map(x => {
    const hex = Math.round(Math.max(0, Math.min(255, x))).toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  }).join('');
}

/**
 * Lighten a color by a percentage
 */
function lighten(hex: string, amount: number): string {
  const rgb = hexToRgb(hex);
  if (!rgb) return hex;
  
  const r = rgb.r + (255 - rgb.r) * amount;
  const g = rgb.g + (255 - rgb.g) * amount;
  const b = rgb.b + (255 - rgb.b) * amount;
  
  return rgbToHex(r, g, b);
}

/**
 * Darken a color by a percentage
 */
function darken(hex: string, amount: number): string {
  const rgb = hexToRgb(hex);
  if (!rgb) return hex;
  
  const r = rgb.r * (1 - amount);
  const g = rgb.g * (1 - amount);
  const b = rgb.b * (1 - amount);
  
  return rgbToHex(r, g, b);
}

/**
 * Generate color palette from hex color
 * This creates Tailwind-compatible shades (50-900)
 */
export function generateColorPalette(hex: string): Record<number, string> {
  return {
    50: lighten(hex, 0.95),
    100: lighten(hex, 0.9),
    200: lighten(hex, 0.75),
    300: lighten(hex, 0.6),
    400: lighten(hex, 0.3),
    500: hex,
    600: darken(hex, 0.1),
    700: darken(hex, 0.3),
    800: darken(hex, 0.5),
    900: darken(hex, 0.7),
  };
}

/**
 * Apply theme to document
 */
export function applyTheme(theme: TenantTheme): void {
  const root = document.documentElement;
  
  // Generate color palettes
  const primaryPalette = generateColorPalette(theme.primaryColor);
  const secondaryPalette = theme.secondaryColor 
    ? generateColorPalette(theme.secondaryColor)
    : generateColorPalette(theme.primaryColor);
  
  // Set CSS variables
  Object.entries(primaryPalette).forEach(([shade, color]) => {
    root.style.setProperty(`--color-primary-${shade}`, color);
  });
  
  Object.entries(secondaryPalette).forEach(([shade, color]) => {
    root.style.setProperty(`--color-secondary-${shade}`, color);
  });
  
  // Set font family
  if (theme.fontFamily) {
    root.style.setProperty('--font-family', theme.fontFamily);
  }
  
  // Update page title
  document.title = `${theme.name} - LMS`;
}

/**
 * Extract subdomain from current URL
 */
export function getSubdomain(): string {
  const hostname = window.location.hostname;
  
  // Development
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'demo';
  }
  
  // Production: subdomain.lms.com
  const parts = hostname.split('.');
  if (parts.length >= 2) {
    return parts[0];
  }
  
  return 'demo';
}

/**
 * Load theme from API based on subdomain
 */
export async function loadTenantTheme(): Promise<TenantTheme> {
  try {
    const { api } = await import('./api');
    const response = await api.get('/tenants/theme/');

    const data = response.data as {
      name: string;
      subdomain: string;
      logo_url?: string | null;
      primary_color: string;
      secondary_color?: string | null;
      font_family?: string | null;
      tenant_found?: boolean;
      reason?: 'not_found' | 'trial_expired' | 'deactivated';
      message?: string;
    };

    return {
      name: data.name,
      subdomain: data.subdomain,
      logo: data.logo_url || undefined,
      primaryColor: data.primary_color || DEFAULT_THEME.primaryColor,
      secondaryColor: data.secondary_color || undefined,
      fontFamily: data.font_family || DEFAULT_THEME.fontFamily,
      tenantFound: data.tenant_found !== false,
      tenantErrorReason: data.tenant_found === false ? data.reason : undefined,
      tenantErrorMessage: data.tenant_found === false ? data.message : undefined,
    };
  } catch (error) {
    console.error('Failed to load theme:', error);
    return DEFAULT_THEME;
  }
}
