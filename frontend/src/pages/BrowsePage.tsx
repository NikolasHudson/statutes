import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import Snackbar from '@mui/material/Snackbar';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';

import KeyboardDoubleArrowLeftRoundedIcon from '@mui/icons-material/KeyboardDoubleArrowLeftRounded';
import KeyboardDoubleArrowRightRoundedIcon from '@mui/icons-material/KeyboardDoubleArrowRightRounded';
import ChevronRightRoundedIcon from '@mui/icons-material/ChevronRightRounded';
import ExpandMoreRoundedIcon from '@mui/icons-material/ExpandMoreRounded';
import ChevronLeftRoundedIcon from '@mui/icons-material/ChevronLeftRounded';
import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded';
import AccessTimeRoundedIcon from '@mui/icons-material/AccessTimeRounded';
import CompareArrowsRoundedIcon from '@mui/icons-material/CompareArrowsRounded';
import IosShareRoundedIcon from '@mui/icons-material/IosShareRounded';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import BookmarkBorderRoundedIcon from '@mui/icons-material/BookmarkBorderRounded';
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined';
import OpenInNewRoundedIcon from '@mui/icons-material/OpenInNewRounded';
import SearchRoundedIcon from '@mui/icons-material/SearchRounded';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';

import {
  browseChapter,
  browseChapters,
  browseNode,
  browseResolve,
  browseSearch,
  browseSources,
  type BrowseChapter,
  type BrowseSearchResponse,
  type BrowseSearchResult,
  type BrowseSource,
  type ChapterDetail,
  type CrossRef,
  type NodeDetail,
} from '../api';
import { usePalette, type Pal } from './legalPalette';
import {
  clearHashQuery,
  hashCitationTarget,
  hashQueryParam,
} from '../useHashRoute';

type Props = { onBack: () => void };

type Selection = {
  slug?: string;
  chapterId?: number;
  nodeId?: number;
};

// ---------------------------------------------------------------------------
// Quick-action helpers (share / download / print)
//
// Everything the bar acts on is already in client state, so these are pure
// browser-side: build a clean plain-text rendering of the current selection,
// then hand it to a Blob download, a print window, or the Web Share API.
// ---------------------------------------------------------------------------

const DISCLAIMER =
  'Disclaimer: This text is provided for convenience and reference only. ' +
  'It reflects the currently effective, reviewed version held in the Iowa ' +
  'Legal Corpus and is not a substitute for the official publication. ' +
  'Always verify against the official source before relying on any provision.';

// parseStatute (declared lower, hoisted) recovers the numbered hierarchy;
// re-emit it depth-indented so the .txt / print output is readable.
function renderStatuteLines(
  items: StatuteItem[],
  depth: number,
  out: string[],
): void {
  for (const it of items) {
    const indent = '    '.repeat(depth);
    const head = [it.marker, it.title].filter(Boolean).join(' ');
    const line = [head, it.text].filter(Boolean).join(' ').trim();
    if (line) out.push(indent + line);
    if (it.children.length) renderStatuteLines(it.children, depth + 1, out);
  }
}

function renderBodyText(raw: string): string {
  const { lead, tree } = parseStatute(raw);
  if (tree.length === 0) return (lead || raw).trim();
  const out: string[] = [];
  if (lead) out.push(lead);
  renderStatuteLines(tree, 0, out);
  return out.join('\n');
}

function buildPlainText(
  source: BrowseSource | null,
  chapter: ChapterDetail | null,
  node: NodeDetail | null,
): string {
  const lines: string[] = [];
  if (source) lines.push(source.name);

  if (node) {
    lines.push('', `${node.citation} ${node.heading}`.trim());
    if (node.effective_from)
      lines.push(
        `Effective ${node.effective_from}` +
          (node.division ? ` · ${node.division}` : ''),
      );
    lines.push('');
    lines.push(
      node.body_text
        ? renderBodyText(node.body_text)
        : '[No extractable text for this provision.]',
    );
    const bodyHistory = parseStatute(node.body_text || '').history;
    const history = [...bodyHistory, ...node.history];
    if (history.length) lines.push('', 'History', ...history);
    if (node.official_url) lines.push('', `Official source: ${node.official_url}`);
  } else if (chapter) {
    lines.push(
      '',
      `${chapter.type} ${chapter.ordinal}`.toUpperCase(),
      chapter.heading.toUpperCase(),
      '',
    );
    chapter.children.forEach((c) =>
      lines.push(`${c.citation}  ${c.heading}`.trim()),
    );
    if (chapter.official_url)
      lines.push('', `Official source: ${chapter.official_url}`);
  }

  lines.push('', '———', DISCLAIMER);
  lines.push('Hosted by: Iowa Legal Corpus — sourced from legis.iowa.gov.');
  return lines.join('\n');
}

function downloadFilename(
  chapter: ChapterDetail | null,
  node: NodeDetail | null,
): string {
  const base =
    node?.citation ??
    (chapter ? `${chapter.type} ${chapter.ordinal}` : 'iowa-legal-corpus');
  const slug = base
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return `${slug || 'document'}.txt`;
}

