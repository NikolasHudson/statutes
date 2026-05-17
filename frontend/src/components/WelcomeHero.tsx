import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import { alpha, useTheme } from '@mui/material/styles';

import HomeWorkRoundedIcon from '@mui/icons-material/HomeWorkRounded';
import AccountBalanceRoundedIcon from '@mui/icons-material/AccountBalanceRounded';
import FamilyRestroomRoundedIcon from '@mui/icons-material/FamilyRestroomRounded';
import BusinessCenterRoundedIcon from '@mui/icons-material/BusinessCenterRounded';
import LocalPoliceRoundedIcon from '@mui/icons-material/LocalPoliceRounded';
import RuleRoundedIcon from '@mui/icons-material/RuleRounded';

import { suggestions, type Suggestion } from '../data/suggestions';

const iconFor = (key: Suggestion['icon']) => {
  switch (key) {
    case 'home':
      return <HomeWorkRoundedIcon />;
    case 'gavel':
      return <AccountBalanceRoundedIcon />;
    case 'family':
      return <FamilyRestroomRoundedIcon />;
    case 'business':
      return <BusinessCenterRoundedIcon />;
    case 'criminal':
      return <LocalPoliceRoundedIcon />;
    case 'rules':
      return <RuleRoundedIcon />;
  }
};

type Props = {
  onPick: (prompt: string) => void;
};

export function WelcomeHero({ onPick }: Props) {
  const theme = useTheme();
  return (
    <Box
      sx={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        px: { xs: 2, md: 4 },
        py: { xs: 4, md: 6 },
      }}
    >
      <Box sx={{ maxWidth: 820, width: '100%' }}>
        <Stack spacing={1.5} sx={{ textAlign: 'center', mb: 5, animation: 'fadeUp 400ms ease both' }}>
          <Typography
            variant="h4"
            sx={{
              fontSize: { xs: 30, md: 40 },
              fontWeight: 700,
              letterSpacing: '-0.02em',
              background: `linear-gradient(90deg, ${theme.palette.text.primary}, ${alpha(theme.palette.primary.main, 0.85)})`,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            How can I help with Iowa law today?
          </Typography>
          <Typography
            variant="body1"
            color="text.secondary"
            sx={{ maxWidth: 560, mx: 'auto' }}
          >
            Ask about a chapter, pull a pinpoint citation, or explore how a section has changed
            over time. Every answer comes back with a verifiable link to the official source.
          </Typography>
        </Stack>

        <Grid container spacing={1.5}>
          {suggestions.map((s, i) => (
            <Grid key={s.title} size={{ xs: 12, sm: 6 }}>
              <Box
                role="button"
                tabIndex={0}
                onClick={() => onPick(s.prompt)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onPick(s.prompt);
                  }
                }}
                sx={{
                  cursor: 'pointer',
                  p: 2,
                  borderRadius: 3,
                  border: `1px solid ${theme.palette.divider}`,
                  bgcolor:
                    theme.palette.mode === 'light'
                      ? alpha('#ffffff', 0.7)
                      : alpha('#ffffff', 0.02),
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 1.5,
                  transition: 'all 180ms ease',
                  animation: `fadeUp 420ms ease both`,
                  animationDelay: `${80 + i * 40}ms`,
                  '&:hover': {
                    borderColor: alpha(theme.palette.primary.main, 0.45),
                    transform: 'translateY(-2px)',
                    boxShadow: `0 12px 32px ${
                      theme.palette.mode === 'light'
                        ? 'rgba(31,58,95,0.10)'
                        : 'rgba(0,0,0,0.4)'
                    }`,
                  },
                  '&:focus-visible': {
                    outline: `2px solid ${theme.palette.primary.main}`,
                    outlineOffset: 2,
                  },
                }}
              >
                <Box
                  sx={{
                    width: 36,
                    height: 36,
                    borderRadius: 1.5,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    bgcolor: alpha(theme.palette.primary.main, 0.1),
                    color: 'primary.main',
                    flexShrink: 0,
                  }}
                >
                  {iconFor(s.icon)}
                </Box>
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.25 }}>
                    {s.title}
                  </Typography>
                  <Typography variant="body2" color="textSecondary" sx={{ lineHeight: 1.45 }}>
                    {s.prompt}
                  </Typography>
                </Box>
              </Box>
            </Grid>
          ))}
        </Grid>
      </Box>
    </Box>
  );
}
