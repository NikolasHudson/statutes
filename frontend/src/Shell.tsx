import { useEffect, useState } from 'react';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Container from '@mui/material/Container';
import CssBaseline from '@mui/material/CssBaseline';
import Stack from '@mui/material/Stack';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import { ThemeProvider } from '@mui/material/styles';

import TestPage from './TestPage';
import { AuthForm } from './pages/AuthForm';
import { AccountPage } from './pages/AccountPage';
import { BrowsePage } from './pages/BrowsePage';
import { ChatPage } from './pages/ChatPage';
import { useHashRoute } from './useHashRoute';
import { fetchMe, logout, type User } from './api';
import { lightTheme } from './theme';

// Top-level shell: owns auth state, picks the page based on the hash route.
// Keeps the existing TestPage as the index — anything more involved (sign in,
// account/keys) lives behind '#/login', '#/register', '#/account'.

export default function Shell() {
  const [route, navigate] = useHashRoute();
  const [user, setUser] = useState<User | null>(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        // 401 means "not signed in" — that's fine, we just leave user=null.
      })
      .finally(() => {
        if (!cancelled) setAuthChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // App is fully gated: logged-out users only see /login and /register.
  // Bounce any other route to /login so the URL is honest about state and
  // a refresh keeps them on the auth page. And bounce authed users away
  // from the auth pages — those don't apply once you're signed in.
  useEffect(() => {
    if (!authChecked) return;
    if (!user && route !== 'login' && route !== 'register') {
      navigate('login');
    } else if (user && (route === 'login' || route === 'register')) {
      navigate('');
    }
  }, [authChecked, route, user, navigate]);

  const onSignOut = async () => {
    try {
      await logout();
    } finally {
      setUser(null);
      navigate('');
    }
  };

  let body;
  if (!authChecked) {
    body = (
      <Container maxWidth="sm" sx={{ py: 8, textAlign: 'center' }}>
        <CircularProgress />
      </Container>
    );
  } else if (!user) {
    // Whole app is gated — only the auth form renders for logged-out users.
    // The bounce effect above keeps `route` at 'login' or 'register'; this
    // branch is what they actually see between bounces and on first paint.
    body = (
      <AuthForm
        mode={route === 'register' ? 'register' : 'login'}
        onAuthed={setUser}
      />
    );
  } else if (route === 'account') {
    body = (
      <AccountPage
        user={user}
        onUserUpdate={setUser}
        onBack={() => navigate('')}
      />
    );
  } else if (route === 'browse') {
    body = <BrowsePage onBack={() => navigate('')} />;
  } else if (route === 'console') {
    body = <TestPage />;
  } else {
    body = <ChatPage user={user} onNavigate={navigate} />;
  }

  // Auth pages own the whole viewport (full-bleed split layout), and the
  // loading spinner has no app to chrome around either — hide chrome any
  // time we're not rendering the authed app.
  const chromeless = !user;

  return (
    <ThemeProvider theme={lightTheme}>
      <CssBaseline />
      <Box
        sx={{
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          bgcolor: 'background.default',
        }}
      >
        {!chromeless && (
        <AppBar
          position="static"
          color="default"
          elevation={0}
          sx={{ borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}
        >
          <Toolbar variant="dense">
            <Typography
              variant="subtitle1"
              sx={{ fontWeight: 600, cursor: 'pointer', flexGrow: 1 }}
              onClick={() => navigate('')}
            >
              Hudson Legal Tech
            </Typography>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Button size="small" onClick={() => navigate('')}>
                Chat
              </Button>
              <Button size="small" onClick={() => navigate('browse')}>
                Browse
              </Button>
              {user ? (
                <>
                  <Typography variant="body2" color="text.secondary">
                    {user.email}
                  </Typography>
                  <Button size="small" onClick={() => navigate('account')}>
                    Account
                  </Button>
                  <Button size="small" onClick={onSignOut}>
                    Sign out
                  </Button>
                </>
              ) : (
                <>
                  <Button size="small" onClick={() => navigate('login')}>
                    Sign in
                  </Button>
                  <Button
                    size="small"
                    variant="contained"
                    onClick={() => navigate('register')}
                  >
                    Get an API key
                  </Button>
                </>
              )}
            </Stack>
          </Toolbar>
        </AppBar>
        )}
        <Box
          sx={{
            flex: 1,
            minHeight: 0,
            overflow:
              route === 'browse' ||
              route === 'account' ||
              route === '' ||
              chromeless
                ? 'hidden'
                : 'auto',
          }}
        >
          {body}
        </Box>
      </Box>
    </ThemeProvider>
  );
}
