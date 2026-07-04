"use client";

// v2 compare editions — the Carbon edition-diff screen wired to the live
// /api/browse/{editions,compare,compare/section} endpoints. Data flow comes
// from lib/use-edition-diff.ts (shared with the legacy /browse/compare);
// this file is the Carbon skin: edition picker bar, bucket tabs + change
// list rail, and the inline / side-by-side section diff.

import { ArrowRightIcon, Columns2Icon, RowsIcon } from "lucide-react";
import { useState } from "react";
import {
	Eyebrow,
	LineTabs,
	Notification,
	SelectField,
} from "@/components/carbon/primitives";
import type { DiffSegment, SectionDiff } from "@/lib/iowa-browse";
import {
	BUCKET_LABEL,
	type Bucket,
	useEditionDiff,
} from "@/lib/use-edition-diff";
import { cn } from "@/lib/utils";

export default function V2ComparePage() {
	const {
		editions,
		fromYear,
		toYear,
		changeFrom,
		changeTo,
		loadError,
		summary,
		summaryLoading,
		bucket,
		setBucket,
		refs,
		selected,
		setSelected,
		diff,
		diffLoading,
	} = useEditionDiff({ source: "iowa-code" });
	const [view, setView] = useState<"inline" | "split">("inline");

	if (loadError) {
		return (
			<div className="px-5 py-10 sm:px-8">
				<Notification
					kind="error"
					title="Couldn't load the comparison"
					className="max-w-xl"
				>
					{loadError}
				</Notification>
			</div>
		);
	}
	if (!editions) {
		return (
			<p className="px-5 py-10 text-[var(--cds-text-2)] text-sm sm:px-8">
				Loading editions…
			</p>
		);
	}
	if (editions.length < 2) {
		return (
			<div className="px-5 py-10 sm:px-8">
				<Notification
					kind="info"
					title="Nothing to compare yet"
					className="max-w-xl"
				>
					Only one edition is loaded for this source. Load a prior edition to
					enable the year-over-year diff.
				</Notification>
			</div>
		);
	}

	const buckets: Bucket[] = ["amended", "added", "repealed"];

	return (
		<div className="flex h-full min-h-0 flex-col">
			{/* Edition picker bar */}
			<div className="flex flex-wrap items-end gap-4 border-[var(--cds-border)] border-b px-5 py-4 sm:px-8">
				<div>
					<Eyebrow>Iowa Code — edition changes</Eyebrow>
					<div className="mt-3 flex items-end gap-3">
						<SelectField
							label="From"
							options={editions.map((e) => ({
								value: String(e.year),
								label: e.label,
							}))}
							value={String(fromYear ?? "")}
							onChange={(e) => changeFrom(Number(e.target.value))}
							className="w-40"
						/>
						<ArrowRightIcon className="mb-2.5 size-4 text-[var(--cds-helper)]" />
						<SelectField
							label="To"
							options={editions.map((e) => ({
								value: String(e.year),
								label: e.label,
							}))}
							value={String(toYear ?? "")}
							onChange={(e) => changeTo(Number(e.target.value))}
							className="w-40"
						/>
					</div>
				</div>
				<p className="mb-1 ml-auto font-mono text-[11px] text-[var(--cds-helper)]">
					{fromYear != null && fromYear === toYear
						? "Pick two different editions."
						: summary
							? `${summary.covered_chapters} chapter${summary.covered_chapters === 1 ? "" : "s"} with prior-edition data`
							: ""}
				</p>
			</div>

			<div className="flex min-h-0 flex-1">
				{/* Change list */}
				<aside className="flex w-80 shrink-0 flex-col border-[var(--cds-border)] border-r">
					<div className="px-4 pt-4">
						<LineTabs
							tabs={buckets.map((b) => ({
								id: b,
								label: BUCKET_LABEL[b],
								count: summary?.counts[b],
							}))}
							value={bucket}
							onChange={setBucket}
						/>
					</div>
					<div className="min-h-0 flex-1 overflow-y-auto py-2">
						{summaryLoading ? (
							<p className="px-4 py-3 text-[var(--cds-text-2)] text-sm">
								Comparing…
							</p>
						) : refs.length === 0 ? (
							<p className="px-4 py-3 text-[var(--cds-text-2)] text-sm">
								No {BUCKET_LABEL[bucket].toLowerCase()} sections.
							</p>
						) : (
							refs.map((r) => (
								<button
									key={r.node_id}
									type="button"
									onClick={() => setSelected(r.node_id)}
									className={cn(
										"flex w-full flex-col border-l-[3px] px-4 py-2.5 text-left transition-colors",
										selected === r.node_id
											? "border-[#0f62fe] bg-[var(--cds-layer-selected)]"
											: "border-transparent hover:bg-[var(--cds-layer-hover)]",
									)}
								>
									<span className="font-mono text-[13px]">{r.citation}</span>
									<span className="truncate text-[var(--cds-text-2)] text-xs">
										{r.heading}
									</span>
								</button>
							))
						)}
					</div>
				</aside>

				{/* Diff pane */}
				<section className="min-w-0 flex-1 overflow-y-auto">
					<div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
						{selected == null ? (
							<p className="text-[var(--cds-text-2)] text-sm">
								Select a section to see what changed
								{fromYear != null && toYear != null
									? ` between ${fromYear} and ${toYear}.`
									: "."}
							</p>
						) : diffLoading || !diff ? (
							<p className="text-[var(--cds-text-2)] text-sm">Loading diff…</p>
						) : (
							<DiffView diff={diff} view={view} onView={setView} />
						)}
					</div>
				</section>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Diff renderings
// ---------------------------------------------------------------------------

function DiffView({
	diff,
	view,
	onView,
}: {
	diff: SectionDiff;
	view: "inline" | "split";
	onView: (v: "inline" | "split") => void;
}) {
	return (
		<div>
			<div className="flex flex-wrap items-end justify-between gap-4">
				<div>
					<p className="font-mono text-[13px]">{diff.citation}</p>
					{diff.heading && (
						<h1 className="mt-1 font-light text-2xl">{diff.heading}</h1>
					)}
				</div>
				<div className="flex border border-[var(--cds-border)]">
					{(
						[
							{ id: "inline", label: "Inline", icon: RowsIcon },
							{ id: "split", label: "Side by side", icon: Columns2Icon },
						] as const
					).map((v) => (
						<button
							key={v.id}
							type="button"
							onClick={() => onView(v.id)}
							className={cn(
								"flex h-9 items-center gap-2 px-3 text-[13px] transition-colors",
								view === v.id
									? "bg-[var(--cds-layer-selected)] font-semibold"
									: "text-[var(--cds-text-2)] hover:bg-[var(--cds-layer-hover)]",
							)}
						>
							<v.icon className="size-3.5" strokeWidth={1.5} />
							{v.label}
						</button>
					))}
				</div>
			</div>

			{!diff.changed && !diff.error && (
				<Notification kind="info" title="No text changes" className="mt-6">
					This section's text is identical in both editions.
				</Notification>
			)}
			{diff.error && (
				<Notification kind="warning" title="Partial diff" className="mt-6">
					{diff.error}
				</Notification>
			)}

			<div className="mt-4 flex gap-4 font-mono text-[11px] text-[var(--cds-helper)]">
				<span>
					<span className="mr-1.5 inline-block size-2.5 bg-[#24a148]/25 align-middle outline outline-1 outline-[#24a148]" />
					added in {diff.to.year}
				</span>
				<span>
					<span className="mr-1.5 inline-block size-2.5 bg-[#da1e28]/20 align-middle outline outline-1 outline-[#da1e28]" />
					removed from {diff.from.year}
				</span>
			</div>

			{view === "inline" ? (
				<p className="mt-6 whitespace-pre-wrap border border-[var(--cds-border)] bg-[var(--cds-layer)] p-6 text-[15px] leading-[1.9]">
					{diff.diff.map((s, i) => segNode(s, i))}
				</p>
			) : (
				<div className="mt-6 grid gap-px border border-[var(--cds-border)] bg-[var(--cds-border)] md:grid-cols-2">
					{(
						[
							{
								side: "from" as const,
								label: `${diff.from.year} · as of ${diff.from.as_of}`,
								present: diff.from.present,
							},
							{
								side: "to" as const,
								label: `${diff.to.year} · as of ${diff.to.as_of}`,
								present: diff.to.present,
							},
						] as const
					).map((col) => (
						<div key={col.side} className="bg-[var(--cds-layer)]">
							<p className="border-[var(--cds-border)] border-b px-5 py-2 font-mono text-[11px] text-[var(--cds-helper)]">
								{col.label}
							</p>
							<p className="whitespace-pre-wrap p-5 text-[14px] leading-[1.85]">
								{col.present ? (
									diff.diff.map((s, i) => segNode(s, i, col.side))
								) : (
									<span className="text-[var(--cds-helper)] italic">
										Not present in this edition.
									</span>
								)}
							</p>
						</div>
					))}
				</div>
			)}
		</div>
	);
}

function segNode(s: DiffSegment, i: number, side?: "from" | "to") {
	if (s.op === "equal")
		return (
			// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered diff segments
			<span key={i}>{s.text}</span>
		);
	if (s.op === "insert") {
		if (side === "from") return null;
		return (
			// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered diff segments
			<ins key={i} className="bg-[#24a148]/20 no-underline">
				{s.text}
			</ins>
		);
	}
	if (side === "to") return null;
	return (
		// biome-ignore lint/suspicious/noArrayIndexKey: static, ordered diff segments
		<del
			key={i}
			className={cn("bg-[#da1e28]/15", side === "from" && "no-underline")}
		>
			{s.text}
		</del>
	);
}
