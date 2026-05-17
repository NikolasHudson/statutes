import { useEffect, useMemo, useState } from 'react';
import Box from '@mui/material/Box';
import CssBaseline from '@mui/material/CssBaseline';
import Drawer from '@mui/material/Drawer';
import { ThemeProvider } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';

import { darkTheme, lightTheme } from './theme';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { Composer } from './components/Composer';
import { MessageList } from './components/MessageList';
import { WelcomeHero } from './components/WelcomeHero';
import { DisclaimerBanner } from './components/DisclaimerBanner';
import { Profile } from './components/Profile';
import { BrowsePage } from './pages/BrowsePage';

import { sampleConversations } from './data/sampleConversations';
import type { Conversation, Message } from './types';

const STORAGE_KEY = 'iowa-legal-theme';

const newId = () => Math.random().toString(36).slice(2, 10);

const fakeAssistantReply = (prompt: string): Message => ({
  id: newId(),
  role: 'assistant',
  createdAt: new Date().toISOString(),
  content:
    `Here's a starting point for: *${prompt.length > 80 ? prompt.slice(0, 80) + '…' : prompt}*\n\n` +
    `In production, this response would come from the MCP server's hybrid search ` +
    `(Postgres FTS + pg_trgm + pgvector embeddings via voyage-law-2), fused with ` +
    `Reciprocal Rank Fusion. Each candidate would arrive with its full citation, the ` +
    `effective date, the enacting session law, and a verifiable link back to ` +
    'legis.iowa.gov.\n\n' +
    `Try one of the example prompts on the welcome screen to preview a fully grounded answer.`,
});

export default function App() {
  const prefersDark = useMediaQuery('(prefers-color-scheme: dark)');
  const isDesktop = useMediaQuery('(min-width: 960px)');

  const [mode, setMode] = useState<'light' | 'dark'>(() => {
    const saved = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
    if (saved === 'light' || saved === 'dark') return saved;
    return prefersDark ? 'dark' : 'light';
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, mode);
  }, [mode]);

  const theme = useMemo(() => (mode === 'light' ? lightTheme : darkTheme), [mode]);

  const [conversations, setConversations] = useState<Conversation[]>(sampleConversations);
  const [activeId, setActiveId] = useState<string | null>(sampleConversations[0]?.id ?? null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [view, setView] = useState<'chat' | 'profile' | 'browse'>('chat');

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const hasMessages = !!active && active.messages.length > 0;

  const handleNewChat = () => {
    const id = newId();
    const conv: Conversation = {
      id,
      title: 'New conversation',
      updatedAt: new Date().toISOString(),
      messages: [],
    };
    setConversations((prev) => [conv, ...prev]);
    setActiveId(id);
    setMobileOpen(false);
    setView('chat');
  };

  const handleSelect = (id: string) => {
    setActiveId(id);
    setMobileOpen(false);
    setView('chat');
  };

  const handleOpenProfile = () => {
    setView('profile');
    setMobileOpen(false);
  };

  const handleOpenSources = () => {
    setView('browse');
    setMobileOpen(false);
  };

  const handleSubmit = (text: string) => {
    if (!active) {
      // create new conversation around this prompt
      const id = newId();
      const userMsg: Message = {
        id: newId(),
        role: 'user',
        content: text,
        createdAt: new Date().toISOString(),
      };
      const conv: Conversation = {
        id,
        title: text.length > 50 ? text.slice(0, 50) + '…' : text,
        updatedAt: new Date().toISOString(),
        messages: [userMsg],
      };
      setConversations((prev) => [conv, ...prev]);
      setActiveId(id);
      setDraft('');
      simulateReply(id, text);
      return;
    }

    const userMsg: Message = {
      id: newId(),
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
    };
    setConversations((prev) =>
      prev.map((c) =>
        c.id === active.id
          ? {
              ...c,
              title:
                c.messages.length === 0
                  ? text.length > 50
                    ? text.slice(0, 50) + '…'
                    : text
                  : c.title,
              messages: [...c.messages, userMsg],
              updatedAt: new Date().toISOString(),
            }
          : c,
      ),
    );
    setDraft('');
    simulateReply(active.id, text);
  };

  const simulateReply = (conversationId: string, prompt: string) => {
    setSending(true);
    const placeholderId = newId();
    const placeholder: Message = {
      id: placeholderId,
      role: 'assistant',
      content: '',
      createdAt: new Date().toISOString(),
      pending: true,
    };
    setConversations((prev) =>
      prev.map((c) =>
        c.id === conversationId
          ? { ...c, messages: [...c.messages, placeholder] }
          : c,
      ),
    );
    setTimeout(() => {
      const reply = fakeAssistantReply(prompt);
      setConversations((prev) =>
        prev.map((c) =>
          c.id === conversationId
            ? {
                ...c,
                messages: c.messages.map((m) => (m.id === placeholderId ? reply : m)),
                updatedAt: new Date().toISOString(),
              }
            : c,
        ),
      );
      setSending(false);
    }, 1100);
  };

  const sidebar = (
    <Sidebar
      conversations={conversations}
      activeId={activeId}
      onSelect={handleSelect}
      onNewChat={handleNewChat}
      onOpenProfile={handleOpenProfile}
      onOpenSources={handleOpenSources}
      themeMode={mode}
      onToggleTheme={() => setMode((m) => (m === 'light' ? 'dark' : 'light'))}
    />
  );

  if (view === 'browse') {
    // Full-width takeover: the three-pane reader owns the whole window,
    // bypassing the conversation sidebar and chat top bar.
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
          <BrowsePage onBack={() => setView('chat')} />
        </Box>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
        {isDesktop ? (
          sidebar
        ) : (
          <Drawer
            open={mobileOpen}
            onClose={() => setMobileOpen(false)}
            slotProps={{ paper: { sx: { width: 288, border: 'none' } } }}
          >
            {sidebar}
          </Drawer>
        )}

        <Box
          component="main"
          sx={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            position: 'relative',
          }}
        >
          <TopBar
            title={
              view === 'profile'
                ? 'Account'
                : (active?.title ?? 'New conversation')
            }
            onOpenSidebar={() => setMobileOpen(true)}
            showSidebarToggle={!isDesktop}
          />

          {view === 'profile' ? (
            <Profile onBack={() => setView('chat')} />
          ) : (
            <>
              {hasMessages && <DisclaimerBanner />}

              {hasMessages ? (
                <MessageList messages={active!.messages} />
              ) : (
                <WelcomeHero onPick={(p) => handleSubmit(p)} />
              )}

              <Composer
                value={draft}
                onChange={setDraft}
                onSubmit={handleSubmit}
                disabled={sending}
                autoFocus
              />
            </>
          )}
        </Box>
      </Box>
    </ThemeProvider>
  );
}
