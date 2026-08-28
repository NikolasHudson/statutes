"use client";

// The workspace bar (SEARCH_BAR_PLAN.md): one 48px bar the shell renders
// above every route — context (breadcrumb / title) · search field · actions.
// Pages fill the two outer slots through portals (<BarContext>, <BarActions>)
// so their own handlers and state keep working, and hand the search field a
// small handle when they have something for it to do:
//
//   useDocumentSearchHandle — a reader (case, section): "This opinion" group,
//                             live find + ↵ walks matches.
//   useSearchSubmitHandle   — the results page: the field is the query box,
//                             ↵ re-runs the search with the page's filters.
//   useAskHandle            — the assistant: an "Ask the assistant" row that
//                             drops the text into the composer.
//
// Handles live in one context, the setter in another, so a page that only
// registers never re-renders when the bar's state changes.

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useState,
} from "react";
import { createPortal } from "react-dom";
import { WorkspaceSearch } from "@/components/carbon/workspace-search";
import { cn } from "@/lib/utils";

export type DocumentSearch = {
	// Group label in the menu, e.g. "This opinion" / "This section".
	label: string;
	// Query the page arrived with (?q= from a results click-through).
	seed: string;
	matches: number | null;
	setQuery: (q: string) => void;
	clear: () => void;
};

export type SearchSubmit = {
	seed: string;
	submit: (q: string) => void;
};

export type AskHandle = {
	label: string;
	run: (q: string) => void;
};

type Handles = {
	doc: DocumentSearch | null;
	search: SearchSubmit | null;
	ask: AskHandle | null;
};

type Slots = {
	context: HTMLElement | null;
	actions: HTMLElement | null;
	// A page has mounted <BarContext>; the default title steps aside.
	contextFilled: number;
};

const NO_HANDLES: Handles = { doc: null, search: null, ask: null };
const NO_SLOTS: Slots = { context: null, actions: null, contextFilled: 0 };

const HandlesCtx = createContext<Handles>(NO_HANDLES);
const SetHandlesCtx = createContext<(patch: Partial<Handles>) => void>(
	() => {},
);
const SlotsCtx = createContext<Slots>(NO_SLOTS);
const SetSlotsCtx = createContext<
	(patch: Partial<Slots> | ((s: Slots) => Slots)) => void
>(() => {});

export function WorkspaceBarProvider({ children }: { children: ReactNode }) {
	const [handles, setHandles] = useState<Handles>(NO_HANDLES);
	const [slots, setSlots] = useState<Slots>(NO_SLOTS);
	const patchHandles = useCallback(
		(p: Partial<Handles>) => setHandles((h) => ({ ...h, ...p })),
		[],
	);
	const patchSlots = useCallback(
		(p: Partial<Slots> | ((s: Slots) => Slots)) =>
			setSlots((s) => (typeof p === "function" ? p(s) : { ...s, ...p })),
		[],
	);
	return (
		<SetHandlesCtx.Provider value={patchHandles}>
			<SetSlotsCtx.Provider value={patchSlots}>
				<HandlesCtx.Provider value={handles}>
					<SlotsCtx.Provider value={slots}>{children}</SlotsCtx.Provider>
				</HandlesCtx.Provider>
			</SetSlotsCtx.Provider>
		</SetHandlesCtx.Provider>
	);
}

export function useBarHandles(): Handles {
	return useContext(HandlesCtx);
}

// --- page side ---------------------------------------------------------------

export function BarContext({ children }: { children: ReactNode }) {
	const { context } = useContext(SlotsCtx);
	const set = useContext(SetSlotsCtx);
	useEffect(() => {
		set((s) => ({ ...s, contextFilled: s.contextFilled + 1 }));
		return () => set((s) => ({ ...s, contextFilled: s.contextFilled - 1 }));
	}, [set]);
	return context ? createPortal(children, context) : null;
}

export function BarActions({ children }: { children: ReactNode }) {
	const { actions } = useContext(SlotsCtx);
	return actions ? createPortal(children, actions) : null;
}

export function useDocumentSearchHandle(handle: DocumentSearch | null) {
	const set = useContext(SetHandlesCtx);
	useEffect(() => {
		set({ doc: handle });
		return () => set({ doc: null });
	}, [set, handle]);
}

export function useSearchSubmitHandle(handle: SearchSubmit | null) {
	const set = useContext(SetHandlesCtx);
	useEffect(() => {
		set({ search: handle });
		return () => set({ search: null });
	}, [set, handle]);
}

export function useAskHandle(handle: AskHandle | null) {
	const set = useContext(SetHandlesCtx);
	useEffect(() => {
		set({ ask: handle });
		return () => set({ ask: null });
	}, [set, handle]);
}

// --- the bar -------------------------------------------------------------------

// Routes that show corpus text root their breadcrumb at Library; the rest
// get a plain title until they register their own context.
const LIBRARY_ROUTES = [
	"/source",
	"/chapter",
	"/results",
	"/advanced",
	"/compare",
];
const TITLES: [string, string][] = [
	["/assistant", "Assistant"],
	["/account", "Account"],
	["/org", "Organization"],
	["/admin", "Admin"],
];

function DefaultContext({ pathname }: { pathname: string }) {
	if (LIBRARY_ROUTES.some((r) => pathname.startsWith(r))) {
		return (
			<Link
				href="/"
				className="text-[var(--cds-text-2)] hover:text-[var(--cds-link)] hover:underline"
			>
				Library
			</Link>
		);
	}
	const title = TITLES.find(([r]) => pathname.startsWith(r))?.[1];
	return title ? <span className="font-semibold">{title}</span> : null;
}

export function WorkspaceBar({ className }: { className?: string }) {
	const pathname = usePathname();
	const { contextFilled } = useContext(SlotsCtx);
	const set = useContext(SetSlotsCtx);
	const contextRef = useCallback(
		(el: HTMLElement | null) => set({ context: el }),
		[set],
	);
	const actionsRef = useCallback(
		(el: HTMLElement | null) => set({ actions: el }),
		[set],
	);
	return (
		<div
			className={cn(
				"flex h-12 shrink-0 items-center gap-1 border-[var(--cds-border)] border-b px-4 print:hidden sm:px-6",
				className,
			)}
		>
			<div className="flex min-w-0 items-center text-sm">
				{contextFilled === 0 && <DefaultContext pathname={pathname} />}
				<div ref={contextRef} className="contents" />
			</div>
			<WorkspaceSearch className="ml-6 hidden min-w-[18rem] max-w-[52rem] flex-1 lg:block" />
			<div
				ref={actionsRef}
				className="ml-auto flex shrink-0 items-center gap-1"
			/>
		</div>
	);
}
