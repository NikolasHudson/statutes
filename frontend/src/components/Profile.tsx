import { useState } from 'react';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import LinearProgress from '@mui/material/LinearProgress';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { alpha, useTheme } from '@mui/material/styles';

import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded';
import VerifiedRoundedIcon from '@mui/icons-material/VerifiedRounded';
import GavelRoundedIcon from '@mui/icons-material/GavelRounded';
import BoltRoundedIcon from '@mui/icons-material/BoltRounded';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import EditRoundedIcon from '@mui/icons-material/EditRounded';

type Props = {
  onBack: () => void;
};

const SOURCES = [
  { key: 'iowa-code', label: 'Iowa Code', enabled: true },
  { key: 'court-rules', label: 'Iowa Court Rules', enabled: true },
  { key: 'admin-code', label: 'Iowa Admin. Code', enabled: false },
  { key: 'session-laws', label: 'Session Laws (acts)', enabled: false },
];

export function Profile({ onBack }: Props) {
  const theme = useTheme();
  const isLight = theme.palette.mode === 'light';

  const [name, setName] = useState('Nick Hudson');
  const [email] = useState('nick@nickhudson.me');
  const [role, setRole] = useState('attorney');
  const [defaultMode, setDefaultMode] = useState('search');
  const [verbosity, setVerbosity] = useState('balanced');
  const [showCitations, setShowCitations] = useState(true);
  const [requireVerified, setRequireVerified] = useState(true);
  const [marketingEmails, setMarketingEmails] = useState(false);
  const [sources, setSources] = useState(SOURCES);

  const queriesUsed = 142;
  const queriesLimit = 500;
  const usagePct = Math.min(100, (queriesUsed / queriesLimit) * 100);

  const card = {
    p: { xs: 2, md: 3 },
    borderRadius: 3,
    border: `1px solid ${theme.palette.divider}`,
    bgcolor: isLight ? alpha('#ffffff', 0.7) : alpha('#ffffff', 0.02),
    backdropFilter: 'blur(10px)',
  } as const;

  return (
    <Box
      sx={{
        flex: 1,
        minHeight: 0,
        overflowY: 'auto',
        px: { xs: 2, md: 4 },
        py: { xs: 2, md: 3 },
      }}
    >
      <Box sx={{ maxWidth: 880, mx: 'auto' }}>
        {/* Header */}
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 3 }}>
          <Tooltip title="Back to chat">
            <IconButton onClick={onBack} size="small" aria-label="Back to chat">
              <ArrowBackRoundedIcon />
            </IconButton>
          </Tooltip>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: '-0.01em' }}>
              Account
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Manage your profile, preferences, and research scope.
            </Typography>
          </Box>
        </Stack>

        <Stack spacing={2.5}>
          {/* Identity card */}
          <Box sx={card}>
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={2.5}
              sx={{ alignItems: { xs: 'flex-start', sm: 'center' } }}
            >
              <Box sx={{ position: 'relative' }}>
                <Avatar
                  sx={{
                    width: 72,
                    height: 72,
                    fontSize: 26,
                    fontWeight: 700,
                    background: `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.primary.dark})`,
                  }}
                >
                  NH
                </Avatar>
                <Tooltip title="Change photo">
                  <IconButton
                    size="small"
                    sx={{
                      position: 'absolute',
                      bottom: -4,
                      right: -4,
                      bgcolor: 'background.paper',
                      border: `1px solid ${theme.palette.divider}`,
                      '&:hover': { bgcolor: 'background.paper' },
                    }}
                  >
                    <EditRoundedIcon sx={{ fontSize: 14 }} />
                  </IconButton>
                </Tooltip>
              </Box>

              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    {name}
                  </Typography>
                  <Chip
                    size="small"
                    icon={<VerifiedRoundedIcon sx={{ fontSize: 14 }} />}
                    label="Verified"
                    sx={{
                      height: 22,
                      bgcolor: alpha(theme.palette.primary.main, 0.12),
                      color: 'primary.main',
                      '& .MuiChip-icon': { color: 'inherit' },
                    }}
                  />
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  {email}
                </Typography>
                <Stack direction="row" spacing={0.75} sx={{ mt: 1, flexWrap: 'wrap' }} useFlexGap>
                  <Chip size="small" variant="outlined" label="Iowa State Bar" />
                  <Chip size="small" variant="outlined" label="Member since 2026" />
                </Stack>
              </Box>
            </Stack>

            <Divider sx={{ my: 2.5 }} />

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                label="Display name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                size="small"
                fullWidth
              />
              <TextField
                label="Email"
                value={email}
                disabled
                size="small"
                fullWidth
                helperText="Contact support to change your email"
              />
              <TextField
                select
                label="Role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                size="small"
                fullWidth
              >
                <MenuItem value="attorney">Attorney</MenuItem>
                <MenuItem value="paralegal">Paralegal</MenuItem>
                <MenuItem value="researcher">Legal researcher</MenuItem>
                <MenuItem value="student">Law student</MenuItem>
                <MenuItem value="public">General public</MenuItem>
              </TextField>
            </Stack>
          </Box>

          {/* Plan + usage */}
          <Box sx={card}>
            <Stack
              direction={{ xs: 'column', md: 'row' }}
              spacing={2}
              sx={{ alignItems: { md: 'center' }, justifyContent: 'space-between' }}
            >
              <Box>
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
                  <BoltRoundedIcon sx={{ color: theme.palette.secondary.main }} fontSize="small" />
                  <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: '0.1em' }}>
                    Plan
                  </Typography>
                </Stack>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  Free · Iowa Code only
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Upgrade to add court rules, admin code, and unlimited queries.
                </Typography>
              </Box>
              <Button
                variant="contained"
                sx={{
                  background: `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.primary.dark})`,
                  '&:hover': {
                    background: `linear-gradient(135deg, ${theme.palette.primary.dark}, ${theme.palette.primary.main})`,
                  },
                }}
              >
                Upgrade plan
              </Button>
            </Stack>

            <Box sx={{ mt: 2.5 }}>
              <Stack direction="row" sx={{ justifyContent: 'space-between', mb: 0.5 }}>
                <Typography variant="body2" color="text.secondary">
                  Queries this month
                </Typography>
                <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                  {queriesUsed.toLocaleString()} / {queriesLimit.toLocaleString()}
                </Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={usagePct}
                sx={{
                  height: 6,
                  borderRadius: 999,
                  bgcolor: alpha(theme.palette.primary.main, 0.12),
                  '& .MuiLinearProgress-bar': {
                    borderRadius: 999,
                    background: `linear-gradient(90deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
                  },
                }}
              />
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                Resets May 1, 2026.
              </Typography>
            </Box>
          </Box>

          {/* Research scope */}
          <Box sx={card}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
              <GavelRoundedIcon fontSize="small" sx={{ color: 'text.secondary' }} />
              <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: '0.1em' }}>
                Research scope
              </Typography>
            </Stack>
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
              Sources
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Choose which corpora to search. Disabled sources are excluded from retrieval.
            </Typography>

            <Stack spacing={1}>
              {sources.map((s) => (
                <Stack
                  key={s.key}
                  direction="row"
                  sx={{
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    py: 1,
                    px: 1.25,
                    borderRadius: 2,
                    border: `1px solid ${theme.palette.divider}`,
                    bgcolor: isLight ? alpha('#ffffff', 0.6) : alpha('#ffffff', 0.01),
                  }}
                >
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {s.label}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {s.enabled ? 'Included in every answer' : 'Excluded'}
                    </Typography>
                  </Box>
                  <Switch
                    checked={s.enabled}
                    onChange={(e) =>
                      setSources((prev) =>
                        prev.map((x) => (x.key === s.key ? { ...x, enabled: e.target.checked } : x)),
                      )
                    }
                  />
                </Stack>
              ))}
            </Stack>
          </Box>

          {/* Preferences */}
          <Box sx={card}>
            <Typography variant="overline" sx={{ color: 'text.secondary', letterSpacing: '0.1em' }}>
              Preferences
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
              Answer style
            </Typography>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
              <TextField
                select
                label="Default mode"
                value={defaultMode}
                onChange={(e) => setDefaultMode(e.target.value)}
                size="small"
                fullWidth
              >
                <MenuItem value="search">Search statutes</MenuItem>
                <MenuItem value="cite">Lookup citation</MenuItem>
                <MenuItem value="history">Version history</MenuItem>
              </TextField>
              <TextField
                select
                label="Verbosity"
                value={verbosity}
                onChange={(e) => setVerbosity(e.target.value)}
                size="small"
                fullWidth
              >
                <MenuItem value="terse">Terse</MenuItem>
                <MenuItem value="balanced">Balanced</MenuItem>
                <MenuItem value="thorough">Thorough</MenuItem>
              </TextField>
            </Stack>

            <Stack divider={<Divider />}>
              <FormControlLabel
                sx={{ justifyContent: 'space-between', ml: 0, py: 1 }}
                labelPlacement="start"
                control={
                  <Switch
                    checked={showCitations}
                    onChange={(e) => setShowCitations(e.target.checked)}
                  />
                }
                label={
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      Always show citations
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Inline source cards below every answer.
                    </Typography>
                  </Box>
                }
              />
              <FormControlLabel
                sx={{ justifyContent: 'space-between', ml: 0, py: 1 }}
                labelPlacement="start"
                control={
                  <Switch
                    checked={requireVerified}
                    onChange={(e) => setRequireVerified(e.target.checked)}
                  />
                }
                label={
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      Require verified citations
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Refuse to answer if a quote can't be matched against legis.iowa.gov.
                    </Typography>
                  </Box>
                }
              />
              <FormControlLabel
                sx={{ justifyContent: 'space-between', ml: 0, py: 1 }}
                labelPlacement="start"
                control={
                  <Switch
                    checked={marketingEmails}
                    onChange={(e) => setMarketingEmails(e.target.checked)}
                  />
                }
                label={
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      Product emails
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Occasional updates about new sources and features.
                    </Typography>
                  </Box>
                }
              />
            </Stack>
          </Box>

          {/* Danger zone */}
          <Box
            sx={{
              ...card,
              borderColor: alpha(theme.palette.error.main, 0.3),
            }}
          >
            <Typography variant="overline" sx={{ color: 'error.main', letterSpacing: '0.1em' }}>
              Account
            </Typography>
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1.5}
              sx={{ mt: 1, alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
            >
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  Sign out of all devices
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  You'll need to log back in everywhere you use Iowa Legal.
                </Typography>
              </Box>
              <Button
                variant="outlined"
                color="error"
                startIcon={<LogoutRoundedIcon />}
                sx={{ alignSelf: { xs: 'flex-start', sm: 'auto' } }}
              >
                Sign out
              </Button>
            </Stack>
          </Box>
        </Stack>
      </Box>
    </Box>
  );
}
