"use client";

// Inline citation hover card: rest the pointer on a linked case citation in
// the opinion and see the cited case's court, cite, date, cited-by count and
// treatment before deciding to open it. One card per reader (a context), the
// links only report enter/leave. Hover-intent delays keep it from flashing
// while the eye scans a paragraph; keyboard focus opens it too; coarse
// pointers get the plain link.

import { ArrowRightIcon, CircleAlertIcon, CircleCheckIcon } from "lucide-react";
import Link from "next/link";
import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import type { CitedCase } from "@/lib/iowa-browse";
import { fmtEffective } from "@/lib/iowa-browse";
import { cn } from "@/lib/utils";
import { courtLong, courtShort, prettyLabel, yearOf } from "./format";

const OPEN_DELAY = 150;
const CLOSE_DELAY = 200;
const CARD_W = 300;

type Anchor = { caseId: number; rect: DOMRect };

const Ctx = createContext<{
	byId: Map<number, CitedCase>;
	enter: (caseId: number, el: HTMLElement) => void;
	leave: () => void;
} | null>(null);

export function CiteHoverProvider({
	cases,
	children,
}: {
	cases: CitedCase[];
	children: ReactNode;
}) {
	const byId = useMemo(
		() => new Map(cases.map((c) => [c.case_id, c])),
		[cases],
	);
	const [anchor, setAnchor] = useState<Anchor | null>(null);
	const openTimer = useRef<number | undefined>(undefined);
	const closeTimer = useRef<number | undefined>(undefined);

	const clearTimers = useCallback(() => {
		window.clearTimeout(openTimer.current);
		window.clearTimeout(closeTimer.current);
	}, []);

	const enter = useCallback(
		(caseId: number, el: HTMLElement) => {
			if (!byId.has(caseId)) return;
			clearTimers();
			openTimer.current = window.setTimeout(
				() => setAnchor({ caseId, rect: el.getBoundingClientRect() }),
				OPEN_DELAY,
			);
		},
		[byId, clearTimers],
	);
	const leave = useCallback(() => {
		clearTimers();
		closeTimer.current = window.setTimeout(() => setAnchor(null), CLOSE_DELAY);
	}, [clearTimers]);
	const hold = () => clearTimers();

	// Scrolling the opinion moves the anchor out from under the card.
	useEffect(() => {
		if (!anchor) return;
		const close = () => setAnchor(null);
		window.addEventListener("scroll", close, true);
		window.addEventListener("resize", close);
		return () => {
			window.removeEventListener("scroll", close, true);
			window.removeEventListener("resize", close);
		};
	}, [anchor]);

	useEffect(() => () => clearTimers(), [clearTimers]);

	const ctx = useMemo(() => ({ byId, enter, leave }), [byId, enter, leave]);
	const c = anchor ? byId.get(anchor.caseId) : undefined;

	return (
		<Ctx.Provider value={ctx}>
			{children}
			{anchor && c && (
				<HoverCard
					c={c}
					rect={anchor.rect}
					onPointerEnter={hold}
					onPointerLeave={leave}
				/>
			)}
		</Ctx.Provider>
	);
}

// A linked case citation inside the opinion text.
export function CiteLink({
	caseId,
	children,
}: {
	caseId: number;
	children: ReactNode;
}) {
	const ctx = useContext(Ctx);
	return (
		<Link
			href={`/case/${caseId}`}
			className="text-[var(--cds-link)] hover:underline"
			onPointerEnter={(e) => {
				if (e.pointerType === "mouse") ctx?.enter(caseId, e.currentTarget);
			}}
			onPointerLeave={() => ctx?.leave()}
			onFocus={(e) => ctx?.enter(caseId, e.currentTarget)}
			onBlur={() => ctx?.leave()}
		>
			{children}
		</Link>
	);
}

function HoverCard({
	c,
	rect,
	onPointerEnter,
	onPointerLeave,
}: {
	c: CitedCase;
	rect: DOMRect;
	onPointerEnter: () => void;
	onPointerLeave: () => void;
}) {
	// Below the link by default; above when the bottom of the viewport is
	// near. Clamped inside the viewport horizontally.
	const vw = typeof window === "undefined" ? 1280 : window.innerWidth;
	const vh = typeof window === "undefined" ? 800 : window.innerHeight;
	const left = Math.max(8, Math.min(rect.left, vw - CARD_W - 8));
	const below = rect.bottom + 8;
	const flip = below + 190 > vh;
	const style = flip
		? { left, bottom: vh - rect.top + 8, width: CARD_W }
		: { left, top: below, width: CARD_W };
	const t = c.treatment;
	const negative = t && (t.status === "negative" || t.status === "caution");

	return (
		<div
			role="tooltip"
			style={style}
			onPointerEnter={onPointerEnter}
			onPointerLeave={onPointerLeave}
			className="fixed z-50 border border-[var(--cds-border)] bg-[var(--cds-bg)] text-[var(--cds-text)] shadow-[0_2px_8px_rgba(0,0,0,0.18)] [font-family:var(--font-plex-sans)]"
		>
			<div className="flex flex-col gap-1 px-4 pt-3 pb-2.5">
				<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
					{courtLong(c.court_id, c.court_name)}
					{c.date_filed ? ` · ${yearOf(c.date_filed)}` : ""}
				</span>
				<span className="font-semibold text-[14px] leading-[1.35]">
					{c.case_name}
				</span>
				<span className="font-mono text-[12px] text-[var(--cds-text-2)]">
					{[c.citation, c.date_filed && fmtEffective(c.date_filed)]
						.filter(Boolean)
						.join(" · ")}
				</span>
			</div>
			<div className="grid grid-cols-2 border-[var(--cds-border)] border-y">
				<div className="flex flex-col gap-0.5 border-[var(--cds-border)] border-r px-4 py-2">
					<span className="text-[12px] text-[var(--cds-helper)]">Cited by</span>
					<span className="font-semibold text-[13px]">
						{c.cited_by === null
							? "—"
							: `${c.cited_by.toLocaleString()} decision${c.cited_by === 1 ? "" : "s"}`}
					</span>
				</div>
				<div className="flex flex-col gap-0.5 px-4 py-2">
					<span className="text-[12px] text-[var(--cds-helper)]">
						Treatment
					</span>
					<span
						className={cn(
							"flex items-center gap-1 font-semibold text-[13px]",
							negative && "text-[var(--cds-danger-text)]",
						)}
					>
						{negative ? (
							<CircleAlertIcon className="size-3.5" />
						) : (
							<CircleCheckIcon className="size-3.5 text-[var(--cds-success-text)]" />
						)}
						{t && negative ? prettyLabel(t) : "None negative"}
					</span>
				</div>
			</div>
			<div className="flex items-center justify-between px-4 py-2">
				<span className="text-[12px] text-[var(--cds-helper)]">
					Cited {c.count === 1 ? "once" : `${c.count} times`} in this opinion
				</span>
				<Link
					href={`/case/${c.case_id}`}
					className="inline-flex items-center gap-1.5 text-[13px] text-[var(--cds-link)] hover:underline"
				>
					Open case
					<ArrowRightIcon className="size-3.5" />
				</Link>
			</div>
			<span className="sr-only">{courtShort(c.court_id)}</span>
		</div>
	);
}
