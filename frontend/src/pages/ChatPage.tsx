import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
} from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import Collapse from '@mui/material/Collapse';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddRoundedIcon from '@mui/icons-material/AddRounded';
import SettingsRoundedIcon from '@mui/icons-material/SettingsRounded';
import SendRoundedIcon from '@mui/icons-material/SendRounded';
import ExpandMoreRoundedIcon from '@mui/icons-material/ExpandMoreRounded';
import MenuBookRoundedIcon from '@mui/icons-material/MenuBookRounded';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import {
  chat,
  browseSources,
  ApiError,
  type ToolCallTrace,
  type BrowseSource,
  type User,
} from '../api';
import { suggestions } from '../data/suggestions';
import { usePalette, type Pal } from './legalPalette';
import type { Citation, Message } from '../types';

// First-class AI chat. Same "American Legal Publishing" chrome as the corpus
// browser (shared usePalette) so the two surfaces never visually conflict.
// Talks to the real /api/chat (server OpenAI key, login required); the
// source picker scopes every search the assistant runs to one corpus.

// Mirror of apps/api/chat.py ALLOWED_CHAT_MODELS — keep in sync.
const CHAT_MODELS = ['gpt-5-mini', 'gpt-4o', 'gpt-4o-mini'] as const;

const MODEL_STORAGE = 'iowa-test-openai-model';
const SCOPE_STORAGE = 'iowa-chat-source-slug';
const CONVO_STORAGE = 'iowa-chat-conversation';

const newId = () => Math.random().toString(36).slice(2, 10);

const SOURCE_LABELS: Record<string, Citation['source']> = {
  'iowa-code': 'Iowa Code',
  'iowa-court-rules': 'Iowa Court Rules',
  'iowa-admin-code': 'Iowa Admin. Code',
};

const sourceLabel = (slug: string | undefined): Citation['source'] =>
  (slug && SOURCE_LABELS[slug]) || 'Iowa Code';

const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
};

type ApiNode = {
  id: number;
  heading: string;
  citation: string;
  official_url: string;
  source_slug: string;
  path?: string;
};

const isNode = (v: unknown): v is ApiNode =>
  !!v && typeof v === 'object' && 'id' in v && 'citation' in v && 'heading' in v;

// Max chars of section text shown on a source card. The backend hands us up
// to ~2000 (so the model can summarize); the card only needs a teaser.
const SNIPPET_MAX = 240;

// The bare number an attorney (and the model) actually writes: "32:1.7",
// "714.16". Falls back to the last token of the rendered citation.
const citeKey = (node: ApiNode): string =>
  (node.path && node.path.trim()) ||
  node.citation.trim().split(/\s+/).pop() ||
  '';

// Walk the tool-call trace and pull every distinct section the assistant
// actually touched, so the answer renders with verifiable source cards
// instead of just prose. Tolerant of the search / lookup / candidate shapes.
// Cap on how many source cards we ever show, even after relevance filtering —
// a focused answer cites a handful of rules, not a syllabus.
const MAX_SOURCES = 8;

