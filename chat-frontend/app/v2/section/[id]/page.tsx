"use client";

// v2 statute/rule section reader — /api/browse/nodes/<id> rendered in Carbon:
// breadcrumb toolbar (with copy-citation / compare / print), the enumerated
// body outline (parsing shared with the legacy pane via lib/statute-format),
// and a metadata rail (citation, official source, in-text citations, history,
// neighboring sections). Improves on the legacy pane in one way: in-text
// citations are real links to their target sections, not just highlights.

import {
	CheckIcon,
	CopyIcon,
	ExternalLinkIcon,
	GitCompareArrowsIcon,
	PrinterIcon,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import {
	KVList,
	Notification,
	Panel,
	Tag,
} from "@/components/carbon/primitives";
import {
	browseChapter,
	browseNode,
	type ChapterDetail,
	fmtEffective,
	type NodeDetail,
} from "@/lib/iowa-browse";
import { parseStatuteBlocks, statuteIndentRem } from "@/lib/statute-format";

export default function V2SectionPage() {
	const params = useParams<{ id: string }>();
	const nodeId = /^\d+$/.test(params.id) ? Number(params.id) : Number.NaN;

	const [node, setNode] = useState<NodeDetail | null>(null);
	const [chapter, setChapter] = useState<ChapterDetail | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		if (!Number.isFinite(nodeId)) {
			setError("Invalid section id.");
			setLoading(false);
			return;
		}
		let cancelled = false;
		setLoading(true);
		setError(null);
		setNode(null);
		setChapter(null);
		browseNode(nodeId)
			.then((n) => {
				if (cancelled) return;
				setNode(n);
				// Chapter powers the breadcrumb heading + neighboring sections;
				// best-effort, the reader works without it.
				if (n.chapter) {
					browseChapter(n.chapter.id)
						.then((c) => !cancelled && setChapter(c))
						.catch(() => {});
				}
			})
			.catch(
				(e) =>
					!cancelled &&
					setError(e instanceof Error ? e.message : "Failed to load section."),
			)
			.finally(() => !cancelled && setLoading(false));
		return () => {
			cancelled = true;
		};
	}, [nodeId]);

	if (!node) {
		return (
			<div className="px-5 py-10 sm:px-8">
				{error ? (
					<Notification
						kind="error"
						title="Couldn't load this section"
						className="max-w-xl"
					>
						{error}
					</Notification>
				) : loading ? (
					<p className="text-[var(--cds-text-2)] text-sm">Loading section…</p>
				) : null}
			</div>
		);
	}

	return <SectionReader node={node} chapter={chapter} />;
}

