"use client";

// The workspace bar's search field: one tinted field that answers two
// questions as you type — "is this phrase in here?" (when a reader has
// registered a document-search handle: live find, ↵ walks the matches) and
// "what else says this?" (known-item suggestions from /api/browse/suggest:
// case names, reporter cites, section numbers, catchlines). ⌘↵ runs the full
// corpus search on /results (or re-runs the results page's own search), ⌘K
// focuses the field from anywhere. The field owns its text; a page seeds it
// through its handle (?q= from a click-through) and it resets on navigation.
// Suggest requests ride a 200 ms debounce, are aborted when superseded, and
// the last 50 answers are kept client-side so backspacing never refetches.

import {
	ArrowRightIcon,
	BookOpenIcon,
	FileTextIcon,
	MessageSquareTextIcon,
	ScaleIcon,
	SearchIcon,
	XIcon,
} from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import {
	type KeyboardEvent,
	type ReactNode,
	useCallback,
	useEffect,
	useId,
	useMemo,
	useRef,
	useState,
} from "react";
import { useBarHandles } from "@/components/carbon/workspace-bar";
import { courtShort, yearOf } from "@/components/case-reader/format";
import {
	browseSuggest,
	type SuggestCase,
	type SuggestResponse,
	type SuggestSection,
} from "@/lib/iowa-browse";
import { buildSearchQuery } from "@/lib/search-url";
import { cn } from "@/lib/utils";

const MIN_QUERY = 2;
const DEBOUNCE_MS = 200;
const CACHE_MAX = 50;
// Module-level so navigating between pages keeps recent answers warm.
const CACHE = new Map<string, SuggestResponse>();

function remember(q: string, r: SuggestResponse) {
	if (r.partial) return; // a timed-out answer is not worth keeping
	CACHE.delete(q);
	CACHE.set(q, r);
	if (CACHE.size > CACHE_MAX) {
		const oldest = CACHE.keys().next().value;
		if (oldest !== undefined) CACHE.delete(oldest);
	}
}

type Item =
	| { id: string; kind: "find" }
	| { id: string; kind: "ask" }
	| { id: string; kind: "case"; row: SuggestCase }
	| { id: string; kind: "section"; row: SuggestSection }
	| { id: string; kind: "all" };