function citationsFromTrace(
  trace: ToolCallTrace[],
  asOfFallback: string,
  answerText: string,
): Citation[] {
  const byId = new Map<number, Citation & { _key: string }>();

  const add = (node: ApiNode, snippet?: string, effectiveFrom?: string) => {
    if (byId.has(node.id)) return;
    let snip = snippet?.trim();
    if (snip && snip.length > SNIPPET_MAX) {
      snip = snip.slice(0, SNIPPET_MAX - 1).trimEnd() + '…';
    }
    byId.set(node.id, {
      id: String(node.id),
      citation: node.citation,
      heading: node.heading,
      source: sourceLabel(node.source_slug),
      url: node.official_url,
      effectiveFrom: effectiveFrom || asOfFallback,
      snippet: snip || undefined,
      _key: citeKey(node),
    });
  };

  for (const call of trace) {
    const r = call.result as Record<string, unknown>;
    if (!r || typeof r !== 'object') continue;

    const hits = r.hits;
    if (Array.isArray(hits)) {
      for (const h of hits as Record<string, unknown>[]) {
        if (isNode(h.node)) {
          const snip =
            (typeof h.body_excerpt === 'string' && h.body_excerpt) ||
            (typeof h.snippet === 'string' && h.snippet) ||
            undefined;
          add(h.node, snip || undefined);
        }
      }
    }

    const section = r.section as Record<string, unknown> | null;
    if (section && isNode(section.node)) {
      const version = section.version as Record<string, unknown> | undefined;
      add(
        section.node,
        typeof version?.body_text === 'string' ? version.body_text : undefined,
        typeof version?.effective_from === 'string' ? version.effective_from : undefined,
      );
    }
    const chapter = r.chapter as Record<string, unknown> | null;
    if (chapter && isNode(chapter.node)) add(chapter.node);
    if (chapter && Array.isArray(chapter.sections)) {
      for (const n of chapter.sections) if (isNode(n)) add(n);
    }

    if (Array.isArray(r.candidates)) {
      for (const n of r.candidates) if (isNode(n)) add(n);
    }
  }

  const all = [...byId.values()];
  // Show what the answer actually relied on. The model writes the bare number
  // ("32:1.9", "714.16"); keep only sections whose key appears in the prose.
  // If nothing matches (model didn't cite explicitly), fall back to the
  // reranked top few so the card list is never empty or overwhelming.
  const cited = all.filter((c) => c._key && answerText.includes(c._key));
  const chosen = (cited.length > 0 ? cited : all).slice(0, MAX_SOURCES);
  return chosen.map(
    (c): Citation => ({
      id: c.id,
      citation: c.citation,
      heading: c.heading,
      source: c.source,
      url: c.url,
      effectiveFrom: c.effectiveFrom,
      snippet: c.snippet,
    }),
  );
}

function loadConversation(): Message[] {
  try {
    const raw = localStorage.getItem(CONVO_STORAGE);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Message[]) : [];
  } catch {
    return [];
  }
}

type ChatPageProps = {
  // null = not signed in; the assistant requires a session (it spends the
  // server's OpenAI key, gated by a per-user daily cap).
  user: User | null;
  onNavigate: (route: 'login') => void;
};

