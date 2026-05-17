import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import LinearProgress from '@mui/material/LinearProgress';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DeleteIcon from '@mui/icons-material/Delete';
import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded';

import {
  ApiError,
  type APIKey,
  type CreatedAPIKey,
  type User,
  changePassword,
  createKey,
  fetchPublicConfig,
  listKeys,
  revokeKey,
  updateProfile,
} from '../api';
import { usePalette, type Pal } from './legalPalette';

type Props = {
  user: User;
  onUserUpdate: (user: User) => void;
  onBack: () => void;
};

const VITE_MCP_HOST = import.meta.env.VITE_MCP_HOST as string | undefined;

// Claude Desktop's MCP config only knows how to launch local stdio servers.
// ``mcp-remote`` is a tiny npx-installed shim that runs as a stdio subprocess
// and forwards to our streamable HTTP transport, attaching the X-API-Key
// header on every request.
//
// Two config quirks worth calling out:
//
//   1. Claude Desktop on macOS spawns subprocesses with a minimal PATH
//      that does NOT include /usr/local/bin or /opt/homebrew/bin, so a
//      bare "npx" command fails with "No such file or directory" even
//      when Node is installed. We bake a broader PATH into env so the
//      common install locations resolve (Apple Silicon Homebrew, Intel
//      Homebrew/installer, nvm default).
//
//   2. The raw key goes in env rather than inline in args because Windows
//      Claude Desktop and Cursor have a quoting bug that mangles spaces
//      inside args; the env-var indirection dodges that. See
//      https://github.com/geelen/mcp-remote#workaround-spaces-in-args.
const PATH_FALLBACK = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin';

const claudeDesktopSnippet = (rawKey: string, mcpHost: string) =>
  JSON.stringify(
    {
      mcpServers: {
        'iowa-legal-corpus': {
          command: 'npx',
          args: [
            '-y',
            'mcp-remote',
            mcpHost,
            '--header',
            'X-API-Key:${IOWA_LEGAL_CORPUS_KEY}',
          ],
          env: {
            IOWA_LEGAL_CORPUS_KEY: rawKey,
            PATH: PATH_FALLBACK,
          },
        },
      },
    },
    null,
    2,
  );

