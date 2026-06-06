"use client";

// Corpus browser shell — "Westlaw era". The sidebar is a flat list of clickable
// sources (no tree); selecting one opens that source's index in the main pane:
// a chapter index → section reader for statutes/rules, or a search-first
// decisions index for caselaw. The default landing and the header are centered
// on search + advanced search. Search results are unified: a caselaw hit routes
// to /cases/<id>, a statute/rule hit opens in the reader. Deep-links
// (#/iowa-code/714.16) still resolve programmatically.

import {
	GitCompareArrowsIcon,
	SearchIcon,
	SlidersHorizontalIcon,
	XIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
	Suspense,
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import {
	type AdvancedFilters,
	toSearchFilters,
} from "@/components/browse/advanced-search";
import { BrowseSidebar } from "@/components/browse/browse-sidebar";
import { CaselawIndex } from "@/components/browse/caselaw-index";
import { LibraryHome } from "@/components/browse/library-home";
import { ReadingPane, type Selection } from "@/components/browse/reader";
import { SearchResultsPane } from "@/components/browse/search-results";
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
	SidebarInset,
	SidebarProvider,
	SidebarTrigger,
} from "@/components/ui/sidebar";
import {
	type BrowseChapter,
	type BrowseSearchResponse,
	type BrowseSearchResult,
	type BrowseSource,
	browseChapter,
	browseChapters,
	browseNode,
	browseResolve,
	browseSearch,
	browseSources,
	type ChapterDetail,
	type NodeDetail,
	type SearchFilters,
} from "@/lib/iowa-browse";

type Mode = "home" | "search" | "browse";

