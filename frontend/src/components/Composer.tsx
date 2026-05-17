import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import InputBase from '@mui/material/InputBase';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import { alpha, useTheme } from '@mui/material/styles';

import SendRoundedIcon from '@mui/icons-material/SendRounded';
import MicNoneRoundedIcon from '@mui/icons-material/MicNoneRounded';
import HistoryEduRoundedIcon from '@mui/icons-material/HistoryEduRounded';
import TravelExploreRoundedIcon from '@mui/icons-material/TravelExploreRounded';
import FactCheckOutlinedIcon from '@mui/icons-material/FactCheckOutlined';

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (v: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
};

export function Composer({ value, onChange, onSubmit, disabled, autoFocus }: Props) {
  const theme = useTheme();
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const [mode, setMode] = useState<'search' | 'cite' | 'history'>('search');

  useEffect(() => {
    if (!ref.current) return;
    ref.current.style.height = 'auto';
    ref.current.style.height = Math.min(ref.current.scrollHeight, 220) + 'px';
  }, [value]);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const modeChips: Array<{ key: typeof mode; label: string; icon: React.ReactNode; hint: string }> = [
    {
      key: 'search',
      label: 'Search statutes',
      icon: <TravelExploreRoundedIcon sx={{ fontSize: 16 }} />,
      hint: 'Hybrid semantic search across the Iowa Code',
    },
    {
      key: 'cite',
      label: 'Lookup citation',
      icon: <FactCheckOutlinedIcon sx={{ fontSize: 16 }} />,
      hint: 'Exact text by citation, never approximate',
    },
    {
      key: 'history',
      label: 'Version history',
      icon: <HistoryEduRoundedIcon sx={{ fontSize: 16 }} />,
      hint: 'How a section has changed over time',
    },
  ];

  return (
    <Box
      sx={{
        position: 'sticky',
        bottom: 0,
        pt: 1,
        pb: 1.5,
        px: { xs: 1.5, md: 3 },
        bgcolor:
          theme.palette.mode === 'light'
            ? `linear-gradient(to top, ${theme.palette.background.default}, transparent)`
            : undefined,
        backgroundImage:
          theme.palette.mode === 'light'
            ? `linear-gradient(to top, ${theme.palette.background.default} 60%, transparent)`
            : `linear-gradient(to top, ${alpha('#0e1117', 0.95)} 60%, transparent)`,
      }}
    >
      <Box sx={{ maxWidth: 820, mx: 'auto' }}>
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: 'wrap', mb: 1 }}>
          {modeChips.map((chip) => {
            const active = mode === chip.key;
            return (
              <Tooltip key={chip.key} title={chip.hint}>
                <Chip
                  size="small"
                  icon={chip.icon as React.ReactElement}
                  label={chip.label}
                  onClick={() => setMode(chip.key)}
                  variant={active ? 'filled' : 'outlined'}
                  sx={{
                    fontWeight: 500,
                    borderColor: theme.palette.divider,
                    bgcolor: active
                      ? alpha(theme.palette.primary.main, 0.12)
                      : 'transparent',
                    color: active ? 'primary.main' : 'text.secondary',
                    '& .MuiChip-icon': {
                      color: 'inherit',
                      ml: 0.75,
                    },
                  }}
                />
              </Tooltip>
            );
          })}
        </Stack>

        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: 0.5,
            py: 0.5,
            pl: 1.75,
            pr: 0.5,
            borderRadius: 24,
            border: `1px solid ${theme.palette.divider}`,
            bgcolor: theme.palette.background.paper,
            boxShadow:
              theme.palette.mode === 'light'
                ? '0 8px 32px rgba(31,58,95,0.10), 0 1px 0 rgba(255,255,255,0.6) inset'
                : '0 12px 32px rgba(0,0,0,0.5), 0 1px 0 rgba(255,255,255,0.04) inset',
            transition: 'border-color 160ms ease, box-shadow 160ms ease',
            '&:focus-within': {
              borderColor: alpha(theme.palette.primary.main, 0.5),
              boxShadow: `0 0 0 4px ${alpha(theme.palette.primary.main, 0.12)}, 0 8px 32px rgba(31,58,95,0.12)`,
            },
          }}
        >
          <InputBase
            inputRef={ref}
            multiline
            minRows={1}
            maxRows={8}
            value={value}
            autoFocus={autoFocus}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKey}
            placeholder="Ask anything about the Iowa Code, court rules, or admin code…"
            sx={{
              flex: 1,
              fontSize: 15.5,
              lineHeight: 1.5,
              p: 0,
              '& textarea': {
                resize: 'none',
                py: '4.5px',
              },
            }}
          />

          <Tooltip title="Voice input">
            <IconButton size="small" sx={{ color: 'text.secondary', width: 32, height: 32 }}>
              <MicNoneRoundedIcon fontSize="small" />
            </IconButton>
          </Tooltip>

          <Tooltip title="Send (Enter)">
            <span>
              <IconButton
                onClick={submit}
                disabled={!value.trim() || disabled}
                sx={{
                  width: 32,
                  height: 32,
                  background: `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.primary.dark})`,
                  color: '#fff',
                  '&:hover': {
                    background: `linear-gradient(135deg, ${theme.palette.primary.dark}, ${theme.palette.primary.main})`,
                  },
                  '&.Mui-disabled': {
                    background: alpha(theme.palette.text.primary, 0.08),
                    color: alpha(theme.palette.text.primary, 0.32),
                  },
                }}
              >
                <SendRoundedIcon sx={{ fontSize: 18 }} />
              </IconButton>
            </span>
          </Tooltip>
        </Box>

        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: 'block', textAlign: 'center', mt: 1 }}
        >
          Iowa Legal can make mistakes. Verify every citation against{' '}
          <Box
            component="a"
            href="https://www.legis.iowa.gov"
            target="_blank"
            rel="noreferrer noopener"
            sx={{ color: 'primary.main', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
          >
            legis.iowa.gov
          </Box>
          .
        </Typography>
      </Box>
    </Box>
  );
}