export function ChatPage({ user, onNavigate }: ChatPageProps) {
  const pal = usePalette();

  const [model, setModel] = useState(() => {
    const saved = localStorage.getItem(MODEL_STORAGE);
    return saved && (CHAT_MODELS as readonly string[]).includes(saved)
      ? saved
      : CHAT_MODELS[0];
  });
  const [scope, setScope] = useState(
    () => localStorage.getItem(SCOPE_STORAGE) ?? '',
  );
  const [sources, setSources] = useState<BrowseSource[]>([]);
  const [messages, setMessages] = useState<Message[]>(loadConversation);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const endRef = useRef<HTMLDivElement | null>(null);
  const draftRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-grow the composer to fit its content. Reset to 'auto' first so it
  // can shrink when the user deletes lines (and collapse back to one row
  // when the draft is cleared after send). The CSS maxHeight/overflowY cap
  // and scrollbar are left to handle the upper bound.
  useEffect(() => {
    const el = draftRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [draft]);

  useEffect(() => {
    localStorage.setItem(MODEL_STORAGE, model);
  }, [model]);
  useEffect(() => {
    localStorage.setItem(SCOPE_STORAGE, scope);
  }, [scope]);
  useEffect(() => {
    localStorage.setItem(CONVO_STORAGE, JSON.stringify(messages));
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  useEffect(() => {
    let cancelled = false;
    browseSources()
      .then((s) => !cancelled && setSources(s))
      .catch(() => {
        /* picker just falls back to "All sources" */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hasMessages = messages.length > 0;
  const scopeName = useMemo(
    () => sources.find((s) => s.slug === scope)?.name,
    [sources, scope],
  );

  const handleNewChat = () => {
    setMessages([]);
    setError(null);
    setDraft('');
  };

  const handleSubmit = async (text: string) => {
    const body = text.trim();
    if (!body || busy) return;
    setError(null);
    if (!user) {
      setError('Please sign in to use the assistant.');
      return;
    }

    const userMsg: Message = {
      id: newId(),
      role: 'user',
      content: body,
      createdAt: new Date().toISOString(),
    };
    const placeholderId = newId();
    const placeholder: Message = {
      id: placeholderId,
      role: 'assistant',
      content: '',
      createdAt: new Date().toISOString(),
      pending: true,
    };
    setMessages((prev) => [...prev, userMsg, placeholder]);
    setDraft('');
    setBusy(true);

    const history = [...messagesRef.current, userMsg]
      .filter((m) => !m.pending)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const res = await chat({
        model,
        messages: history,
        source_slug: scope || null,
      });
      const reply: Message = {
        id: placeholderId,
        role: 'assistant',
        content: res.content || '(no answer returned)',
        createdAt: new Date().toISOString(),
        citations: citationsFromTrace(
          res.tool_calls,
          new Date().toISOString().slice(0, 10),
          res.content || '',
        ),
      };
      setMessages((prev) =>
        prev.map((m) => (m.id === placeholderId ? reply : m)),
      );
    } catch (e) {
      const unauthorized = e instanceof ApiError && e.status === 401;
      const detail = unauthorized
        ? 'Your session has expired. Please sign in again to continue.'
        : e instanceof Error
          ? e.message
          : String(e);
      setError(detail);
      if (unauthorized) onNavigate('login');
      setMessages((prev) =>
        prev.map((m) =>
          m.id === placeholderId
            ? { ...m, pending: false, content: `The request failed: ${detail}` }
            : m,
        ),
      );
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(draft);
    }
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
      {/* Top chrome strip — mirrors the browser's ActionBar */}
      <Box>
        <Box
          sx={{
            bgcolor: pal.chrome,
            color: pal.chromeText,
            minHeight: 44,
            px: 1.5,
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
          }}
        >
          <Typography
            component="span"
            sx={{ fontSize: 13, opacity: 0.85, flexShrink: 0 }}
          >
            Iowa Legal Corpus
          </Typography>

          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 0.75,
              px: 1.5,
              py: 0.5,
              borderRadius: 999,
              bgcolor: pal.chromeHover,
              border: `1px solid ${pal.circleBorder}`,
            }}
          >
            <Typography component="span" sx={{ fontSize: 12.5, opacity: 0.85 }}>
              Ask
            </Typography>
            <Box
              component="select"
              value={scope}
              onChange={(e: ChangeEvent<HTMLSelectElement>) =>
                setScope(e.target.value)
              }
              sx={{
                all: 'unset',
                cursor: 'pointer',
                fontSize: 13.5,
                fontWeight: 600,
                color: pal.chromeText,
                '& option': { color: '#212529' },
              }}
            >
              <option value="">All sources</option>
              {sources.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.name}
                </option>
              ))}
            </Box>
            <ExpandMoreRoundedIcon sx={{ fontSize: 16, opacity: 0.8 }} />
          </Box>

          <Box sx={{ flex: 1 }} />

          <Tooltip title="New chat">
            <Box component="span">
              <IconButton
                size="small"
                onClick={handleNewChat}
                disabled={busy || !hasMessages}
                aria-label="New chat"
                sx={{
                  color: pal.chromeText,
                  '&:hover': { bgcolor: pal.chromeHover },
                  '&.Mui-disabled': { color: pal.chromeText, opacity: 0.4 },
                }}
              >
                <AddRoundedIcon fontSize="small" />
              </IconButton>
            </Box>
          </Tooltip>
          <Tooltip title="Model">
            <IconButton
              size="small"
              onClick={() => setShowSettings((s) => !s)}
              aria-label="Settings"
              sx={{
                color: pal.chromeText,
                '&:hover': { bgcolor: pal.chromeHover },
              }}
            >
              <SettingsRoundedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>

        <Collapse in={showSettings}>
          <Box
            sx={{
              borderBottom: `1px solid ${pal.border}`,
              bgcolor: pal.paper,
              px: { xs: 2, md: 3 },
              py: 2,
            }}
          >
            <Box
              sx={{
                maxWidth: 880,
                mx: 'auto',
                display: 'flex',
                flexDirection: { xs: 'column', sm: 'row' },
                gap: 1.5,
                alignItems: { sm: 'center' },
              }}
            >
              <Typography sx={{ fontSize: 13, color: pal.muted, flex: 1 }}>
                The assistant runs on the firm's account — no API key needed.
                Messages are capped per day per user.
              </Typography>
              <Box
                component="select"
                value={model}
                onChange={(e: ChangeEvent<HTMLSelectElement>) =>
                  setModel(e.target.value)
                }
                aria-label="Model"
                sx={{
                  all: 'unset',
                  cursor: 'pointer',
                  width: { xs: 'auto', sm: 170 },
                  px: 1.5,
                  py: 0.75,
                  borderRadius: 1,
                  border: `1px solid ${pal.border}`,
                  fontSize: 14,
                  color: pal.text,
                }}
              >
                {CHAT_MODELS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </Box>
            </Box>
          </Box>
        </Collapse>
      </Box>

      {/* Conversation */}
      <Box sx={{ minHeight: 0, overflowY: 'auto', bgcolor: pal.paper }}>
        <Box sx={{ maxWidth: 880, mx: 'auto', px: { xs: 3, md: 8 }, pt: 4 }}>
          {error && (
            <Alert
              severity="error"
              onClose={() => setError(null)}
              sx={{ mb: 3, borderRadius: 1 }}
            >
              {error}
            </Alert>
          )}

          {hasMessages ? (
            <Box sx={{ pb: 3 }}>
              {messages.map((m) => (
                <Turn key={m.id} pal={pal} message={m} scopeName={scopeName} />
              ))}
              <Box ref={endRef} />
            </Box>
          ) : (
            <EmptyState pal={pal} onPick={handleSubmit} />
          )}
        </Box>
      </Box>

      {/* Composer — navy send to echo the bottom nav */}
      <Box
        sx={{
          borderTop: `1px solid ${pal.border}`,
          bgcolor: pal.paper,
          px: { xs: 2, md: 3 },
          py: 1.75,
        }}
      >
        <Box sx={{ maxWidth: 880, mx: 'auto' }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'flex-end',
              gap: 1,
              px: 1.75,
              py: 1,
              borderRadius: 1,
              border: `1px solid ${pal.border}`,
              bgcolor: pal.paper,
              '&:focus-within': { borderColor: pal.chrome },
            }}
          >
            <Box
              component="textarea"
              ref={draftRef}
              value={draft}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) =>
                setDraft(e.target.value)
              }
              onKeyDown={onKey}
              rows={1}
              placeholder={
                scopeName
                  ? `Ask the ${scopeName} a question or describe a scenario…`
                  : 'Ask about the Iowa Code or Court Rules, or describe a scenario…'
              }
              disabled={busy}
              sx={{
                all: 'unset',
                flex: 1,
                minWidth: 0,
                fontSize: 15,
                lineHeight: 1.6,
                color: pal.text,
                resize: 'none',
                maxHeight: 160,
                overflowY: 'auto',
                '&::placeholder': { color: pal.muted },
              }}
            />
            <Tooltip title="Send (Enter)">
              <Box component="span">
                <IconButton
                  onClick={() => handleSubmit(draft)}
                  disabled={!draft.trim() || busy}
                  aria-label="Send"
                  sx={{
                    width: 34,
                    height: 34,
                    borderRadius: 1,
                    bgcolor: pal.bottomBar,
                    color: pal.chromeText,
                    '&:hover': { bgcolor: pal.chrome },
                    '&.Mui-disabled': {
                      bgcolor: pal.border,
                      color: pal.muted,
                    },
                  }}
                >
                  {busy ? (
                    <CircularProgress size={16} sx={{ color: pal.chromeText }} />
                  ) : (
                    <SendRoundedIcon sx={{ fontSize: 18 }} />
                  )}
                </IconButton>
              </Box>
            </Tooltip>
          </Box>
          <Typography
            sx={{
              mt: 1,
              fontSize: 11,
              color: pal.muted,
              textAlign: 'center',
            }}
          >
            Iowa Legal Corpus can make mistakes. Verify every citation against
            the official source before relying on it.
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}


