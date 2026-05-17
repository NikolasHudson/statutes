import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import { alpha, useTheme } from '@mui/material/styles';

import ContentCopyRoundedIcon from '@mui/icons-material/ContentCopyRounded';
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined';
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined';
import ReplayRoundedIcon from '@mui/icons-material/ReplayRounded';

import type { Message } from '../types';
import { CitationChip } from './CitationChip';
import { SourceCard } from './SourceCard';
import { MarkdownText } from './markdown';

type Props = { message: Message };

function TypingDots() {
  return (
    <Stack direction="row" spacing={0.6} sx={{ alignItems: 'center', py: 0.5 }}>
      {[0, 1, 2].map((i) => (
        <Box
          key={i}
          sx={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            bgcolor: 'text.secondary',
            animation: 'blink 1.2s infinite',
            animationDelay: `${i * 0.18}s`,
          }}
        />
      ))}
    </Stack>
  );
}

export function MessageBubble({ message }: Props) {
  const theme = useTheme();
  const isUser = message.role === 'user';

  return (
    <Box
      sx={{
        display: 'flex',
        gap: 2,
        maxWidth: 820,
        mx: 'auto',
        width: '100%',
        px: { xs: 2, md: 3 },
        py: 2.5,
        animation: 'fadeUp 280ms ease both',
      }}
    >
      <Avatar
        sx={{
          width: 34,
          height: 34,
          mt: 0.25,
          flexShrink: 0,
          background: isUser
            ? alpha(theme.palette.text.primary, 0.08)
            : `linear-gradient(135deg, ${theme.palette.primary.light}, ${theme.palette.primary.dark})`,
          color: isUser ? theme.palette.text.primary : theme.palette.secondary.main,
          fontSize: 14,
          fontWeight: 600,
        }}
      >
        {isUser ? (
          'NH'
        ) : (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M4 6h16M4 12h16M4 18h11"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <circle cx="19" cy="18" r="2" fill="currentColor" />
          </svg>
        )}
      </Avatar>

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.75 }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {isUser ? 'You' : 'Iowa Legal'}
          </Typography>
          <Typography variant="caption" color="textSecondary">
            {new Date(message.createdAt).toLocaleTimeString([], {
              hour: 'numeric',
              minute: '2-digit',
            })}
          </Typography>
        </Stack>

        <Box
          sx={{
            color: 'text.primary',
            ...(isUser
              ? {
                  display: 'inline-block',
                  bgcolor:
                    theme.palette.mode === 'light'
                      ? alpha(theme.palette.primary.main, 0.07)
                      : alpha(theme.palette.primary.light, 0.12),
                  border: `1px solid ${
                    theme.palette.mode === 'light'
                      ? alpha(theme.palette.primary.main, 0.12)
                      : alpha(theme.palette.primary.light, 0.18)
                  }`,
                  px: 2,
                  py: 1.25,
                  borderRadius: 2.5,
                }
              : {}),
          }}
        >
          {message.pending ? <TypingDots /> : <MarkdownText text={message.content} />}
        </Box>

        {!isUser && message.citations && message.citations.length > 0 && (
          <Box sx={{ mt: 1.5 }}>
            <Stack
              direction="row"
              spacing={0.75}
              useFlexGap
              sx={{ flexWrap: 'wrap', mb: 1.25 }}
            >
              {message.citations.map((c) => (
                <CitationChip key={c.id} citation={c} />
              ))}
            </Stack>
            <Typography
              variant="caption"
              color="textSecondary"
              sx={{
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                fontWeight: 600,
                fontSize: 11,
                display: 'block',
                mb: 0.75,
              }}
            >
              Sources
            </Typography>
            <Stack spacing={1}>
              {message.citations.map((c) => (
                <SourceCard key={`src-${c.id}`} citation={c} />
              ))}
            </Stack>
          </Box>
        )}

        {!isUser && !message.pending && (
          <Stack direction="row" spacing={0.25} sx={{ mt: 1, ml: -1 }}>
            <Tooltip title="Copy">
              <IconButton size="small" sx={{ color: 'text.secondary' }}>
                <ContentCopyRoundedIcon sx={{ fontSize: 16 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Helpful">
              <IconButton size="small" sx={{ color: 'text.secondary' }}>
                <ThumbUpAltOutlinedIcon sx={{ fontSize: 16 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Not helpful">
              <IconButton size="small" sx={{ color: 'text.secondary' }}>
                <ThumbDownAltOutlinedIcon sx={{ fontSize: 16 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Regenerate">
              <IconButton size="small" sx={{ color: 'text.secondary' }}>
                <ReplayRoundedIcon sx={{ fontSize: 16 }} />
              </IconButton>
            </Tooltip>
          </Stack>
        )}
      </Box>
    </Box>
  );
}