export function AccountPage({ user, onUserUpdate, onBack }: Props) {
  const pal = usePalette();
  const [keys, setKeys] = useState<APIKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<CreatedAPIKey | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<APIKey | null>(null);
  const [mcpHost, setMcpHost] = useState<string>(
    VITE_MCP_HOST ?? 'https://your-host.example.com/mcp',
  );
  const [mcpSource, setMcpSource] = useState<'explicit' | 'codespaces' | 'unset' | 'env'>(
    VITE_MCP_HOST ? 'env' : 'unset',
  );

  // Profile editing (display name + login email).
  const [fullName, setFullName] = useState(user.full_name);
  const [email, setEmail] = useState(user.email);
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const [profileErr, setProfileErr] = useState<string | null>(null);

  // Password change.
  const [curPw, setCurPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [savingPw, setSavingPw] = useState(false);
  const [pwMsg, setPwMsg] = useState<string | null>(null);
  const [pwErr, setPwErr] = useState<string | null>(null);

  const profileDirty =
    fullName !== user.full_name || email.trim() !== user.email;

  const onSaveProfile = async () => {
    setSavingProfile(true);
    setProfileMsg(null);
    setProfileErr(null);
    try {
      const updated = await updateProfile({
        full_name: fullName,
        email: email.trim().toLowerCase(),
      });
      onUserUpdate(updated);
      setFullName(updated.full_name);
      setEmail(updated.email);
      setProfileMsg('Profile updated.');
    } catch (err) {
      setProfileErr(
        err instanceof ApiError ? err.detail : 'Failed to update profile',
      );
    } finally {
      setSavingProfile(false);
    }
  };

  const onChangePassword = async () => {
    setSavingPw(true);
    setPwMsg(null);
    setPwErr(null);
    try {
      await changePassword({
        current_password: curPw,
        new_password: newPw,
      });
      setCurPw('');
      setNewPw('');
      setPwMsg('Password updated.');
    } catch (err) {
      setPwErr(
        err instanceof ApiError ? err.detail : 'Failed to change password',
      );
    } finally {
      setSavingPw(false);
    }
  };

  const refresh = async () => {
    setLoading(true);
    try {
      setKeys(await listKeys());
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load keys');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // Pull the MCP host from the backend so Codespaces forwarded URLs work
    // without forcing the user to set VITE_MCP_HOST. The frontend env var
    // still wins if it's set explicitly.
    fetchPublicConfig()
      .then((cfg) => {
        if (!VITE_MCP_HOST && cfg.mcp_host) {
          setMcpHost(cfg.mcp_host);
          setMcpSource(cfg.source);
        }
      })
      .catch(() => {
        // Non-fatal — placeholder URL stays.
      });
  }, []);

  const onCreate = async () => {
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createKey(name.trim());
      setJustCreated(created);
      setName('');
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create key');
    } finally {
      setCreating(false);
    }
  };

  const onRevoke = async (key: APIKey) => {
    try {
      await revokeKey(key.id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to revoke key');
    } finally {
      setConfirmRevoke(null);
    }
  };

  const copy = (text: string) => {
    navigator.clipboard?.writeText(text);
  };

  return (
    <Box
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'grid',
        gridTemplateRows: 'auto 1fr auto',
        bgcolor: pal.paper,
        color: pal.text,
      }}
    >
      <ChromeBar pal={pal} />

      <Box sx={{ minWidth: 0, overflowY: 'auto', bgcolor: pal.paper }}>
        <Box sx={{ maxWidth: 880, mx: 'auto', px: { xs: 3, md: 8 }, pb: 6 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 1,
              mt: 4,
              mb: 4,
            }}
          >
            <Typography
              sx={{
                fontSize: { xs: 22, md: 26 },
                fontWeight: 700,
                letterSpacing: '0.02em',
                color: pal.text,
              }}
            >
              Account
            </Typography>
            <Chip
              size="small"
              label={`${user.tier} tier`}
              sx={{
                bgcolor: 'transparent',
                border: `1px solid ${pal.circleBorder}`,
                color: pal.text,
              }}
            />
          </Box>

          {/* Profile — display name + login email */}
          <SectionCard pal={pal} title="Profile">
            {profileErr && (
              <Alert
                severity="error"
                onClose={() => setProfileErr(null)}
                sx={{ mb: 2 }}
              >
                {profileErr}
              </Alert>
            )}
            {profileMsg && (
              <Alert
                severity="success"
                onClose={() => setProfileMsg(null)}
                sx={{ mb: 2 }}
              >
                {profileMsg}
              </Alert>
            )}
            <Stack spacing={2}>
              <TextField
                label="Full name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                size="small"
                fullWidth
                disabled={savingProfile}
              />
              <TextField
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                size="small"
                fullWidth
                disabled={savingProfile}
                helperText="This is also your sign-in address."
              />
              <Box>
                <Button
                  variant="contained"
                  onClick={onSaveProfile}
                  disabled={
                    savingProfile || !profileDirty || !email.trim()
                  }
                  sx={{
                    bgcolor: pal.bottomBar,
                    color: pal.chromeText,
                    '&:hover': { bgcolor: pal.chrome },
                    '&.Mui-disabled': {
                      bgcolor: pal.border,
                      color: pal.muted,
                    },
                  }}
                >
                  {savingProfile ? 'Saving…' : 'Save changes'}
                </Button>
              </Box>
            </Stack>
          </SectionCard>

          {/* Change password */}
          <SectionCard pal={pal} title="Change password">
            {pwErr && (
              <Alert
                severity="error"
                onClose={() => setPwErr(null)}
                sx={{ mb: 2 }}
              >
                {pwErr}
              </Alert>
            )}
            {pwMsg && (
              <Alert
                severity="success"
                onClose={() => setPwMsg(null)}
                sx={{ mb: 2 }}
              >
                {pwMsg}
              </Alert>
            )}
            <Stack spacing={2}>
              <TextField
                label="Current password"
                type="password"
                value={curPw}
                onChange={(e) => setCurPw(e.target.value)}
                size="small"
                fullWidth
                autoComplete="current-password"
                disabled={savingPw}
              />
              <TextField
                label="New password"
                type="password"
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                size="small"
                fullWidth
                autoComplete="new-password"
                disabled={savingPw}
                helperText="At least 8 characters."
              />
              <Box>
                <Button
                  variant="contained"
                  onClick={onChangePassword}
                  disabled={savingPw || !curPw || newPw.length < 8}
                  sx={{
                    bgcolor: pal.bottomBar,
                    color: pal.chromeText,
                    '&:hover': { bgcolor: pal.chrome },
                    '&.Mui-disabled': {
                      bgcolor: pal.border,
                      color: pal.muted,
                    },
                  }}
                >
                  {savingPw ? 'Updating…' : 'Update password'}
                </Button>
              </Box>
            </Stack>
          </SectionCard>

          <Typography
            sx={{
              fontSize: { xs: 18, md: 20 },
              fontWeight: 700,
              color: pal.text,
              mt: 5,
              mb: 2,
            }}
          >
            API keys
          </Typography>

          {error && (
            <Alert
              severity="error"
              onClose={() => setError(null)}
              sx={{ mb: 3 }}
            >
              {error}
            </Alert>
          )}

          <Box
            sx={{
              border: `1px solid ${pal.border}`,
              borderRadius: 1,
              bgcolor: pal.paper,
              p: 3,
              mb: 3,
            }}
          >
            <Typography
              sx={{ fontSize: 16, fontWeight: 700, color: pal.text, mb: 0.5 }}
            >
              Create a new key
            </Typography>
            <Typography sx={{ fontSize: 13.5, color: pal.muted, mb: 2 }}>
              Name it for the place you'll use it (e.g. "Claude Desktop —
              laptop"). The full key is shown <em>once</em>; we only store its
              hash.
            </Typography>
            <Stack direction="row" spacing={2}>
              <TextField
                label="Key name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                size="small"
                fullWidth
                disabled={creating}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onCreate();
                }}
              />
              <Button
                variant="contained"
                onClick={onCreate}
                disabled={creating || !name.trim()}
                sx={{
                  bgcolor: pal.bottomBar,
                  color: pal.chromeText,
                  flexShrink: 0,
                  '&:hover': { bgcolor: pal.chrome },
                  '&.Mui-disabled': { bgcolor: pal.border, color: pal.muted },
                }}
              >
                {creating ? 'Creating…' : 'Create key'}
              </Button>
            </Stack>
          </Box>

          <Box
            sx={{
              border: `1px solid ${pal.border}`,
              borderRadius: 1,
              overflow: 'hidden',
            }}
          >
            {loading && <LinearProgress />}
            <Table
              size="small"
              sx={{
                '& td, & th': { borderColor: pal.border, color: pal.text },
                '& thead th': {
                  color: pal.muted,
                  fontWeight: 700,
                  fontSize: 11,
                  letterSpacing: '0.05em',
                  textTransform: 'uppercase',
                  bgcolor: pal.borderSoft,
                },
                '& tbody tr:hover': { bgcolor: pal.borderSoft },
              }}
            >
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Prefix</TableCell>
                  <TableCell>Created</TableCell>
                  <TableCell>Last used</TableCell>
                  <TableCell align="right" />
                </TableRow>
              </TableHead>
              <TableBody>
                {keys.length === 0 && !loading && (
                  <TableRow>
                    <TableCell colSpan={5}>
                      <Typography
                        sx={{
                          fontSize: 13.5,
                          color: pal.muted,
                          textAlign: 'center',
                          py: 3,
                        }}
                      >
                        No active keys yet.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
                {keys.map((k) => (
                  <TableRow key={k.id}>
                    <TableCell>{k.name}</TableCell>
                    <TableCell>
                      <Box
                        component="code"
                        sx={{ fontFamily: 'monospace', color: pal.link }}
                      >
                        {k.prefix}…
                      </Box>
                    </TableCell>
                    <TableCell>
                      {new Date(k.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      {k.last_used_at
                        ? new Date(k.last_used_at).toLocaleString()
                        : '—'}
                    </TableCell>
                    <TableCell align="right">
                      <Tooltip title="Revoke">
                        <IconButton
                          size="small"
                          onClick={() => setConfirmRevoke(k)}
                          aria-label={`Revoke ${k.name}`}
                          sx={{ color: pal.muted }}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Box>
      </Box>

      <PinnedBottomNav pal={pal} onBack={onBack} />

      {/* New-key dialog: only place the raw value is ever shown. */}
      <Dialog
        open={!!justCreated}
        onClose={() => setJustCreated(null)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Save your new API key</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            This is the only time we'll show the full key. Copy it now — once you close this
            dialog, you can't retrieve it again.
          </DialogContentText>
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              mb: 3,
              fontFamily: 'monospace',
              wordBreak: 'break-all',
              display: 'flex',
              alignItems: 'center',
              gap: 1,
            }}
          >
            <Box sx={{ flex: 1 }}>{justCreated?.raw_key}</Box>
            <Tooltip title="Copy key">
              <IconButton size="small" onClick={() => justCreated && copy(justCreated.raw_key)}>
                <ContentCopyIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Paper>

          <Typography variant="subtitle2" gutterBottom>
            Claude Desktop config
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            In Claude Desktop, open <strong>Settings → Developer → Edit Config</strong> and paste
            this in. The file lives at{' '}
            <code>~/Library/Application Support/Claude/claude_desktop_config.json</code> on macOS or{' '}
            <code>%APPDATA%\Claude\claude_desktop_config.json</code> on Windows if you prefer to
            edit it directly. Restart Claude Desktop and the seven Iowa Code tools should appear in
            the tool picker (look for the slider icon in the message composer).
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
            Why <code>mcp-remote</code>? Claude Desktop's config file only knows how to launch
            local stdio servers. <code>mcp-remote</code> is a tiny npx-installed shim that runs
            locally and forwards to our HTTPS endpoint, attaching your API key on every request.
            For claude.ai web (Custom Connectors), the Iowa Code corpus does not yet support OAuth —
            use the Claude Desktop flow above for now.
          </Typography>
          {mcpSource === 'codespaces' && (
            <Alert severity="info" sx={{ mb: 1 }}>
              MCP host auto-detected from this Codespace. The forwarded URL is stable for the life
              of the codespace; if you stop the codespace and start a fresh one, regenerate the
              config from the new key dialog.
            </Alert>
          )}
          {mcpSource === 'unset' && (
            <Alert severity="warning" sx={{ mb: 1 }}>
              MCP host is unset. Set the <code>MCP_HOST</code> env var on the server (or{' '}
              <code>VITE_MCP_HOST</code> on the frontend) before sharing this snippet.
            </Alert>
          )}
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              fontFamily: 'monospace',
              fontSize: 13,
              whiteSpace: 'pre',
              overflow: 'auto',
              position: 'relative',
            }}
          >
            <IconButton
              size="small"
              sx={{ position: 'absolute', top: 4, right: 4 }}
              onClick={() => justCreated && copy(claudeDesktopSnippet(justCreated.raw_key, mcpHost))}
            >
              <ContentCopyIcon fontSize="small" />
            </IconButton>
            {justCreated ? claudeDesktopSnippet(justCreated.raw_key, mcpHost) : ''}
          </Paper>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setJustCreated(null)} variant="contained">
            I've saved it
          </Button>
        </DialogActions>
      </Dialog>

      {/* Revoke confirmation. */}
      <Dialog open={!!confirmRevoke} onClose={() => setConfirmRevoke(null)}>
        <DialogTitle>Revoke this key?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            <strong>{confirmRevoke?.name}</strong> ({confirmRevoke?.prefix}…) will stop working
            immediately. Existing integrations using it will need a new key.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmRevoke(null)}>Cancel</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => confirmRevoke && onRevoke(confirmRevoke)}
          >
            Revoke
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Shared chrome — mirrors the corpus browser's ActionBar / banner / bottom nav
// so the account surface never drifts from the rest of the app.
// ---------------------------------------------------------------------------

function ChromeBar({ pal }: { pal: Pal }) {
  return (
    <Box
      sx={{
        bgcolor: pal.chrome,
        color: pal.chromeText,
        height: 44,
        px: 1.5,
        display: 'flex',
        alignItems: 'center',
        gap: 0.75,
      }}
    >
      <Typography component="span" sx={{ fontSize: 13, opacity: 0.85 }}>
        Iowa Legal Corpus
      </Typography>
      <Box component="span" sx={{ opacity: 0.55 }}>
        ›
      </Box>
      <Typography component="span" sx={{ fontSize: 16, fontWeight: 600 }}>
        Account
      </Typography>
    </Box>
  );
}

function SectionCard({
  pal,
  title,
  children,
}: {
  pal: Pal;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Box
      sx={{
        border: `1px solid ${pal.border}`,
        borderRadius: 1,
        bgcolor: pal.paper,
        p: 3,
        mb: 3,
      }}
    >
      <Typography
        sx={{ fontSize: 16, fontWeight: 700, color: pal.text, mb: 2 }}
      >
        {title}
      </Typography>
      {children}
    </Box>
  );
}

function PinnedBottomNav({ pal, onBack }: { pal: Pal; onBack: () => void }) {
  return (
    <Box
      sx={{
        bgcolor: pal.bottomBar,
        color: pal.chromeText,
        height: 44,
        display: 'flex',
        alignItems: 'center',
        px: 2,
      }}
    >
      <Box
        component="button"
        onClick={onBack}
        sx={{
          all: 'unset',
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          cursor: 'pointer',
          color: pal.chromeText,
          fontSize: 13,
          textDecoration: 'underline',
          '&:hover': { opacity: 0.8 },
        }}
      >
        <ArrowBackRoundedIcon sx={{ fontSize: 16 }} />
        Back to chat
      </Box>
    </Box>
  );
}
