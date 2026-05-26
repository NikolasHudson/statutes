import { useEffect, useRef, useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Container from '@mui/material/Container';
import CssBaseline from '@mui/material/CssBaseline';
import LinearProgress from '@mui/material/LinearProgress';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import { ThemeProvider } from '@mui/material/styles';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { lightTheme } from './theme';

type Role = 'user' | 'assistant';

type ToolCallTrace = {
  name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
};

type Message = {
  role: Role;
  content: string;
  toolCalls?: ToolCallTrace[];
};

const MODEL_STORAGE = 'iowa-test-openai-model';
// Mirror of apps/api/chat.py ALLOWED_CHAT_MODELS — keep in sync.
const CHAT_MODELS = ['gpt-5-mini', 'gpt-4o', 'gpt-4o-mini'];

// Same-origin: Vite proxies /api → backend in dev (see vite.config.ts).
// Override with VITE_API_BASE for non-dev hosting.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

const SAMPLE_PROMPTS = [
  'What does Iowa Code 714.16 cover?',
  'Find statutes about consumer fraud.',
  'Define "consumer" in chapter 714.',
  'What sections does 714.16 cross-reference?',
];

export default function TestPage() {
  const [model, setModel] = useState(() => {
    const saved = localStorage.getItem(MODEL_STORAGE);
    return saved && CHAT_MODELS.includes(saved) ? saved : CHAT_MODELS[0];
  });
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    localStorage.setItem(MODEL_STORAGE, model);
  }, [model]);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, busy]);

  const send = async (text: string) => {
    setError(null);
    if (!text.trim()) return;

    const next: Message[] = [...messages, { role: 'user', content: text }];
    setMessages(next);
    setDraft('');
    setBusy(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        // Session cookie must ride along — /api/chat requires login.
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model,
          messages: next.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (!res.ok) {
        const body = await res.text();
        const hint =
          res.status === 401 ? ' — sign in first (the assistant requires login)' : '';
        throw new Error(`${res.status} ${res.statusText}${hint}: ${body}`);
      }

      const data = (await res.json()) as {
        content: string;
        tool_calls: ToolCallTrace[];
        model: string;
      };

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.content, toolCalls: data.tool_calls },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ThemeProvider theme={lightTheme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
        <Container maxWidth="md" sx={{ py: 4 }}>
          <Stack spacing={3}>
            <Box>
              <Typography variant="h4" sx={{ fontWeight: 700 }}>
                Iowa Code Test Console
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Sanity check that an LLM with tool access can ground answers in
                the loaded Iowa Code. Runs on the server's OpenAI key — sign in
                first; requests are capped per user per day.
              </Typography>
            </Box>

            <Paper variant="outlined" sx={{ p: 2 }}>
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={2}
                sx={{ alignItems: 'stretch' }}
              >
                <TextField
                  label="Model"
                  select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  size="small"
                  fullWidth
                  slotProps={{ select: { native: true } }}
                >
                  {CHAT_MODELS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </TextField>
              </Stack>
            </Paper>

            {messages.length === 0 && (
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Try a sample prompt
                </Typography>
                <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1 }}>
                  {SAMPLE_PROMPTS.map((p) => (
                    <Chip
                      key={p}
                      label={p}
                      onClick={() => send(p)}
                      clickable
                      disabled={busy}
                    />
                  ))}
                </Stack>
              </Paper>
            )}

            <Box
              ref={scrollRef}
              sx={{
                maxHeight: '55vh',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: 2,
              }}
            >
              {messages.map((m, i) => (
                <MessageBubble key={i} message={m} />
              ))}
              {busy && (
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <Typography variant="caption" color="text.secondary">
                    thinking…
                  </Typography>
                  <LinearProgress sx={{ mt: 1 }} />
                </Paper>
              )}
            </Box>

            {error && <Alert severity="error">{error}</Alert>}

            <Paper variant="outlined" sx={{ p: 1.5 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-end' }}>
                <TextField
                  multiline
                  minRows={1}
                  maxRows={6}
                  fullWidth
                  placeholder="Ask about an Iowa Code section…"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      send(draft);
                    }
                  }}
                  disabled={busy}
                />
                <Button
                  variant="contained"
                  onClick={() => send(draft)}
                  disabled={busy || !draft.trim()}
                >
                  Send
                </Button>
              </Stack>
            </Paper>

            <Typography variant="caption" color="text.secondary">
              Backend: {API_BASE || 'same-origin'}/api/chat · the existing
              demo UI is still available at <Link href="?demo">?demo</Link>.
            </Typography>
          </Stack>
        </Container>
      </Box>
    </ThemeProvider>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        bgcolor: isUser ? 'action.hover' : 'background.paper',
        alignSelf: isUser ? 'flex-end' : 'flex-start',
        maxWidth: '95%',
      }}
    >
      <Typography variant="overline" color="text.secondary">
        {isUser ? 'you' : 'assistant'}
      </Typography>
      {isUser ? (
        <Typography
          component="div"
          sx={{ whiteSpace: 'pre-wrap', mt: 0.5, fontSize: '0.95rem' }}
        >
          {message.content}
        </Typography>
      ) : (
        <Box sx={{ mt: 0.5, fontSize: '0.95rem' }}>
          <MarkdownContent text={message.content || '(no content)'} />
        </Box>
      )}
      {message.toolCalls && message.toolCalls.length > 0 && (
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary">
            {message.toolCalls.length} tool call
            {message.toolCalls.length === 1 ? '' : 's'}
          </Typography>
          <Stack spacing={1} sx={{ mt: 0.5 }}>
            {message.toolCalls.map((tc, idx) => (
              <ToolCallView key={idx} call={tc} />
            ))}
          </Stack>
        </Box>
      )}
    </Paper>
  );
}

