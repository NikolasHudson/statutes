import { useEffect, useState } from 'react';

// Tiny hash-based router. Avoids pulling in react-router for four pages
// that map cleanly to "/" | "/register" | "/login" | "/account".
//
// Returns the current route (everything after the leading "#/") and a
// navigate() helper that updates window.location.hash. Listens for both
// hashchange (back/forward) and popstate so external links work.

// '' is the chat home. 'console' keeps the original BYO-key test console
// reachable for debugging the tool-calling loop.
export type Route =
  | ''
  | 'register'
  | 'login'
  | 'account'
  | 'browse'
  | 'console';

const KNOWN: Route[] = [
  '',
  'register',
  'login',
  'account',
  'browse',
  'console',
];

function segments(): string[] {
  return window.location.hash
    .replace(/^#\/?/, '')
    .split('?')[0]
    .split('/')
    .filter(Boolean);
}

function read(): Route {
  const segs = segments();
  const head = segs[0] ?? '';
  if ((KNOWN as readonly string[]).includes(head)) return head as Route;
  // Citation-native permalink: "#/iowa-code/714.16" → the corpus browser.
  // (A lone unknown segment stays the chat home, unchanged.)
  if (segs.length >= 2) return 'browse';
  return '';
}

// Parse a citation permalink: "#/iowa-code/714.16" → { slug, path }.
// The path can carry dots/colons/parens; we keep everything after the
// source slug verbatim (decoded) and let the backend resolver parse it.
// Returns null for the fixed routes ("#/account") and the bare home.
export function hashCitationTarget(): { slug: string; path: string } | null {
  const segs = segments();
  if (segs.length < 2) return null;
  const head = segs[0];
  if ((KNOWN as readonly string[]).includes(head)) return null;
  return {
    slug: head,
    path: decodeURIComponent(segs.slice(1).join('/')),
  };
}

// Read a query param off the hash, e.g. "#/browse?node=123" → "123".
// Lets a chat source card deep-link straight into the corpus browser.
export function hashQueryParam(key: string): string | null {
  const q = window.location.hash.split('?')[1];
  return q ? new URLSearchParams(q).get(key) : null;
}

// Drop the query off the current hash without adding a history entry, so a
// consumed deep link doesn't re-fire on the next hashchange / reload.
export function clearHashQuery(): void {
  const base = window.location.hash.split('?')[0] || '#/';
  window.history.replaceState(null, '', base);
}

export function useHashRoute(): [Route, (next: Route) => void] {
  const [route, setRoute] = useState<Route>(() => read());

  useEffect(() => {
    const handler = () => setRoute(read());
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, []);

  const navigate = (next: Route) => {
    window.location.hash = next ? `/${next}` : '/';
  };
  return [route, navigate];
}
