import { useMemo } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import Avatar from '@mui/material/Avatar';
import Stack from '@mui/material/Stack';
import { alpha, useTheme } from '@mui/material/styles';

import AddRoundedIcon from '@mui/icons-material/AddRounded';
import SearchRoundedIcon from '@mui/icons-material/SearchRounded';
import ChevronLeftRoundedIcon from '@mui/icons-material/ChevronLeftRounded';
import PushPinRoundedIcon from '@mui/icons-material/PushPinRounded';
import HistoryRoundedIcon from '@mui/icons-material/HistoryRounded';
import LightModeRoundedIcon from '@mui/icons-material/LightModeRounded';
import DarkModeRoundedIcon from '@mui/icons-material/DarkModeRounded';
import LibraryBooksRoundedIcon from '@mui/icons-material/LibraryBooksRounded';

import { BrandMark } from './BrandMark';
import type { Conversation } from '../types';

type Props = {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onOpenProfile?: () => void;
  onOpenSources?: () => void;
  onCollapse?: () => void;
  themeMode: 'light' | 'dark';
  onToggleTheme: () => void;
};

function groupByRecency(items: Conversation[]) {
  const now = Date.now();
  const day = 1000 * 60 * 60 * 24;
  const groups: Record<string, Conversation[]> = {
    Pinned: [],
    Today: [],
    'Previous 7 days': [],
    'Previous 30 days': [],
    Older: [],
  };
  for (const c of items) {
    const age = now - new Date(c.updatedAt).getTime();
    if (c.pinned) groups.Pinned.push(c);
    else if (age < day) groups.Today.push(c);
    else if (age < day * 7) groups['Previous 7 days'].push(c);
    else if (age < day * 30) groups['Previous 30 days'].push(c);
    else groups.Older.push(c);
  }
  return groups;
}