function downloadText(filename: string, text: string): void {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Citation-native permalink: "…#/iowa-code/714.16". Stable, human-typeable,
// and matches how the section is actually cited. Falls back to the legacy
// "?node=<id>" form only if the detail (and thus its path) hasn't loaded
// yet — that form is still resolved on the way in, so old shared links and
// chat source-card deep-links keep working.
function shareUrl(
  sel: Selection,
  node: NodeDetail | null,
  chapter: ChapterDetail | null,
): string {
  const { origin, pathname } = window.location;
  const permalink =
    node && node.path
      ? `${node.source_slug}/${encodeURIComponent(node.path)}`
      : chapter && chapter.path
        ? `${chapter.source_slug}/${encodeURIComponent(chapter.path)}`
        : '';
  if (permalink) return `${origin}${pathname}#/${permalink}`;
  const q = sel.nodeId
    ? `node=${sel.nodeId}`
    : sel.chapterId
      ? `chapter=${sel.chapterId}`
      : '';
  return `${origin}${pathname}#/browse${q ? `?${q}` : ''}`;
}

function printText(title: string, text: string): void {
  const w = window.open('', '_blank');
  if (!w) return;
  const esc = (s: string) =>
    s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  w.document.write(
    `<!doctype html><html><head><meta charset="utf-8">` +
      `<title>${esc(title)}</title><style>` +
      `body{font-family:Georgia,'Times New Roman',serif;line-height:1.7;` +
      `font-size:12pt;color:#1a1a1a;max-width:46rem;margin:2.5rem auto;` +
      `padding:0 1.5rem;}` +
      `pre{white-space:pre-wrap;word-break:break-word;font:inherit;margin:0;}` +
      `</style></head><body><pre>${esc(text)}</pre></body></html>`,
  );
  w.document.close();
  w.focus();
  // about:blank rarely fires a reliable load event after document.write, so
  // give it a tick to lay out, then print.
  setTimeout(() => {
    try {
      w.print();
    } catch {
      /* window already closed by the user */
    }
  }, 250);
}

type QuickAction = {
  key: 'share' | 'download' | 'bookmark' | 'print';
  icon: React.ReactNode;
  label: string;
};

const QUICK_ACTIONS: QuickAction[] = [
  { key: 'share', icon: <IosShareRoundedIcon />, label: 'Share' },
  { key: 'download', icon: <FileDownloadOutlinedIcon />, label: 'Download' },
  { key: 'bookmark', icon: <BookmarkBorderRoundedIcon />, label: 'Bookmark' },
  { key: 'print', icon: <PrintOutlinedIcon />, label: 'Print' },
];

type ActionHandlers = {
  onShare: () => void;
  onDownload: () => void;
  onPrint: () => void;
  enabled: boolean;
};

export function BrowsePage({ onBack }: Props) {
  const pal = usePalette();

  const [sources, setSources] = useState<BrowseSource[] | null>(null);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [chapters, setChapters] = useState<Record<string, BrowseChapter[]>>({});
  const [chapterDetails, setChapterDetails] = useState<
    Record<number, ChapterDetail>
  >({});
  const [nodes, setNodes] = useState<Record<number, NodeDetail>>({});

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [sel, setSel] = useState<Selection>({});

  const [tocOpen, setTocOpen] = useState(
    typeof window === 'undefined' ? true : window.innerWidth > 960,
  );

  // Search: a query takes over the reading pane with a ranked result list;
  // picking a hit resolves it back into the tree + reader (same path as a
  // chat deep-link). `searchScope` null = whole corpus, else a source slug.
  const [searchInput, setSearchInput] = useState('');
  const [searchActive, setSearchActive] = useState(false);
  const [searchResults, setSearchResults] = useState<BrowseSearchResponse | null>(
    null,
  );
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchScope, setSearchScope] = useState<string | null>(null);

  const mark = useCallback((key: string, on: boolean) => {
    setBusy((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  useEffect(() => {
    let alive = true;
    browseSources()
      .then((d) => alive && setSources(d))
      .catch((e) => alive && setSourcesError(e?.message ?? 'Failed to load'));
    return () => {
      alive = false;
    };
  }, []);

  // In-flight request caches. The `if (cache[id]) return` guards below read a
  // stale closure value, so two callers in the same tick (e.g. a chapter row
  // firing both onToggleChapter and onSelectChapter, or React StrictMode's
  // dev double-invoke) would both miss the guard and fire duplicate fetches.
  // Keying the live promise by id collapses concurrent callers onto one
  // request; the entry is dropped once it settles so a later miss refetches.
  const chaptersInFlight = useRef<Map<string, Promise<unknown>>>(new Map());
  const chapterInFlight = useRef<Map<number, Promise<ChapterDetail>>>(new Map());
  const nodeInFlight = useRef<Map<number, Promise<unknown>>>(new Map());

  const loadChapters = useCallback(
    (slug: string) => {
      if (chapters[slug]) return Promise.resolve();
      const existing = chaptersInFlight.current.get(slug);
      if (existing) return existing;
      mark(`src:${slug}`, true);
      const p = browseChapters(slug)
        .then((r) => {
          setChapters((prev) => ({ ...prev, [slug]: r.chapters }));
        })
        .finally(() => {
          chaptersInFlight.current.delete(slug);
          mark(`src:${slug}`, false);
        });
      chaptersInFlight.current.set(slug, p);
      return p;
    },
    [chapters, mark],
  );

  const loadChapter = useCallback(
    (id: number): Promise<ChapterDetail | undefined> => {
      const cached = chapterDetails[id];
      if (cached) return Promise.resolve(cached);
      const existing = chapterInFlight.current.get(id);
      if (existing) return existing;
      mark(`chap:${id}`, true);
      const p = browseChapter(id)
        .then((d) => {
          setChapterDetails((prev) => ({ ...prev, [id]: d }));
          return d;
        })
        .finally(() => {
          chapterInFlight.current.delete(id);
          mark(`chap:${id}`, false);
        });
      chapterInFlight.current.set(id, p);
      return p;
    },
    [chapterDetails, mark],
  );

  const loadNode = useCallback(
    (id: number) => {
      if (nodes[id]) return Promise.resolve();
      const existing = nodeInFlight.current.get(id);
      if (existing) return existing;
      mark(`node:${id}`, true);
      const p = browseNode(id)
        .then((d) => {
          setNodes((prev) => ({ ...prev, [id]: d }));
        })
        .finally(() => {
          nodeInFlight.current.delete(id);
          mark(`node:${id}`, false);
        });
      nodeInFlight.current.set(id, p);
      return p;
    },
    [nodes, mark],
  );

  const toggle = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const openSource = useCallback(
    (slug: string) => {
      void loadChapters(slug);
      setExpanded((p) => new Set(p).add(`src:${slug}`));
    },
    [loadChapters],
  );

  const selectChapter = useCallback(
    (slug: string, id: number) => {
      setSel({ slug, chapterId: id });
      setExpanded((p) => {
        const n = new Set(p);
        n.add(`src:${slug}`);
        n.add(`chap:${id}`);
        return n;
      });
      void loadChapter(id);
    },
    [loadChapter],
  );

  const selectNode = useCallback(
    (slug: string, chapterId: number, nodeId: number) => {
      setSel({ slug, chapterId, nodeId });
      void loadChapter(chapterId);
      void loadNode(nodeId);
    },
    [loadChapter, loadNode],
  );

  // Inline cross-reference click: resolve the cited path to a node and
  // open it in place (no reload), then reflect the canonical permalink in
  // the address bar. replaceState (not location.hash) so it doesn't fire
  // the router — selection is already driven by state here. Targets come
  // from the backend-resolved cross_refs list, so resolve essentially
  // always succeeds; a miss just leaves the current view untouched.
  const goToCitation = useCallback(
    async (sourceSlug: string, path: string) => {
      try {
        const r = await browseResolve(sourceSlug, path);
        if (!r.found) return;
        const d = await browseNode(r.node_id);
        const slug = d.source_slug;
        const chapterId = d.chapter?.id ?? d.id;
        setNodes((p) => ({ ...p, [d.id]: d }));
        await loadChapters(slug);
        await loadChapter(chapterId);
        setSel({
          slug,
          chapterId,
          nodeId: d.chapter ? d.id : undefined,
        });
        setExpanded((p) =>
          new Set(p).add(`src:${slug}`).add(`chap:${chapterId}`),
        );
        window.history.replaceState(
          null,
          '',
          `#/${slug}/${encodeURIComponent(path)}`,
        );
      } catch {
        /* unresolved / transient — leave the current view as-is */
      }
    },
    [loadChapters, loadChapter],
  );

  // Deep links into the reader. Two shapes:
  //   • Citation-native permalink — "#/iowa-code/714.16" (the canonical
  //     shareable URL; also what an inline cross-ref click navigates to).
  //   • Legacy query form — "#/browse?node=<id>" / "?chapter=<id>" (old
  //     shared links + chat source cards). Still resolved on the way in.
  // Both resolve to a node, prime the caches, select it, and open the
  // tree. Consume the legacy query once so it doesn't re-fire; keep a
  // permalink in the address bar since it *is* the shareable URL.
  //
  // Self-contained on purpose: it does its own fetches rather than calling
  // loadChapters/loadChapter, because those useCallbacks are keyed on the very
  // state they mutate — depending on them would re-run this effect mid-flight
  // and abort the selection before it lands.
  const deepLinked = useRef(false);
  useEffect(() => {
    if (deepLinked.current || !sources) return;
    const permalink = hashCitationTarget();
    const nodeRaw = hashQueryParam('node');
    const chapterRaw = hashQueryParam('chapter');
    const nodeId = nodeRaw ? Number(nodeRaw) : NaN;
    const chapterParam = chapterRaw ? Number(chapterRaw) : NaN;
    const wantsNode = !!nodeRaw && !Number.isNaN(nodeId);
    const wantsChapter = !wantsNode && !!chapterRaw && !Number.isNaN(chapterParam);
    if (!permalink && !wantsNode && !wantsChapter) return;
    deepLinked.current = true;

    (async () => {
      try {
        // A citation permalink resolves to a node id first; a chapter-
        // level permalink ("#/iowa-code/714") resolves to the chapter
        // node, which browseNode reports with chapter:null — the node
        // branch below already handles that shape.
        let resolvedNodeId = wantsNode ? nodeId : NaN;
        if (permalink) {
          const r = await browseResolve(permalink.slug, permalink.path);
          if (!r.found) return; // unknown cite — leave the landing view
          resolvedNodeId = r.node_id;
        }

        if (permalink || wantsNode) {
          const d = await browseNode(resolvedNodeId);
          const slug = d.source_slug;
          // A node with no parent is itself a chapter; otherwise read the
          // chapter under which it lives.
          const chapterId = d.chapter?.id ?? d.id;
          const [chList, chDetail] = await Promise.all([
            browseChapters(slug),
            browseChapter(chapterId),
          ]);
          setNodes((p) => ({ ...p, [d.id]: d }));
          setChapters((p) => ({ ...p, [slug]: chList.chapters }));
          setChapterDetails((p) => ({ ...p, [chapterId]: chDetail }));
          setSel({
            slug,
            chapterId,
            nodeId: d.chapter ? d.id : undefined,
          });
          setExpanded((p) =>
            new Set(p).add(`src:${slug}`).add(`chap:${chapterId}`),
          );
        } else {
          const chDetail = await browseChapter(chapterParam);
          const slug = chDetail.source_slug;
          const chList = await browseChapters(slug);
          setChapters((p) => ({ ...p, [slug]: chList.chapters }));
          setChapterDetails((p) => ({ ...p, [chDetail.id]: chDetail }));
          setSel({ slug, chapterId: chDetail.id });
          setExpanded((p) =>
            new Set(p).add(`src:${slug}`).add(`chap:${chDetail.id}`),
          );
        }
      } catch {
        /* bad / stale id — just leave the browser on its landing view */
      } finally {
        // The permalink is the canonical URL — leave it in the bar.
        // Only the legacy ?query= form gets consumed.
        if (!permalink) clearHashQuery();
      }
    })();
  }, [sources]);

  // Fill the empty sidebar on first load: expand the first source so the
  // reader lands on a populated tree instead of two collapsed rows over a
  // blank column. Runs once; yields to a deep link or any prior expansion.
  const autoExpanded = useRef(false);
  useEffect(() => {
    if (autoExpanded.current || !sources || sources.length === 0) return;
    autoExpanded.current = true;
    if (deepLinked.current || expanded.size > 0) return;
    openSource(sources[0].slug);
  }, [sources, expanded.size, openSource]);

  const selSource = sources?.find((s) => s.slug === sel.slug) ?? null;
  const selChapterDetail = sel.chapterId
    ? chapterDetails[sel.chapterId] ?? null
    : null;
  const selNode = sel.nodeId ? nodes[sel.nodeId] ?? null : null;

  // Prev / Next within the active chapter's leaf list.
  const siblings = selChapterDetail?.children ?? [];
  const idx = sel.nodeId
    ? siblings.findIndex((c) => c.id === sel.nodeId)
    : -1;
  const prevChild = idx > 0 ? siblings[idx - 1] : null;
  const nextChild =
    idx >= 0 && idx < siblings.length - 1
      ? siblings[idx + 1]
      : idx < 0 && siblings.length > 0
        ? siblings[0]
        : null;

  // Quick-action wiring. The bar acts on the most specific thing in view:
  // the selected node, else the selected chapter index.
  const [snack, setSnack] = useState<string | null>(null);
  const hasContent = !!(selSource && (selNode || selChapterDetail));

  const runSearch = useCallback(
    async (query: string, scope: string | null) => {
      const q = query.trim();
      if (q.length < 2) return;
      setSearchScope(scope);
      setSearchActive(true);
      setSearching(true);
      setSearchError(null);
      try {
        const r = await browseSearch(q, scope);
        setSearchResults(r);
      } catch (e) {
        setSearchError((e as Error)?.message ?? 'Search failed');
        setSearchResults(null);
      } finally {
        setSearching(false);
      }
    },
    [],
  );

  // Hide the results pane but KEEP the result set, so picking a hit (or
  // "Back to reading") can be reversed with "Results". The box ✕ is the
  // only full reset.
  const hideSearch = useCallback(() => setSearchActive(false), []);

  const closeSearch = useCallback(() => {
    setSearchActive(false);
    setSearchResults(null);
    setSearchError(null);
    setSearchInput('');
  }, []);

  // Resolve a hit back into the tree + reader. Self-contained for the same
  // reason the deep-link effect is: loadChapter/loadChapters are keyed on the
  // very state they mutate, so calling them here would race the selection.
  const openSearchResult = useCallback(async (nodeId: number) => {
    try {
      const d = await browseNode(nodeId);
      const slug = d.source_slug;
      const chapterId = d.chapter?.id ?? d.id;
      const [chList, chDetail] = await Promise.all([
        browseChapters(slug),
        browseChapter(chapterId),
      ]);
      setNodes((p) => ({ ...p, [d.id]: d }));
      setChapters((p) => ({ ...p, [slug]: chList.chapters }));
      setChapterDetails((p) => ({ ...p, [chapterId]: chDetail }));
      setSel({ slug, chapterId, nodeId: d.chapter ? d.id : undefined });
      setExpanded((p) =>
        new Set(p).add(`src:${slug}`).add(`chap:${chapterId}`),
      );
      setSearchActive(false);
    } catch {
      setSnack('Could not open that result');
    }
  }, []);

  const actionTitle = useCallback(
    () =>
      selNode
        ? `${selNode.citation} ${selNode.heading}`.trim()
        : selChapterDetail
          ? `${selChapterDetail.type} ${selChapterDetail.ordinal} — ${selChapterDetail.heading}`
          : 'Iowa Legal Corpus',
    [selNode, selChapterDetail],
  );

  const handleShare = useCallback(async () => {
    const url = shareUrl(sel, selNode, selChapterDetail);
    const title = actionTitle();
    if (navigator.share) {
      try {
        await navigator.share({ title, url });
        return;
      } catch {
        // User dismissed the native sheet, or it's unavailable here — fall
        // through to the clipboard copy.
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setSnack('Link copied to clipboard');
    } catch {
      setSnack('Could not copy the link');
    }
  }, [sel, selNode, selChapterDetail, actionTitle]);

  const handleDownload = useCallback(() => {
    if (!hasContent) return;
    downloadText(
      downloadFilename(selChapterDetail, selNode),
      buildPlainText(selSource, selChapterDetail, selNode),
    );
  }, [hasContent, selSource, selChapterDetail, selNode]);

  const handlePrint = useCallback(() => {
    if (!hasContent) return;
    printText(
      actionTitle(),
      buildPlainText(selSource, selChapterDetail, selNode),
    );
  }, [hasContent, actionTitle, selSource, selChapterDetail, selNode]);

  const actions: ActionHandlers = {
    onShare: () => void handleShare(),
    onDownload: handleDownload,
    onPrint: handlePrint,
    enabled: hasContent,
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
      <ActionBar
        pal={pal}
        tocOpen={tocOpen}
        onToggleToc={() => setTocOpen((v) => !v)}
        crumbs={buildCrumbs(selSource, selChapterDetail, selNode)}
        onCrumb={(c) => {
          if (c === 'source' && sel.slug)
            setSel({ slug: sel.slug });
          else if (c === 'chapter' && sel.slug && sel.chapterId)
            setSel({ slug: sel.slug, chapterId: sel.chapterId });
        }}
        search={{
          value: searchInput,
          onChange: setSearchInput,
          // Default scope: the source the reader is in, if any. The results
          // header lets the user widen to the whole corpus.
          onSubmit: () => runSearch(searchInput, sel.slug ?? null),
          onClear: closeSearch,
          active: searchActive,
        }}
      />

      <Box
        sx={{
          minHeight: 0,
          display: 'grid',
          gridTemplateColumns: tocOpen
            ? { xs: '0 1fr', sm: '310px 1fr' }
            : '0 1fr',
          transition: 'grid-template-columns 160ms ease',
        }}
      >
        <Box
          sx={{
            minWidth: 0,
            borderRight: tocOpen ? `1px solid ${pal.border}` : 'none',
            bgcolor: pal.sidebar,
            overflowY: 'auto',
            overflowX: 'hidden',
            display: tocOpen ? 'block' : 'none',
          }}
        >
          <VersionSelector pal={pal} />
          {sourcesError ? (
            <Box sx={{ p: 2 }}>
              <Alert severity="error">{sourcesError}</Alert>
            </Box>
          ) : !sources ? (
            <Centered>
              <CircularProgress size={24} />
            </Centered>
          ) : (
            <Box sx={{ py: 1 }}>
              {sources.map((s) => (
                <SourceBranch
                  key={s.slug}
                  pal={pal}
                  source={s}
                  expanded={expanded}
                  busy={busy}
                  chapters={chapters[s.slug]}
                  chapterDetails={chapterDetails}
                  sel={sel}
                  onToggleSource={() => {
                    const key = `src:${s.slug}`;
                    if (!expanded.has(key)) openSource(s.slug);
                    else toggle(key);
                  }}
                  onToggleChapter={(id) => {
                    const key = `chap:${id}`;
                    if (!expanded.has(key)) {
                      void loadChapter(id);
                      setExpanded((p) => new Set(p).add(key));
                    } else toggle(key);
                  }}
                  onSelectChapter={(id) => selectChapter(s.slug, id)}
                  onSelectNode={(cid, nid) => selectNode(s.slug, cid, nid)}
                />
              ))}
            </Box>
          )}
        </Box>

        <Box sx={{ minWidth: 0, overflowY: 'auto', bgcolor: pal.paper }}>
          {searchActive ? (
            <SearchResultsPane
              pal={pal}
              query={searchResults?.query ?? searchInput}
              loading={searching}
              error={searchError}
              data={searchResults}
              scope={searchScope}
              scopeSource={selSource}
              onPick={openSearchResult}
              onSetScope={(slug) => runSearch(searchInput, slug)}
              onClose={hideSearch}
            />
          ) : (
            <ReadingPane
              pal={pal}
              actions={actions}
              source={selSource}
              chapter={selChapterDetail}
              chapterLoading={
                !!sel.chapterId && busy.has(`chap:${sel.chapterId}`)
              }
              node={selNode}
              nodeLoading={!!sel.nodeId && busy.has(`node:${sel.nodeId}`)}
              hasNode={!!sel.nodeId}
              onPickChild={(cid, nid) =>
                sel.slug && selectNode(sel.slug, cid, nid)
              }
              onCitation={goToCitation}
              onBackToResults={
                searchResults ? () => setSearchActive(true) : undefined
              }
            />
          )}
        </Box>
      </Box>

      <PinnedBottomNav
        pal={pal}
        tocOpen={tocOpen}
        onBack={onBack}
        onPrev={
          prevChild && sel.slug && sel.chapterId
            ? () => selectNode(sel.slug!, sel.chapterId!, prevChild.id)
            : undefined
        }
        onNext={
          nextChild && sel.slug && sel.chapterId
            ? () => selectNode(sel.slug!, sel.chapterId!, nextChild.id)
            : undefined
        }
        prevLabel={prevChild?.citation}
        nextLabel={nextChild?.citation}
      />

      <Snackbar
        open={!!snack}
        autoHideDuration={2500}
        onClose={() => setSnack(null)}
        message={snack ?? ''}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Action / breadcrumb bar (blue strip)
// ---------------------------------------------------------------------------

type Crumb = { key: 'source' | 'chapter' | 'node'; label: string };

function buildCrumbs(
  source: BrowseSource | null,
  chapter: ChapterDetail | null,
  node: NodeDetail | null,
): Crumb[] {
  const out: Crumb[] = [];
  if (source) out.push({ key: 'source', label: source.abbreviation });
  if (chapter)
    out.push({
      key: 'chapter',
      label: `${chapter.type} ${chapter.ordinal}`,
    });
  if (node) out.push({ key: 'node', label: node.citation });
  return out;
}

type SearchBoxProps = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onClear: () => void;
  active: boolean;
};

function ActionBar({
  pal,
  tocOpen,
  onToggleToc,
  crumbs,
  onCrumb,
  search,
}: {
  pal: Pal;
  tocOpen: boolean;
  onToggleToc: () => void;
  crumbs: Crumb[];
  onCrumb: (key: Crumb['key']) => void;
  search: SearchBoxProps;
}) {
  return (
    <Box
      sx={{
        bgcolor: pal.chrome,
        color: pal.chromeText,
        height: 44,
        px: 1,
        display: 'flex',
        alignItems: 'center',
        gap: 1,
      }}
    >
      <Tooltip title={tocOpen ? 'Collapse contents' : 'Show contents'}>
        <IconButton
          size="small"
          onClick={onToggleToc}
          sx={{ color: pal.chromeText, '&:hover': { bgcolor: pal.chromeHover } }}
          aria-label="Toggle table of contents"
        >
          {tocOpen ? (
            <KeyboardDoubleArrowLeftRoundedIcon fontSize="small" />
          ) : (
            <KeyboardDoubleArrowRightRoundedIcon fontSize="small" />
          )}
        </IconButton>
      </Tooltip>

      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 0.75,
          overflow: 'hidden',
          whiteSpace: 'nowrap',
        }}
      >
        <Typography
          component="span"
          sx={{ fontSize: 13, opacity: 0.85, flexShrink: 0 }}
        >
          Iowa Legal Corpus
        </Typography>
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <Box
              key={c.key}
              component="span"
              sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}
            >
              <Box component="span" sx={{ opacity: 0.55, flexShrink: 0 }}>
                ›
              </Box>
              {last ? (
                <Typography
                  component="span"
                  sx={{
                    fontSize: 16,
                    fontWeight: 600,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {c.label}
                </Typography>
              ) : (
                <Box
                  component="button"
                  onClick={() => onCrumb(c.key)}
                  sx={{
                    all: 'unset',
                    cursor: 'pointer',
                    fontSize: 13,
                    color: pal.chromeText,
                    textDecoration: 'underline',
                    flexShrink: 0,
                    '&:hover': { opacity: 0.8 },
                  }}
                >
                  {c.label}
                </Box>
              )}
            </Box>
          );
        })}
      </Box>

      <Box
        sx={{
          display: { xs: 'none', md: 'flex' },
          alignItems: 'center',
          gap: 0.75,
          flexShrink: 0,
          width: { md: 320, lg: 440 },
          px: 1.75,
          py: 0.85,
          borderRadius: 999,
          bgcolor: pal.chromeHover,
          border: `1px solid ${pal.circleBorder}`,
          color: pal.chromeText,
        }}
      >
        <SearchRoundedIcon sx={{ fontSize: 20, opacity: 0.85 }} />
        <Box
          component="input"
          value={search.value}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
            search.onChange(e.target.value)
          }
          onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => {
            if (e.key === 'Enter') search.onSubmit();
            else if (e.key === 'Escape' && search.active) search.onClear();
          }}
          placeholder="Search the corpus…"
          aria-label="Search the corpus"
          sx={{
            all: 'unset',
            flex: 1,
            minWidth: 0,
            fontSize: 14.5,
            color: pal.chromeText,
            '&::placeholder': { color: pal.chromeText, opacity: 0.7 },
          }}
        />
        {(search.value || search.active) && (
          <Tooltip title="Clear search">
            <IconButton
              size="small"
              onClick={search.onClear}
              aria-label="Clear search"
              sx={{
                p: 0.25,
                color: pal.chromeText,
                '&:hover': { bgcolor: pal.chromeHover },
              }}
            >
              <CloseRoundedIcon sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>

    </Box>
  );
}

// ---------------------------------------------------------------------------
// Version selector (visual placeholder — no historical-version API yet)
// ---------------------------------------------------------------------------

function VersionSelector({ pal }: { pal: Pal }) {
  return (
    <Box
      sx={{
        px: 1.5,
        py: 1.25,
        borderBottom: `1px solid ${pal.border}`,
      }}
    >
      <Typography
        sx={{
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: 0.4,
          textTransform: 'uppercase',
          color: pal.muted,
          mb: 0.75,
        }}
      >
        Viewing as of
      </Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Tooltip title="Historical versions — not available in preview">
        <Box
          component="span"
          sx={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            px: 1.25,
            py: 0.75,
            borderRadius: 999,
            border: `1px solid ${pal.border}`,
            color: pal.muted,
            fontSize: 13,
            cursor: 'default',
          }}
        >
          <AccessTimeRoundedIcon sx={{ fontSize: 16 }} />
          <Box component="span" sx={{ flex: 1 }}>
            May 2026 (current)
          </Box>
          <ExpandMoreRoundedIcon sx={{ fontSize: 18 }} />
        </Box>
      </Tooltip>
      <Tooltip title="Compare versions — not available in preview">
        <Box component="span">
          <IconButton size="small" disabled aria-label="Compare versions">
            <CompareArrowsRoundedIcon
              sx={{ fontSize: 18, color: pal.muted }}
            />
          </IconButton>
        </Box>
      </Tooltip>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// TOC tree
// ---------------------------------------------------------------------------

function Row({
  pal,
  depth,
  caret,
  active,
  onClick,
  children,
}: {
  pal: Pal;
  depth: number;
  caret?: 'collapsed' | 'expanded' | 'none';
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Box
      component="button"
      onClick={onClick}
      sx={{
        all: 'unset',
        boxSizing: 'border-box',
        width: '100%',
        minHeight: 36,
        display: 'flex',
        alignItems: 'center',
        gap: 0.5,
        pl: `${8 + depth * 16}px`,
        pr: 1,
        py: 0.75,
        cursor: 'pointer',
        borderRadius: '2px',
        bgcolor: active ? pal.activeRow : 'transparent',
        borderLeft: active
          ? `3px solid ${pal.chrome}`
          : '3px solid transparent',
        '&:hover': { bgcolor: active ? pal.activeRow : pal.borderSoft },
      }}
    >
      <Box
        sx={{
          width: 18,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: pal.muted,
        }}
      >
        {caret === 'collapsed' && (
          <ChevronRightRoundedIcon sx={{ fontSize: 18 }} />
        )}
        {caret === 'expanded' && (
          <ExpandMoreRoundedIcon sx={{ fontSize: 18 }} />
        )}
      </Box>
      <Box sx={{ minWidth: 0, flex: 1 }}>{children}</Box>
    </Box>
  );
}

function SourceBranch({
  pal,
  source,
  expanded,
  busy,
  chapters,
  chapterDetails,
  sel,
  onToggleSource,
  onToggleChapter,
  onSelectChapter,
  onSelectNode,
}: {
  pal: Pal;
  source: BrowseSource;
  expanded: Set<string>;
  busy: Set<string>;
  chapters?: BrowseChapter[];
  chapterDetails: Record<number, ChapterDetail>;
  sel: Selection;
  onToggleSource: () => void;
  onToggleChapter: (id: number) => void;
  onSelectChapter: (id: number) => void;
  onSelectNode: (chapterId: number, nodeId: number) => void;
}) {
  const open = expanded.has(`src:${source.slug}`);
  return (
    <Box>
      <Row
        pal={pal}
        depth={0}
        caret={open ? 'expanded' : 'collapsed'}
        onClick={onToggleSource}
      >
        <Typography
          sx={{ fontSize: 14, fontWeight: 700, color: pal.text }}
          noWrap
        >
          {source.name}
        </Typography>
      </Row>

      {open && (
        <Box>
          {busy.has(`src:${source.slug}`) && !chapters && (
            <Centered small>
              <CircularProgress size={18} />
            </Centered>
          )}
          {chapters?.map((c) => {
            const disabled = c.reserved || c.child_count === 0;
            const cKey = `chap:${c.id}`;
            const cOpen = expanded.has(cKey);
            const detail = chapterDetails[c.id];
            const chapterActive =
              sel.chapterId === c.id && sel.nodeId == null;
            return (
              <Box key={c.id}>
                <Row
                  pal={pal}
                  depth={1}
                  caret={disabled ? 'none' : cOpen ? 'expanded' : 'collapsed'}
                  active={chapterActive}
                  onClick={() => {
                    if (disabled) return;
                    onToggleChapter(c.id);
                    onSelectChapter(c.id);
                  }}
                >
                  <Typography
                    sx={{
                      fontSize: 14,
                      color: disabled ? pal.muted : pal.link,
                      textDecoration: disabled ? 'none' : 'underline',
                      opacity: disabled ? 0.7 : 1,
                    }}
                  >
                    <Box
                      component="span"
                      sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}
                    >
                      Ch. {c.ordinal}
                    </Box>{' '}
                    {c.heading}
                    {c.reserved && (
                      <Box component="span" sx={{ color: pal.muted }}>
                        {' '}
                        (reserved)
                      </Box>
                    )}
                  </Typography>
                </Row>

                {cOpen && (
                  <Box>
                    {busy.has(cKey) && !detail && (
                      <Centered small>
                        <CircularProgress size={16} />
                      </Centered>
                    )}
                    {detail?.children.map((n, i) => {
                      const prevDiv =
                        i > 0 ? detail.children[i - 1].division : null;
                      const nodeActive = sel.nodeId === n.id;
                      return (
                        <Box key={n.id}>
                          {n.division && n.division !== prevDiv && (
                            <Typography
                              sx={{
                                pl: '40px',
                                pr: 1,
                                pt: 1,
                                pb: 0.25,
                                fontSize: 11,
                                fontWeight: 700,
                                letterSpacing: '0.05em',
                                textTransform: 'uppercase',
                                color: pal.muted,
                              }}
                            >
                              {n.division}
                            </Typography>
                          )}
                          <Row
                            pal={pal}
                            depth={2}
                            caret="none"
                            active={nodeActive}
                            onClick={() => onSelectNode(c.id, n.id)}
                          >
                            <Typography
                              sx={{
                                fontSize: 13,
                                color: pal.link,
                                textDecoration: 'underline',
                              }}
                            >
                              <Box component="span" sx={{ fontWeight: 600 }}>
                                {n.citation}
                              </Box>{' '}
                              {n.heading}
                            </Typography>
                          </Row>
                        </Box>
                      );
                    })}
                    {detail && detail.children.length === 0 && (
                      <Typography
                        sx={{
                          pl: '40px',
                          pr: 1,
                          py: 1,
                          fontSize: 12,
                          color: pal.muted,
                          fontStyle: 'italic',
                        }}
                      >
                        No rule-structured entries.
                      </Typography>
                    )}
                  </Box>
                )}
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Reading pane
// ---------------------------------------------------------------------------

function ReadingPane({
  pal,
  actions,
  source,
  chapter,
  chapterLoading,
  node,
  nodeLoading,
  hasNode,
  onPickChild,
  onCitation,
  onBackToResults,
}: {
  pal: Pal;
  actions: ActionHandlers;
  source: BrowseSource | null;
  chapter: ChapterDetail | null;
  chapterLoading: boolean;
  node: NodeDetail | null;
  nodeLoading: boolean;
  hasNode: boolean;
  onPickChild: (chapterId: number, nodeId: number) => void;
  // Inline cross-reference click — resolve a cited path to a node and
  // open it in place. (sourceSlug, path) so the reader can pass the
  // viewed section's own source.
  onCitation: (sourceSlug: string, path: string) => void;
  // Set only when a hidden-but-preserved search result set exists (user
  // drilled into a hit). Renders a return link above the banner.
  onBackToResults?: () => void;
}) {
  if (!source) {
    return (
      <Box
        sx={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          color: pal.muted,
          textAlign: 'center',
          px: 4,
          gap: 1,
        }}
      >
        <Typography sx={{ fontSize: 20, fontWeight: 700, color: pal.text }}>
          Iowa Legal Corpus
        </Typography>
        <Typography sx={{ fontSize: 14, maxWidth: 420 }}>
          Pick a source in the table of contents, then drill into a chapter to
          read the currently effective, reviewed text of any provision.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 880, mx: 'auto', px: { xs: 3, md: 8 }, py: 0 }}>
      {onBackToResults && (
        <Box
          component="button"
          onClick={onBackToResults}
          sx={{
            all: 'unset',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 0.25,
            mt: 2.5,
            fontSize: 13,
            fontWeight: 600,
            color: pal.link,
            '&:hover': { opacity: 0.75 },
          }}
        >
          <ChevronLeftRoundedIcon sx={{ fontSize: 18 }} />
          Back to search results
        </Box>
      )}

      <DocumentBanner pal={pal} text={source.name} />

      {chapterLoading && !chapter ? (
        <Centered>
          <CircularProgress />
        </Centered>
      ) : chapter ? (
        <>
          <ChapterTitleBlock
            pal={pal}
            chapter={chapter}
            showOfficialLink={!hasNode}
          />

          {hasNode ? (
            nodeLoading && !node ? (
              <Centered>
                <CircularProgress size={28} />
              </Centered>
            ) : node ? (
              <SectionBlock
                pal={pal}
                actions={actions}
                node={node}
                onCitation={onCitation}
              />
            ) : null
          ) : (
            <SectionIndexGrid
              pal={pal}
              chapter={chapter}
              onPick={(nid) => onPickChild(chapter.id, nid)}
            />
          )}

          <DisclaimerFooter pal={pal} />
        </>
      ) : (
        <Centered>
          <Typography sx={{ color: pal.muted }}>
            Select a chapter to begin reading.
          </Typography>
        </Centered>
      )}
    </Box>
  );
}

function DocumentBanner({ pal, text }: { pal: Pal; text: string }) {
  return (
    <Box
      sx={{
        bgcolor: pal.banner,
        color: pal.bannerText,
        my: 4,
        // Break out of the 880px max-width container so the black bar spans
        // the full width of the reading pane, while the text stays constrained.
        position: 'relative',
        left: '50%',
        right: '50%',
        ml: '-50vw',
        mr: '-50vw',
        width: '100vw',
        maxWidth: '100vw',
      }}
    >
      <Box
        sx={{
          maxWidth: 880,
          mx: 'auto',
          px: { xs: 3, md: 8 },
          py: { xs: 2.5, md: 3.5 },
          textAlign: 'center',
        }}
      >
        <Typography
          sx={{
            fontSize: { xs: 22, md: 30 },
            fontWeight: 700,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}
        >
          {text}
        </Typography>
      </Box>
    </Box>
  );
}

function ChapterTitleBlock({
  pal,
  chapter,
  // When a section is open it carries its own "Official source" link, so the
  // chapter-level one here is redundant — suppress it then.
  showOfficialLink,
}: {
  pal: Pal;
  chapter: ChapterDetail;
  showOfficialLink: boolean;
}) {
  return (
    <Box
      sx={{
        textAlign: 'center',
        borderTop: `2px solid ${pal.text}`,
        borderBottom: `2px solid ${pal.text}`,
        py: 2,
        mb: 4,
      }}
    >
      <Typography
        sx={{
          fontSize: { xs: 22, md: 26 },
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.02em',
        }}
      >
        {chapter.type} {chapter.ordinal}
      </Typography>
      <Typography
        sx={{
          fontSize: { xs: 16, md: 18 },
          fontWeight: 700,
          textTransform: 'uppercase',
          mt: 0.5,
        }}
      >
        {chapter.heading}
      </Typography>
      {showOfficialLink && chapter.official_url && (
        <Box
          component="a"
          href={chapter.official_url}
          target="_blank"
          rel="noopener"
          sx={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 0.5,
            mt: 1,
            fontSize: 12,
            color: pal.link,
          }}
        >
          Official source
          <OpenInNewRoundedIcon sx={{ fontSize: 13 }} />
        </Box>
      )}
    </Box>
  );
}

function SectionIndexGrid({
  pal,
  chapter,
  onPick,
}: {
  pal: Pal;
  chapter: ChapterDetail;
  onPick: (nodeId: number) => void;
}) {
  if (chapter.children.length === 0) {
    return (
      <Alert severity="info" sx={{ my: 2 }}>
        This chapter has no rule-structured entries (it uses Forms / Canons /
        Roman-numeral standards the extractor does not yet split). Use the
        official source link above.
      </Alert>
    );
  }
  return (
    // Single column with a left number gutter — mirrors how the section pages
    // read, and sidesteps the mid-entry wrap the old two-column flow caused.
    <Box sx={{ mb: 5 }}>
      {chapter.children.map((c) => {
        // Reserved / repealed placeholders aren't navigable text — mute them
        // and drop the link affordance so a scanning eye skips past.
        const inactive = /^(reserved\b|repealed\b)/i.test(c.heading.trim());
        return (
          <Box
            key={c.id}
            component={inactive ? 'div' : 'button'}
            onClick={inactive ? undefined : () => onPick(c.id)}
            sx={{
              all: 'unset',
              boxSizing: 'border-box',
              width: '100%',
              display: 'grid',
              gridTemplateColumns: { xs: '5.5rem 1fr', sm: '7rem 1fr' },
              columnGap: 2,
              alignItems: 'baseline',
              py: 0.7,
              fontSize: 14.5,
              lineHeight: 1.5,
              borderBottom: `1px solid ${pal.borderSoft}`,
              cursor: inactive ? 'default' : 'pointer',
              '&:hover .cite': inactive
                ? {}
                : { textDecoration: 'underline' },
            }}
          >
            <Box
              component="span"
              className="cite"
              sx={{
                color: inactive ? pal.muted : pal.link,
                fontWeight: 600,
                fontVariantNumeric: 'tabular-nums',
                whiteSpace: 'nowrap',
              }}
            >
              {c.citation}
            </Box>
            <Box
              component="span"
              sx={{
                color: inactive ? pal.muted : pal.body,
                fontStyle: inactive ? 'italic' : 'normal',
              }}
            >
              {c.heading}
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Rule body formatter
//
// The corpus stores body_text as one unbroken string (the upstream source has
// no line breaks). Iowa rules are heavily numbered, so we can recover the
// structure heuristically: split on the structural markers, indent by depth,
// and bold the run-in catchline that opens each subrule / lettered paragraph.
// ---------------------------------------------------------------------------

type Block = {
  level: 0 | 1 | 2;
  marker: string;
  title: string;
  text: string;
  // True when the whole segment was taken as a catchline (no body followed).
  // Only a real heading if a deeper marker comes next; resolved post-parse.
  solo?: boolean;
};
type ParsedBody = { blocks: Block[]; history: string | null };

// A marker starts a new block when it follows sentence-ending punctuation +
// space (or a colon/quote/paren), and is followed by space + a capital, quote,
// or open paren. That context is what separates a real marker like ". 2.3(2) "
// from an inline cross-reference like "rule 2.18(2)".
const SPLIT_RE =
  /(?<=[.:;”")]\s)(\d+\.\d+\(\d+\)|[a-z]\.|\(\d+\))(?=\s[A-Z“"(])/g;

const RE_L0 = /^(\d+\.\d+\(\d+\))\s+([\s\S]*)$/;
const RE_L1 = /^([a-z]\.)\s+([\s\S]*)$/;
const RE_L2 = /^(\(\d+\))\s+([\s\S]*)$/;
// Run-in catchline: a short Title-style phrase ending in a period, followed by
// the start of the substantive sentence.
const RE_TITLE = /^([A-Z][^.]{0,69})\.\s+(?=[A-Z“"(])/;

function classify(seg: string): Block | null {
  let m = RE_L0.exec(seg);
  let level: 0 | 1 | 2 = 0;
  if (!m) {
    m = RE_L1.exec(seg);
    level = 1;
  }
  if (!m) {
    m = RE_L2.exec(seg);
    level = 2;
  }
  if (!m) return null;
  const marker = m[1];
  let rest = m[2].trim();
  let title = '';
  let solo = false;
  // Catchlines reliably appear on subrules and lettered paragraphs; numbered
  // sub-items are usually substantive sentences or quotations, so skip them.
  if (level !== 2) {
    const tm = RE_TITLE.exec(rest);
    if (tm) {
      title = tm[1] + '.';
      rest = rest.slice(tm[0].length).trim();
    } else if (rest.length <= 80 && rest.endsWith('.') && !/\d/.test(rest)) {
      title = rest;
      rest = '';
      solo = true;
    }
  }
  return { level, marker, title, text: rest, solo };
}

function parseRuleBody(raw: string): ParsedBody {
  let text = raw.trim();
  let history: string | null = null;
  const hm = text.match(/\s*(\[[^\]]*\])\s*$/);
  if (hm) {
    history = hm[1];
    text = text.slice(0, hm.index).trimEnd();
  }

  const cuts = [0];
  let m: RegExpExecArray | null;
  SPLIT_RE.lastIndex = 0;
  while ((m = SPLIT_RE.exec(text))) cuts.push(m.index);

  const segments: string[] = [];
  for (let i = 0; i < cuts.length; i++) {
    const seg = text.slice(cuts[i], cuts[i + 1] ?? text.length).trim();
    if (seg) segments.push(seg);
  }

  const blocks: Block[] = [];
  for (const seg of segments) {
    const b = classify(seg);
    if (b) blocks.push(b);
    else if (blocks.length) {
      // Unmarked continuation — append to the previous block.
      const prev = blocks[blocks.length - 1];
      prev.text = `${prev.text} ${seg}`.trim();
    } else {
      blocks.push({ level: 0, marker: '', title: '', text: seg });
    }
  }

  // A whole-segment catchline is only a heading if a deeper marker follows it
  // (e.g. "c. Oaths administered." → (1)(2)). Otherwise it's just a short list
  // item — render it as body, not a bold heading.
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    if (!b.solo) continue;
    const next = blocks[i + 1];
    if (!next || next.level <= b.level) {
      b.text = b.title;
      b.title = '';
    }
  }

  return { blocks, history };
}

// ---------------------------------------------------------------------------
// Statute structure parser + nested-list renderer
//
// Two upstream shapes feed this:
//
//  • Iowa Code — body_text is newline-delimited with NBSP-padded markers
//    ("1.  …", "a.  …", "(1)  …"). Indentation
//    is NOT meaningful (every line carries the same 2-NBSP lead); the hierarchy
//    lives in the marker shape alone: 1. → a. → (1) → (a). A line may open a
//    child inline ("4.  a.  The director …").
//
//  • Iowa Court Rules — one unbroken string, no newlines/NBSP. parseRuleBody
//    (above) recovers its 2.20(1)/a./(1) structure heuristically; we fold its
//    flat levelled blocks into the same tree so one renderer serves both.
//
// parseStatute() returns { lead, tree, history }. StatuteBody renders a real
// nested <ol> so the document is semantic and screen-readable.
// ---------------------------------------------------------------------------

type StatuteItem = {
  marker: string;
  // Bold run-in catchline (Court Rules only — Iowa Code markers are explicit).
  title: string;
  text: string;
  children: StatuteItem[];
};

type ParsedStatute = { lead: string; tree: StatuteItem[]; history: string[] };

const NBSP_RE = /\u00A0/g;

// Marker → depth. Numeric "1." is the top tier, lowercase "a." next, then
// parenthesised "(1)", then "(a)"/"(A)".
function markerLevel(marker: string): number {
  if (/^\d+\.$/.test(marker)) return 0;
  if (/^[a-z]+\.$/.test(marker)) return 1;
  if (/^\(\d+\)$/.test(marker)) return 2;
  if (/^\([A-Za-z]+\)$/.test(marker)) return 3;
  return 0;
}

// One leading marker at the start of an (NBSP-normalised) line segment.
const LEAD_MARKER_RE = /^(\d+\.|[a-z]+\.|\([0-9A-Za-z]+\))[ \t]+/;

// A trailing line is history/notes when it is the Acts-enactment trail, a
// "See …" cross-reference note, the bracketed codification, the older C/S/R
// codification, or the truncated "eferred to in …" scrape artifact. These
// always sit after the substantive text, contiguous, at the very end.
const HISTORY_LINE_RE =
  /(\bActs?,\s+ch\b|^See\s|eferred to in|^\[.*\]$|^[CSR]\d{2}\b|^C\d{2,4},)/;

// Strip the scrape artifact ("…§16; ; ; ; eferred to in §2.14, …" → "…§16")
// and any now-dangling separators. Mirrors the backend _normalize_body fix so
// already-ingested rows display clean without a re-ingest.
function cleanHistoryLine(line: string): string {
  return line
    .replace(/[\s;]*\b[Rr]?eferred to in\b[^\n]*/g, '')
    .replace(/[;\s]+$/g, '')
    .trim();
}

function blocksToTree(blocks: Block[]): StatuteItem[] {
  const tree: StatuteItem[] = [];
  const stack: { item: StatuteItem; level: number }[] = [];
  for (const b of blocks) {
    const item: StatuteItem = {
      marker: b.marker,
      title: b.title,
      text: b.text,
      children: [],
    };
    while (stack.length && stack[stack.length - 1].level >= b.level)
      stack.pop();
    const parent = stack.length
      ? stack[stack.length - 1].item.children
      : tree;
    parent.push(item);
    stack.push({ item, level: b.level });
  }
  return tree;
}

function parseStatute(raw: string): ParsedStatute {
  const src = (raw ?? '').replace(/\r\n/g, '\n');
  if (!src.trim()) return { lead: '', tree: [], history: [] };

  // Court Rules: no newlines/NBSP — defer to the legacy heuristic, then nest.
  if (!src.includes('\n') && !src.includes("\u00A0")) {
    const { blocks, history } = parseRuleBody(src);
    return {
      lead: '',
      tree: blocksToTree(blocks),
      history: history ? [history] : [],
    };
  }

  // Iowa Code. Normalise NBSP → space, split into lines.
  const lines = src.split('\n').map((l) => l.replace(NBSP_RE, ' ').trim());

  // Peel the trailing history/notes run off the end (blank + history-shaped
  // lines, contiguous, until the first real body line).
  const history: string[] = [];
  let cut = lines.length;
  for (let i = lines.length - 1; i >= 0; i--) {
    const ln = lines[i];
    if (ln === '') {
      cut = i;
      continue;
    }
    if (HISTORY_LINE_RE.test(ln)) {
      const cleaned = cleanHistoryLine(ln);
      if (cleaned) history.unshift(cleaned);
      cut = i;
      continue;
    }
    break;
  }
  const bodyLines = lines.slice(0, cut).filter((l) => l !== '');

  const tree: StatuteItem[] = [];
  const stack: { item: StatuteItem; level: number }[] = [];
  const leadParts: string[] = [];
  let started = false;

  for (const line of bodyLines) {
    // Pull the chain of leading markers off this line ("4. a. The director").
    let rest = line;
    const markers: string[] = [];
    let mm: RegExpMatchArray | null;
    while ((mm = rest.match(LEAD_MARKER_RE))) {
      markers.push(mm[1]);
      rest = rest.slice(mm[0].length);
    }
    if (markers.length === 0) {
      if (!started) leadParts.push(line);
      else if (stack.length) {
        const top = stack[stack.length - 1].item;
        top.text = `${top.text} ${line}`.trim();
      } else leadParts.push(line);
      continue;
    }
    started = true;
    let leaf: StatuteItem | null = null;
    for (const marker of markers) {
      const level = markerLevel(marker);
      while (stack.length && stack[stack.length - 1].level >= level)
        stack.pop();
      const parent = stack.length
        ? stack[stack.length - 1].item.children
        : tree;
      const item: StatuteItem = {
        marker,
        title: '',
        text: '',
        children: [],
      };
      parent.push(item);
      stack.push({ item, level });
      leaf = item;
    }
    if (leaf) leaf.text = rest.trim();
  }

  return { lead: leadParts.join(' ').trim(), tree, history };
}

// ---------------------------------------------------------------------------
// Inline cross-reference links.
//
// The backend resolves every citation in the body to a live node and hands
// back the literal phrases (node.cross_refs). We match on the phrase, not a
// byte offset, because parseStatute reparses the body (NBSP→space, trim,
// line-join) before render — offsets wouldn't survive that, the phrase does.
// ---------------------------------------------------------------------------

type Linkify = (s: string) => React.ReactNode;

const IDENTITY_LINKIFY: Linkify = (s) => s;

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normWs(s: string): string {
  return s.replace(/\s+/g, ' ').trim();
}

function buildCitationMatcher(
  refs: CrossRef[] | undefined,
): { re: RegExp; byText: Map<string, CrossRef> } | null {
  if (!refs || refs.length === 0) return null;
  const byText = new Map<string, CrossRef>();
  for (const r of refs) {
    const key = normWs(r.text);
    if (key && !byText.has(key)) byText.set(key, r);
  }
  if (byText.size === 0) return null;
  // Longest phrase first so "§ 714.16" wins over the bare "714.16"
  // alternative at the same position.
  const phrases = [...byText.keys()].sort((a, b) => b.length - a.length);
  const alt = phrases
    .map((p) => p.split(' ').map(escapeRegExp).join('\\s+'))
    .join('|');
  // group1 = one boundary char (or start) re-emitted as plain text;
  // group2 = the phrase. Trailing guard blocks continuation into a
  // longer token — a word char ("714.16" inside "714.160", "501" inside
  // "501A") or a dotted-path digit ("714.16" inside "714.16.5") — but
  // still allows a sentence-ending period ("…section 22.7."). No
  // lookbehind — keeps older Safari happy.
  const re = new RegExp(`(^|[^\\w.])(${alt})(?!\\w|\\.\\d)`, 'g');
  return { re, byText };
}

function CitationLink({
  pal,
  onClick,
  children,
}: {
  pal: Pal;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Box
      component="a"
      role="link"
      tabIndex={0}
      onClick={(e: React.MouseEvent) => {
        e.preventDefault();
        onClick();
      }}
      onKeyDown={(e: React.KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      sx={{
        color: pal.link,
        textDecoration: 'underline',
        textDecorationThickness: '1px',
        textUnderlineOffset: '2px',
        cursor: 'pointer',
        '&:hover': { textDecorationThickness: '2px' },
      }}
    >
      {children}
    </Box>
  );
}

function makeLinkify(
  matcher: { re: RegExp; byText: Map<string, CrossRef> } | null,
  pal: Pal,
  onCitation: (path: string) => void,
): Linkify {
  if (!matcher) return IDENTITY_LINKIFY;
  const { re, byText } = matcher;
  return (s: string) => {
    if (!s) return s;
    re.lastIndex = 0;
    const out: React.ReactNode[] = [];
    let last = 0;
    let hit = false;
    let m: RegExpExecArray | null;
    while ((m = re.exec(s)) !== null) {
      hit = true;
      const lead = m[1] ?? '';
      const phrase = m[2];
      const ref = byText.get(normWs(phrase));
      out.push(s.slice(last, m.index) + lead);
      if (ref) {
        out.push(
          <CitationLink
            key={m.index}
            pal={pal}
            onClick={() => onCitation(ref.path)}
          >
            {phrase}
          </CitationLink>,
        );
      } else {
        out.push(phrase);
      }
      last = m.index + m[0].length;
      if (re.lastIndex === m.index) re.lastIndex += 1;
    }
    if (!hit) return s;
    out.push(s.slice(last));
    return out;
  };
}

function StatuteItemList({
  pal,
  items,
  depth,
  linkify = IDENTITY_LINKIFY,
}: {
  pal: Pal;
  items: StatuteItem[];
  depth: number;
  linkify?: Linkify;
}) {
  return (
    <Box
      component="ol"
      sx={{
        listStyle: 'none',
        m: 0,
        p: 0,
        // Stair-step each nested level deeper than its parent.
        pl: depth === 0 ? 0 : { xs: 1.5, sm: 2.25 },
      }}
    >
      {items.map((it, i) => (
        <Box
          component="li"
          key={i}
          sx={{
            display: 'grid',
            // Marker sits in a fixed left gutter; body wraps cleanly aligned
            // underneath itself (hanging indent).
            gridTemplateColumns: it.marker
              ? 'minmax(1.9rem, auto) 1fr'
              : '1fr',
            columnGap: it.marker ? 1 : 0,
            // Looser between top-level items, tighter within a hierarchy.
            mt: i === 0 ? 0 : depth === 0 ? 1.6 : 0.65,
          }}
        >
          {it.marker && (
            <Box
              component="span"
              sx={{
                fontVariantNumeric: 'tabular-nums',
                fontWeight: 600,
                color: pal.text,
                whiteSpace: 'nowrap',
              }}
            >
              {it.marker}
            </Box>
          )}
          <Box sx={{ minWidth: 0 }}>
            {(it.title || it.text) && (
              <Typography
                component="p"
                sx={{
                  m: 0,
                  fontSize: 15.5,
                  lineHeight: 1.75,
                  color: pal.body,
                  textAlign: 'left',
                }}
              >
                {it.title && (
                  <Box
                    component="span"
                    sx={{ fontWeight: 700, color: pal.text }}
                  >
                    {linkify(it.title)}
                    {it.text ? ' ' : ''}
                  </Box>
                )}
                {linkify(it.text)}
              </Typography>
            )}
            {it.children.length > 0 && (
              <Box sx={{ mt: 0.65 }}>
                <StatuteItemList
                  pal={pal}
                  items={it.children}
                  depth={depth + 1}
                  linkify={linkify}
                />
              </Box>
            )}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

function StatuteBody({
  pal,
  text,
  crossRefs,
  onCitation,
}: {
  pal: Pal;
  text: string;
  crossRefs?: CrossRef[];
  onCitation?: (path: string) => void;
}) {
  const { lead, tree } = useMemo(() => parseStatute(text), [text]);
  // Rebuild the matcher only when the cross-ref set changes; the click
  // handler is recreated each render (cheap) and closes over the memo.
  const matcher = useMemo(
    () => buildCitationMatcher(crossRefs),
    [crossRefs],
  );
  const linkify = onCitation
    ? makeLinkify(matcher, pal, onCitation)
    : IDENTITY_LINKIFY;

  // No recoverable structure: keep newlines, wrap as a single prose block.
  if (tree.length === 0) {
    return (
      <Typography
        component="div"
        sx={{
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          fontSize: 15.5,
          lineHeight: 1.75,
          color: pal.body,
          textAlign: 'left',
        }}
      >
        {linkify(lead || text)}
      </Typography>
    );
  }

  return (
    <Box>
      {lead && (
        <Typography
          component="p"
          sx={{
            m: 0,
            mb: 2,
            fontSize: 15.5,
            lineHeight: 1.75,
            color: pal.body,
            textAlign: 'left',
          }}
        >
          {linkify(lead)}
        </Typography>
      )}
      <StatuteItemList
        pal={pal}
        items={tree}
        depth={0}
        linkify={linkify}
      />
    </Box>
  );
}

function SectionBlock({
  pal,
  actions,
  node,
  onCitation,
}: {
  pal: Pal;
  actions: ActionHandlers;
  node: NodeDetail;
  onCitation: (sourceSlug: string, path: string) => void;
}) {
  // Two history trails: the Acts-enactment + "See …" notes that trail the
  // body text (parsed + de-artifacted here), and the older bracketed
  // codification the API exposes via node.history (source_metadata). Show
  // enactment first; the terser codification is grouped under it, italicised.
  const bodyHistory = useMemo(
    () => parseStatute(node.body_text).history,
    [node.body_text],
  );
  const history = [...bodyHistory, ...node.history];
  // A long heading reads heavy in all-caps — keep the source's natural mixed
  // case for those, reserve uppercase for short ones.
  const upperHeading = node.heading.length <= 46;
  return (
    <Box sx={{ mb: 5 }}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 2,
          mb: 2,
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            sx={{
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              color: pal.muted,
            }}
          >
            {node.citation}
          </Typography>
          <Typography
            sx={{
              fontSize: { xs: 18, md: 21 },
              fontWeight: 700,
              lineHeight: 1.3,
              mt: 0.25,
              color: pal.text,
              textTransform: upperHeading ? 'uppercase' : 'none',
            }}
          >
            {node.heading}
          </Typography>
        </Box>
        <Box sx={{ display: { xs: 'none', sm: 'flex' }, gap: 0.5, pt: 0.25 }}>
          {QUICK_ACTIONS.map((a) => {
            const isBookmark = a.key === 'bookmark';
            const onClick =
              a.key === 'share'
                ? actions.onShare
                : a.key === 'download'
                  ? actions.onDownload
                  : a.key === 'print'
                    ? actions.onPrint
                    : undefined;
            const title = isBookmark
              ? 'Bookmark — not available in preview'
              : a.label;
            return (
              <Tooltip key={a.key} title={title}>
                <Box component="span">
                  <IconButton
                    size="small"
                    disabled={isBookmark}
                    onClick={onClick}
                    aria-label={a.label}
                    sx={{
                      width: 26,
                      height: 26,
                      border: `1px solid ${pal.circleBorder}`,
                      '& svg': { fontSize: 14, color: pal.circleIcon },
                    }}
                  >
                    {a.icon}
                  </IconButton>
                </Box>
              </Tooltip>
            );
          })}
        </Box>
      </Box>

      {node.effective_from && (
        <Typography sx={{ fontSize: 12, color: pal.muted, mb: 1.5 }}>
          Effective {node.effective_from}
          {node.division ? ` · ${node.division}` : ''}
        </Typography>
      )}

      {node.body_text ? (
        <StatuteBody
          pal={pal}
          text={node.body_text}
          crossRefs={node.cross_refs}
          onCitation={(path) => onCitation(node.source_slug, path)}
        />
      ) : (
        <Alert severity="info" sx={{ my: 1 }}>
          No extractable text for this provision.{' '}
          {node.official_url && (
            <Box
              component="a"
              href={node.official_url}
              target="_blank"
              rel="noopener"
              sx={{ color: pal.link }}
            >
              See the official source.
            </Box>
          )}
        </Alert>
      )}

      {history.length > 0 && (
        <Box
          sx={{
            mt: 4,
            pt: 2,
            borderTop: `1px solid ${pal.border}`,
          }}
        >
          <Typography
            sx={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.09em',
              textTransform: 'uppercase',
              color: pal.muted,
              mb: 0.75,
            }}
          >
            History
          </Typography>
          {history.map((h, i) => (
            <Typography
              key={i}
              sx={{
                fontSize: 13,
                lineHeight: 1.6,
                color: pal.muted,
                // The bracketed codification trail (after the body-derived
                // entries) is the older, terser line — italicise it and group
                // it tight under the enactment history.
                fontStyle: i >= bodyHistory.length ? 'italic' : 'normal',
                mt: i === 0 ? 0 : i === bodyHistory.length ? 0.75 : 0.4,
                textAlign: 'left',
              }}
            >
              {h}
            </Typography>
          ))}
        </Box>
      )}

      {node.official_url && node.body_text && (
        <Box sx={{ mt: 2.5 }}>
          <Box
            component="a"
            href={node.official_url}
            target="_blank"
            rel="noopener"
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 0.5,
              fontSize: 12,
              color: pal.link,
            }}
          >
            Official source
            <OpenInNewRoundedIcon sx={{ fontSize: 13 }} />
          </Box>
        </Box>
      )}
    </Box>
  );
}

function DisclaimerFooter({ pal }: { pal: Pal }) {
  return (
    <Box
      sx={{
        mt: 6,
        pt: 3,
        pb: 5,
        borderTop: `1px solid ${pal.border}`,
        color: pal.muted,
        fontSize: 10.5,
        lineHeight: 1.6,
      }}
    >
      <Typography sx={{ fontSize: 'inherit', mb: 1 }}>
        <Box component="span" sx={{ fontWeight: 700 }}>
          Disclaimer:
        </Box>{' '}
        This text is provided for convenience and reference only. It reflects
        the currently effective, reviewed version held in the Iowa Legal Corpus
        and is not a substitute for the official publication. Always verify
        against the official source before relying on any provision.
      </Typography>
      <Typography sx={{ fontSize: 'inherit' }}>
        Hosted by: Iowa Legal Corpus — sourced from legis.iowa.gov.
      </Typography>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Search results pane (takes over the reading column while a query is active)
// ---------------------------------------------------------------------------

function ScopeChip({
  pal,
  label,
  active,
  onClick,
}: {
  pal: Pal;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Box
      component="button"
      onClick={onClick}
      sx={{
        all: 'unset',
        cursor: 'pointer',
        px: 1.25,
        py: 0.4,
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        bgcolor: active ? pal.chrome : 'transparent',
        color: active ? pal.chromeText : pal.muted,
        border: `1px solid ${active ? pal.chrome : pal.border}`,
        '&:hover': { borderColor: pal.chrome },
      }}
    >
      {label}
    </Box>
  );
}

function SearchResultsPane({
  pal,
  query,
  loading,
  error,
  data,
  scope,
  scopeSource,
  onPick,
  onSetScope,
  onClose,
}: {
  pal: Pal;
  query: string;
  loading: boolean;
  error: string | null;
  data: BrowseSearchResponse | null;
  scope: string | null;
  scopeSource: BrowseSource | null;
  onPick: (nodeId: number) => void;
  onSetScope: (slug: string | null) => void;
  onClose: () => void;
}) {
  const results = data?.results ?? [];
  return (
    <Box sx={{ maxWidth: 880, mx: 'auto', px: { xs: 3, md: 8 }, py: 4 }}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 2,
          flexWrap: 'wrap',
        }}
      >
        <Typography sx={{ fontSize: 20, fontWeight: 700, color: pal.text }}>
          Search
        </Typography>
        <Box
          component="button"
          onClick={onClose}
          sx={{
            all: 'unset',
            cursor: 'pointer',
            fontSize: 13,
            color: pal.link,
            textDecoration: 'underline',
            '&:hover': { opacity: 0.8 },
          }}
        >
          Back to reading
        </Box>
      </Box>

      <Typography sx={{ fontSize: 14, color: pal.muted, mt: 0.5 }}>
        {loading
          ? `Searching for “${query}”…`
          : error
            ? 'Search failed.'
            : `${data?.count ?? 0} result${
                (data?.count ?? 0) === 1 ? '' : 's'
              } for “${query}”`}
      </Typography>

      {scopeSource && (
        <Box sx={{ display: 'flex', gap: 1, mt: 2, alignItems: 'center' }}>
          <Typography sx={{ fontSize: 12, color: pal.muted }}>
            Scope:
          </Typography>
          <ScopeChip
            pal={pal}
            label="All sources"
            active={scope == null}
            onClick={() => scope != null && onSetScope(null)}
          />
          <ScopeChip
            pal={pal}
            label={scopeSource.abbreviation}
            active={scope === scopeSource.slug}
            onClick={() =>
              scope !== scopeSource.slug && onSetScope(scopeSource.slug)
            }
          />
        </Box>
      )}

      {loading ? (
        <Centered>
          <CircularProgress />
        </Centered>
      ) : error ? (
        <Alert severity="error" sx={{ mt: 3 }}>
          {error}
        </Alert>
      ) : results.length === 0 ? (
        <Typography sx={{ mt: 4, color: pal.muted, fontSize: 14 }}>
          No matching provisions. Try different keywords, or an exact citation
          such as <em>714.16</em> or <em>32:1.10</em>.
        </Typography>
      ) : (
        <Box sx={{ mt: 3, display: 'flex', flexDirection: 'column' }}>
          {results.map((r) => (
            <SearchResultRow
              key={r.node_id}
              pal={pal}
              r={r}
              onClick={() => onPick(r.node_id)}
            />
          ))}
        </Box>
      )}
    </Box>
  );
}

function SearchResultRow({
  pal,
  r,
  onClick,
}: {
  pal: Pal;
  r: BrowseSearchResult;
  onClick: () => void;
}) {
  const context = [
    r.source,
    r.chapter ? `Ch. ${r.chapter.ordinal} — ${r.chapter.heading}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <Box
      component="button"
      onClick={onClick}
      sx={{
        all: 'unset',
        cursor: 'pointer',
        display: 'block',
        py: 2,
        borderTop: `1px solid ${pal.border}`,
        '&:hover .cite': { opacity: 0.7 },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
        <Typography
          className="cite"
          component="span"
          sx={{
            fontSize: 15,
            fontWeight: 700,
            color: pal.link,
            textDecoration: 'underline',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {r.citation}
        </Typography>
        {r.exact && (
          <Box
            component="span"
            sx={{
              fontSize: 10.5,
              fontWeight: 700,
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              px: 0.75,
              py: 0.2,
              borderRadius: 999,
              bgcolor: pal.chrome,
              color: pal.chromeText,
            }}
          >
            Exact match
          </Box>
        )}
      </Box>
      <Typography
        sx={{ fontSize: 14.5, fontWeight: 600, color: pal.text, mt: 0.25 }}
      >
        {r.heading}
      </Typography>
      <Typography sx={{ fontSize: 12, color: pal.muted, mt: 0.25 }}>
        {context}
      </Typography>
      {r.snippet && (
        <Typography
          sx={{
            fontSize: 13.5,
            color: pal.body,
            mt: 0.75,
            lineHeight: 1.6,
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {r.snippet}
        </Typography>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Pinned bottom nav
// ---------------------------------------------------------------------------

function PinnedBottomNav({
  pal,
  tocOpen,
  onBack,
  onPrev,
  onNext,
  prevLabel,
  nextLabel,
}: {
  pal: Pal;
  tocOpen: boolean;
  onBack: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  prevLabel?: string;
  nextLabel?: string;
}) {
  const linkSx = (enabled: boolean) => ({
    all: 'unset' as const,
    display: 'flex',
    alignItems: 'center',
    gap: 0.5,
    cursor: enabled ? 'pointer' : 'default',
    color: pal.chromeText,
    fontSize: 13,
    textDecoration: 'underline',
    opacity: enabled ? 1 : 0.4,
    '&:hover': { opacity: enabled ? 0.8 : 0.4 },
  });
  return (
    <Box
      sx={{
        bgcolor: pal.bottomBar,
        color: pal.chromeText,
        height: 44,
        display: 'flex',
        alignItems: 'stretch',
      }}
    >
      <Box
        sx={{
          width: tocOpen ? { xs: 'auto', sm: 310 } : 'auto',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          px: 2,
          borderRight: `1px solid rgba(255,255,255,0.12)`,
        }}
      >
        <Box component="button" onClick={onBack} sx={linkSx(true)}>
          <ArrowBackRoundedIcon sx={{ fontSize: 16 }} />
          Back to chat
        </Box>
      </Box>
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 2,
          gap: 2,
          minWidth: 0,
        }}
      >
        <Box
          component="button"
          onClick={onPrev}
          disabled={!onPrev}
          sx={linkSx(!!onPrev)}
        >
          <ChevronLeftRoundedIcon sx={{ fontSize: 18 }} />
          <Box
            component="span"
            sx={{
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              maxWidth: { xs: 110, sm: 280 },
            }}
          >
            {prevLabel ? `Prev · ${prevLabel}` : 'Previous'}
          </Box>
        </Box>
        <Box
          component="button"
          onClick={onNext}
          disabled={!onNext}
          sx={linkSx(!!onNext)}
        >
          <Box
            component="span"
            sx={{
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              maxWidth: { xs: 110, sm: 280 },
            }}
          >
            {nextLabel ? `Next · ${nextLabel}` : 'Next'}
          </Box>
          <ChevronRightRoundedIcon sx={{ fontSize: 18 }} />
        </Box>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------

function Centered({
  children,
  small,
}: {
  children: React.ReactNode;
  small?: boolean;
}) {
  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'center',
        py: small ? 2 : 6,
      }}
    >
      {children}
    </Box>
  );
}
