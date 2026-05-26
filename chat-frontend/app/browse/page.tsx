"use client";

// Corpus browser. Three-pane shell on top of /api/browse: sources tree on
// the left, section reader in the middle, metadata sidecar on the right.
// State is centralised here so deep-links (#/iowa-code/714.16) can drive
// expansion + selection programmatically.

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  AlertCircleIcon,
  BookOpenIcon,
  CheckIcon,
  ChevronRightIcon,
  CircleEllipsisIcon,
  Download,
  ExternalLinkIcon,
  Loader2Icon,
  Printer,
  SearchIcon,
  Share2,
  XIcon,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  browseChapter,
  browseChapters,
  browseNode,
  browseResolve,
  browseSearch,
  browseSources,
  fmtEffective,
  type BrowseChapter,
  type BrowseSearchResponse,
  type BrowseSearchResult,
  type BrowseSource,
  type ChapterDetail,
  type NodeDetail,
} from "@/lib/iowa-browse";
import { AppSidebarFooter } from "@/components/app-sidebar-footer";
import { AppSidebarNav } from "@/components/app-sidebar-nav";

type Selection = {
  slug?: string;
  chapterId?: number;
  sectionId?: number;
};

// Stable composite keys for the expanded/busy sets so source ids and node
// ids can't collide.
const srcKey = (slug: string) => `src:${slug}`;
const chapKey = (id: number) => `chap:${id}`;