// ---------------------------------------------------------------------------
// Empty state — suggestion list styled like the chapter section index
// ---------------------------------------------------------------------------

function EmptyState({
  pal,
  onPick,
}: {
  pal: Pal;
  onPick: (prompt: string) => void;
}) {
  return (
    <Box sx={{ pb: 6 }}>
      <Typography
        sx={{
          textAlign: 'center',
          fontSize: 14,
          color: pal.muted,
          maxWidth: 540,
          mx: 'auto',
          mb: 4,
        }}
      >
        Describe a scenario or ask a question in plain English. Every answer
        comes back grounded in the corpus, with the sections it relied on.
      </Typography>
      <Box
        sx={{
          borderTop: `2px solid ${pal.text}`,
          borderBottom: `1px solid ${pal.border}`,
          py: 1,
          mb: 1,
        }}
      >
        <Typography
          sx={{
            fontSize: 12,
            fontWeight: 700,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: pal.muted,
          }}
        >
          Try a question
        </Typography>
      </Box>
      <Box sx={{ columnGap: 5, columnCount: { xs: 1, sm: 2 } }}>
        {suggestions.map((s) => (
          <Box
            key={s.title}
            component="button"
            onClick={() => onPick(s.prompt)}
            sx={{
              all: 'unset',
              display: 'block',
              breakInside: 'avoid',
              cursor: 'pointer',
              py: 1,
              '&:hover .ttl': { opacity: 0.7 },
            }}
          >
            <Box
              component="span"
              className="ttl"
              sx={{
                display: 'block',
                color: pal.link,
                textDecoration: 'underline',
                fontWeight: 700,
                fontSize: 14,
              }}
            >
              {s.title}
            </Box>
            <Box
              component="span"
              sx={{
                display: 'block',
                color: pal.body,
                fontSize: 13.5,
                lineHeight: 1.5,
                mt: 0.25,
              }}
            >
              {s.prompt}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// One conversation turn
// ---------------------------------------------------------------------------

function PendingStages({ pal, scopeName }: { pal: Pal; scopeName?: string }) {
  // Honest staging: each phase corresponds to real backend work (corpus
  // search, then section reads, then the model composing). The timings are
  // approximate — they exist so testers don't think a multi-second request
  // is hung. If the response lands before "Drafting", the placeholder is
  // swapped out anyway.
  const stages = useMemo(
    () => [
      `Searching ${scopeName ?? 'the Iowa corpus'}…`,
      'Reading sections…',
      'Drafting answer…',
    ],
    [scopeName],
  );
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const t1 = window.setTimeout(() => setStage(1), 3000);
    const t2 = window.setTimeout(() => setStage(2), 8000);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, []);
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        color: pal.muted,
        py: 1,
      }}
    >
      <CircularProgress size={16} sx={{ color: pal.muted }} />
      <Typography sx={{ fontSize: 14, fontStyle: 'italic' }}>
        {stages[stage]}
      </Typography>
    </Box>
  );
}

function Turn({
  pal,
  message,
  scopeName,
}: {
  pal: Pal;
  message: Message;
  scopeName?: string;
}) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', my: 3 }}>
        <Box
          sx={{
            maxWidth: '85%',
            bgcolor: pal.activeRow,
            color: pal.text,
            border: `1px solid ${pal.border}`,
            borderRadius: 1,
            px: 2,
            py: 1.25,
            fontSize: 15,
            lineHeight: 1.6,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {message.content}
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ my: 3 }}>
      <Typography
        sx={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: pal.muted,
          mb: 1,
        }}
      >
        Assistant
      </Typography>

      {message.pending ? (
        <PendingStages pal={pal} scopeName={scopeName} />
      ) : (
        <Answer pal={pal} text={message.content} />
      )}

      {!message.pending &&
        message.citations &&
        message.citations.length > 0 && (
          <Box sx={{ mt: 3 }}>
            <Typography
              sx={{
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: pal.muted,
                borderBottom: `1px solid ${pal.border}`,
                pb: 0.75,
                mb: 1.5,
              }}
            >
              Sources
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              {message.citations.map((c) => (
                <SourceCard key={c.id} pal={pal} citation={c} />
              ))}
            </Box>
          </Box>
        )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Markdown answer — palette-matched typography
// ---------------------------------------------------------------------------

function Answer({ pal, text }: { pal: Pal; text: string }) {
  return (
    <Box
      sx={{
        color: pal.body,
        fontSize: 15.5,
        lineHeight: 1.75,
        '& p': { my: 1.25 },
        '& p:first-of-type': { mt: 0 },
        '& h1, & h2, & h3, & h4': {
          color: pal.text,
          fontWeight: 700,
          mt: 2.5,
          mb: 1,
          lineHeight: 1.3,
        },
        '& h1': { fontSize: 22 },
        '& h2': { fontSize: 19 },
        '& h3': { fontSize: 17 },
        '& h4': { fontSize: 15.5 },
        '& ul, & ol': { my: 1.25, pl: 3.25 },
        '& li': { mb: 0.5 },
        '& a': {
          color: pal.link,
          textDecoration: 'underline',
        },
        '& strong': { color: pal.text, fontWeight: 700 },
        '& code': {
          fontFamily: '"JetBrains Mono", ui-monospace, monospace',
          fontSize: '0.88em',
          bgcolor: pal.borderSoft,
          px: 0.5,
          py: 0.15,
          borderRadius: 0.5,
        },
        '& pre': {
          bgcolor: pal.borderSoft,
          p: 1.5,
          borderRadius: 1,
          overflowX: 'auto',
          my: 1.5,
        },
        '& pre code': { bgcolor: 'transparent', p: 0 },
        '& blockquote': {
          borderLeft: `3px solid ${pal.border}`,
          pl: 1.5,
          ml: 0,
          my: 1.5,
          color: pal.muted,
          fontStyle: 'italic',
        },
        '& table': {
          borderCollapse: 'collapse',
          my: 1.5,
          fontSize: '0.92em',
        },
        '& th, & td': {
          border: `1px solid ${pal.border}`,
          px: 1,
          py: 0.5,
          textAlign: 'left',
        },
        '& th': { bgcolor: pal.borderSoft, fontWeight: 700, color: pal.text },
        '& hr': {
          border: 0,
          borderTop: `1px solid ${pal.border}`,
          my: 2,
        },
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

// ---------------------------------------------------------------------------
// Source card — bordered, citation-link styling from the browser
// ---------------------------------------------------------------------------

function SourceCard({ pal, citation }: { pal: Pal; citation: Citation }) {
  return (
    <Box
      component="a"
      href={`#/browse?node=${citation.id}`}
      title="Open in the corpus browser"
      sx={{
        display: 'block',
        textDecoration: 'none',
        color: 'inherit',
        border: `1px solid ${pal.border}`,
        borderRadius: 1,
        p: 1.5,
        bgcolor: pal.paper,
        transition: 'border-color 140ms ease',
        '&:hover': { borderColor: pal.chrome },
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 1,
          mb: 0.5,
          flexWrap: 'wrap',
        }}
      >
        <Box
          component="span"
          sx={{
            color: pal.link,
            textDecoration: 'underline',
            fontWeight: 700,
            fontSize: 14,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {citation.citation}
        </Box>
        <Box
          component="span"
          sx={{ fontSize: 14, fontWeight: 600, color: pal.text }}
        >
          {citation.heading}
        </Box>
        <Box sx={{ flex: 1 }} />
        <MenuBookRoundedIcon sx={{ fontSize: 14, color: pal.muted }} />
      </Box>

      {citation.snippet && (
        <Typography
          sx={{
            fontSize: 13.5,
            color: pal.body,
            lineHeight: 1.55,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            mb: 0.75,
          }}
        >
          {citation.snippet}
        </Typography>
      )}

      <Typography sx={{ fontSize: 12, color: pal.muted }}>
        {citation.source} · Effective {fmtDate(citation.effectiveFrom)}
      </Typography>
    </Box>
  );
}
