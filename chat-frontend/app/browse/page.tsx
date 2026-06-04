"use client";

// Corpus browser shell — "Westlaw era". The sidebar is a flat list of clickable
// sources (no tree); selecting one opens that source's index in the main pane:
// a chapter index → section reader for statutes/rules, or a search-first
// decisions index for caselaw. The default landing and the header are centered
// on search + advanced search. Search results are unified: a caselaw hit routes
// to /cases/<id>, a statute/rule hit opens in the reader. Deep-links
// (#/iowa-code/714.16) still resolve programmatically.

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  GitCompareArrowsIcon,
  Loader2Icon,
  AlertCircleIcon,
  BookOpenIcon,
  SearchIcon,
  SlidersHorizontalIcon,
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
  type BrowseChapter,
  type BrowseSearchResponse,
  type BrowseSearchResult,
  type BrowseSource,
  type ChapterDetail,
  type NodeDetail,
  type SearchFilters,
} from "@/lib/iowa-browse";
import { AppSidebarFooter } from "@/components/app-sidebar-footer";
import { AppSidebarNav } from "@/components/app-sidebar-nav";
import { ReadingPane, type Selection } from "@/components/browse/reader";
import { SearchResultsPane } from "@/components/browse/search-results";
import {
  AdvancedSearch,
  COURT_LABEL,
  DOC_TYPE_LABEL,
  EMPTY_FILTERS,
  HomeView,
  SOURCE_ICON,
  toSearchFilters,
  type AdvancedFilters,
} from "@/components/browse/advanced-search";
import { CaselawIndex } from "@/components/browse/caselaw-index";

type Mode = "home" | "search" | "browse";

// Stable composite keys for the busy set so source slugs and node ids can't
// collide.
const srcKey = (slug: string) => `src:${slug}`;
const chapKey = (id: number) => `chap:${id}`;

// Read-only chips for the results pane, built from whatever SearchFilters drove
// the search (so the caselaw index and the header advanced panel agree).
function chipsFromSearchFilters(sf: SearchFilters): string[] {
  const chips: string[] = [];
  if (sf.doc_type) chips.push(DOC_TYPE_LABEL[sf.doc_type] ?? sf.doc_type);
  if (sf.court) chips.push(COURT_LABEL[sf.court] ?? sf.court);
  if (sf.status) chips.push(sf.status);
  if (sf.date_from || sf.date_to)
    chips.push(
      `${(sf.date_from ?? "").slice(0, 4) || "earliest"}–${
        (sf.date_to ?? "").slice(0, 4) || "latest"
      }`,
    );
  return chips;
}

// Parse the hash fragment "#/iowa-code/714.16" into {slug, cite}. Returns null
// for shapes the resolver doesn't understand.
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

// ---- URL <-> search-state adapters -------------------------------------
// The search (and an opened section) live in the query string so the browser
// back button restores them and a search is shareable. `from`/`to` are the
// year inputs widened to full ISO bounds.
function buildSearchQuery(q: string, sf: SearchFilters): string {
  const p = new URLSearchParams();
  p.set("q", q);
  if (sf.doc_type) p.set("doc_type", sf.doc_type);
  if (sf.court) p.set("court", sf.court);
  if (sf.status) p.set("status", sf.status);
  if (sf.date_from) p.set("from", sf.date_from);
  if (sf.date_to) p.set("to", sf.date_to);
  return p.toString();
}

function searchFiltersFromParams(sp: URLSearchParams): SearchFilters {
  return {
    doc_type: sp.get("doc_type"),
    court: sp.get("court"),
    status: sp.get("status"),
    date_from: sp.get("from"),
    date_to: sp.get("to"),
  };
}

// Reconstruct the advanced-search panel inputs from the URL.
function advancedFromParams(sp: URLSearchParams): AdvancedFilters {
  const dt = sp.get("doc_type");
  return {
    docType:
      dt === "code" || dt === "rules" || dt === "cases" ? dt : "all",
    court: sp.get("court") ?? "",
    status: sp.get("status") ?? "",
    yearFrom: (sp.get("from") ?? "").slice(0, 4),
    yearTo: (sp.get("to") ?? "").slice(0, 4),
  };
}