// Parse the hash fragment "#/iowa-code/714.16" into {slug, cite}. Returns
// null for shapes the resolver doesn't understand.
function parseHashTarget(): { slug: string; cite: string } | null {
  if (typeof window === "undefined") return null;
  const raw = window.location.hash.replace(/^#\/?/, "").split("?")[0];
  const parts = raw.split("/").filter(Boolean);
  if (parts.length < 2) return null;
  return {
    slug: parts[0],
    cite: decodeURIComponent(parts.slice(1).join("/")),
  };
}

export default function BrowsePage() {
  // ---- data caches -------------------------------------------------------
  const [sources, setSources] = useState<BrowseSource[] | null>(null);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [chapters, setChapters] = useState<Record<string, BrowseChapter[]>>({});
  const [chapterDetails, setChapterDetails] = useState<
    Record<number, ChapterDetail>
  >({});
  const [nodes, setNodes] = useState<Record<number, NodeDetail>>({});

  // ---- UI state ----------------------------------------------------------
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [sel, setSel] = useState<Selection>({});
  const [readerError, setReaderError] = useState<string | null>(null);

  // ---- search state -----------------------------------------------------
  const [searchInput, setSearchInput] = useState("");
  const [searchActive, setSearchActive] = useState(false);
  const [searchResults, setSearchResults] = useState<
    BrowseSearchResponse | null
  >(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  // null = all sources. Initialised lazily to the active reading source so
  // an in-context search defaults to "stay in this corpus".
  const [searchScope, setSearchScope] = useState<string | null>(null);

  // ---- helpers -----------------------------------------------------------
  const setBusyKey = useCallback((key: string, on: boolean) => {
    setBusy((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  const toggleExpanded = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const loadChapters = useCallback(
    async (slug: string): Promise<BrowseChapter[] | null> => {
      if (chapters[slug]) return chapters[slug];
      const key = srcKey(slug);
      setBusyKey(key, true);
      try {
        const data = await browseChapters(slug);
        setChapters((p) => ({ ...p, [slug]: data.chapters }));
        return data.chapters;
      } catch (e) {
        console.error("browseChapters failed", e);
        return null;
      } finally {
        setBusyKey(key, false);
      }
    },
    [chapters, setBusyKey],
  );

  const loadChapterDetail = useCallback(
    async (chapterId: number): Promise<ChapterDetail | null> => {
      if (chapterDetails[chapterId]) return chapterDetails[chapterId];
      const key = chapKey(chapterId);
      setBusyKey(key, true);
      try {
        const data = await browseChapter(chapterId);
        setChapterDetails((p) => ({ ...p, [chapterId]: data }));
        return data;
      } catch (e) {
        console.error("browseChapter failed", e);
        return null;
      } finally {
        setBusyKey(key, false);
      }
    },
    [chapterDetails, setBusyKey],
  );

  const loadNode = useCallback(
    async (nodeId: number): Promise<NodeDetail | null> => {
      if (nodes[nodeId]) return nodes[nodeId];
      try {
        const data = await browseNode(nodeId);
        setNodes((p) => ({ ...p, [nodeId]: data }));
        return data;
      } catch (e) {
        console.error("browseNode failed", e);
        setReaderError(
          e instanceof Error ? e.message : "Failed to load this section.",
        );
        return null;
      }
    },
    [nodes],
  );

  // ---- mount: load sources + resolve any incoming citation ---------------
  useEffect(() => {
    let cancelled = false;
    browseSources()
      .then((s) => !cancelled && setSources(s))
      .catch((e) => {
        if (cancelled) return;
        setSourcesError(
          e instanceof Error ? e.message : "Failed to load corpus sources.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Resolve hash deep-links once sources have loaded. Runs again whenever
  // the hash changes (back/forward navigation).
  useEffect(() => {
    if (!sources) return;

    const resolveFromHash = async () => {
      const target = parseHashTarget();
      if (!target) return;
      if (!sources.some((s) => s.slug === target.slug)) return;

      let resolved;
      try {
        resolved = await browseResolve(target.slug, target.cite);
      } catch (e) {
        console.error("browseResolve failed", e);
        return;
      }
      if (!resolved.found) return;

      // Open the source, then the chapter, then select the node.
      setExpanded((p) => new Set(p).add(srcKey(target.slug)));
      const chaps = await loadChapters(target.slug);
      if (!chaps) return;

      // If the resolved id IS a chapter, just stop there.
      if (resolved.is_chapter) {
        setSel({ slug: target.slug, chapterId: resolved.node_id });
        return;
      }

      // Otherwise it's a section: figure out which chapter it lives under
      // by walking the chapter list and loading details until we find it.
      // The resolve endpoint doesn't return the chapter id directly, but
      // the node's payload will.
      const node = await loadNode(resolved.node_id);
      if (!node) return;
      const chapId = node.chapter?.id;
      if (chapId) {
        setExpanded((p) => new Set(p).add(chapKey(chapId)));
        await loadChapterDetail(chapId);
        setSel({ slug: target.slug, chapterId: chapId, sectionId: node.id });
      } else {
        setSel({ slug: target.slug, sectionId: node.id });
      }
    };

    void resolveFromHash();
    const onHash = () => void resolveFromHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [sources, loadChapters, loadChapterDetail, loadNode]);

  // ---- user actions ------------------------------------------------------
  const onToggleSource = useCallback(
    (slug: string) => {
      const key = srcKey(slug);
      if (!expanded.has(key)) {
        toggleExpanded(key);
        void loadChapters(slug);
      } else {
        toggleExpanded(key);
      }
    },
    [expanded, loadChapters, toggleExpanded],
  );

  const onToggleChapter = useCallback(
    (chapterId: number) => {
      const key = chapKey(chapterId);
      if (!expanded.has(key)) {
        toggleExpanded(key);
        void loadChapterDetail(chapterId);
      } else {
        toggleExpanded(key);
      }
    },
    [expanded, loadChapterDetail, toggleExpanded],
  );

  const onSelectChapter = useCallback(
    (slug: string, chapterId: number) => {
      setReaderError(null);
      setSel({ slug, chapterId });
      void loadChapterDetail(chapterId);
    },
    [loadChapterDetail],
  );

  const onSelectSection = useCallback(
    (slug: string, chapterId: number | undefined, sectionId: number) => {
      setReaderError(null);
      setSel({ slug, chapterId, sectionId });
      void loadNode(sectionId);
    },
    [loadNode],
  );

  // ---- search actions ---------------------------------------------------
  const runSearch = useCallback(
    async (query: string, scope: string | null) => {
      const q = query.trim();
      if (!q) return;
      setSearchActive(true);
      setSearching(true);
      setSearchError(null);
      setSearchScope(scope);
      try {
        const data = await browseSearch(q, scope);
        setSearchResults(data);
      } catch (e) {
        setSearchError(
          e instanceof Error ? e.message : "Search failed.",
        );
        setSearchResults(null);
      } finally {
        setSearching(false);
      }
    },
    [],
  );

  const closeSearch = useCallback(() => {
    setSearchActive(false);
    setSearchResults(null);
    setSearchError(null);
    setSearchInput("");
  }, []);

  // Result click: open the node in the reader and dismiss the search pane.
  // The tree gets opened to that node so the sidebar reflects the new state.
  const onPickSearchResult = useCallback(
    async (r: BrowseSearchResult) => {
      const slug = r.source_slug;
      setExpanded((p) => new Set(p).add(srcKey(slug)));
      await loadChapters(slug);

      // The search response doesn't carry the chapter id directly; the node
      // payload does. Fetch it, then mirror the deep-link open logic.
      const node = await loadNode(r.node_id);
      if (!node) {
        // Even without metadata, surface the node by id so the user sees
        // _something_ — the reader will still render the body.
        setSel({ slug, sectionId: r.node_id });
        closeSearch();
        return;
      }
      const chapId = node.chapter?.id;
      if (chapId) {
        setExpanded((p) => new Set(p).add(chapKey(chapId)));
        await loadChapterDetail(chapId);
        setSel({ slug, chapterId: chapId, sectionId: node.id });
      } else {
        setSel({ slug, sectionId: node.id });
      }
      closeSearch();
    },
    [closeSearch, loadChapterDetail, loadChapters, loadNode],
  );

  // ---- side effects -----------------------------------------------------
  // When the active section changes (deep-link, search pick, related-rules
  // click), scroll its sidebar row into view. Use a small timeout so the
  // tree's expand-and-mount has time to land the new row in the DOM. The
  // SectionLink renders a stable data-section-id attribute we can target.
  useEffect(() => {
    if (!sel.sectionId) return;
    const id = sel.sectionId;
    const tick = window.setTimeout(() => {
      const el = document.querySelector<HTMLElement>(
        `[data-section-id="${id}"]`,
      );
      el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }, 120);
    return () => window.clearTimeout(tick);
  }, [sel.sectionId, chapterDetails]);

  // ---- derived -----------------------------------------------------------
  const selSource = useMemo(
    () => sources?.find((s) => s.slug === sel.slug) ?? null,
    [sources, sel.slug],
  );
  const selChapter = useMemo(
    () => (sel.chapterId ? (chapterDetails[sel.chapterId] ?? null) : null),
    [chapterDetails, sel.chapterId],
  );
  const selNode = useMemo(
    () => (sel.sectionId ? (nodes[sel.sectionId] ?? null) : null),
    [nodes, sel.sectionId],
  );

  return (
    <SidebarProvider>
      <div className="flex h-dvh w-full pr-0.5">
        <BrowseSidebar
          sources={sources}
          sourcesError={sourcesError}
          chapters={chapters}
          chapterDetails={chapterDetails}
          expanded={expanded}
          busy={busy}
          sel={sel}
          onToggleSource={onToggleSource}
          onToggleChapter={onToggleChapter}
          onSelectChapter={onSelectChapter}
          onSelectSection={onSelectSection}
        />
        <SidebarInset>
          <BrowseHeader
            source={selSource}
            chapter={selChapter}
            node={selNode}
            searchActive={searchActive}
            searchInput={searchInput}
            onSearchInput={setSearchInput}
            onSubmit={() => runSearch(searchInput, sel.slug ?? null)}
            onClose={closeSearch}
          />
          {searchActive ? (
            <SearchResultsPane
              query={searchResults?.query ?? searchInput}
              loading={searching}
              error={searchError}
              data={searchResults}
              scope={searchScope}
              scopeSource={selSource}
              onSetScope={(slug) =>
                runSearch(searchResults?.query ?? searchInput, slug)
              }
              onPick={onPickSearchResult}
              onClose={closeSearch}
            />
          ) : (
            <ReadingPane
              sel={sel}
              source={selSource}
              chapter={selChapter}
              node={selNode}
              busyChapter={
                sel.chapterId != null && busy.has(chapKey(sel.chapterId))
              }
              error={readerError}
              onSelectSection={(id) =>
                onSelectSection(sel.slug!, sel.chapterId, id)
              }
            />
          )}
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}

// ---------------------------------------------------------------------------
// Top header — breadcrumb + search
// ---------------------------------------------------------------------------

function BrowseHeader({
  source,
  chapter,
  node,
  searchActive,
  searchInput,
  onSearchInput,
  onSubmit,
  onClose,
}: {
  source: BrowseSource | null;
  chapter: ChapterDetail | null;
  node: NodeDetail | null;
  searchActive: boolean;
  searchInput: string;
  onSearchInput: (s: string) => void;
  onSubmit: () => void;
  onClose: () => void;
}) {
  return (
    <header className="flex h-16 shrink-0 items-center gap-3 border-b px-4">
      <SidebarTrigger />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList>
          {source ? (
            <>
              <BreadcrumbItem className="hidden md:block">
                <BreadcrumbLink href="#">{source.name}</BreadcrumbLink>
              </BreadcrumbItem>
              {chapter && (
                <>
                  <BreadcrumbSeparator className="hidden md:block" />
                  <BreadcrumbItem className="hidden lg:block">
                    <BreadcrumbLink href="#">
                      {chapter.ordinal}
                      {chapter.heading ? ` — ${chapter.heading}` : ""}
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                </>
              )}
              {node && (
                <>
                  <BreadcrumbSeparator className="hidden lg:block" />
                  <BreadcrumbItem>
                    <BreadcrumbPage>{node.citation}</BreadcrumbPage>
                  </BreadcrumbItem>
                </>
              )}
              {!chapter && !node && (
                <>
                  <BreadcrumbSeparator className="hidden md:block" />
                  <BreadcrumbItem>
                    <BreadcrumbPage>All chapters</BreadcrumbPage>
                  </BreadcrumbItem>
                </>
              )}
            </>
          ) : (
            <BreadcrumbItem>
              <BreadcrumbPage>Browse the corpus</BreadcrumbPage>
            </BreadcrumbItem>
          )}
        </BreadcrumbList>
      </Breadcrumb>

      <form
        className="relative w-full max-w-sm"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <SearchIcon className="-translate-y-1/2 absolute top-1/2 left-3 size-4 text-muted-foreground" />
        <Input
          value={searchInput}
          onChange={(e) => onSearchInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape" && searchActive) {
              e.preventDefault();
              onClose();
            }
          }}
          placeholder={
            source
              ? `Search ${source.name}…`
              : "Search the corpus…"
          }
          className="h-9 pl-9 pr-9"
        />
        {(searchInput || searchActive) && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Clear search"
            className="-translate-y-1/2 absolute top-1/2 right-2 flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <XIcon className="size-3.5" />
          </button>
        )}
      </form>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Sidebar tree
// ---------------------------------------------------------------------------

type SidebarProps = {
  sources: BrowseSource[] | null;
  sourcesError: string | null;
  chapters: Record<string, BrowseChapter[]>;
  chapterDetails: Record<number, ChapterDetail>;
  expanded: Set<string>;
  busy: Set<string>;
  sel: Selection;
  onToggleSource: (slug: string) => void;
  onToggleChapter: (chapterId: number) => void;
  onSelectChapter: (slug: string, chapterId: number) => void;
  onSelectSection: (
    slug: string,
    chapterId: number | undefined,
    sectionId: number,
  ) => void;
};

function BrowseSidebar(props: SidebarProps) {
  return (
    <Sidebar>
      <SidebarHeader className="mb-2 border-b">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link href="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  <BookOpenIcon className="size-4" />
                </div>
                <div className="me-6 flex flex-col gap-0.5 leading-none">
                  <span className="font-semibold">Hudson Legal Tech</span>
                  <span className="text-sidebar-foreground/60 text-xs">
                    Browse the corpus
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent className="px-2">
        <AppSidebarNav />
        <SidebarGroup>
          <SidebarGroupLabel>Sources</SidebarGroupLabel>
          <SidebarMenu>
            {props.sourcesError ? (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-2 text-destructive text-xs">
                <AlertCircleIcon className="mt-0.5 size-3.5 shrink-0" />
                <span>{props.sourcesError}</span>
              </div>
            ) : !props.sources ? (
              <div className="flex items-center gap-2 px-2 py-3 text-sidebar-foreground/60 text-xs">
                <Loader2Icon className="size-3.5 animate-spin" />
                <span>Loading sources…</span>
              </div>
            ) : (
              props.sources.map((src) => (
                <SourceBranch key={src.slug} src={src} {...props} />
              ))
            )}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarRail />

      <SidebarFooter className="border-t">
        <AppSidebarFooter />
      </SidebarFooter>
    </Sidebar>
  );
}

function SourceBranch({
  src,
  chapters,
  chapterDetails,
  expanded,
  busy,
  sel,
  onToggleSource,
  onToggleChapter,
  onSelectChapter,
  onSelectSection,
}: { src: BrowseSource } & SidebarProps) {
  const key = srcKey(src.slug);
  const isOpen = expanded.has(key);
  const isLoading = busy.has(key) && !chapters[src.slug];
  const list = chapters[src.slug];
  const isActive = sel.slug === src.slug;
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        onClick={() => onToggleSource(src.slug)}
        isActive={isActive}
        className="font-semibold"
      >
        <ChevronRightIcon
          className={`size-3.5 transition-transform ${isOpen ? "rotate-90" : ""}`}
        />
        <span className="flex-1 truncate">{src.name}</span>
        <span className="ml-1 text-sidebar-foreground/50 text-xs">
          {src.chapters}
        </span>
      </SidebarMenuButton>
      {isOpen && (
        <div className="ml-3 mt-0.5 border-sidebar-border/60 border-l pl-2">
          {isLoading && (
            <div className="flex items-center gap-2 px-2 py-1.5 text-sidebar-foreground/60 text-xs">
              <Loader2Icon className="size-3.5 animate-spin" /> Loading…
            </div>
          )}
          {list?.map((ch) => (
            <ChapterBranch
              key={ch.id}
              src={src}
              chapter={ch}
              detail={chapterDetails[ch.id]}
              isOpen={expanded.has(chapKey(ch.id))}
              isLoading={busy.has(chapKey(ch.id)) && !chapterDetails[ch.id]}
              sel={sel}
              onToggleChapter={onToggleChapter}
              onSelectChapter={onSelectChapter}
              onSelectSection={onSelectSection}
            />
          ))}
        </div>
      )}
    </SidebarMenuItem>
  );
}

function ChapterBranch({
  src,
  chapter,
  detail,
  isOpen,
  isLoading,
  sel,
  onToggleChapter,
  onSelectChapter,
  onSelectSection,
}: {
  src: BrowseSource;
  chapter: BrowseChapter;
  detail: ChapterDetail | undefined;
  isOpen: boolean;
  isLoading: boolean;
  sel: Selection;
  onToggleChapter: (chapterId: number) => void;
  onSelectChapter: (slug: string, chapterId: number) => void;
  onSelectSection: (
    slug: string,
    chapterId: number | undefined,
    sectionId: number,
  ) => void;
}) {
  const isActive = sel.chapterId === chapter.id && !sel.sectionId;
  const hasChildren = !chapter.reserved && chapter.child_count > 0;
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        isActive={isActive}
        className="h-auto items-start py-1.5"
        onClick={() => {
          if (hasChildren) onToggleChapter(chapter.id);
          onSelectChapter(src.slug, chapter.id);
        }}
      >
        <ChevronRightIcon
          className={`mt-0.5 size-3.5 shrink-0 transition-transform ${
            isOpen ? "rotate-90" : ""
          } ${hasChildren ? "" : "invisible"}`}
        />
        <div className="flex min-w-0 flex-col">
          <span className="text-sm">
            <span className="font-semibold">{chapter.ordinal}</span>
            {chapter.heading && (
              <span
                className={chapter.reserved ? "text-sidebar-foreground/40" : ""}
              >
                {" — "}
                {chapter.heading}
              </span>
            )}
          </span>
        </div>
      </SidebarMenuButton>
      {isOpen && hasChildren && (
        <div className="ml-3 mt-0.5 border-sidebar-border/60 border-l pl-2">
          {isLoading && (
            <div className="flex items-center gap-2 px-2 py-1.5 text-sidebar-foreground/60 text-xs">
              <Loader2Icon className="size-3.5 animate-spin" /> Loading…
            </div>
          )}
          {detail?.children.map((c) => (
            <SectionLink
              key={c.id}
              src={src}
              chapterId={chapter.id}
              child={c}
              isActive={sel.sectionId === c.id}
              onSelectSection={onSelectSection}
            />
          ))}
        </div>
      )}
    </SidebarMenuItem>
  );
}

function SectionLink({
  src,
  chapterId,
  child,
  isActive,
  onSelectSection,
}: {
  src: BrowseSource;
  chapterId: number;
  child: { id: number; citation: string; heading: string };
  isActive: boolean;
  onSelectSection: (
    slug: string,
    chapterId: number | undefined,
    sectionId: number,
  ) => void;
}) {
  return (
    <SidebarMenuItem
      data-section-id={child.id}
      data-active={isActive ? "true" : undefined}
    >
      <SidebarMenuButton
        isActive={isActive}
        className="h-auto items-start py-1.5"
        onClick={() => onSelectSection(src.slug, chapterId, child.id)}
      >
        <div className="flex min-w-0 flex-col">
          <span className="font-medium text-sm">{child.citation}</span>
          {child.heading && (
            <span className="truncate text-sidebar-foreground/70 text-xs">
              {child.heading}
            </span>
          )}
        </div>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

// ---------------------------------------------------------------------------
// Reading pane + sidecar
// ---------------------------------------------------------------------------

function ReadingPane({
  sel,
  source,
  chapter,
  node,
  busyChapter,
  error,
  onSelectSection,
}: {
  sel: Selection;
  source: BrowseSource | null;
  chapter: ChapterDetail | null;
  node: NodeDetail | null;
  busyChapter: boolean;
  error: string | null;
  onSelectSection: (id: number) => void;
}) {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[1fr_280px]">
      <main className="min-w-0 overflow-y-auto px-6 py-8 md:px-10 lg:px-16">
        <div className="mx-auto max-w-3xl">
          {error && (
            <div className="mb-6 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm">
              <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {!sel.slug ? (
            <EmptyState />
          ) : sel.sectionId ? (
            node ? (
              <NodeView node={node} />
            ) : (
              <LoadingBlock label="Loading section…" />
            )
          ) : sel.chapterId ? (
            chapter ? (
              <ChapterView
                chapter={chapter}
                onSelectSection={onSelectSection}
              />
            ) : (
              <LoadingBlock
                label={busyChapter ? "Loading chapter…" : "Select a section"}
              />
            )
          ) : (
            <SourceView source={source} />
          )}
        </div>
      </main>

      <Sidecar source={source} chapter={chapter} node={node} />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-2xl border border-dashed bg-muted/30 px-6 py-16 text-center">
      <BookOpenIcon className="mx-auto size-8 text-muted-foreground/70" />
      <h2 className="mt-4 font-semibold text-lg">Pick a source to start</h2>
      <p className="mt-1 text-muted-foreground text-sm">
        Expand a corpus in the left sidebar to browse its chapters and
        sections.
      </p>
    </div>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-dashed bg-muted/30 px-4 py-10 text-muted-foreground text-sm">
      <Loader2Icon className="size-4 animate-spin" />
      <span>{label}</span>
    </div>
  );
}

function SourceView({ source }: { source: BrowseSource | null }) {
  if (!source) return <LoadingBlock label="Loading source…" />;
  return (
    <div>
      <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-wide">
        <span>{source.jurisdiction}</span>
      </div>
      <h1 className="mt-2 font-semibold text-3xl tracking-tight">
        {source.name}
      </h1>
      <p className="mt-2 text-muted-foreground text-sm">
        {source.chapters.toLocaleString()} chapters ·{" "}
        {source.entries.toLocaleString()} {source.entry_label.toLowerCase()}
      </p>
      <div className="mt-6 rounded-xl border bg-muted/30 p-4 text-muted-foreground text-sm">
        Expand the source in the sidebar and pick a chapter to read.
      </div>
    </div>
  );
}

function ChapterView({
  chapter,
  onSelectSection,
}: {
  chapter: ChapterDetail;
  onSelectSection: (id: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-wide">
        <span>{chapter.ordinal}</span>
      </div>
      <h1 className="mt-2 font-semibold text-3xl tracking-tight">
        {chapter.heading || chapter.ordinal}
      </h1>
      {chapter.reserved && (
        <p className="mt-2 text-muted-foreground italic text-sm">
          This chapter is reserved.
        </p>
      )}

      <ActionToolbar node={null} />
      <Separator className="my-6" />

      <h2 className="font-semibold text-muted-foreground text-xs uppercase tracking-[0.18em]">
        Sections in this chapter
      </h2>
      {chapter.children.length === 0 ? (
        <p className="mt-4 text-muted-foreground text-sm">
          No sections published.
        </p>
      ) : (
        <ul className="mt-3 divide-y border-y">
          {chapter.children.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onSelectSection(c.id)}
                className="group flex w-full items-baseline gap-4 py-2.5 text-left transition-colors hover:bg-muted/40"
              >
                <span className="w-20 shrink-0 font-mono font-semibold text-foreground/90 text-sm tabular-nums group-hover:text-primary">
                  {c.citation.trim().split(/\s+/).pop() || c.ordinal}
                </span>
                <span className="flex-1 text-foreground/90 text-sm leading-snug">
                  {c.heading || c.ordinal}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NodeView({ node }: { node: NodeDetail }) {
  return (
    <div>
      <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-wide">
        <span>
          {node.source}
          {node.chapter ? ` · ${node.chapter.citation}` : ""}
        </span>
      </div>
      <h1 className="mt-2 font-semibold text-3xl tracking-tight">
        {node.citation}
        {node.heading ? <> — {node.heading}</> : null}
      </h1>
      {node.effective_from && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground text-sm">
          <span>Effective {fmtEffective(node.effective_from)}</span>
        </div>
      )}

      <ActionToolbar node={node} />

      <Separator className="my-6" />

      {node.has_content ? (
        <BodyText text={node.body_text} crossRefs={node.cross_refs} />
      ) : (
        <p className="text-muted-foreground text-sm italic">
          No body text is published for this section.
        </p>
      )}
    </div>
  );
}

// Render the body text with paragraph breaks. Highlights any literal phrases
// listed in cross_refs so the in-text citations are visually distinct (we
// don't make them links yet — that's a Phase 2/3 enhancement).
function BodyText({
  text,
  crossRefs,
}: {
  text: string;
  crossRefs: NodeDetail["cross_refs"];
}) {
  // Split into paragraphs on blank lines (the backend preserves them).
  const paragraphs = text.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);

  // Build a single regex of all cross-ref literals (longest first so we don't
  // match a shorter substring inside a longer one).
  const phrases = [...new Set(crossRefs.map((r) => r.text))]
    .filter(Boolean)
    .sort((a, b) => b.length - a.length);
  const re =
    phrases.length > 0
      ? new RegExp(
          "(" +
            phrases.map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") +
            ")",
          "g",
        )
      : null;

  const renderInline = (s: string): ReactNode[] => {
    if (!re) return [s];
    const out: ReactNode[] = [];
    let last = 0;
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    let i = 0;
    while ((m = re.exec(s)) !== null) {
      if (m.index > last) out.push(s.slice(last, m.index));
      out.push(
        <span
          key={`xr-${i++}`}
          className="rounded-sm bg-accent/40 px-0.5 font-medium text-foreground"
          title="In-text citation"
        >
          {m[0]}
        </span>,
      );
      last = m.index + m[0].length;
    }
    if (last < s.length) out.push(s.slice(last));
    return out;
  };

  return (
    <article className="space-y-5 text-[15.5px] leading-relaxed">
      {paragraphs.map((p, i) => (
        <p key={i}>{renderInline(p)}</p>
      ))}
    </article>
  );
}

function ActionToolbar({ node }: { node: NodeDetail | null }) {
  const enabled = !!node?.has_content;
  // Track which button just fired so we can swap its icon to a check for
  // ~1.5s — gives the user a confidence ping without needing a toast.
  const [copied, setCopied] = useState<"share" | "cite" | null>(null);
  const ping = (which: "share" | "cite") => {
    setCopied(which);
    window.setTimeout(() => setCopied((c) => (c === which ? null : c)), 1500);
  };

  const onShare = async () => {
    if (!node) return;
    const bare =
      (node.path && node.path.trim()) ||
      node.citation.trim().split(/\s+/).pop() ||
      "";
    const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
    const url = `${window.location.origin}${basePath}/browse#/${node.source_slug}/${bare}`;
    try {
      await navigator.clipboard.writeText(url);
      ping("share");
    } catch {
      window.prompt("Copy this link:", url);
    }
  };

  const onCite = async () => {
    if (!node) return;
    try {
      await navigator.clipboard.writeText(node.citation);
      ping("cite");
    } catch {
      window.prompt("Copy this citation:", node.citation);
    }
  };

  return (
    <div className="mt-3 flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={!enabled}
        onClick={onShare}
      >
        {copied === "share" ? (
          <CheckIcon className="size-3.5" />
        ) : (
          <Share2 className="size-3.5" />
        )}
        {copied === "share" ? "Copied" : "Share"}
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled
        title="Print/Download coming soon"
      >
        <Download className="size-3.5" /> Download
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled
        title="Print/Download coming soon"
      >
        <Printer className="size-3.5" /> Print
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="ml-auto"
        disabled={!enabled}
        onClick={onCite}
      >
        {copied === "cite" ? (
          <CheckIcon className="size-3.5" />
        ) : (
          <CircleEllipsisIcon className="size-3.5" />
        )}
        {copied === "cite" ? "Copied" : "Cite"}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Search results pane
// ---------------------------------------------------------------------------

function SearchResultsPane({
  query,
  loading,
  error,
  data,
  scope,
  scopeSource,
  onSetScope,
  onPick,
  onClose,
}: {
  query: string;
  loading: boolean;
  error: string | null;
  data: BrowseSearchResponse | null;
  scope: string | null;
  scopeSource: BrowseSource | null;
  onSetScope: (slug: string | null) => void;
  onPick: (r: BrowseSearchResult) => void;
  onClose: () => void;
}) {
  return (
    <main className="min-w-0 flex-1 overflow-y-auto px-6 py-8 md:px-10 lg:px-16">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <h2 className="font-semibold text-muted-foreground text-xs uppercase tracking-[0.18em]">
              Search results
            </h2>
            <h1 className="mt-1 font-semibold text-2xl tracking-tight">
              <span className="text-muted-foreground/70">for</span>{" "}
              <span className="font-mono">&ldquo;{query}&rdquo;</span>
            </h1>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <XIcon className="size-3.5" /> Close
          </Button>
        </div>

        {/* Scope toggle */}
        <div className="mt-4 flex flex-wrap items-center gap-1.5 text-sm">
          <span className="text-muted-foreground">Scope:</span>
          <ScopeButton
            label="All sources"
            active={scope == null}
            onClick={() => onSetScope(null)}
          />
          {scopeSource && (
            <ScopeButton
              label={`Just ${scopeSource.name}`}
              active={scope === scopeSource.slug}
              onClick={() => onSetScope(scopeSource.slug)}
            />
          )}
        </div>

        <Separator className="my-6" />

        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm">
            <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : loading ? (
          <LoadingBlock label="Searching the corpus…" />
        ) : !data || data.results.length === 0 ? (
          <div className="rounded-md border border-dashed bg-muted/30 px-4 py-10 text-center text-muted-foreground text-sm">
            No matches for{" "}
            <span className="font-mono">&ldquo;{query}&rdquo;</span>
            {scope ? " in this source." : "."}
          </div>
        ) : (
          <>
            <p className="text-muted-foreground text-xs">
              {data.count} {data.count === 1 ? "result" : "results"}
              {scope ? " in this source" : " across the corpus"}.
            </p>
            <ul className="mt-3 divide-y border-y">
              {data.results.map((r, i) => (
                <SearchResultRow
                  key={`${r.node_id}-${i}`}
                  result={r}
                  onPick={onPick}
                />
              ))}
            </ul>
          </>
        )}
      </div>
    </main>
  );
}

// Sibling sections from the same chapter, anchored around the current node.
// Hash links so the existing /browse#... resolver handles navigation.
function RelatedRules({
  node,
  chapter,
}: {
  node: NodeDetail;
  chapter: ChapterDetail | null;
}) {
  if (!chapter || chapter.children.length <= 1) return null;
  const idx = chapter.children.findIndex((c) => c.id === node.id);
  // Show up to 4 neighbors centered on the current section (capped by the
  // ends of the chapter list). Falls back to the first few if the current
  // node isn't in the children array (shouldn't happen, but be defensive).
  const start = idx >= 0 ? Math.max(0, idx - 2) : 0;
  const end = idx >= 0 ? Math.min(chapter.children.length, start + 5) : 5;
  const neighbors = chapter.children
    .slice(start, end)
    .filter((c) => c.id !== node.id);
  if (neighbors.length === 0) return null;

  return (
    <div>
      <Separator />
      <h3 className="mt-5 font-semibold text-foreground text-sm">
        Related rules
      </h3>
      <ul className="mt-2 flex flex-col gap-0.5 text-sm">
        {neighbors.map((c) => {
          const bare = c.citation.trim().split(/\s+/).pop() || c.ordinal;
          return (
            <li key={c.id}>
              <a
                href={`#/${node.source_slug}/${bare}`}
                className="block rounded-md px-2 py-1 hover:bg-muted/50"
              >
                <div className="font-mono font-medium text-xs text-foreground">
                  {bare}
                </div>
                {c.heading && (
                  <div className="truncate text-muted-foreground text-xs">
                    {c.heading}
                  </div>
                )}
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ScopeButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded-full bg-primary px-3 py-1 font-medium text-primary-foreground text-xs"
          : "rounded-full border border-input px-3 py-1 text-xs hover:bg-accent"
      }
    >
      {label}
    </button>
  );
}

function SearchResultRow({
  result,
  onPick,
}: {
  result: BrowseSearchResult;
  onPick: (r: BrowseSearchResult) => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onPick(result)}
        className="group flex w-full flex-col gap-1 py-3 text-left transition-colors hover:bg-muted/40"
      >
        <div className="flex items-baseline gap-3">
          <span className="font-mono font-semibold text-foreground/90 text-sm tabular-nums group-hover:text-primary">
            {result.citation.trim().split(/\s+/).pop()}
          </span>
          <span className="flex-1 text-foreground/90 text-sm">
            {result.heading || "(no heading)"}
          </span>
          {result.exact && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 font-medium text-primary text-xs">
              Exact
            </span>
          )}
        </div>
        <div className="text-muted-foreground text-xs">
          {result.source}
          {result.chapter ? (
            <>
              {" "}· {result.chapter.ordinal}
              {result.chapter.heading
                ? ` — ${result.chapter.heading}`
                : ""}
            </>
          ) : null}
        </div>
        {result.snippet && (
          <div
            className="mt-1 text-foreground/75 text-sm leading-relaxed"
            // Snippet comes from Postgres ts_headline with HTML <mark>
            // wrappers; render as HTML so highlights show.
            dangerouslySetInnerHTML={{ __html: result.snippet }}
          />
        )}
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Right sidecar
// ---------------------------------------------------------------------------

function Sidecar({
  source,
  chapter,
  node,
}: {
  source: BrowseSource | null;
  chapter: ChapterDetail | null;
  node: NodeDetail | null;
}) {
  // If nothing is selected, just show a quiet hint so the column doesn't go
  // entirely blank.
  if (!source) {
    return (
      <aside className="hidden border-l bg-muted/20 px-6 py-8 xl:block">
        <p className="text-muted-foreground text-xs">
          Section metadata will appear here once you open a section.
        </p>
      </aside>
    );
  }

  return (
    <aside className="hidden border-l bg-muted/20 px-6 py-8 xl:block">
      <div className="sticky top-0 space-y-5">
        {node ? (
          <>
            <div>
              <h3 className="font-semibold text-foreground text-sm">
                Citation
              </h3>
              <div className="mt-2 rounded-lg border bg-background px-3 py-2 font-mono text-xs">
                {node.citation}
              </div>
            </div>

            {node.official_url && (
              <div>
                <h3 className="font-semibold text-foreground text-sm">
                  Official source
                </h3>
                <a
                  className="mt-1 inline-flex items-center gap-1.5 text-primary text-sm underline-offset-2 hover:underline"
                  href={node.official_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  legis.iowa.gov <ExternalLinkIcon className="size-3" />
                </a>
              </div>
            )}

            {node.cross_refs.length > 0 && (
              <div>
                <Separator />
                <h3 className="mt-5 font-semibold text-foreground text-sm">
                  In-text citations
                </h3>
                <ul className="mt-2 flex flex-col gap-1.5 text-sm">
                  {node.cross_refs.slice(0, 8).map((r, i) => (
                    <li key={`${r.node_id}-${i}`}>
                      <a
                        href={`#/${node.source_slug}/${r.path}`}
                        className="block rounded-md px-2 py-1 hover:bg-muted/50"
                      >
                        <div className="font-mono text-muted-foreground text-xs">
                          {r.text}
                        </div>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {node.history.length > 0 && (
              <div>
                <Separator />
                <h3 className="mt-5 font-semibold text-foreground text-sm">
                  History
                </h3>
                <ul className="mt-2 flex flex-col gap-1 text-muted-foreground text-xs">
                  {node.history.slice(0, 6).map((h, i) => (
                    <li key={i}>{h}</li>
                  ))}
                </ul>
              </div>
            )}

            <RelatedRules node={node} chapter={chapter} />
          </>
        ) : chapter ? (
          <>
            <div>
              <h3 className="font-semibold text-foreground text-sm">
                Chapter
              </h3>
              <div className="mt-2 rounded-lg border bg-background px-3 py-2 font-mono text-xs">
                {chapter.citation}
              </div>
            </div>
            {chapter.official_url && (
              <div>
                <h3 className="font-semibold text-foreground text-sm">
                  Official source
                </h3>
                <a
                  className="mt-1 inline-flex items-center gap-1.5 text-primary text-sm underline-offset-2 hover:underline"
                  href={chapter.official_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open <ExternalLinkIcon className="size-3" />
                </a>
              </div>
            )}
          </>
        ) : (
          <>
            <div>
              <h3 className="font-semibold text-foreground text-sm">Source</h3>
              <p className="mt-2 text-muted-foreground text-sm">
                {source.name}
              </p>
              <p className="mt-1 font-mono text-muted-foreground text-xs">
                {source.abbreviation}
              </p>
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
