"use client";

// Carbon mockup of the search-results screen. Mirrors the live results pane
// (components/browse/search-results.tsx) plus the richer results-v2
// exploration: refine rail (content type, court, status, decided-year
// histogram, cited authorities), result rows with kind/treatment tags and
// highlighted snippets, and a pager. Static demo data themed to the
// "spring gun" query; nothing calls the API.

import {
	ArrowRightIcon,
	BellPlusIcon,
	CheckIcon,
	CircleAlertIcon,
	CircleXIcon,
	DownloadIcon,
	ListFilterIcon,
	QuoteIcon,
	SearchIcon,
	XIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { AppShell, BtnGhost, CheckboxRow, LineTabs, Tag } from "../carbon";

// ---------------------------------------------------------------------------
// Static demo data
// ---------------------------------------------------------------------------

const QUERY = "spring gun liability";

const CONTENT_TYPES: { label: string; count: number }[] = [
	{ label: "All content", count: 45 },
	{ label: "Cases", count: 18 },
	{ label: "Iowa Code", count: 7 },
	{ label: "Court Rules", count: 3 },
	{ label: "Books & journals", count: 9 },
	{ label: "Commentary", count: 8 },
];

const COURTS: { label: string; count?: number }[] = [
	{ label: "Any court" },
	{ label: "Supreme Court of Iowa", count: 12 },
	{ label: "Court of Appeals of Iowa", count: 6 },
];

const STATUSES: { label: string; count?: number }[] = [
	{ label: "Any status" },
	{ label: "Published", count: 14 },
	{ label: "Unpublished", count: 4 },
];

// Decade buckets for the date-filter histogram (single-series magnitude:
// Blue 60 in range, hairline gray out of range — per docs/carbon-design-system.md).
const DECADES: { label: string; count: number }[] = [
	{ label: "1860", count: 3 },
	{ label: "1880", count: 2 },
	{ label: "1900", count: 1 },
	{ label: "1920", count: 2 },
	{ label: "1940", count: 1 },
	{ label: "1960", count: 8 },
	{ label: "1980", count: 6 },
	{ label: "2000", count: 9 },
	{ label: "2020", count: 13 },
];

const AUTHORITIES: { label: string; count: number }[] = [
	{ label: "Iowa Code § 704.4", count: 15 },
	{ label: "Restatement (2d) of Torts § 85", count: 12 },
	{ label: "Bird v. Holbrook (1828)", count: 9 },
	{ label: "Hooker v. Miller, 37 Iowa 613", count: 6 },
];

type Treatment = "followed" | "caution" | "negative";

type Result = {
	kind: "Case" | "Iowa Code" | "Court Rules" | "Journal" | "Commentary";
	title: string;
	citation: string;
	context: string;
	snippet: React.ReactNode;
	treatment?: Treatment;
	citedBy?: number;
	paragraphs?: number;
};

const mark = (t: string) => (
	<mark className="bg-[#0f62fe]/20 text-inherit">{t}</mark>
);

const RESULTS: Result[] = [
	{
		kind: "Case",
		title: "Katko v. Briney",
		citation: "183 N.W.2d 657 (Iowa 1971)",
		context: "Supreme Court of Iowa · Feb 9, 1971",
		treatment: "followed",
		citedBy: 1284,
		paragraphs: 11,
		snippet: (
			<>
				…the law has always placed a higher value upon human safety than upon
				mere rights in property, it is the accepted rule that there is no
				privilege to use any force calculated to cause death or serious injury
				to repel the threat to land… set a {mark("spring gun")} in a bedroom of
				an old farm house…
			</>
		),
	},
	{
		kind: "Iowa Code",
		title: "§ 704.4 — Defense of property",
		citation: "Iowa Code § 704.4 (2025)",
		context: "Chapter 704 — Force — reasonable or deadly force",
		paragraphs: 2,
		snippet: (
			<>
				A person is justified in the use of reasonable force to prevent or
				terminate criminal interference with the person&rsquo;s possession or
				other right in property… reasonable force does not include a device such
				as a {mark("spring gun")} that employs {mark("deadly force")} against an
				intruder.
			</>
		),
	},
	{
		kind: "Case",
		title: "Hooker v. Miller",
		citation: "37 Iowa 613 (1873)",
		context: "Supreme Court of Iowa · 1873",
		treatment: "followed",
		citedBy: 89,
		paragraphs: 4,
		snippet: (
			<>
				…defendant liable for damages resulting from a {mark("spring gun")}{" "}
				shot, although plaintiff was a trespasser and there to steal grapes —
				the {mark("liability")} attaches because such means of protection are
				without justification.
			</>
		),
	},
	{
		kind: "Case",
		title: "State v. Metcalf",
		citation: "260 N.W.2d 857 (Iowa 1977)",
		context: "Supreme Court of Iowa · Dec 21, 1977",
		treatment: "caution",
		citedBy: 41,
		paragraphs: 3,
		snippet: (
			<>
				…distinguishing the civil rule of Katko: the criminal statute reaches
				only devices {mark("intended")} to inflict{" "}
				{mark("death or serious injury")}, and the record here showed a warning
				device only…
			</>
		),
	},
	{
		kind: "Journal",
		title: "Spring Guns and the Value of Life: Katko at Fifty",
		citation: "106 Iowa L. Rev. 1121 (2021)",
		context: "Law review · 2021",
		paragraphs: 22,
		snippet: (
			<>
				…fifty years on, {mark("Katko")} remains the canonical statement that
				mechanical {mark("deadly force")} cannot be delegated to a device; this
				article traces its adoption in forty-one jurisdictions…
			</>
		),
	},
	{
		kind: "Case",
		title: "Simpson v. State",
		citation: "12 N.W. 542 (Iowa 1882)",
		context: "Supreme Court of Iowa · 1882",
		treatment: "negative",
		citedBy: 17,
		paragraphs: 2,
		snippet: (
			<>
				…the owner of premises may protect them by such {mark("devices")} as a
				prudent man would employ — <em>overruled in part by Katko</em> insofar
				as it excused {mark("deadly")} mechanical force against trespassers…
			</>
		),
	},
];

const TREATMENT_SPEC: Record<
	Treatment,
	{ label: string; kind: "green" | "yellow" | "red"; icon: React.ElementType }
> = {
	followed: { label: "Followed", kind: "green", icon: CheckIcon },
	caution: { label: "Distinguished", kind: "yellow", icon: CircleAlertIcon },
	negative: { label: "Overruled in part", kind: "red", icon: CircleXIcon },
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ResultsCarbonMockup() {
	const [tab, setTab] = useState<"results" | "charts">("results");
	return (
		<AppShell active="/app-carbon-mockup/results">
			<div className="px-5 py-8 sm:px-8">
				<SearchBar />

				<div className="mt-6 flex flex-wrap items-baseline gap-x-4 gap-y-1">
					<h1 className="font-light text-2xl sm:text-3xl">
						Results for &ldquo;{QUERY}&rdquo;
					</h1>
					<p className="text-[var(--cds-helper)] text-sm">
						Showing 1–6 of 45 · 0.34 s
					</p>
					<div className="ml-auto flex items-center gap-1">
						<BtnGhost>
							<BellPlusIcon className="size-4" />
							Create alert
						</BtnGhost>
						<BtnGhost>
							<DownloadIcon className="size-4" />
							Download
						</BtnGhost>
					</div>
				</div>

				<div className="mt-3 flex flex-wrap items-center gap-2">
					<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.14em]">
						Filters
					</span>
					<FilterChip>Cases + Iowa Code</FilterChip>
					<FilterChip>1860–2026</FilterChip>
					<button
						type="button"
						className="text-[13px] text-[var(--cds-link)] hover:underline"
					>
						Clear all
					</button>
				</div>

				<div className="mt-5">
					<LineTabs
						tabs={[
							{ id: "results" as const, label: "Results", count: 45 },
							{ id: "charts" as const, label: "Charts" },
						]}
						value={tab}
						onChange={setTab}
					/>
				</div>

				<div className="mt-6 grid gap-10 lg:grid-cols-[17rem_1fr] xl:grid-cols-[19rem_1fr]">
					<RefineRail />
					<div className="min-w-0">
						<div className="divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]">
							{RESULTS.map((r) => (
								<ResultRow key={r.citation} r={r} />
							))}
						</div>
						<Pager />
					</div>
				</div>
			</div>
		</AppShell>
	);
}

// ---------------------------------------------------------------------------
// Search bar — fluid input + primary button, same register as the Library
// ---------------------------------------------------------------------------

function SearchBar() {
	return (
		<form className="flex items-stretch" onSubmit={(e) => e.preventDefault()}>
			<div className="relative flex flex-1 items-center border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] focus-within:outline-2 focus-within:-outline-offset-2 focus-within:outline-[#0f62fe]">
				<SearchIcon className="pointer-events-none absolute left-4 size-4 text-[var(--cds-text-2)]" />
				<input
					defaultValue={QUERY}
					aria-label="Search the corpus"
					className="h-12 w-full bg-transparent pr-4 pl-11 text-sm outline-none placeholder:text-[var(--cds-placeholder)]"
				/>
			</div>
			<button
				type="submit"
				className="flex h-12 items-center gap-8 bg-[#0f62fe] px-5 text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c]"
			>
				Search
				<ArrowRightIcon className="size-4" />
			</button>
		</form>
	);
}

function FilterChip({ children }: { children: React.ReactNode }) {
	return (
		<span className="inline-flex h-6 items-center gap-1.5 bg-[var(--cds-layer-selected)] px-2 text-xs">
			{children}
			<button
				type="button"
				aria-label="Remove filter"
				className="hover:opacity-70"
			>
				<XIcon className="size-3" />
			</button>
		</span>
	);
}

// ---------------------------------------------------------------------------
// Refine rail
// ---------------------------------------------------------------------------

function RailSection({
	title,
	children,
}: {
	title: string;
	children: React.ReactNode;
}) {
	return (
		<section className="border-[var(--cds-border)] border-b pb-5">
			<h3 className="pt-5 pb-3 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				{title}
			</h3>
			{children}
		</section>
	);
}

function FacetRow({
	label,
	count,
	active,
	onClick,
}: {
	label: string;
	count?: number;
	active?: boolean;
	onClick?: () => void;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"flex w-full items-center gap-2.5 border-l-[3px] py-1.5 pl-3 text-left text-sm transition-colors",
				active
					? "border-[#0f62fe] font-semibold"
					: "border-transparent text-[var(--cds-text-2)] hover:text-[var(--cds-text)]",
			)}
		>
			<span className="min-w-0 flex-1 truncate">{label}</span>
			{count !== undefined && (
				<span className="shrink-0 font-mono text-[var(--cds-helper)] text-[11px] tabular-nums">
					{count}
				</span>
			)}
		</button>
	);
}