// useSearchParams() must be read inside a Suspense boundary.
export default function BrowsePage() {
  return (
    <Suspense
      fallback={
        <div className="grid h-dvh place-items-center text-muted-foreground text-sm">
          Loading…
        </div>
      }
    >
      <BrowsePageInner />
    </Suspense>
  );
}

function BrowsePageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const spStr = searchParams.toString();

  // ---- data caches -------------------------------------------------------
  const [sources, setSources] = useState<BrowseSource[] | null>(null);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [chapters, setChapters] = useState<Record<string, BrowseChapter[]>>({});
  const [chapterDetails, setChapterDetails] = useState<
    Record<number, ChapterDetail>
  >({});
  const [nodes, setNodes] = useState<Record<number, NodeDetail>>({});

  // ---- UI state ----------------------------------------------------------
  // The view is DERIVED from the URL (search + open-section live in the query
  // string) so the browser back button restores it. `browseSlug` is the only
  // non-URL view state: a source opened from the sidebar (table-of-contents
  // browsing isn't deep-linked).
  const [browseSlug, setBrowseSlug] = useState<string | null>(null);
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [sel, setSel] = useState<Selection>({});
  const [readerError, setReaderError] = useState<string | null>(null);

  // ---- search input state (hydrated from the URL) -----------------------
  const [query, setQuery] = useState(() => searchParams.get("q") ?? "");
  const [filters, setFilters] = useState<AdvancedFilters>(() =>
    advancedFromParams(searchParams),
  );
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [searchResults, setSearchResults] =
    useState<BrowseSearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Last hash the deep-link effect resolved — lets it ignore re-runs caused by
  // cache churn (vs. a genuine hashchange). See the resolve effect below.
  const lastHashRef = useRef<string | null>(null);
  // (query+filters) of the results currently in state — set only AFTER a fetch
  // resolves, so a search isn't re-run when only ?sec changes, and a stale
  // (StrictMode-cancelled) run never blocks the spinner from clearing.
  const loadedSearchKeyRef = useRef<string | null>(null);

  // ---- view derived from the URL ----------------------------------------
  const urlQ = (searchParams.get("q") ?? "").trim();
  const urlSec = searchParams.get("sec");
  const mode: Mode = urlSec
    ? "browse"
    : urlQ
      ? "search"
      : browseSlug
        ? "browse"
        : "home";
  const activeChips = useMemo(
    () => chipsFromSearchFilters(searchFiltersFromParams(new URLSearchParams(spStr))),
    [spStr],
  );

  // ---- helpers -----------------------------------------------------------
  const setBusyKey = useCallback((key: string, on: boolean) => {
    setBusy((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
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

  // ---- mount: load sources ----------------------------------------------
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

  // Resolve hash deep-links once sources have loaded. Runs again on hashchange
  // (back/forward). Caselaw isn't cite-deep-linked (cases use /cases/[id]); a
  // caselaw hash just opens its index.
  useEffect(() => {
    if (!sources) return;

    const resolveFromHash = async () => {
      // The effect re-runs whenever a load* callback's identity changes (cache
      // churn from in-page navigation). Only resolve when the hash *actually*
      // changed, otherwise a stale hash would clobber the user's selection.
      const hash = window.location.hash;
      if (hash === lastHashRef.current) return;
      lastHashRef.current = hash;

      const target = parseHashTarget();
      if (!target) {
        // Hash removed (e.g. backing out of a cross-ref) — drop the hash-driven
        // source so the derived mode falls back to the search/home view.
        setBrowseSlug(null);
        return;
      }
      const src = sources.find((s) => s.slug === target.slug);
      if (!src) return;

      if (src.kind === "caselaw") {
        setBrowseSlug(target.slug);
        setSel({ slug: target.slug });
        return;
      }

      let resolved;
      try {
        resolved = await browseResolve(target.slug, target.cite);
      } catch (e) {
        console.error("browseResolve failed", e);
        return;
      }
      if (!resolved.found) return;

      setBrowseSlug(target.slug);
      await loadChapters(target.slug);

      if (resolved.is_chapter) {
        await loadChapterDetail(resolved.node_id);
        setSel({ slug: target.slug, chapterId: resolved.node_id });
        return;
      }

      const node = await loadNode(resolved.node_id);
      if (!node) return;
      const chapId = node.chapter?.id;
      if (chapId) {
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

  // Fetch search results whenever the URL's q/filters change — covers initial
  // load of a shared/bookmarked search and back/forward navigation.
  useEffect(() => {
    const sp = new URLSearchParams(spStr);
    const q = (sp.get("q") ?? "").trim();
    if (!q) {
      setSearching(false);
      return;
    }
    // Mirror the URL into the input controls and drop any sidebar selection.
    setQuery(q);
    setFilters(advancedFromParams(sp));
    setShowAdvanced(false);
    setBrowseSlug(null);

    const sf = searchFiltersFromParams(sp);
    const page = Math.max(1, Number(sp.get("page")) || 1);
    const key = `${q} ${JSON.stringify(sf)}`;
    // Same search+page already loaded (only ?sec changed) -> just clear spinner.
    const pageKey = `${key} p${page}`;
    if (pageKey === loadedSearchKeyRef.current) {
      setSearching(false);
      return;
    }

    let active = true;
    setSearching(true);
    setSearchError(null);
    browseSearch(q, sf, page)
      .then((d) => {
        if (!active) return;
        setSearchResults(d);
        loadedSearchKeyRef.current = pageKey;
        setSearching(false);
      })
      .catch((e) => {
        if (!active) return;
        setSearchError(e instanceof Error ? e.message : "Search failed.");
        setSearchResults(null);
        setSearching(false);
      });
    return () => {
      active = false;
    };
  }, [spStr]);

  // Open a section from the URL (?sec=<id>) — e.g. a statute search result, so
  // the back button returns to the results it was opened from.
  useEffect(() => {
    const id = Number(searchParams.get("sec"));
    if (!Number.isFinite(id) || id <= 0) return;
    setReaderError(null);
    setBrowseSlug(null);
    let cancelled = false;
    void (async () => {
      const node = await loadNode(id);
      if (cancelled) return;
      if (!node) {
        setSel({ sectionId: id });
        return;
      }
      const chapId = node.chapter?.id;
      if (chapId) {
        await loadChapterDetail(chapId);
        if (!cancelled)
          setSel({ slug: node.source_slug, chapterId: chapId, sectionId: id });
      } else {
        setSel({ slug: node.source_slug, sectionId: id });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [spStr, searchParams, loadNode, loadChapterDetail]);

  // ---- navigation actions ------------------------------------------------
  const goHome = useCallback(() => {
    router.push("/browse");
    setBrowseSlug(null);
  }, [router]);

  const openSource = useCallback(
    (slug: string) => {
      setReaderError(null);
      setSel({ slug });
      setBrowseSlug(slug);
      // Drop any search/section query params so the derived mode shows this
      // source's index.
      router.push("/browse");
      const src = sources?.find((s) => s.slug === slug);
      if (src?.kind !== "caselaw") void loadChapters(slug);
    },
    [router, sources, loadChapters],
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
  // Run a search by writing it to the URL; the effect above does the fetch, so
  // back/forward and shared links restore the results.
  const runSearch = useCallback(
    (q: string, sf: SearchFilters) => {
      const trimmed = q.trim();
      if (!trimmed) return;
      router.push(`/browse?${buildSearchQuery(trimmed, sf)}`);
    },
    [router],
  );

  // Header / home search uses the shared advanced-filter state.
  const submitFilterSearch = useCallback(() => {
    runSearch(query, toSearchFilters(filters));
  }, [query, filters, runSearch]);

  // Result click: caselaw → the /cases reader; statute/rule → open the section
  // via the URL (?…&sec=id) so the back button returns to these results.
  const onPickSearchResult = useCallback(
    (r: BrowseSearchResult) => {
      if (r.kind === "case" && r.case_id != null) {
        router.push(`/cases/${r.case_id}`);
        return;
      }
      const sp = new URLSearchParams(spStr);
      sp.set("sec", String(r.node_id));
      router.push(`/browse?${sp.toString()}`);
    },
    [router, spStr],
  );

  // Move between result pages by updating ?page in the URL (so paging is in
  // history and shareable). Page 1 drops the param for a clean URL.
  const onSearchPageChange = useCallback(
    (next: number) => {
      const sp = new URLSearchParams(spStr);
      if (next <= 1) sp.delete("page");
      else sp.set("page", String(next));
      router.push(`/browse?${sp.toString()}`);
    },
    [router, spStr],
  );

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
          mode={mode}
          activeSlug={mode === "browse" ? (sel.slug ?? null) : null}
          onHome={goHome}
          onOpenSource={openSource}
        />
        <SidebarInset>
          <header className="flex h-16 shrink-0 items-center gap-3 border-b px-4">
            <SidebarTrigger />
            <Separator orientation="vertical" className="mr-1 h-4" />
            <BrowseBreadcrumb
              mode={mode}
              source={selSource}
              chapter={selChapter}
              node={selNode}
              onSourceClick={() => selSource && openSource(selSource.slug)}
              onChapterClick={() =>
                selSource &&
                selChapter &&
                onSelectChapter(selSource.slug, selChapter.id)
              }
            />

            <form
              className="relative ml-auto w-full max-w-xs"
              onSubmit={(e) => {
                e.preventDefault();
                submitFilterSearch();
              }}
            >
              <SearchIcon className="-translate-y-1/2 absolute top-1/2 left-3 size-4 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape" && mode === "search") {
                    e.preventDefault();
                    goHome();
                  }
                }}
                placeholder="Search the corpus…"
                className="h-9 pr-9 pl-9"
              />
              {(query || mode === "search") && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery("");
                    if (mode === "search") goHome();
                  }}
                  aria-label="Clear search"
                  className="-translate-y-1/2 absolute top-1/2 right-2 flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <XIcon className="size-3.5" />
                </button>
              )}
            </form>

            {/* Home already surfaces advanced search inline; avoid a second panel. */}
            {mode !== "home" && (
              <Button
                variant={showAdvanced ? "secondary" : "outline"}
                size="sm"
                className="shrink-0"
                onClick={() => setShowAdvanced((v) => !v)}
              >
                <SlidersHorizontalIcon className="size-4" />
                <span className="hidden sm:inline">Advanced</span>
              </Button>
            )}

            <Button asChild variant="outline" size="sm" className="shrink-0">
              <Link href="/browse/compare">
                <GitCompareArrowsIcon className="size-4" />
                <span className="hidden lg:inline">Compare editions</span>
              </Link>
            </Button>
          </header>

          {showAdvanced && mode !== "home" && (
            <div className="border-b bg-muted/20 px-4 py-3">
              <div className="mx-auto max-w-3xl">
                <AdvancedSearch filters={filters} onChange={setFilters} />
                <div className="mt-3 flex justify-end gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setFilters(EMPTY_FILTERS)}
                  >
                    Reset
                  </Button>
                  <Button size="sm" onClick={submitFilterSearch}>
                    <SearchIcon className="size-4" /> Search
                  </Button>
                </div>
              </div>
            </div>
          )}

          {mode === "home" ? (
            <HomeView
              sources={sources}
              query={query}
              onQueryChange={setQuery}
              filters={filters}
              onFiltersChange={setFilters}
              onSubmit={submitFilterSearch}
              onOpenSource={openSource}
            />
          ) : mode === "search" ? (
            <SearchResultsPane
              query={searchResults?.query ?? query}
              loading={searching}
              error={searchError}
              data={searchResults}
              chips={activeChips}
              onPick={onPickSearchResult}
              onClose={goHome}
              onPageChange={onSearchPageChange}
            />
          ) : selSource?.kind === "caselaw" ? (
            <CaselawIndex source={selSource} onSearch={runSearch} />
          ) : (
            <ReadingPane
              sel={sel}
              source={selSource}
              chapter={selChapter}
              node={selNode}
              chapters={sel.slug ? (chapters[sel.slug] ?? null) : null}
              busySource={sel.slug ? busy.has(srcKey(sel.slug)) : false}
              busyChapter={
                sel.chapterId != null && busy.has(chapKey(sel.chapterId))
              }
              error={readerError}
              onSelectChapter={(id) => onSelectChapter(sel.slug!, id)}
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
// Breadcrumb
// ---------------------------------------------------------------------------

function BrowseBreadcrumb({
  mode,
  source,
  chapter,
  node,
  onSourceClick,
  onChapterClick,
}: {
  mode: Mode;
  source: BrowseSource | null;
  chapter: ChapterDetail | null;
  node: NodeDetail | null;
  onSourceClick: () => void;
  onChapterClick: () => void;
}) {
  const browsing = mode === "browse" && source != null;
  // A crumb is a clickable link when something is below it (so it can step back
  // up the hierarchy); the deepest crumb is a plain page label.
  const sourceIsLeaf = browsing && !chapter && !node;
  const chapterHeading = chapter
    ? `${chapter.ordinal}${chapter.heading ? ` — ${chapter.heading}` : ""}`
    : "";

  let label = "Browse the corpus";
  if (mode === "search") label = "Search results";
  else if (browsing && source) label = source.name;

  return (
    <Breadcrumb className="min-w-0">
      <BreadcrumbList>
        <BreadcrumbItem>
          {browsing && !sourceIsLeaf ? (
            <BreadcrumbLink asChild>
              <button type="button" onClick={onSourceClick} className="truncate">
                {label}
              </button>
            </BreadcrumbLink>
          ) : (
            <BreadcrumbPage className="truncate">{label}</BreadcrumbPage>
          )}
        </BreadcrumbItem>
        {browsing && chapter && (
          <>
            <BreadcrumbSeparator className="hidden md:block" />
            <BreadcrumbItem className="hidden md:block">
              {node ? (
                <BreadcrumbLink asChild>
                  <button
                    type="button"
                    onClick={onChapterClick}
                    className="truncate"
                  >
                    {chapterHeading}
                  </button>
                </BreadcrumbLink>
              ) : (
                <BreadcrumbPage className="truncate">
                  {chapterHeading}
                </BreadcrumbPage>
              )}
            </BreadcrumbItem>
          </>
        )}
        {browsing && node && (
          <>
            <BreadcrumbSeparator className="hidden lg:block" />
            <BreadcrumbItem className="hidden lg:block">
              <BreadcrumbPage>{node.citation}</BreadcrumbPage>
            </BreadcrumbItem>
          </>
        )}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

// ---------------------------------------------------------------------------
// Sidebar — flat clickable source list (no tree)
// ---------------------------------------------------------------------------

function BrowseSidebar({
  sources,
  sourcesError,
  mode,
  activeSlug,
  onHome,
  onOpenSource,
}: {
  sources: BrowseSource[] | null;
  sourcesError: string | null;
  mode: Mode;
  activeSlug: string | null;
  onHome: () => void;
  onOpenSource: (slug: string) => void;
}) {
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
          <SidebarGroupLabel>Search</SidebarGroupLabel>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                onClick={onHome}
                isActive={mode === "home" || mode === "search"}
              >
                <SearchIcon className="size-4" />
                <span>Search the corpus</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Sources</SidebarGroupLabel>
          <SidebarMenu>
            {sourcesError ? (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-2 text-destructive text-xs">
                <AlertCircleIcon className="mt-0.5 size-3.5 shrink-0" />
                <span>{sourcesError}</span>
              </div>
            ) : !sources ? (
              <div className="flex items-center gap-2 px-2 py-3 text-sidebar-foreground/60 text-xs">
                <Loader2Icon className="size-3.5 animate-spin" />
                <span>Loading sources…</span>
              </div>
            ) : (
              sources.map((src) => {
                const Icon = SOURCE_ICON[src.slug] ?? BookOpenIcon;
                return (
                  <SidebarMenuItem key={src.slug}>
                    <SidebarMenuButton
                      onClick={() => onOpenSource(src.slug)}
                      isActive={activeSlug === src.slug}
                      className="h-auto items-start py-2"
                      tooltip={src.name}
                    >
                      <Icon className="mt-0.5 size-4 shrink-0" />
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate font-medium">{src.name}</span>
                        <span className="text-sidebar-foreground/50 text-xs">
                          {src.entries.toLocaleString()}{" "}
                          {src.entry_label.toLowerCase()}
                        </span>
                      </div>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })
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
