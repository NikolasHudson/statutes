import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import { alpha, useTheme } from '@mui/material/styles';

import MenuRoundedIcon from '@mui/icons-material/MenuRounded';
import IosShareRoundedIcon from '@mui/icons-material/IosShareRounded';
import KeyboardArrowDownRoundedIcon from '@mui/icons-material/KeyboardArrowDownRounded';
import TuneRoundedIcon from '@mui/icons-material/TuneRounded';

type Props = {
  title: string;
  onOpenSidebar?: () => void;
  showSidebarToggle?: boolean;
};

export function TopBar({ title, onOpenSidebar, showSidebarToggle }: Props) {
  const theme = useTheme();
  return (
    <Box
      component="header"
      sx={{
        position: 'sticky',
        top: 0,
        zIndex: 5,
        px: { xs: 1.5, md: 2.5 },
        py: 1.25,
        bgcolor:
          theme.palette.mode === 'light'
            ? alpha('#ffffff', 0.7)
            : alpha('#0b0e13', 0.65),
        backdropFilter: 'blur(14px)',
        borderBottom: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        {showSidebarToggle && (
          <Tooltip title="Open sidebar">
            <IconButton size="small" onClick={onOpenSidebar} aria-label="Open sidebar">
              <MenuRoundedIcon />
            </IconButton>
          </Tooltip>
        )}

        <Button
          size="small"
          endIcon={<KeyboardArrowDownRoundedIcon />}
          sx={{
            color: 'text.primary',
            fontWeight: 600,
            px: 1.25,
            '&:hover': {
              bgcolor: alpha(theme.palette.text.primary, 0.06),
            },
          }}
        >
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Typography variant="body2" noWrap sx={{ fontWeight: 600, maxWidth: 360 }}>
              {title}
            </Typography>
            <Chip
              size="small"
              label="Iowa Code"
              sx={{
                height: 20,
                fontSize: 11,
                fontWeight: 600,
                bgcolor: alpha(theme.palette.primary.main, 0.1),
                color: 'primary.main',
              }}
            />
          </Stack>
        </Button>

        <Box sx={{ flex: 1 }} />

        <Tooltip title="Conversation settings">
          <IconButton size="small">
            <TuneRoundedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Share">
          <IconButton size="small">
            <IosShareRoundedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    </Box>
  );
}
