"use client";

// Year-over-year edition diff for a corpus source. Self-contained: an edition
// picker (from -> to), a list of changed sections bucketed added/amended/
// repealed, and a per-section diff that toggles between an inline and a
// side-by-side view. Talks to /api/browse/{editions,compare,compare/section}.

import {
	ArrowRightIcon,
	Columns2Icon,
	Loader2Icon,
	RowsIcon,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
	type CompareRef,
	type CompareSummary,
	type DiffSegment,
	type Edition,
	fmtEffective,
	type SectionDiff,
} from "@/lib/iowa-browse";
import {
	BUCKET_LABEL,
	type Bucket,
	useEditionDiff,
} from "@/lib/use-edition-diff";

type ViewMode = "inline" | "split";

// The diff state machine lives in lib/use-edition-diff.ts, shared with the
// Carbon v2 compare screen (app/v2/compare); this file is the legacy skin.

export function EditionDiff({
	source = "iowa-code",
	initialNodeId,
	onSection,
}: {
	source?: string;
	initialNodeId?: number;
	// Reports the path of the section currently open in the diff, so a parent
	// (e.g. the page's "Browse" link) can return there. null when none is open.
	onSection?: (path: string | null) => void;
}) {
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
	} = useEditionDiff({ source, initialNodeId, onSection });
	const [view, setView] = useState<ViewMode>("inline");

	if (loadError) {
		return (
			<div className="p-6 text-sm text-destructive">
				Could not load comparison: {loadError}
			</div>
		);
	}
	if (!editions) {
		return (
			<div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
				<Loader2Icon className="size-4 animate-spin" /> Loading editions…
			</div>
		);
	}
	if (editions.length < 2) {
		return (
			<div className="p-6 text-sm text-muted-foreground">
				Only one edition is loaded for this source, so there is nothing to
				compare yet. Load a prior edition to enable the diff.
			</div>
		);
	}

	return (
		<div className="flex h-full flex-col">
			<EditionPicker
				editions={editions}
				fromYear={fromYear}
				toYear={toYear}
				onFrom={changeFrom}
				onTo={changeTo}
				coverageNote={
					summary
						? `${summary.covered_chapters} chapter${
								summary.covered_chapters === 1 ? "" : "s"
							} with prior-edition data`
						: null
				}
			/>

			<div className="flex min-h-0 flex-1">
				{/* Changes list */}
				<div className="flex w-80 shrink-0 flex-col border-r">
					<BucketTabs
						counts={summary?.counts}
						active={bucket}
						onSelect={setBucket}
					/>
					<div className="min-h-0 flex-1 overflow-y-auto">
						{summaryLoading ? (
							<div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
								<Loader2Icon className="size-4 animate-spin" /> Comparing…
							</div>
						) : (
							<ChangeList
								refs={refs}
								selected={selected}
								onSelect={setSelected}
								emptyLabel={`No ${BUCKET_LABEL[bucket].toLowerCase()} sections.`}
							/>
						)}
					</div>
				</div>

				{/* Diff pane */}
				<div className="min-h-0 flex-1 overflow-y-auto">
					{selected == null ? (
						<div className="p-8 text-sm text-muted-foreground">
							Select a section to see what changed
							{fromYear != null && toYear != null
								? ` between ${fromYear} and ${toYear}.`
								: "."}
						</div>
					) : diffLoading || !diff ? (
						<div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
							<Loader2Icon className="size-4 animate-spin" /> Loading diff…
						</div>
					) : (
						<SectionDiffView diff={diff} view={view} onView={setView} />
					)}
				</div>
			</div>
		</div>
	);
}

function EditionPicker({
	editions,
	fromYear,
	toYear,
	onFrom,
	onTo,
	coverageNote,
}: {
	editions: Edition[];
	fromYear: number | null;
	toYear: number | null;
	onFrom: (y: number) => void;
	onTo: (y: number) => void;
	coverageNote: string | null;
}) {
	return (
		<div className="flex items-center gap-3 border-b px-4 py-3 text-sm">
			<span className="font-medium">Compare editions</span>
			<EditionSelect editions={editions} value={fromYear} onChange={onFrom} />
			<ArrowRightIcon className="size-4 text-muted-foreground" />
			<EditionSelect editions={editions} value={toYear} onChange={onTo} />
			{fromYear != null && fromYear === toYear ? (
				<span className="text-destructive">Pick two different editions.</span>
			) : null}
			{coverageNote ? (
				<span className="ml-auto text-xs text-muted-foreground">
					{coverageNote}
				</span>
			) : null}
		</div>
	);
}

function EditionSelect({
	editions,
	value,
	onChange,
}: {
	editions: Edition[];
	value: number | null;
	onChange: (y: number) => void;
}) {
	return (
		<select
			className="rounded-md border bg-background px-2 py-1"
			value={value ?? ""}
			onChange={(e) => onChange(Number(e.target.value))}
		>
			{editions.map((e) => (
				<option key={e.year} value={e.year}>
					{e.label}
				</option>
			))}
		</select>
	);
}

