import Chip from '@mui/material/Chip';
import { alpha, useTheme } from '@mui/material/styles';
import OpenInNewRoundedIcon from '@mui/icons-material/OpenInNewRounded';
import type { Citation } from '../types';

type Props = {
  citation: Citation;
  onClick?: (c: Citation) => void;
};

export function CitationChip({ citation, onClick }: Props) {
  const theme = useTheme();
  return (
    <Chip
      onClick={() => onClick?.(citation)}
      component="a"
      href={citation.url}
      target="_blank"
      rel="noreferrer noopener"
      clickable
      label={citation.citation}
      icon={<OpenInNewRoundedIcon style={{ fontSize: 14 }} />}
      size="small"
      sx={{
        fontFamily: '"JetBrains Mono", ui-monospace, monospace',
        fontWeight: 500,
        fontSize: 12.5,
        px: 0.5,
        bgcolor:
          theme.palette.mode === 'light'
            ? alpha(theme.palette.primary.main, 0.08)
            : alpha(theme.palette.primary.light, 0.18),
        color:
          theme.palette.mode === 'light'
            ? theme.palette.primary.dark
            : theme.palette.primary.light,
        border: `1px solid ${
          theme.palette.mode === 'light'
            ? alpha(theme.palette.primary.main, 0.2)
            : alpha(theme.palette.primary.light, 0.3)
        }`,
        '& .MuiChip-icon': { ml: 0.5, mr: -0.25, color: 'inherit' },
        '&:hover': {
          bgcolor:
            theme.palette.mode === 'light'
              ? alpha(theme.palette.primary.main, 0.14)
              : alpha(theme.palette.primary.light, 0.26),
        },
      }}
    />
  );
}
