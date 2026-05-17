import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { useTheme } from '@mui/material/styles';

type Props = {
  size?: number;
  showWordmark?: boolean;
};

export function BrandMark({ size = 32, showWordmark = true }: Props) {
  const theme = useTheme();
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
      <Box
        sx={{
          width: size,
          height: size,
          borderRadius: 2,
          background: `linear-gradient(135deg, ${theme.palette.primary.light}, ${theme.palette.primary.dark})`,
          color: theme.palette.secondary.main,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          boxShadow: `0 6px 16px ${theme.palette.mode === 'light' ? 'rgba(31,58,95,0.18)' : 'rgba(0,0,0,0.4)'}`,
        }}
        aria-hidden
      >
        <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 24 24" fill="none">
          <path
            d="M4 6h16M4 12h16M4 18h11"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <circle cx="19" cy="18" r="2" fill="currentColor" />
        </svg>
      </Box>
      {showWordmark && (
        <Box sx={{ lineHeight: 1.1 }}>
          <Typography variant="body1" sx={{ fontWeight: 700, letterSpacing: '-0.01em' }}>
            Iowa Legal
          </Typography>
          <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: '-2px' }}>
            Corpus chat · beta
          </Typography>
        </Box>
      )}
    </Box>
  );
}