function DecadeHistogram() {
	// In-range decades render Blue 60; out-of-range fall back to the hairline
	// gray. Single series, so identity needs no legend — the title names it.
	const max = Math.max(...DECADES.map((d) => d.count));
	const inRange = (label: string) => Number(label) >= 1860;
	return (
		<div>
			<div
				className="flex h-16 items-end gap-0.5"
				role="img"
				aria-label="Results per decade, 1860 to 2020"
			>
				{DECADES.map((d) => (
					<div
						key={d.label}
						title={`${d.label}s — ${d.count} result${d.count === 1 ? "" : "s"}`}
						className={cn(
							"min-h-1 flex-1 transition-colors",
							inRange(d.label)
								? "bg-[#0f62fe] hover:bg-[#0353e9]"
								: "bg-[var(--cds-border)]",
						)}
						style={{ height: `${Math.round((d.count / max) * 100)}%` }}
					/>
				))}
			</div>
			<div className="mt-1 flex justify-between font-mono text-[10px] text-[var(--cds-helper)]">
				<span>1860s</span>
				<span>2020s</span>
			</div>
		</div>
	);
}

function RefineRail() {
	const [contentType, setContentType] = useState("All content");
	const [court, setCourt] = useState("Any court");
	const [status, setStatus] = useState("Any status");
	const [cited, setCited] = useState<Record<string, boolean>>({});
	return (
		<aside>
			<div className="flex items-center gap-2 border-[var(--cds-border)] border-b pb-3">
				<ListFilterIcon className="size-4 text-[var(--cds-text-2)]" />
				<h2 className="font-semibold text-sm">Refine results</h2>
			</div>

			<RailSection title="Search within results">
				<div className="flex items-center border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] focus-within:outline-2 focus-within:-outline-offset-2 focus-within:outline-[#0f62fe]">
					<input
						placeholder="Search within results…"
						aria-label="Search within results"
						className="h-9 w-full bg-transparent px-3 text-[13px] outline-none placeholder:text-[var(--cds-placeholder)]"
					/>
					<SearchIcon className="mr-3 size-3.5 shrink-0 text-[var(--cds-text-2)]" />
				</div>
			</RailSection>

			<RailSection title="Content type">
				{CONTENT_TYPES.map((c) => (
					<FacetRow
						key={c.label}
						label={c.label}
						count={c.count}
						active={contentType === c.label}
						onClick={() => setContentType(c.label)}
					/>
				))}
			</RailSection>

			<RailSection title="Court">
				{COURTS.map((c) => (
					<FacetRow
						key={c.label}
						label={c.label}
						count={c.count}
						active={court === c.label}
						onClick={() => setCourt(c.label)}
					/>
				))}
			</RailSection>

			<RailSection title="Status">
				{STATUSES.map((s) => (
					<FacetRow
						key={s.label}
						label={s.label}
						count={s.count}
						active={status === s.label}
						onClick={() => setStatus(s.label)}
					/>
				))}
				<p className="mt-2 pl-3 text-[var(--cds-helper)] text-[11px] leading-snug">
					Court, status, and year apply to cases.
				</p>
			</RailSection>

			<RailSection title="Decided year">
				<DecadeHistogram />
				<div className="mt-3 grid grid-cols-2 gap-3">
					<label className="block">
						<span className="mb-1 block text-[var(--cds-helper)] text-[11px]">
							From
						</span>
						<input
							defaultValue="1860"
							inputMode="numeric"
							className="h-9 w-full border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] px-3 font-mono text-[13px] outline-none focus:outline-2 focus:-outline-offset-2 focus:outline-[#0f62fe]"
						/>
					</label>
					<label className="block">
						<span className="mb-1 block text-[var(--cds-helper)] text-[11px]">
							To
						</span>
						<input
							defaultValue="2026"
							inputMode="numeric"
							className="h-9 w-full border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] px-3 font-mono text-[13px] outline-none focus:outline-2 focus:-outline-offset-2 focus:outline-[#0f62fe]"
						/>
					</label>
				</div>
			</RailSection>

			<RailSection title="Cited authorities">
				{AUTHORITIES.map((a) => (
					<CheckboxRow
						key={a.label}
						label={
							<span className="flex items-baseline gap-2">
								<span className="min-w-0 flex-1">{a.label}</span>
								<span className="shrink-0 font-mono text-[var(--cds-helper)] text-[11px] tabular-nums">
									{a.count}
								</span>
							</span>
						}
						checked={!!cited[a.label]}
						onChange={(v) => setCited((prev) => ({ ...prev, [a.label]: v }))}
					/>
				))}
			</RailSection>
		</aside>
	);
}