function SectionReader({
	node,
	chapter,
}: {
	node: NodeDetail;
	chapter: ChapterDetail | null;
}) {
	const [copied, setCopied] = useState(false);
	const tail = node.citation.trim().split(/\s+/).pop() || node.citation;

	const copyCitation = async () => {
		try {
			await navigator.clipboard.writeText(node.citation);
			setCopied(true);
			setTimeout(() => setCopied(false), 1500);
		} catch {
			/* clipboard unavailable */
		}
	};

	// Neighboring sections in the same chapter (±2 around this one).
	const neighbors = useMemo(() => {
		if (!chapter) return [];
		const idx = chapter.children.findIndex((c) => c.id === node.id);
		if (idx < 0) return chapter.children.slice(0, 5);
		const start = Math.max(0, idx - 2);
		return chapter.children.slice(start, start + 5);
	}, [chapter, node.id]);

	return (
		<div className="flex h-full min-h-0 flex-col">
			{/* Toolbar */}
			<div className="flex h-12 shrink-0 items-center gap-1 border-[var(--cds-border)] border-b px-5 print:hidden sm:px-8">
				<p className="min-w-0 truncate text-sm">
					<Link
						href="/v2"
						className="text-[var(--cds-text-2)] hover:text-[var(--cds-link)] hover:underline"
					>
						Library
					</Link>
					<span className="mx-2 text-[var(--cds-helper)]">/</span>
					<Link
						href={`/v2/source/${node.source_slug}`}
						className="text-[var(--cds-text-2)] hover:text-[var(--cds-link)] hover:underline"
					>
						{node.source}
					</Link>
					{node.chapter && (
						<>
							<span className="mx-2 text-[var(--cds-helper)]">/</span>
							<Link
								href={`/v2/chapter/${node.chapter.id}`}
								className="text-[var(--cds-text-2)] hover:text-[var(--cds-link)] hover:underline"
							>
								{node.chapter.citation}
							</Link>
						</>
					)}
					<span className="mx-2 text-[var(--cds-helper)]">/</span>
					<span className="font-semibold">{tail}</span>
				</p>
				<div className="ml-auto flex shrink-0 items-center gap-1">
					<ToolbarButton onClick={copyCitation}>
						{copied ? (
							<CheckIcon className="size-4 text-[var(--cds-success-text)]" />
						) : (
							<CopyIcon className="size-4" />
						)}
						{copied ? "Copied" : "Copy citation"}
					</ToolbarButton>
					{node.source_slug === "iowa-code" && (
						<Link
							href={`/v2/compare?node=${node.id}`}
							className="flex h-9 items-center gap-2 px-3 text-[13px] text-[var(--cds-text-2)] transition-colors hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]"
						>
							<GitCompareArrowsIcon className="size-4" />
							Compare editions
						</Link>
					)}
					<ToolbarButton onClick={() => window.print()}>
						<PrinterIcon className="size-4" />
						Print
					</ToolbarButton>
				</div>
			</div>

			<div className="flex min-h-0 flex-1">
				{/* Center — the section */}
				<article
					aria-label={node.citation}
					className="min-w-0 flex-1 overflow-y-auto print:overflow-visible"
				>
					<div className="mx-auto max-w-3xl px-5 py-10 sm:px-8">
						<header>
							<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.22em]">
								{node.source}
								{node.chapter ? ` · ${node.chapter.citation}` : ""}
							</p>
							<h1 className="mt-3 font-light text-3xl sm:text-4xl">
								<span className="font-mono text-[0.85em] tabular-nums">
									{tail}
								</span>
								{node.heading && <> — {node.heading}</>}
							</h1>
							<p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--cds-text-2)]">
								{node.effective_from && (
									<span>Effective {fmtEffective(node.effective_from)}</span>
								)}
								<Tag kind="gray">Currently effective</Tag>
							</p>
						</header>

						<div className="mt-8 border-[var(--cds-border)] border-t pt-8">
							{node.has_content ? (
								<StatuteBody
									text={node.body_text}
									crossRefs={node.cross_refs}
								/>
							) : (
								<p className="text-[var(--cds-text-2)] text-sm italic">
									No body text is published for this section.
								</p>
							)}
						</div>

						{node.history.length > 0 && (
							<div className="mt-10 border-[var(--cds-border)] border-t pt-5">
								<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
									History
								</p>
								<ul className="mt-3 space-y-1 text-[13px] text-[var(--cds-text-2)]">
									{node.history.map((h, i) => (
										// biome-ignore lint/suspicious/noArrayIndexKey: static history list
										<li key={i}>{h}</li>
									))}
								</ul>
							</div>
						)}
					</div>
				</article>

				{/* Right rail — metadata */}
				<aside
					aria-label="Section metadata"
					className="hidden w-80 shrink-0 space-y-6 overflow-y-auto border-[var(--cds-border)] border-l p-5 print:hidden xl:block"
				>
					<Panel title="Citation">
						<p className="px-4 py-3 font-mono text-[13px]">{node.citation}</p>
						{node.official_url && (
							<a
								href={node.official_url}
								target="_blank"
								rel="noopener noreferrer"
								className="flex items-center gap-1.5 border-[var(--cds-border)] border-t px-4 py-2.5 text-[13px] text-[var(--cds-link)] transition-colors hover:bg-[var(--cds-layer-hover)]"
							>
								Official source — legis.iowa.gov
								<ExternalLinkIcon className="size-3.5" />
							</a>
						)}
					</Panel>

					{node.cross_refs.length > 0 && (
						<Panel title="In-text citations">
							<div className="divide-y divide-[var(--cds-border)]">
								{node.cross_refs.slice(0, 8).map((r, i) => (
									<Link
										// biome-ignore lint/suspicious/noArrayIndexKey: cross-refs can repeat a node
										key={`${r.node_id}-${i}`}
										href={`/v2/section/${r.node_id}`}
										className="block px-4 py-2.5 font-mono text-[13px] transition-colors hover:bg-[var(--cds-layer-hover)] hover:underline"
									>
										{r.text}
									</Link>
								))}
							</div>
						</Panel>
					)}

					{neighbors.length > 0 && (
						<Panel title="In this chapter">
							<div className="divide-y divide-[var(--cds-border)]">
								{neighbors.map((c) => (
									<Link
										key={c.id}
										href={`/v2/section/${c.id}`}
										className={`block px-4 py-2.5 transition-colors hover:bg-[var(--cds-layer-hover)] ${
											c.id === node.id ? "bg-[var(--cds-layer-selected)]" : ""
										}`}
									>
										<span className="block font-mono text-[13px]">
											{c.citation.trim().split(/\s+/).pop() || c.ordinal}
										</span>
										<span className="block truncate text-[var(--cds-text-2)] text-xs">
											{c.heading || c.ordinal}
										</span>
									</Link>
								))}
							</div>
							{chapter && (
								<Link
									href={`/v2/chapter/${chapter.id}`}
									className="block border-[var(--cds-border)] border-t px-4 py-2.5 text-[13px] text-[var(--cds-link)] transition-colors hover:bg-[var(--cds-layer-hover)]"
								>
									All of {chapter.citation}
								</Link>
							)}
						</Panel>
					)}

					<Panel title="Section facts">
						<KVList
							rows={[
								["Type", node.type],
								["In-text citations", String(node.cross_refs.length)],
								["History entries", String(node.history.length)],
							]}
						/>
					</Panel>
				</aside>
			</div>
		</div>
	);
}

