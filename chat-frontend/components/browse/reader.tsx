"use client";

// Statute / court-rule reading surface for the corpus browser: the chapter
// index, the chapter view (its section list), the section reader (NodeView +
// structured BodyText), the right-hand metadata Sidecar, and small shared atoms
// (LoadingBlock, ActionToolbar). Pure presentational — all data + handlers
// arrive as props so app/browse/page.tsx owns the state machine. Extracted
// verbatim from the original browse page during the search-first redesign.

import {
	AlertCircleIcon,
	CheckIcon,
	CircleEllipsisIcon,
	Download,
	ExternalLinkIcon,
	GitCompareArrowsIcon,
	Loader2Icon,
	Printer,
	Share2,
} from "lucide-react";
import Link from "next/link";
import { type ReactNode, useState } from "react";
import { DocChat } from "@/components/doc-chat";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
	type BrowseChapter,
	type BrowseSource,
	type ChapterDetail,
	fmtEffective,
	type NodeDetail,
} from "@/lib/iowa-browse";
import { parseStatuteBlocks, statuteIndentRem } from "@/lib/statute-format";

export type Selection = {
	slug?: string;
	chapterId?: number;
	sectionId?: number;
};

export function LoadingBlock({ label }: { label: string }) {
	return (
		<div className="flex items-center gap-2 rounded-md border border-dashed bg-muted/30 px-4 py-10 text-muted-foreground text-sm">
			<Loader2Icon className="size-4 animate-spin" />
			<span>{label}</span>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Reading pane + sidecar
// ---------------------------------------------------------------------------

export function ReadingPane({
	sel,
	source,
	chapter,
	node,
	chapters,
	busySource,
	busyChapter,
	error,
	onSelectChapter,
	onSelectSection,
}: {
	sel: Selection;
	source: BrowseSource | null;
	chapter: ChapterDetail | null;
	node: NodeDetail | null;
	chapters: BrowseChapter[] | null;
	busySource: boolean;
	busyChapter: boolean;
	error: string | null;
	onSelectChapter: (id: number) => void;
	onSelectSection: (id: number) => void;
}) {
	return (
		<>
			<div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[1fr_280px]">
				<main className="min-w-0 overflow-y-auto px-6 py-8 md:px-10 lg:px-16">
					<div className="mx-auto max-w-3xl">
						{error && (
							<div className="mb-6 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm">
								<AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
								<span>{error}</span>
							</div>
						)}

						{sel.sectionId ? (
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
							<ChapterIndex
								source={source}
								chapters={chapters}
								busy={busySource}
								onSelectChapter={onSelectChapter}
							/>
						)}
					</div>
				</main>

				<Sidecar source={source} chapter={chapter} node={node} />
			</div>

			{/* Press "/" to chat about the open section. Keyed by node id so a new
          section starts a fresh conversation. */}
			{sel.sectionId && node ? (
				<DocChat
					key={node.id}
					nodeId={node.id}
					title={node.heading || node.citation}
					citation={node.citation}
					kind="statute"
				/>
			) : null}
		</>
	);
}

// The source's table of contents — every chapter, clickable. Replaces the old
// sidebar tree: picking a source now opens this index in the main pane.
function ChapterIndex({
	source,
	chapters,
	busy,
	onSelectChapter,
}: {
	source: BrowseSource | null;
	chapters: BrowseChapter[] | null;
	busy: boolean;
	onSelectChapter: (id: number) => void;
}) {
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

			<Separator className="my-6" />

			<h2 className="font-semibold text-muted-foreground text-xs uppercase tracking-[0.18em]">
				Chapters
			</h2>
			{busy && !chapters ? (
				<div className="mt-4">
					<LoadingBlock label="Loading chapters…" />
				</div>
			) : !chapters || chapters.length === 0 ? (
				<p className="mt-4 text-muted-foreground text-sm">
					No chapters published.
				</p>
			) : (
				<ul className="mt-3 divide-y border-y">
					{chapters.map((ch) => (
						<li key={ch.id}>
							<button
								type="button"
								onClick={() => onSelectChapter(ch.id)}
								className="group flex w-full items-baseline gap-4 py-2.5 text-left transition-colors hover:bg-muted/40"
							>
								<span className="w-16 shrink-0 font-mono font-semibold text-foreground/90 text-sm tabular-nums group-hover:text-primary">
									{ch.ordinal}
								</span>
								<span
									className={`flex-1 text-sm leading-snug ${
										ch.reserved
											? "text-muted-foreground/50 italic"
											: "text-foreground/90"
									}`}
								>
									{ch.heading || (ch.reserved ? "Reserved" : ch.ordinal)}
								</span>
								{ch.child_count > 0 && (
									<span className="shrink-0 text-muted-foreground text-xs tabular-nums">
										{ch.child_count}
									</span>
								)}
							</button>
						</li>
					))}
				</ul>
			)}
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

// Body-outline parsing lives in lib/statute-format.ts, shared with the
// Carbon v2 section reader (app/v2/section/[id]).

// Render the body text as a structured outline. Highlights any literal phrases
// listed in cross_refs so the in-text citations are visually distinct (we
// don't make them links yet — that's a Phase 2/3 enhancement).
function BodyText({
	text,
	crossRefs,
}: {
	text: string;
	crossRefs: NodeDetail["cross_refs"];
}) {
	const blocks = parseStatuteBlocks(text);
	const hasStructure = blocks.some((b) => b.marker !== null);

	// Build a single regex of all cross-ref literals (longest first so we don't
	// match a shorter substring inside a longer one).
	const phrases = [...new Set(crossRefs.map((r) => r.text))]
		.filter(Boolean)
		.sort((a, b) => b.length - a.length);
	const re =
		phrases.length > 0
			? new RegExp(
					"(" +
						phrases
							.map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
							.join("|") +
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

	// No enumerated markers: fall back to plain paragraphs (split on blank lines).
	if (!hasStructure) {
		const paragraphs = text
			.split(/\n{2,}/)
			.map((p) => p.replace(/\s+/g, " ").trim())
			.filter(Boolean);
		return (
			<article className="space-y-5 text-[15.5px] leading-relaxed">
				{paragraphs.map((p, i) => (
					// biome-ignore lint/suspicious/noArrayIndexKey: static paragraph list
					<p key={i}>{renderInline(p)}</p>
				))}
			</article>
		);
	}

	return (
		<article className="space-y-3 text-[15.5px] leading-relaxed">
			{blocks.map((b, i) =>
				b.marker === null ? (
					// biome-ignore lint/suspicious/noArrayIndexKey: stable ordered blocks
					<p key={i} style={{ marginLeft: `${statuteIndentRem(b.level)}rem` }}>
						{renderInline(b.text)}
					</p>
				) : (
					<div
						// biome-ignore lint/suspicious/noArrayIndexKey: stable ordered blocks
						key={i}
						className="flex gap-2"
						style={{ marginLeft: `${statuteIndentRem(b.level)}rem` }}
					>
						<span className="shrink-0 select-none font-medium text-muted-foreground tabular-nums">
							{b.marker}
						</span>
						<div className="flex-1">{renderInline(b.text)}</div>
					</div>
				),
			)}
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
		const url = `${window.location.origin}/browse#/${node.source_slug}/${bare}`;
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
			<Button variant="outline" size="sm" disabled={!enabled} onClick={onShare}>
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
			{enabled && node ? (
				<Button asChild variant="outline" size="sm">
					<Link
						href={`/browse/compare?node=${node.id}&path=${encodeURIComponent(
							node.path,
						)}`}
						title="Compare this section across editions"
					>
						<GitCompareArrowsIcon className="size-3.5" /> Compare
					</Link>
				</Button>
			) : (
				<Button variant="outline" size="sm" disabled>
					<GitCompareArrowsIcon className="size-3.5" /> Compare
				</Button>
			)}
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
										// biome-ignore lint/suspicious/noArrayIndexKey: static history list
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
							<h3 className="font-semibold text-foreground text-sm">Chapter</h3>
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
