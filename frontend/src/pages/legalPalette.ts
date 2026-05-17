import { useMemo } from 'react';
import { useTheme } from '@mui/material/styles';

// Shared "American Legal Publishing" palette used by both the corpus browser
// and the AI chat so the two surfaces never drift into conflicting designs.
// Light mode mirrors the reference (blue chrome, black title banner, near-black
// links); dark mode keeps the same layout with dark-adapted equivalents.
export function usePalette() {
  const theme = useTheme();
  const light = theme.palette.mode === 'light';
  return useMemo(
    () =>
      light
        ? {
            chrome: '#4275BD',
            chromeText: '#ffffff',
            chromeHover: 'rgba(255,255,255,0.16)',
            banner: '#000000',
            bannerText: '#ffffff',
            paper: '#ffffff',
            sidebar: '#ffffff',
            text: '#212529',
            body: '#333333',
            link: '#1f3a5f',
            muted: '#6b7280',
            activeRow: '#e9e9e9',
            border: 'rgba(0,0,0,0.12)',
            borderSoft: 'rgba(0,0,0,0.07)',
            bottomBar: '#1f3a5f',
            circleBorder: '#4275BD',
            circleIcon: '#4275BD',
          }
        : {
            chrome: '#26344d',
            chromeText: '#e6edf3',
            chromeHover: 'rgba(255,255,255,0.10)',
            banner: '#000000',
            bannerText: '#ffffff',
            paper: '#161b22',
            sidebar: '#12161d',
            text: '#e6edf3',
            body: '#c4cdd9',
            link: '#7ea6e0',
            muted: '#8b97a5',
            activeRow: 'rgba(255,255,255,0.08)',
            border: 'rgba(255,255,255,0.12)',
            borderSoft: 'rgba(255,255,255,0.07)',
            bottomBar: '#0e1117',
            circleBorder: 'rgba(126,166,224,0.55)',
            circleIcon: '#7ea6e0',
          },
    [light],
  );
}

export type Pal = ReturnType<typeof usePalette>;