function ToolCallView({ call }: { call: ToolCallTrace }) {
  const [open, setOpen] = useState(false);
  return (
    <Box sx={{ borderLeft: 2, borderColor: 'primary.light', pl: 1.5 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <Chip label={call.name} size="small" color="primary" variant="outlined" />
        <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
          {summarizeArgs(call.arguments)}
        </Typography>
        <Button size="small" onClick={() => setOpen((o) => !o)}>
          {open ? 'hide' : 'show'} result
        </Button>
      </Stack>
      {open && (
        <Box
          component="pre"
          sx={{
            mt: 1,
            p: 1,
            bgcolor: 'grey.100',
            borderRadius: 1,
            fontSize: '0.75rem',
            overflowX: 'auto',
            maxHeight: 320,
            overflowY: 'auto',
          }}
        >
          {JSON.stringify(call.result, null, 2)}
        </Box>
      )}
    </Box>
  );
}

function summarizeArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (entries.length === 0) return '(no args)';
  return entries
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(', ');
}

function MarkdownContent({ text }: { text: string }) {
  return (
    <Box
      sx={{
        // Reset native browser margins so MUI spacing dominates.
        '& p': { mt: 0, mb: 1.25, lineHeight: 1.55 },
        '& p:last-child': { mb: 0 },
        '& h1, & h2, & h3, & h4': {
          mt: 1.75,
          mb: 0.75,
          fontWeight: 600,
          lineHeight: 1.3,
        },
        '& h1': { fontSize: '1.4rem' },
        '& h2': { fontSize: '1.2rem' },
        '& h3': { fontSize: '1.05rem' },
        '& h4': { fontSize: '1rem' },
        '& ul, & ol': { mt: 0.25, mb: 1.25, pl: 3.25 },
        '& li': { mb: 0.5 },
        '& li > ul, & li > ol': { mt: 0.5, mb: 0.5 },
        '& li > p': { mb: 0.25 },
        '& a': {
          color: 'primary.main',
          textDecorationColor: (theme) => theme.palette.primary.light,
          '&:hover': { textDecorationColor: (theme) => theme.palette.primary.main },
        },
        '& strong': { fontWeight: 600 },
        '& code': {
          fontFamily: 'JetBrains Mono, ui-monospace, monospace',
          fontSize: '0.85em',
          bgcolor: 'action.hover',
          px: 0.5,
          py: 0.1,
          borderRadius: 0.5,
        },
        '& pre': {
          bgcolor: 'action.hover',
          p: 1.25,
          borderRadius: 1,
          overflowX: 'auto',
          fontSize: '0.85em',
          lineHeight: 1.5,
          mt: 0.5,
          mb: 1.25,
        },
        '& pre code': { bgcolor: 'transparent', px: 0, py: 0 },
        '& blockquote': {
          borderLeft: 3,
          borderColor: 'divider',
          pl: 1.5,
          ml: 0,
          my: 1,
          color: 'text.secondary',
          fontStyle: 'italic',
        },
        '& hr': { my: 2, border: 0, borderTop: 1, borderColor: 'divider' },
        '& table': {
          borderCollapse: 'collapse',
          my: 1,
          fontSize: '0.9em',
        },
        '& th, & td': {
          border: 1,
          borderColor: 'divider',
          px: 1,
          py: 0.5,
          textAlign: 'left',
        },
        '& th': { bgcolor: 'action.hover', fontWeight: 600 },
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </Box>
  );
}