function BucketTabs({
	counts,
	active,
	onSelect,
}: {
	counts: CompareSummary["counts"] | undefined;
	active: Bucket;
	onSelect: (b: Bucket) => void;
}) {
	const buckets: Bucket[] = ["amended", "added", "repealed"];
	return (
		<div className="flex border-b text-sm">
			{buckets.map((b) => (
				<button
					type="button"
					key={b}
					onClick={() => onSelect(b)}
					className={`flex-1 px-2 py-2 ${
						active === b
							? "border-b-2 border-primary font-medium"
							: "text-muted-foreground hover:text-foreground"
					}`}
				>
					{BUCKET_LABEL[b]}
					{counts ? (
						<span className="ml-1 text-xs text-muted-foreground">
							{counts[b]}
						</span>
					) : null}
				</button>
			))}
		</div>
	);
}

function ChangeList({
	refs,
	selected,
	onSelect,
	emptyLabel,
}: {
	refs: CompareRef[];
	selected: number | null;
	onSelect: (id: number) => void;
	emptyLabel: string;
}) {
	if (!refs.length) {
		return (
			<div className="p-4 text-sm text-muted-foreground">{emptyLabel}</div>
		);
	}
	return (
		<ul>
			{refs.map((r) => (
				<li key={r.node_id}>
					<button
						type="button"
						onClick={() => onSelect(r.node_id)}
						className={`block w-full px-4 py-2 text-left text-sm hover:bg-muted ${
							selected === r.node_id ? "bg-muted" : ""
						}`}
					>
						<span className="font-medium">{r.citation}</span>
						{r.heading ? (
							<span className="ml-1 text-muted-foreground">{r.heading}</span>
						) : null}
					</button>
				</li>
			))}
		</ul>
	);
}

function SectionDiffView({
	diff,
	view,
	onView,
}: {
	diff: SectionDiff;
	view: ViewMode;
	onView: (v: ViewMode) => void;
}) {
	return (
		<div className="flex h-full flex-col">
			<div className="flex items-center justify-between border-b px-4 py-3">
				<div>
					<div className="font-medium">{diff.citation}</div>
					{diff.heading ? (
						<div className="text-sm text-muted-foreground">{diff.heading}</div>
					) : null}
				</div>
				<div className="flex gap-1">
					<Button
						variant={view === "inline" ? "secondary" : "ghost"}
						size="sm"
						onClick={() => onView("inline")}
					>
						<RowsIcon className="size-4" /> Inline
					</Button>
					<Button
						variant={view === "split" ? "secondary" : "ghost"}
						size="sm"
						onClick={() => onView("split")}
					>
						<Columns2Icon className="size-4" /> Side by side
					</Button>
				</div>
			</div>

			{!diff.changed ? (
				<div className="p-4 text-sm text-muted-foreground">
					No textual change between these editions.
				</div>
			) : view === "inline" ? (
				<InlineDiff segments={diff.diff} />
			) : (
				<SplitDiff diff={diff} />
			)}
		</div>
	);
}

function InlineDiff({ segments }: { segments: DiffSegment[] }) {
	return (
		<div className="overflow-y-auto whitespace-pre-wrap p-4 font-serif text-sm leading-relaxed">
			{segments.map((seg, i) =>
				seg.op === "equal" ? (
					// biome-ignore lint/suspicious/noArrayIndexKey: segments are a stable ordered diff
					<span key={i}>{seg.text}</span>
				) : seg.op === "insert" ? (
					<span
						// biome-ignore lint/suspicious/noArrayIndexKey: stable ordered diff
						key={i}
						className="rounded bg-green-500/20 text-green-900 dark:text-green-200"
					>
						{seg.text}
					</span>
				) : (
					<span
						// biome-ignore lint/suspicious/noArrayIndexKey: stable ordered diff
						key={i}
						className="rounded bg-red-500/20 text-red-900 line-through dark:text-red-200"
					>
						{seg.text}
					</span>
				),
			)}
		</div>
	);
}

function SplitDiff({ diff }: { diff: SectionDiff }) {
	// Left column shows the "from" text (equal + deletions); right shows "to"
	// (equal + insertions). Reuses the same word-level segments.
	return (
		<div className="grid min-h-0 flex-1 grid-cols-2 divide-x overflow-y-auto">
			<DiffColumn
				label={`${diff.from.year} · ${fmtEffective(diff.from.as_of)}`}
				present={diff.from.present}
				segments={diff.diff.filter((s) => s.op !== "insert")}
				changeOp="delete"
			/>
			<DiffColumn
				label={`${diff.to.year} · ${fmtEffective(diff.to.as_of)}`}
				present={diff.to.present}
				segments={diff.diff.filter((s) => s.op !== "delete")}
				changeOp="insert"
			/>
		</div>
	);
}

function DiffColumn({
	label,
	present,
	segments,
	changeOp,
}: {
	label: string;
	present: boolean;
	segments: DiffSegment[];
	changeOp: "insert" | "delete";
}) {
	const changeClass =
		changeOp === "insert"
			? "rounded bg-green-500/20 text-green-900 dark:text-green-200"
			: "rounded bg-red-500/20 text-red-900 line-through dark:text-red-200";
	return (
		<div className="p-4">
			<div className="mb-2 text-xs font-medium uppercase text-muted-foreground">
				{label}
				{!present ? " · not present" : ""}
			</div>
			<div className="whitespace-pre-wrap font-serif text-sm leading-relaxed">
				{segments.map((seg, i) => (
					<span
						// biome-ignore lint/suspicious/noArrayIndexKey: stable ordered diff
						key={i}
						className={seg.op === "equal" ? "" : changeClass}
					>
						{seg.text}
					</span>
				))}
			</div>
		</div>
	);
}
