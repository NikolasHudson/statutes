"use client";

// The citator rail: Citing decisions (default) · Authorities · Ask. Citing
// rows come from the detail payload's embedded first page; changing sort or
// court, or loading more, goes to /api/browse/cases/:id/citing.

import { CircleAlertIcon, CircleCheckIcon, Loader2Icon } from "lucide-react";
import Link from "next/link";
import {
	memo,
	type ReactNode,
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import {
	type DocAskHandle,
	type DocAskMessage,
	DocAskPanel,
} from "@/components/carbon/doc-ask";
import {
	browseCaseCiting,
	type CaseDetail,
	type CitingDecision,
	type CitingResponse,
	type CitingSort,
	fmtEffective,
} from "@/lib/iowa-browse";
import { cn } from "@/lib/utils";
import { courtShort, prettyLabel, yearOf } from "./format";

export type CitatorTab = "citing" | "authorities" | "ask";

const PAGE = 50;

export function CitatorTabs({
	value,
	onChange,
	citingCount,
	authoritiesCount,
}: {
	value: CitatorTab;
	onChange: (t: CitatorTab) => void;
	citingCount: number;
	authoritiesCount: number;
}) {
	const tabs: { id: CitatorTab; label: string; count?: number }[] = [
		{ id: "citing", label: "Citing decisions", count: citingCount },
		{ id: "authorities", label: "Authorities", count: authoritiesCount },
		{ id: "ask", label: "Ask" },
	];
	return (
		<div
			role="tablist"
			aria-label="Citator"
			className="flex h-10 shrink-0 border-[var(--cds-border)] border-b"
		>
			{tabs.map((t) => {
				const active = t.id === value;
				return (
					<button
						key={t.id}
						type="button"
						role="tab"
						aria-selected={active}
						onClick={() => onChange(t.id)}
						className={cn(
							"-mb-px flex items-center gap-2 whitespace-nowrap border-b-2 px-3.5 text-[13px] transition-colors",
							active
								? "border-[#0f62fe] font-semibold"
								: "border-transparent text-[var(--cds-text-2)] hover:border-[var(--cds-border-strong)] hover:text-[var(--cds-text)]",
						)}
					>
						{t.label}
						{t.count !== undefined && (
							<span className="font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
								{t.count.toLocaleString()}
							</span>
						)}
					</button>
				);
			})}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Citing decisions
// ---------------------------------------------------------------------------

const SORTS: { id: CitingSort; label: string }[] = [
	{ id: "recent", label: "Most recent" },
	{ id: "oldest", label: "Oldest" },
	{ id: "depth", label: "Most citing" },
];

export const CitingList = memo(function CitingList({
	data,
}: {
	data: CaseDetail;
}) {
	const [sort, setSort] = useState<CitingSort>("recent");
	const [court, setCourt] = useState<string>("");
	const [rows, setRows] = useState<CitingDecision[]>(data.citing_decisions);
	const [total, setTotal] = useState(data.citing_folded_count);
	const [hasMore, setHasMore] = useState(
		data.citing_decisions.length < data.citing_folded_count,
	);
	const [courts, setCourts] = useState<CitingResponse["courts"] | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	// Monotonic request id: a response only lands if no newer request (or a
	// reset to the embedded page) superseded it, so a quick sort→court click
	// pair can't leave the list describing the earlier filter.
	const seqRef = useRef(0);

	// Court options: the server facet once we've fetched, else derived from
	// the embedded rows (complete whenever every row is embedded).
	const courtOptions = useMemo(() => {
		if (courts) return courts;
		const seen = new Map<
			string,
			{ court_id: string; court_name: string; count: number }
		>();
		for (const r of data.citing_decisions) {
			const c = seen.get(r.court_id) ?? {
				court_id: r.court_id,
				court_name: r.court_name,
				count: 0,
			};
			c.count += 1;
			seen.set(r.court_id, c);
		}
		return [...seen.values()];
	}, [courts, data.citing_decisions]);

	const fetchPage = useCallback(
		async (
			next: { sort: CitingSort; court: string; offset: number },
			append: boolean,
		) => {
			const seq = ++seqRef.current;
			setLoading(true);
			setError(null);
			try {
				const res = await browseCaseCiting(data.id, {
					sort: next.sort,
					court: next.court || null,
					limit: PAGE,
					offset: next.offset,
				});
				if (seq !== seqRef.current) return; // superseded
				setRows((prev) => (append ? [...prev, ...res.results] : res.results));
				setTotal(res.total);
				setHasMore(res.has_more);
				setCourts(res.courts);
			} catch (e) {
				if (seq !== seqRef.current) return;
				setError(
					e instanceof Error ? e.message : "Couldn't load citing decisions.",
				);
			} finally {
				if (seq === seqRef.current) setLoading(false);
			}
		},
		[data.id],
	);

	// Reset to the embedded page when the case changes (and drop any
	// in-flight page for the previous one).
	useEffect(() => {
		seqRef.current += 1;
		setLoading(false);
		setRows(data.citing_decisions);
		setTotal(data.citing_folded_count);
		setHasMore(data.citing_decisions.length < data.citing_folded_count);
		setCourts(null);
		setSort("recent");
		setCourt("");
	}, [data.citing_decisions, data.citing_folded_count]);

	const change = (s: CitingSort, c: string) => {
		setSort(s);
		setCourt(c);
		if (s === "recent" && !c) {
			seqRef.current += 1; // discard any in-flight fetch
			setLoading(false);
			setError(null);
			setRows(data.citing_decisions);
			setTotal(data.citing_folded_count);
			setHasMore(data.citing_decisions.length < data.citing_folded_count);
			return;
		}
		void fetchPage({ sort: s, court: c, offset: 0 }, false);
	};

	const t = data.treatment;
	const negative = t && (t.status === "negative" || t.status === "caution");

	return (
		<div className="flex min-h-0 flex-1 flex-col">
			<div className="flex shrink-0 items-center gap-3 border-[var(--cds-border)] border-b px-3 py-1.5 text-[12px]">
				<InlineSelect
					aria-label="Sort citing decisions"
					value={sort}
					onChange={(v) => change(v as CitingSort, court)}
					options={SORTS.map((s) => ({ value: s.id, label: s.label }))}
				/>
				<InlineSelect
					aria-label="Filter by court"
					value={court}
					onChange={(v) => change(sort, v)}
					options={[
						{ value: "", label: "All courts" },
						...courtOptions.map((c) => ({
							value: c.court_id,
							label: `${courtShort(c.court_id, c.court_name)} (${c.count})`,
						})),
					]}
				/>
				<span className="ml-auto font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
					{loading ? (
						<Loader2Icon className="size-3.5 animate-spin" />
					) : (
						`${rows.length.toLocaleString()} of ${total.toLocaleString()}`
					)}
				</span>
			</div>

			{data.citing_count > 0 && (
				<div
					className={cn(
						"flex shrink-0 gap-2.5 border-[var(--cds-border)] border-b border-l-[3px] bg-[var(--cds-layer)] py-2.5 pr-4 pl-3",
						negative
							? "border-l-[var(--cds-danger-text)]"
							: "border-l-[var(--cds-success-text)]",
					)}
				>
					{negative ? (
						<CircleAlertIcon className="mt-0.5 size-4 shrink-0 text-[var(--cds-danger-text)]" />
					) : (
						<CircleCheckIcon className="mt-0.5 size-4 shrink-0 text-[var(--cds-success-text)]" />
					)}
					<p className="text-[12px] text-[var(--cds-text-2)] leading-[1.5]">
						{negative && t ? (
							<>
								<span className="font-semibold text-[var(--cds-text)]">
									{prettyLabel(t)}
									{t.by_citation ? ` by ${t.by_citation}.` : "."}
								</span>{" "}
								{t.excerpt ? (
									<span className="italic">“{t.excerpt}”</span>
								) : null}{" "}
								Phrase-based flag ({Math.round((t.confidence || 0) * 100)}%
								confidence) — read the citing passage before relying on it.
							</>
						) : (
							<>
								<span className="font-semibold text-[var(--cds-text)]">
									No negative treatment found.
								</span>{" "}
								Phrase-based check on each citing opinion — advisory; read the
								citing passage before relying on it.
							</>
						)}
					</p>
				</div>
			)}

			<div className="min-h-0 flex-1 overflow-y-auto">
				{error && (
					<p className="px-4 py-3 text-[12px] text-[var(--cds-danger-text)]">
						{error}
					</p>
				)}
				{rows.length === 0 && !loading && !error && (
					<p className="px-4 py-4 text-[13px] text-[var(--cds-text-2)]">
						{data.citing_count === 0
							? "No decision in the corpus cites this case yet. The citation graph refreshes with the quarterly bulk reload."
							: "No citing decisions match this filter."}
					</p>
				)}
				{rows.map((r) => (
					<Link
						key={r.case_id}
						href={`/case/${r.case_id}`}
						className="flex flex-col gap-0.5 border-[var(--cds-border)] border-b px-4 py-2.5 transition-colors hover:bg-[var(--cds-layer-hover)]"
					>
						<span className="text-[13px] leading-[1.35]">{r.case_name}</span>
						<span className="flex items-center gap-2 font-mono text-[11px] text-[var(--cds-helper)]">
							<span className="text-[var(--cds-text-2)]">
								{courtShort(r.court_id, r.court_name)}
							</span>
							<span>{fmtEffective(r.date_filed)}</span>
							{r.citation && <span className="truncate">{r.citation}</span>}
							{r.depth > 1 && (
								<span className="ml-auto text-[var(--cds-text)] tabular-nums">
									×{r.depth}
								</span>
							)}
						</span>
					</Link>
				))}
				{hasMore && (
					<button
						type="button"
						disabled={loading}
						onClick={() =>
							void fetchPage({ sort, court, offset: rows.length }, true)
						}
						className="flex w-full items-center justify-center gap-2 px-4 py-3 text-[13px] text-[var(--cds-link)] transition-colors hover:bg-[var(--cds-layer-hover)] disabled:opacity-60"
					>
						{loading ? <Loader2Icon className="size-4 animate-spin" /> : null}
						Load more
					</button>
				)}
			</div>
			<p className="shrink-0 border-[var(--cds-border)] border-t px-4 py-2.5 text-[11px] text-[var(--cds-helper)] leading-[1.5]">
				Amended reports and duplicate imports are folded into one row. The
				citation graph refreshes with the quarterly bulk reload, so decisions
				from the last few months may not appear yet.
			</p>
		</div>
	);
});

function InlineSelect({
	value,
	onChange,
	options,
	...rest
}: {
	value: string;
	onChange: (v: string) => void;
	options: { value: string; label: string }[];
	"aria-label": string;
}) {
	return (
		<select
			{...rest}
			value={value}
			onChange={(e) => onChange(e.target.value)}
			className="h-7 max-w-[10.5rem] cursor-pointer truncate bg-transparent pr-1 text-[12px] text-[var(--cds-text-2)] outline-none hover:text-[var(--cds-text)] focus-visible:outline-2 focus-visible:outline-[#0f62fe]"
		>
			{options.map((o) => (
				<option key={o.value} value={o.value}>
					{o.label}
				</option>
			))}
		</select>
	);
}

// ---------------------------------------------------------------------------
// Cited authorities
// ---------------------------------------------------------------------------

export const AuthoritiesList = memo(function AuthoritiesList({
	data,
}: {
	data: CaseDetail;
}) {
	return (
		<div className="flex min-h-0 flex-1 flex-col">
			<div className="min-h-0 flex-1 overflow-y-auto">
				{data.cited_cases.length === 0 ? (
					<p className="px-4 py-4 text-[13px] text-[var(--cds-text-2)]">
						No in-corpus authorities cited.
					</p>
				) : (
					data.cited_cases.map((c) => {
						const neg =
							c.treatment &&
							(c.treatment.status === "negative" ||
								c.treatment.status === "caution");
						return (
							<Link
								key={c.case_id}
								href={`/case/${c.case_id}`}
								className="flex flex-col gap-0.5 border-[var(--cds-border)] border-b px-4 py-2.5 transition-colors hover:bg-[var(--cds-layer-hover)]"
							>
								<span className="flex items-start gap-2 text-[13px] leading-[1.35]">
									<span className="min-w-0 flex-1">{c.case_name}</span>
									{neg && (
										<CircleAlertIcon
											aria-label="Negative treatment"
											className="mt-0.5 size-3.5 shrink-0 text-[var(--cds-danger-text)]"
										/>
									)}
								</span>
								<span className="flex items-center gap-2 font-mono text-[11px] text-[var(--cds-helper)]">
									<span className="text-[var(--cds-text-2)]">
										{courtShort(c.court_id, c.court_name)}
									</span>
									{c.date_filed && <span>{yearOf(c.date_filed)}</span>}
									{c.citation && <span className="truncate">{c.citation}</span>}
									<span className="ml-auto text-[var(--cds-text)] tabular-nums">
										×{c.count}
									</span>
								</span>
							</Link>
						);
					})
				)}
			</div>
			{data.external_citation_count > 0 && (
				<p className="shrink-0 border-[var(--cds-border)] border-t px-4 py-2.5 text-[11px] text-[var(--cds-helper)] leading-[1.5]">
					{data.external_citation_count} additional citation
					{data.external_citation_count === 1 ? "" : "s"} to authorities outside
					this corpus (other states, federal, secondary sources).
				</p>
			)}
		</div>
	);
});

// ---------------------------------------------------------------------------
// The rail — a header of tabs + the active tab's body.
// ---------------------------------------------------------------------------

export function CitatorPanel({
	data,
	tab,
	onTab,
	ask,
	askRef,
	header = true,
}: {
	data: CaseDetail;
	tab: CitatorTab;
	onTab: (t: CitatorTab) => void;
	ask: {
		messages: DocAskMessage[];
		busy: boolean;
		send: (t: string) => void;
		stop: () => void;
	};
	askRef?: React.Ref<DocAskHandle>;
	header?: boolean;
}): ReactNode {
	return (
		<>
			{header && (
				<CitatorTabs
					value={tab}
					onChange={onTab}
					citingCount={data.citing_count}
					authoritiesCount={
						data.cited_cases.length + data.external_citation_count
					}
				/>
			)}
			{tab === "citing" ? (
				<CitingList data={data} />
			) : tab === "authorities" ? (
				<AuthoritiesList data={data} />
			) : (
				<DocAskPanel
					title={data.case_name}
					citation={data.citations[0]}
					messages={ask.messages}
					busy={ask.busy}
					onSend={ask.send}
					onStop={ask.stop}
					handleRef={askRef}
				/>
			)}
		</>
	);
}
