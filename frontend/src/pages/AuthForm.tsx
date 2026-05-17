import { useState, type FormEvent } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';

import VerifiedOutlinedIcon from '@mui/icons-material/VerifiedOutlined';
import HistoryEduOutlinedIcon from '@mui/icons-material/HistoryEduOutlined';
import TravelExploreRoundedIcon from '@mui/icons-material/TravelExploreRounded';

import { ApiError, login, register, type User } from '../api';
import { useHashRoute } from '../useHashRoute';
import { usePalette } from './legalPalette';

type Mode = 'login' | 'register';

type Props = {
  mode: Mode;
  onAuthed: (user: User) => void;
};

const FEATURES = [
  {
    icon: <VerifiedOutlinedIcon />,
    title: 'Reviewed & grounded',
    body: 'Every answer is traced to the currently effective, human-reviewed text.',
  },
  {
    icon: <HistoryEduOutlinedIcon />,
    title: 'Full citations',
    body: 'Citation, effective date, and enacting session law on every provision.',
  },
  {
    icon: <TravelExploreRoundedIcon />,
    title: 'Hybrid search',
    body: 'FTS + pg_trgm + pgvector embeddings fused with Reciprocal Rank Fusion.',
  },
];

export function AuthForm({ mode, onAuthed }: Props) {
  const pal = usePalette();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, navigate] = useHashRoute();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const user =
        mode === 'register'
          ? await register({ email, password, full_name: fullName })
          : await login({ email, password });
      onAuthed(user);
      navigate('account');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Network error');
    } finally {
      setBusy(false);
    }
  };

  const title = mode === 'register' ? 'Create your account' : 'Sign in';
  const cta = mode === 'register' ? 'Create account' : 'Sign in';
  const otherLabel =
    mode === 'register'
      ? 'Already have an account? Sign in'
      : 'New here? Create an account';
  const otherTarget = mode === 'register' ? 'login' : 'register';

  return (
    <Box
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', md: '1fr 1fr', lg: '1.05fr 1fr' },
        bgcolor: pal.paper,
        color: pal.text,
      }}
    >
      {/* Left — branded "image" panel. Mirrors the corpus browser's black
          title banner over deep-navy chrome so the two surfaces never drift. */}
      <Box
        sx={{
          display: { xs: 'none', md: 'flex' },
          position: 'relative',
          flexDirection: 'column',
          justifyContent: 'space-between',
          overflow: 'hidden',
          color: pal.chromeText,
          bgcolor: pal.bottomBar,
          backgroundImage: 'url(/login-bg.webp)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          px: { md: 6, lg: 8 },
          py: { md: 6, lg: 8 },
        }}
      >
        {/* Palette-tinted scrim so the white copy stays legible over any
            photo — darkest on the left where the text column sits. */}
        <Box
          aria-hidden
          sx={{
            position: 'absolute',
            inset: 0,
            backgroundImage: `linear-gradient(135deg, ${pal.bottomBar}f2 0%, ${pal.bottomBar}cc 45%, ${pal.chrome}99 100%)`,
            pointerEvents: 'none',
          }}
        />

        <Box sx={{ position: 'relative' }}>
          <Typography
            sx={{
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              opacity: 0.7,
            }}
          >
            Iowa Legal Corpus
          </Typography>
        </Box>

        <Box sx={{ position: 'relative', maxWidth: 460 }}>
          {/* Black banner block, same treatment as the reader's DocumentBanner. */}
          <Box
            sx={{
              bgcolor: pal.banner,
              color: pal.bannerText,
              display: 'inline-block',
              px: 3,
              py: 2,
              mb: 4,
            }}
          >
            <Typography
              sx={{
                fontSize: { md: 28, lg: 34 },
                fontWeight: 700,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                lineHeight: 1.15,
              }}
            >
              Iowa Statutes
              <br />& Court Rules
            </Typography>
          </Box>

          <Typography
            sx={{ fontSize: 16, lineHeight: 1.7, opacity: 0.88, mb: 4 }}
          >
            A grounded, citable interface to the Iowa Code and Court Rules —
            built for practitioners who need the effective text, not a guess.
          </Typography>

          <Stack spacing={2.5}>
            {FEATURES.map((f) => (
              <Box
                key={f.title}
                sx={{ display: 'flex', gap: 1.75, alignItems: 'flex-start' }}
              >
                <Box
                  sx={{
                    flexShrink: 0,
                    width: 34,
                    height: 34,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    border: `1px solid ${pal.circleBorder}`,
                    bgcolor: pal.chromeHover,
                    '& svg': { fontSize: 18 },
                  }}
                >
                  {f.icon}
                </Box>
                <Box>
                  <Typography sx={{ fontSize: 14.5, fontWeight: 700 }}>
                    {f.title}
                  </Typography>
                  <Typography
                    sx={{ fontSize: 13, opacity: 0.78, lineHeight: 1.55 }}
                  >
                    {f.body}
                  </Typography>
                </Box>
              </Box>
            ))}
          </Stack>
        </Box>

        <Typography
          sx={{ position: 'relative', fontSize: 12, opacity: 0.6 }}
        >
          Sourced from legis.iowa.gov · Not a substitute for the official
          publication.
        </Typography>
      </Box>

      {/* Right — the form. */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflowY: 'auto',
          px: { xs: 3, sm: 6 },
          py: 6,
        }}
      >
        <Box sx={{ width: '100%', maxWidth: 400 }}>
          <Typography
            sx={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              color: pal.muted,
              mb: 1,
              display: { md: 'none' },
            }}
          >
            Iowa Legal Corpus
          </Typography>

          <Typography
            sx={{
              fontSize: 26,
              fontWeight: 700,
              color: pal.text,
              mb: 0.75,
            }}
          >
            {title}
          </Typography>
          <Typography sx={{ fontSize: 14, color: pal.muted, mb: 3.5 }}>
            {mode === 'register'
              ? 'Get an API key to use the Iowa Legal Corpus from Claude Desktop or your own integration.'
              : 'Sign in to manage your API keys.'}
          </Typography>

          {error && (
            <Alert severity="error" sx={{ mb: 2.5 }}>
              {error}
            </Alert>
          )}

          <Box component="form" onSubmit={submit}>
            <Stack spacing={2.25}>
              {mode === 'register' && (
                <TextField
                  label="Full name (optional)"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  disabled={busy}
                  fullWidth
                />
              )}
              <TextField
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={busy}
                fullWidth
                autoComplete={mode === 'register' ? 'email' : 'username'}
              />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={busy}
                fullWidth
                autoComplete={
                  mode === 'register' ? 'new-password' : 'current-password'
                }
                helperText={
                  mode === 'register' ? 'At least 8 characters.' : ' '
                }
              />
              <Button
                type="submit"
                variant="contained"
                disabled={busy}
                size="large"
                sx={{ py: 1.25 }}
              >
                {busy ? 'Working…' : cta}
              </Button>
              <Link
                component="button"
                type="button"
                onClick={() => navigate(otherTarget)}
                underline="hover"
                sx={{
                  alignSelf: 'center',
                  color: pal.link,
                  fontSize: 14,
                  mt: 0.5,
                }}
              >
                {otherLabel}
              </Link>
            </Stack>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