// ---------------------------------------------------------------------------
// Result rows
// ---------------------------------------------------------------------------

const KIND_TAG: Record<Result["kind"], "blue" | "gray" | "outline"> = {
	Case: "blue",
	"Iowa Code": "gray",
	"Court Rules": "gray",
	Journal: "outline",
	Commentary: "outline",
};

function ResultRow({ r }: { r: Result }) {
	const treatment = r.treatment && TREATMENT_SPEC[r.treatment];
	const TreatmentIcon = treatment?.icon;
	return (
		<article className="group bg-[var(--cds-layer)] p-4 transition-colors hover:bg-[var(--cds-layer-hover)] sm:p-5">
			<div className="flex flex-wrap items-center gap-2">
				<Tag kind={KIND_TAG[r.kind]}>{r.kind}</Tag>
				{treatment && TreatmentIcon && (
					<Tag kind={treatment.kind}>
						<TreatmentIcon className="size-3" strokeWidth={2.5} />
						{treatment.label}
					</Tag>
				)}
				{r.citedBy !== undefined && (
					<span className="inline-flex items-center gap-1 font-mono text-[var(--cds-helper)] text-[11px] tabular-nums">
						<QuoteIcon className="size-3" />
						Cited by {r.citedBy.toLocaleString()}
					</span>
				)}
			</div>

			<h3 className="mt-2.5">
				<Link
					href="/app-carbon-mockup/case"
					className="font-semibold text-[15px] hover:text-[var(--cds-link)] hover:underline"
				>
					{r.title}
				</Link>
			</h3>
			<p className="mt-0.5 text-[13px] text-[var(--cds-text-2)]">
				<span className="font-mono">{r.citation}</span>
				<span className="mx-2 text-[var(--cds-helper)]">·</span>
				{r.context}
			</p>

			<p className="mt-2 line-clamp-3 max-w-3xl text-[var(--cds-text-2)] text-sm leading-relaxed">
				{r.snippet}
			</p>

			{r.paragraphs !== undefined && (
				<button
					type="button"
					className="mt-2 text-[13px] text-[var(--cds-link)] hover:underline"
				>
					Show {r.paragraphs} matching paragraphs
				</button>
			)}
		</article>
	);
}

function Pager() {
	return (
		<div className="flex items-center justify-between border border-[var(--cds-border)] border-t-0">
			<button
				type="button"
				disabled
				className="h-11 px-4 text-[var(--cds-helper)] text-sm disabled:cursor-not-allowed"
			>
				Previous
			</button>
			<span className="font-mono text-[var(--cds-helper)] text-xs tabular-nums">
				Page 1 of 8
			</span>
			<button
				type="button"
				className="flex h-11 items-center gap-3 px-4 text-[var(--cds-link)] text-sm transition-colors hover:bg-[var(--cds-layer-hover)]"
			>
				Next
				<ArrowRightIcon className="size-4" />
			</button>
		</div>
	);
}