function ToolbarButton({
	children,
	...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
	return (
		<button
			type="button"
			{...props}
			className="flex h-9 items-center gap-2 px-3 text-[13px] text-[var(--cds-text-2)] transition-colors hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]"
		>
			{children}
		</button>
	);
}

// ---------------------------------------------------------------------------
// Body — enumerated outline with linked in-text citations
// ---------------------------------------------------------------------------

function StatuteBody({
	text,
	crossRefs,
}: {
	text: string;
	crossRefs: NodeDetail["cross_refs"];
}) {
	const blocks = useMemo(() => parseStatuteBlocks(text), [text]);
	const hasStructure = blocks.some((b) => b.marker !== null);

	// Map each cross-ref literal to its target section, longest phrase first so
	// a shorter cite never swallows part of a longer one.
	const refs = useMemo(() => {
		const byText = new Map<string, number>();
		for (const r of crossRefs) {
			if (r.text && !byText.has(r.text)) byText.set(r.text, r.node_id);
		}
		return [...byText.entries()].sort((a, b) => b[0].length - a[0].length);
	}, [crossRefs]);

	const re = useMemo(
		() =>
			refs.length > 0
				? new RegExp(
						`(${refs
							.map(([t]) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
							.join("|")})`,
						"g",
					)
				: null,
		[refs],
	);

	const renderInline = (s: string): ReactNode[] => {
		if (!re) return [s];
		const out: ReactNode[] = [];
		let last = 0;
		re.lastIndex = 0;
		let m: RegExpExecArray | null = re.exec(s);
		let i = 0;
		while (m !== null) {
			if (m.index > last) out.push(s.slice(last, m.index));
			const target = refs.find(([t]) => t === m?.[0])?.[1];
			out.push(
				target != null ? (
					<Link
						key={`xr-${i++}`}
						href={`/v2/section/${target}`}
						className="text-[var(--cds-link)] hover:underline"
					>
						{m[0]}
					</Link>
				) : (
					m[0]
				),
			);
			last = m.index + m[0].length;
			m = re.exec(s);
		}
		if (last < s.length) out.push(s.slice(last));
		return out;
	};

	// No enumerated markers: plain paragraphs split on blank lines.
	if (!hasStructure) {
		const paragraphs = text
			.split(/\n{2,}/)
			.map((p) => p.replace(/\s+/g, " ").trim())
			.filter(Boolean);
		return (
			<div className="space-y-5 text-[15.5px] leading-relaxed">
				{paragraphs.map((p, i) => (
					// biome-ignore lint/suspicious/noArrayIndexKey: static paragraph list
					<p key={i}>{renderInline(p)}</p>
				))}
			</div>
		);
	}

	return (
		<div className="space-y-3 text-[15.5px] leading-relaxed">
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
						<span className="shrink-0 select-none font-medium font-mono text-[var(--cds-helper)] tabular-nums">
							{b.marker}
						</span>
						<div className="flex-1">{renderInline(b.text)}</div>
					</div>
				),
			)}
		</div>
	);
}