// Stable composite keys for the busy set so source slugs and node ids can't
// collide.
const srcKey = (slug: string) => `src:${slug}`;
const chapKey = (id: number) => `chap:${id}`;

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
		docType: dt === "code" || dt === "rules" || dt === "cases" ? dt : "all",
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
	// The browse view is DERIVED ENTIRELY from the URL query string
	// (?source=<slug>&chap=<id>&sec=<id>, alongside the search ?q=…). Nothing
	// about "what's open" lives in React state, so every step of table-of-contents
	// navigation (source → chapter → section) is a real history entry and the
	// browser back button walks back through it instead of jumping to home. Only
	// data caches and transient flags live in state.
	const [busy, setBusy] = useState<Set<string>>(new Set());
	const [readerError, setReaderError] = useState<string | null>(null);

	// ---- search input state (hydrated from the URL) -----------------------
	const [query, setQuery] = useState(() => searchParams.get("q") ?? "");
	const [filters, setFilters] = useState<AdvancedFilters>(() =>
		advancedFromParams(searchParams),
	);
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
	// Browse selection: ?source=<slug>&chap=<chapterId>&sec=<sectionId>. Each
	// level is optional and a deeper one implies the shallower ones. `sec` is also
	// set on its own (no source/chap) when a section is opened from search
	// results, so the back button returns to those results.
	const urlQ = (searchParams.get("q") ?? "").trim();
	const urlSource = searchParams.get("source");
	const urlChapId = Number(searchParams.get("chap")) || null;
	const urlSecId = Number(searchParams.get("sec")) || null;
	const mode: Mode =
		urlSecId || urlSource ? "browse" : urlQ ? "search" : "home";
	// Link to the full-page advanced builder, seeded with whatever is in the box
	// and the active filters so a search can be carried over and refined there.
	const advancedHref = useMemo(() => {
		const p = new URLSearchParams();
		if (query.trim()) p.set("q", query.trim());
		const sf = toSearchFilters(filters);
		if (sf.doc_type) p.set("doc_type", sf.doc_type);
		if (sf.court) p.set("court", sf.court);
		if (sf.status) p.set("status", sf.status);
		if (sf.date_from) p.set("from", sf.date_from);
		if (sf.date_to) p.set("to", sf.date_to);
		const qs = p.toString();
		return qs ? `/browse/advanced?${qs}` : "/browse/advanced";
	}, [query, filters]);

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

	// Resolve hash deep-links (#/iowa-code/714.16) once sources have loaded, and
	// again on every hashchange (the in-text cross-reference anchors in the reader
	// navigate by setting the hash). These are the shareable / cross-page entry
	// form — chat citations, the Compare page, and the Share button all emit them.
	// We resolve the cite to a node id and REPLACE the hash with the canonical
	// ?source&chap&sec query form, so the whole browser stays uniformly URL-driven
	// and back/forward walks the history. A caselaw hash just opens its index.
	useEffect(() => {
		if (!sources) return;

		const resolveFromHash = async () => {
			const hash = window.location.hash;
			if (!hash || hash === lastHashRef.current) return;
			lastHashRef.current = hash;

			const target = parseHashTarget();
			if (!target) return;
			const src = sources.find((s) => s.slug === target.slug);
			if (!src) return;

			// The hash is about to be stripped by the replace; clear the guard so the
			// same cross-ref can be followed again later.
			const go = (qs: string) => {
				lastHashRef.current = null;
				router.replace(`/browse?${qs}`);
			};

			if (src.kind === "caselaw") {
				go(`source=${encodeURIComponent(target.slug)}`);
				return;
			}

			const resolved = await browseResolve(target.slug, target.cite).catch(
				(e) => {
					console.error("browseResolve failed", e);
					return null;
				},
			);
			if (!resolved?.found) return;

			const p = new URLSearchParams();
			p.set("source", target.slug);
			if (resolved.is_chapter) p.set("chap", String(resolved.node_id));
			else p.set("sec", String(resolved.node_id));
			go(p.toString());
		};

		void resolveFromHash();
		const onHash = () => void resolveFromHash();
		window.addEventListener("hashchange", onHash);
		return () => window.removeEventListener("hashchange", onHash);
	}, [sources, router]);

	// Fetch search results whenever the URL's q/filters change — covers initial
	// load of a shared/bookmarked search and back/forward navigation.
	useEffect(() => {
		const sp = new URLSearchParams(spStr);
		const q = (sp.get("q") ?? "").trim();
		if (!q) {
			setSearching(false);
			return;
		}
		// Mirror the URL into the header / home input controls.
		setQuery(q);
		setFilters(advancedFromParams(sp));

		const sf = searchFiltersFromParams(sp);
		const page = Math.max(1, Number(sp.get("page")) || 1);
		const key = `${q}\0${JSON.stringify(sf)}`;
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

	// Load whatever data the URL's browse selection needs — runs on every
	// browse-param change, including back/forward, so the panes are populated
	// without any component-local "what's open" state. The load* cache guards make
	// re-runs (cache churn changing their identities) cheap no-ops.
	useEffect(() => {
		if (urlSource) {
			const src = sources?.find((s) => s.slug === urlSource);
			// Caselaw uses the search-first index — there's no chapter list to load.
			if (src && src.kind !== "caselaw") void loadChapters(urlSource);
		}
		if (urlChapId) void loadChapterDetail(urlChapId);
		if (urlSecId) {
			void (async () => {
				const node = await loadNode(urlSecId);
				// Section opened from search (no ?chap): pull its chapter too, so the
				// breadcrumb, sidecar, and related-rules resolve.
				const chapId = node?.chapter?.id;
				if (chapId) void loadChapterDetail(chapId);
			})();
		}
	}, [
		urlSource,
		urlChapId,
		urlSecId,
		sources,
		loadChapters,
		loadChapterDetail,
		loadNode,
	]);

	// Clear any stale reader error when the open source/chapter/section changes.
	// The URL ids are intentional triggers (not values read in the body): keying
	// on them — rather than on the load* identities — means a freshly-set load
	// error isn't immediately wiped by unrelated cache churn.
	// biome-ignore lint/correctness/useExhaustiveDependencies: deps are navigation triggers, not read values
	useEffect(() => {
		setReaderError(null);
	}, [urlSource, urlChapId, urlSecId]);

	// ---- navigation actions ------------------------------------------------
	// Every action is a plain router.push to the canonical browse URL; the derived
	// state + the load effect above do the rest. This is what makes the back
	// button retrace the path. A direct /browse?source=<slug> link (the Library
	// cards, the advanced page, the case reader) lands on the same URL with no
	// special-casing.
	const goHome = useCallback(() => {
		router.push("/browse");
	}, [router]);

	const openSource = useCallback(
		(slug: string) => {
			setReaderError(null);
			router.push(`/browse?source=${encodeURIComponent(slug)}`);
		},
		[router],
	);

	const onSelectChapter = useCallback(
		(slug: string, chapterId: number) => {
			setReaderError(null);
			const p = new URLSearchParams({ source: slug, chap: String(chapterId) });
			router.push(`/browse?${p.toString()}`);
		},
		[router],
	);

	const onSelectSection = useCallback(
		(
			slug: string | undefined,
			chapterId: number | undefined,
			sectionId: number,
		) => {
			setReaderError(null);
			const p = new URLSearchParams();
			if (slug) p.set("source", slug);
			if (chapterId) p.set("chap", String(chapterId));
			p.set("sec", String(sectionId));
			router.push(`/browse?${p.toString()}`);
		},
		[router],
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

	// Results-pane filter rail: re-run the server search with the new fielded
	// filters, keeping the committed query (the URL's q). Optimistically mirror
	// into `filters` so the rail updates instantly, ahead of navigation.
	const onResultsFiltersChange = useCallback(
		(next: AdvancedFilters) => {
			const q = (searchParams.get("q") ?? "").trim();
			if (!q) return;
			setFilters(next);
			runSearch(q, toSearchFilters(next));
		},
		[searchParams, runSearch],
	);

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

	// ---- derived selection (all from the URL) -----------------------------
	// The open section drives the rest: when it's opened from search (only
	// ?sec=<id> in the URL), its source + chapter come from the loaded node so the
	// breadcrumb, sidecar, and related-rules still resolve.
	const selNode = useMemo(
		() => (urlSecId ? (nodes[urlSecId] ?? null) : null),
		[nodes, urlSecId],
	);
	const selChapterId = urlChapId ?? selNode?.chapter?.id ?? null;
	const selChapter = useMemo(
		() => (selChapterId ? (chapterDetails[selChapterId] ?? null) : null),
		[chapterDetails, selChapterId],
	);
	const selSlug = urlSource ?? selNode?.source_slug ?? null;
	const selSource = useMemo(
		() => (selSlug ? (sources?.find((s) => s.slug === selSlug) ?? null) : null),
		[sources, selSlug],
	);
	// Selection passed to the ReadingPane for its branching + DocChat key.
	const sel: Selection = useMemo(
		() => ({
			slug: selSlug ?? undefined,
			chapterId: selChapterId ?? undefined,
			sectionId: urlSecId ?? undefined,
		}),
		[selSlug, selChapterId, urlSecId],
	);

	return (
		<SidebarProvider defaultOpen={false}>
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

						{/* Home links to the full-page advanced builder directly; surface a
						    shortcut to it here once you're in results/browse. */}
						{mode !== "home" && (
							<Button asChild variant="outline" size="sm" className="shrink-0">
								<Link href={advancedHref}>
									<SlidersHorizontalIcon className="size-4" />
									<span className="hidden sm:inline">Advanced</span>
								</Link>
							</Button>
						)}

						<Button asChild variant="outline" size="sm" className="shrink-0">
							<Link href="/browse/compare">
								<GitCompareArrowsIcon className="size-4" />
								<span className="hidden lg:inline">Compare editions</span>
							</Link>
						</Button>
					</header>

					{mode === "home" ? (
						<LibraryHome
							sources={sources}
							query={query}
							onQueryChange={setQuery}
							filters={filters}
							onSubmit={submitFilterSearch}
							onOpenSource={openSource}
						/>
					) : mode === "search" ? (
						<SearchResultsPane
							query={searchResults?.query ?? query}
							loading={searching}
							error={searchError}
							data={searchResults}
							filters={filters}
							onFiltersChange={onResultsFiltersChange}
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
							onSelectChapter={(id) =>
								sel.slug && onSelectChapter(sel.slug, id)
							}
							onSelectSection={(id) =>
								onSelectSection(sel.slug, sel.chapterId, id)
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
							<button
								type="button"
								onClick={onSourceClick}
								className="truncate"
							>
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