export function WorkspaceSearch({ className }: { className?: string }) {
	const router = useRouter();
	const pathname = usePathname();
	const { doc, search, ask } = useBarHandles();
	const listId = useId();
	const inputRef = useRef<HTMLInputElement>(null);

	// The field owns its text; pages seed it and navigation resets it.
	const seed = doc?.seed ?? search?.seed ?? "";
	const [value, setValue] = useState(seed);
	const [live, setLive] = useState(seed);
	// biome-ignore lint/correctness/useExhaustiveDependencies: pathname is the reset trigger
	useEffect(() => {
		setValue(seed);
		setLive(seed);
	}, [seed, pathname]);
	useEffect(() => {
		const t = window.setTimeout(() => setLive(value.trim()), DEBOUNCE_MS);
		return () => window.clearTimeout(t);
	}, [value]);
	// The reader highlights whatever the debounced text is.
	const docSetQuery = doc?.setQuery;
	useEffect(() => {
		docSetQuery?.(live);
	}, [docSetQuery, live]);

	const [open, setOpen] = useState(false);
	const [active, setActive] = useState(0);
	const [suggest, setSuggest] = useState<SuggestResponse | null>(null);
	// Which highlighted match ↵ jumps to next; resets with the query.
	const cursor = useRef(0);

	// --- suggestions --------------------------------------------------------
	useEffect(() => {
		cursor.current = 0;
		if (live.length < MIN_QUERY) {
			setSuggest(null);
			return;
		}
		const hit = CACHE.get(live);
		if (hit) {
			setSuggest(hit);
			return;
		}
		const ctl = new AbortController();
		browseSuggest(live, ctl.signal)
			.then((r) => {
				if (ctl.signal.aborted) return;
				remember(live, r);
				setSuggest(r);
			})
			.catch(() => {
				// Aborted or failed: keep whatever is showing; the footer still
				// leads to the full search.
			});
		return () => ctl.abort();
	}, [live]);

	const q = value.trim();
	const items = useMemo<Item[]>(() => {
		if (!q) return [];
		const out: Item[] = [];
		if (doc) out.push({ id: "find", kind: "find" });
		if (ask) out.push({ id: "ask", kind: "ask" });
		// Suggestions lag the typed text by the debounce; only show ones that
		// answer the query on screen so a stale list never sits under new text.
		const fresh = suggest && suggest.query === live ? suggest : null;
		for (const row of fresh?.cases ?? [])
			out.push({ id: `case-${row.case_id}`, kind: "case", row });
		for (const row of fresh?.sections ?? [])
			out.push({ id: `section-${row.node_id}`, kind: "section", row });
		out.push({ id: "all", kind: "all" });
		return out;
	}, [q, suggest, live, doc, ask]);

	// The row ↵ picks before the user has moved: find-in-document when there
	// is a document, otherwise the corpus search.
	const defaultActive = doc ? 0 : Math.max(0, items.length - 1);
	useEffect(() => {
		setActive((a) => Math.min(a, Math.max(0, items.length - 1)));
	}, [items.length]);

	// --- actions ------------------------------------------------------------
	const jumpToMatch = useCallback(() => {
		const registry = (
			CSS as unknown as { highlights?: Map<string, Iterable<Range>> }
		).highlights;
		const hl = registry?.get("search-hit");
		if (!hl) return;
		const ranges = [...hl];
		if (ranges.length === 0) return;
		const i = cursor.current % ranges.length;
		scrollRangeToCenter(ranges[i]);
		cursor.current = i + 1;
	}, []);

	const close = useCallback(() => {
		setOpen(false);
		setActive(0);
	}, []);

	const clear = useCallback(() => {
		setValue("");
		setLive("");
		doc?.clear();
	}, [doc]);

	const searchAll = useCallback(() => {
		if (!q) return;
		close();
		if (search) search.submit(q);
		else router.push(`/results?${buildSearchQuery(q, {})}`);
	}, [q, close, search, router]);

	const activate = useCallback(
		(item: Item) => {
			switch (item.kind) {
				case "find":
					// Keep focus in the field so ↵ again walks to the next match.
					jumpToMatch();
					return;
				case "ask":
					close();
					ask?.run(q);
					setValue("");
					setLive("");
					return;
				case "case":
					close();
					router.push(`/case/${item.row.case_id}`);
					return;
				case "section":
					close();
					router.push(`/section/${item.row.node_id}`);
					return;
				case "all":
					searchAll();
			}
		},
		[jumpToMatch, close, ask, q, router, searchAll],
	);

	// ⌘K / Ctrl+K focuses the field from anywhere on the page.
	useEffect(() => {
		const onKey = (e: globalThis.KeyboardEvent) => {
			if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
				const el = inputRef.current;
				if (!el || el.offsetParent === null) return; // hidden below lg
				e.preventDefault();
				el.focus();
				el.select();
				setOpen(true);
			}
		};
		document.addEventListener("keydown", onKey);
		return () => document.removeEventListener("keydown", onKey);
	}, []);

	const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
		if (e.key === "ArrowDown" || e.key === "ArrowUp") {
			if (items.length === 0) return;
			e.preventDefault();
			if (!open) {
				// Closed → reopen on the default row, like a native combobox.
				setOpen(true);
				setActive(defaultActive);
				return;
			}
			const step = e.key === "ArrowDown" ? 1 : -1;
			setActive((a) => (a + step + items.length) % items.length);
			return;
		}
		if (e.key === "Enter") {
			e.preventDefault();
			if (e.metaKey || e.ctrlKey) {
				searchAll();
				return;
			}
			const item = items[open ? active : defaultActive];
			if (item) activate(item);
			return;
		}
		if (e.key === "Escape") {
			// A search input clears itself on Escape natively; we decide.
			e.preventDefault();
			if (open) {
				close();
			} else if (value) {
				clear();
			} else {
				inputRef.current?.blur();
			}
			return;
		}
		if (e.key === "Tab") close();
	};

	const showMenu = open && items.length > 0;
	const activeId = showMenu ? `${listId}-${items[active]?.id}` : undefined;
	const matches = doc?.matches ?? null;
	const matchLabel =
		matches === null
			? ""
			: `${matches.toLocaleString()} match${matches === 1 ? "" : "es"}`;
	const scope = doc ? doc.label.toLowerCase() : null;
	const placeholder = scope
		? `Search ${scope} or all Iowa law…`
		: "Search Iowa law…";

	return (
		<div className={cn("relative", className)}>
			<label className="flex h-8 items-center gap-2 border-[var(--cds-field-tint-border)] border-b bg-[var(--cds-field-tint)] px-3 text-[13px] focus-within:outline-2 focus-within:-outline-offset-2 focus-within:outline-[#0f62fe]">
				<SearchIcon className="size-4 shrink-0 text-[var(--cds-tint-text)]" />
				<input
					ref={inputRef}
					type="search"
					value={value}
					onChange={(e) => {
						setValue(e.target.value);
						setOpen(true);
						setActive(defaultActive);
					}}
					onFocus={() => setOpen(true)}
					onBlur={close}
					onKeyDown={onKeyDown}
					placeholder={placeholder}
					aria-label={placeholder.replace(/…$/, "")}
					role="combobox"
					aria-expanded={showMenu}
					aria-controls={listId}
					aria-activedescendant={activeId}
					aria-autocomplete="list"
					autoComplete="off"
					spellCheck={false}
					className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-[var(--cds-field-tint-border)] [&::-webkit-search-cancel-button]:hidden"
				/>
				{q ? (
					<>
						{matchLabel && (
							<span className="shrink-0 font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
								{matchLabel}
							</span>
						)}
						<button
							type="button"
							aria-label="Clear search"
							onMouseDown={(e) => e.preventDefault()}
							onClick={clear}
							className="shrink-0 text-[var(--cds-helper)] hover:text-[var(--cds-text)]"
						>
							<XIcon className="size-3.5" />
						</button>
					</>
				) : (
					<kbd className="shrink-0 font-mono text-[11px] text-[var(--cds-field-tint-border)]">
						⌘K
					</kbd>
				)}
			</label>

			<div
				id={listId}
				role="listbox"
				aria-label="Suggestions"
				hidden={!showMenu}
				className="absolute top-[34px] left-0 z-30 w-full bg-[var(--cds-bg)] pb-1 shadow-[0_2px_6px_rgba(0,0,0,0.3)]"
			>
				{showMenu &&
					renderGroups({
						items,
						active,
						listId,
						matchLabel,
						q,
						docLabel: doc?.label ?? "",
						askLabel: ask?.label ?? "",
						activate,
						setActive,
					})}
			</div>
		</div>
	);
}

