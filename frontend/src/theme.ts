import { createTheme, alpha } from '@mui/material/styles';
import type { PaletteMode, ThemeOptions } from '@mui/material';

// Iowa Legal Corpus palette: deep slate-blue primary, warm gold accent.
// Designed to feel authoritative without being stiff. Surfaces use a warm
// near-white in light mode and a deep ink in dark mode (Claude/ChatGPT-like).
const brand = {
  primary: '#2a5b9c',
  primaryDeep: '#1f3a5f',
  primaryLight: '#5e87c8',
  accent: '#c9a227',
  accentSoft: '#f4d774',
};

const buildTheme = (mode: PaletteMode): ThemeOptions => {
  const isLight = mode === 'light';
  return {
    palette: {
      mode,
      primary: {
        main: isLight ? brand.primary : brand.primaryLight,
        dark: brand.primaryDeep,
        light: brand.primaryLight,
        contrastText: '#ffffff',
      },
      secondary: {
        main: isLight ? brand.accent : brand.accentSoft,
        contrastText: isLight ? '#1a1a1a' : '#1a1a1a',
      },
      background: {
        default: isLight ? '#f7f5f2' : '#0e1117',
        paper: isLight ? '#ffffff' : '#161b22',
      },
      text: {
        primary: isLight ? '#1a1f2b' : '#e6edf3',
        secondary: isLight ? '#525a6b' : '#9aa6b2',
      },
      divider: isLight ? alpha('#1a1f2b', 0.08) : alpha('#e6edf3', 0.08),
    },
    shape: { borderRadius: 14 },
    typography: {
      fontFamily:
        '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      h1: { fontWeight: 700, letterSpacing: '-0.02em' },
      h2: { fontWeight: 700, letterSpacing: '-0.02em' },
      h3: { fontWeight: 700, letterSpacing: '-0.01em' },
      h4: { fontWeight: 600, letterSpacing: '-0.01em' },
      h5: { fontWeight: 600 },
      h6: { fontWeight: 600 },
      button: { textTransform: 'none', fontWeight: 500 },
      body1: { lineHeight: 1.65 },
      body2: { lineHeight: 1.6 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundImage: isLight
              ? `radial-gradient(at 0% 0%, ${alpha(brand.primaryLight, 0.08)} 0%, transparent 50%),
                 radial-gradient(at 100% 0%, ${alpha(brand.accentSoft, 0.12)} 0%, transparent 50%)`
              : `radial-gradient(at 0% 0%, ${alpha(brand.primary, 0.18)} 0%, transparent 50%),
                 radial-gradient(at 100% 100%, ${alpha(brand.primaryDeep, 0.4)} 0%, transparent 50%)`,
            backgroundAttachment: 'fixed',
          },
          '*::-webkit-scrollbar': { width: 10, height: 10 },
          '*::-webkit-scrollbar-thumb': {
            background: isLight ? alpha('#1a1f2b', 0.18) : alpha('#e6edf3', 0.18),
            borderRadius: 8,
          },
          '*::-webkit-scrollbar-thumb:hover': {
            background: isLight ? alpha('#1a1f2b', 0.28) : alpha('#e6edf3', 0.28),
          },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: { borderRadius: 12, paddingInline: 18 },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: { backgroundImage: 'none' },
        },
      },
      MuiTooltip: {
        styleOverrides: {
          tooltip: { fontSize: 12, borderRadius: 8, paddingInline: 10 },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { borderRadius: 8, fontWeight: 500 },
        },
      },
    },
  };
};

export const lightTheme = createTheme(buildTheme('light'));
export const darkTheme = createTheme(buildTheme('dark'));