export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onOpenProfile,
  onOpenSources,
  onCollapse,
  themeMode,
  onToggleTheme,
}: Props) {
  const theme = useTheme();
  const grouped = useMemo(() => groupByRecency(conversations), [conversations]);

  return (
    <Box
      component="aside"
      sx={{
        height: '100%',
        width: 288,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        bgcolor:
          theme.palette.mode === 'light'
            ? alpha('#ffffff', 0.7)
            : alpha('#0b0e13', 0.65),
        backdropFilter: 'blur(14px)',
        borderRight: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Box sx={{ p: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <BrandMark />
        {onCollapse && (
          <Tooltip title="Collapse sidebar">
            <IconButton size="small" onClick={onCollapse} aria-label="Collapse sidebar">
              <ChevronLeftRoundedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      <Box sx={{ px: 2, pb: 1.5 }}>
        <Button
          fullWidth
          variant="contained"
          startIcon={<AddRoundedIcon />}
          onClick={onNewChat}
          sx={{
            justifyContent: 'flex-start',
            py: 1.1,
            background: `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.primary.dark})`,
            '&:hover': {
              background: `linear-gradient(135deg, ${theme.palette.primary.dark}, ${theme.palette.primary.main})`,
            },
          }}
        >
          New chat
        </Button>
      </Box>

      <Box sx={{ px: 2, pb: 1.5 }}>
        <TextField
          fullWidth
          size="small"
          placeholder="Search conversations"
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchRoundedIcon fontSize="small" sx={{ color: 'text.secondary' }} />
                </InputAdornment>
              ),
              sx: {
                borderRadius: 2,
                bgcolor:
                  theme.palette.mode === 'light'
                    ? alpha(theme.palette.primary.main, 0.04)
                    : alpha('#ffffff', 0.04),
              },
            },
          }}
        />
      </Box>

      <Box sx={{ flex: 1, overflowY: 'auto', px: 1, pb: 1 }}>
        {Object.entries(grouped).map(([label, items]) =>
          items.length === 0 ? null : (
            <Box key={label} sx={{ mt: 1.5 }}>
              <Stack
                direction="row"
                spacing={0.75}
                sx={{ alignItems: 'center', px: 1.5, mb: 0.5 }}
              >
                {label === 'Pinned' ? (
                  <PushPinRoundedIcon sx={{ fontSize: 13, color: 'text.secondary' }} />
                ) : (
                  <HistoryRoundedIcon sx={{ fontSize: 13, color: 'text.secondary' }} />
                )}
                <Typography
                  variant="caption"
                  sx={{
                    color: 'text.secondary',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    fontWeight: 600,
                    fontSize: 11,
                  }}
                >
                  {label}
                </Typography>
              </Stack>
              <List dense disablePadding>
                {items.map((c) => {
                  const active = c.id === activeId;
                  return (
                    <ListItemButton
                      key={c.id}
                      selected={active}
                      onClick={() => onSelect(c.id)}
                      sx={{
                        borderRadius: 2,
                        mx: 0.5,
                        my: 0.25,
                        py: 0.85,
                        '&.Mui-selected': {
                          bgcolor:
                            theme.palette.mode === 'light'
                              ? alpha(theme.palette.primary.main, 0.1)
                              : alpha(theme.palette.primary.main, 0.18),
                          '&:hover': {
                            bgcolor:
                              theme.palette.mode === 'light'
                                ? alpha(theme.palette.primary.main, 0.14)
                                : alpha(theme.palette.primary.main, 0.24),
                          },
                        },
                      }}
                    >
                      <ListItemText
                        primary={c.title}
                        slotProps={{
                          primary: {
                            noWrap: true,
                            sx: { fontWeight: active ? 600 : 500, fontSize: 14 },
                          },
                        }}
                      />
                    </ListItemButton>
                  );
                })}
              </List>
            </Box>
          ),
        )}
      </Box>

      <Divider />

      <Box sx={{ p: 1.5 }}>
        <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
          <Button
            size="small"
            onClick={onOpenSources}
            startIcon={<LibraryBooksRoundedIcon fontSize="small" />}
            sx={{ color: 'text.secondary', flex: 1, justifyContent: 'flex-start' }}
          >
            Sources
          </Button>
          <Tooltip title={themeMode === 'light' ? 'Dark mode' : 'Light mode'}>
            <IconButton size="small" onClick={onToggleTheme} aria-label="Toggle theme">
              {themeMode === 'light' ? (
                <DarkModeRoundedIcon fontSize="small" />
              ) : (
                <LightModeRoundedIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
        </Stack>

        <Tooltip title="Open account" placement="top">
          <Stack
            component="button"
            type="button"
            onClick={onOpenProfile}
            direction="row"
            spacing={1.25}
            sx={{
              width: '100%',
              alignItems: 'center',
              p: 1,
              borderRadius: 2,
              border: `1px solid ${theme.palette.divider}`,
              bgcolor:
                theme.palette.mode === 'light'
                  ? alpha('#ffffff', 0.6)
                  : alpha('#ffffff', 0.02),
              cursor: 'pointer',
              textAlign: 'left',
              font: 'inherit',
              color: 'inherit',
              transition: 'background-color 120ms ease, border-color 120ms ease',
              '&:hover': {
                bgcolor:
                  theme.palette.mode === 'light'
                    ? alpha(theme.palette.primary.main, 0.06)
                    : alpha(theme.palette.primary.main, 0.12),
                borderColor: alpha(theme.palette.primary.main, 0.3),
              },
              '&:focus-visible': {
                outline: `2px solid ${alpha(theme.palette.primary.main, 0.5)}`,
                outlineOffset: 2,
              },
            }}
          >
            <Avatar
              sx={{
                width: 32,
                height: 32,
                bgcolor: theme.palette.primary.main,
                fontSize: 14,
                fontWeight: 600,
              }}
            >
              NH
            </Avatar>
            <Box sx={{ minWidth: 0, lineHeight: 1.2 }}>
              <Typography variant="body2" noWrap sx={{ fontWeight: 600 }}>
                Nick Hudson
              </Typography>
              <Typography variant="caption" color="textSecondary" noWrap>
                Free plan · Iowa Code only
              </Typography>
            </Box>
          </Stack>
        </Tooltip>
      </Box>
    </Box>
  );
}