function renderGroups({
	items,
	active,
	listId,
	matchLabel,
	q,
	docLabel,
	askLabel,
	activate,
	setActive,
}: {
	items: Item[];
	active: number;
	listId: string;
	matchLabel: string;
	q: string;
	docLabel: string;
	askLabel: string;
	activate: (item: Item) => void;
	setActive: (i: number) => void;
}): ReactNode {
	const out: ReactNode[] = [];
	let lastKind: Item["kind"] | null = null;
	items.forEach((item, i) => {
		if (item.kind !== lastKind) {
			if (item.kind === "find")
				out.push(
					<GroupLabel key="g-find" meta={matchLabel || undefined}>
						{docLabel}
					</GroupLabel>,
				);
			if (item.kind === "ask")
				out.push(<GroupLabel key="g-ask">Assistant</GroupLabel>);
			if (item.kind === "case")
				out.push(<GroupLabel key="g-case">Cases</GroupLabel>);
			if (item.kind === "section")
				out.push(<GroupLabel key="g-section">Iowa Code</GroupLabel>);
			lastKind = item.kind;
		}
		const common = {
			id: `${listId}-${item.id}`,
			selected: i === active,
			onPick: () => activate(item),
			onHover: () => setActive(i),
		};
		switch (item.kind) {
			case "find":
				out.push(
					<Row
						key={item.id}
						{...common}
						icon={<FileTextIcon className="size-4" />}
						title={
							<>
								Find <q>{q}</q> in {docLabel.toLowerCase()}
							</>
						}
						meta="↵"
					/>,
				);
				break;
			case "ask":
				out.push(
					<Row
						key={item.id}
						{...common}
						icon={<MessageSquareTextIcon className="size-4" />}
						title={
							<>
								{askLabel}: <q>{q}</q>
							</>
						}
						meta=""
					/>,
				);
				break;
			case "case": {
				const r = item.row;
				const meta = [
					courtShort(r.court_id, r.court_name),
					yearOf(r.date_filed),
					r.citation,
				]
					.filter(Boolean)
					.join(" · ");
				out.push(
					<Row
						key={item.id}
						{...common}
						icon={<ScaleIcon className="size-4" />}
						title={r.case_name}
						meta={meta}
					/>,
				);
				break;
			}
			case "section": {
				const r = item.row;
				out.push(
					<Row
						key={item.id}
						{...common}
						icon={<BookOpenIcon className="size-4" />}
						title={
							<>
								§ {r.path}
								{r.heading && <> — {r.heading}</>}
							</>
						}
						meta={r.chapter ? `ch. ${r.chapter.ordinal}` : ""}
					/>,
				);
				break;
			}
			case "all":
				out.push(
					<button
						type="button"
						tabIndex={-1}
						key={item.id}
						id={common.id}
						role="option"
						aria-selected={common.selected}
						onMouseDown={(e) => e.preventDefault()}
						onMouseEnter={common.onHover}
						onClick={common.onPick}
						className={cn(
							"mt-1 flex h-11 w-full cursor-pointer items-center gap-3 bg-[#0f62fe] px-4 text-left text-[13px] text-white",
							common.selected ? "bg-[#0353e9]" : "hover:bg-[#0353e9]",
						)}
					>
						<ArrowRightIcon className="size-4 shrink-0" />
						<span className="min-w-0 flex-1 truncate">
							Search all Iowa law for <q>{q}</q>
						</span>
						<kbd className="shrink-0 font-mono text-[11px] text-[#d0e2ff]">
							⌘↵
						</kbd>
					</button>,
				);
		}
	});
	return out;
}

