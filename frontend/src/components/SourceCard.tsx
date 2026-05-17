import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import { alpha, useTheme } from '@mui/material/styles';
import VerifiedRoundedIcon from '@mui/icons-material/VerifiedRounded';
import EventAvailableRoundedIcon from '@mui/icons-material/EventAvailableRounded';
import LaunchRoundedIcon from '@mui/icons-material/LaunchRounded';

import type { Citation } from '../types';

const fmt = (iso: string) =>
  new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });

export function SourceCard({ citation }: { citation: Citation }) {
  const theme = useTheme();
  return (
    <Box
      component="a"
      href={citation.url}
      target="_blank"
      rel="noreferrer noopener"
      sx={{
        textDecoration: 'none',
        color: 'inherit',
        display: 'block',
        p: 1.75,
        borderRadius: 2.5,
        border: `1px solid ${theme.palette.divider}`,
        bgcolor:
          theme.palette.mode === 'light'
            ? alpha('#ffffff', 0.7)
            : alpha('#ffffff', 0.02),
        transition: 'all 160ms ease',
        '&:hover': {
          borderColor: alpha(theme.palette.primary.main, 0.45),
          transform: 'translateY(-1px)',
          boxShadow: `0 8px 24px ${
            theme.palette.mode === 'light'
              ? 'rgba(31,58,95,0.10)'
              : 'rgba(0,0,0,0.4)'
          }`,
        },
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
        <Typography
          variant="caption"
          sx={{
            fontFamily: '"JetBrains Mono", monospace',
            fontWeight: 600,
            color: 'primary.main',
            letterSpacing: '-0.01em',
          }}
        >
          {citation.citation}
        </Typography>
        <Tooltip title="Verified against legis.iowa.gov">
          <VerifiedRoundedIcon sx={{ fontSize: 14, color: 'secondary.main' }} />
        </Tooltip>
        <Box sx={{ flex: 1 }} />
        <LaunchRoundedIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
      </Stack>

      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5, lineHeight: 1.3 }}>
        {citation.heading}
      </Typography>

      {citation.snippet && (
        <Typography
          variant="body2"
          color="textSecondary"
          sx={{
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            mb: 1,
          }}
        >
          {citation.snippet}
        </Typography>
      )}

      <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', mt: 0.5 }}>
        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
          <EventAvailableRoundedIcon sx={{ fontSize: 13, color: 'text.secondary' }} />
          <Typography variant="caption" color="textSecondary">
            As of {fmt(citation.effectiveFrom)}
          </Typography>
        </Stack>
        <Typography variant="caption" color="textSecondary">
          ·
        </Typography>
        <Typography variant="caption" color="textSecondary">
          {citation.source}
        </Typography>
        {typeof citation.relevance === 'number' && (
          <>
            <Typography variant="caption" color="textSecondary">
              ·
            </Typography>
            <Typography variant="caption" color="textSecondary">
              {Math.round(citation.relevance * 100)}% match
            </Typography>
          </>
        )}
      </Stack>
    </Box>
  );
}