// Center a highlight range in its scrolling ancestor. Scrolling by the range
// (not its paragraph) is what makes ↵ walk match-by-match through a
// paragraph that holds several.
function scrollRangeToCenter(range: Range) {
	let el = range.startContainer.parentElement;
	while (el && el !== document.body) {
		const oy = getComputedStyle(el).overflowY;
		if (oy === "auto" || oy === "scroll") break;
		el = el.parentElement;
	}
	const rect = range.getBoundingClientRect();
	if (!el || el === document.body) {
		window.scrollBy({
			top: rect.top - window.innerHeight / 2,
			behavior: "smooth",
		});
		return;
	}
	const box = el.getBoundingClientRect();
	el.scrollTo({
		top: el.scrollTop + (rect.top - box.top) - el.clientHeight / 2,
		behavior: "smooth",
	});
}

function GroupLabel({
	children,
	meta,
}: {
	children: ReactNode;
	meta?: string;
}) {
	return (
		<div
			role="presentation"
			className="flex items-center px-4 pt-3 pb-1 font-mono text-[11px] text-[var(--cds-tint-text)] uppercase tracking-[0.18em]"
		>
			<span>{children}</span>
			{meta && (
				<span className="ml-auto text-[var(--cds-helper)] normal-case tracking-normal">
					{meta}
				</span>
			)}
		</div>
	);
}

function Row({
	id,
	selected,
	icon,
	title,
	meta,
	onPick,
	onHover,
}: {
	id: string;
	selected: boolean;
	icon: ReactNode;
	title: ReactNode;
	meta: string;
	onPick: () => void;
	onHover: () => void;
}) {
	return (
		<button
			type="button"
			tabIndex={-1}
			id={id}
			role="option"
			aria-selected={selected}
			// preventDefault keeps focus in the input so blur doesn't close the
			// menu before the click lands.
			onMouseDown={(e) => e.preventDefault()}
			onMouseEnter={onHover}
			onClick={onPick}
			className={cn(
				"flex h-11 w-full cursor-pointer items-center gap-3 px-4 text-left text-[13px] text-[var(--cds-text)]",
				selected
					? "bg-[var(--cds-tint-selected)]"
					: "hover:bg-[var(--cds-layer-hover)]",
			)}
		>
			<span className="shrink-0 text-[var(--cds-tint-text)]">{icon}</span>
			<span className="min-w-0 flex-1 truncate">{title}</span>
			{meta && (
				<span className="shrink-0 font-mono text-[11px] text-[var(--cds-helper)]">
					{meta}
				</span>
			)}
		</button>
	);
}
