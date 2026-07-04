"use client";

// Source view — kind-routed like the legacy browse: a statutes-kind source
// (Iowa Code, Court Rules) shows its chapter index; the caselaw source shows
// recent decisions with court facets (search stays the primary way in).

import { ArrowRightIcon, SearchIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
	BtnGhost,
	Eyebrow,
	Notification,
} from "@/components/carbon/primitives";
import {
	type BrowseChapter,
	type BrowseSource,
	browseCases,
	browseChapters,
	browseSources,
	type CaseListResponse,
	fmtEffective,
} from "@/lib/iowa-browse";
import { cn } from "@/lib/utils";

export default function V2SourcePage() {
	const params = useParams<{ slug: string }>();
	const slug = params.slug;

	const [source, setSource] = useState<BrowseSource | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let cancelled = false;
		setSource(null);
		setError(null);
		browseSources()
			.then((all) => {
				if (cancelled) return;
				const s = all.find((x) => x.slug === slug);
				if (s) setSource(s);
				else setError(`Unknown source “${slug}”.`);
			})
			.catch(
				(e) =>
					!cancelled &&
					setError(e instanceof Error ? e.message : "Failed to load source."),
			);
		return () => {
			cancelled = true;
		};
	}, [slug]);

	if (!source) {
		return (
			<div className="px-5 py-10 sm:px-8">
				{error ? (
					<Notification
						kind="error"
						title="Couldn't open this source"
						className="max-w-xl"
					>
						{error}
					</Notification>
				) : (
					<p className="text-[var(--cds-text-2)] text-sm">Loading source…</p>
				)}
			</div>
		);
	}

	return source.kind === "caselaw" ? (
		<CaselawIndex source={source} />
	) : (
		<ChapterIndex source={source} />
	);
}

function SourceHeader({ source }: { source: BrowseSource }) {
	return (
		<>
			<nav className="text-sm">
				<Link
					href="/"
					className="text-[var(--cds-text-2)] hover:text-[var(--cds-link)] hover:underline"
				>
					Library
				</Link>
				<span className="mx-2 text-[var(--cds-helper)]">/</span>
				<span className="font-semibold">{source.name}</span>
			</nav>
			<header className="mt-8">
				<Eyebrow>{source.jurisdiction}</Eyebrow>
				<h1 className="mt-4 font-light text-3xl sm:text-4xl">{source.name}</h1>
				<p className="mt-3 text-[15px] text-[var(--cds-text-2)]">
					{source.has_chapters &&
						`${source.chapters.toLocaleString()} chapters · `}
					{source.entries.toLocaleString()} {source.entry_label.toLowerCase()}
				</p>
			</header>
		</>
	);
}

// ---------------------------------------------------------------------------
// Statutes / rules — chapter index
// ---------------------------------------------------------------------------

function ChapterIndex({ source }: { source: BrowseSource }) {
	const [chapters, setChapters] = useState<BrowseChapter[] | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let cancelled = false;
		browseChapters(source.slug)
			.then((r) => !cancelled && setChapters(r.chapters))
			.catch((e) => !cancelled && setError((e as Error).message));
		return () => {
			cancelled = true;
		};
	}, [source.slug]);

	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<SourceHeader source={source} />

			<p className="mt-10 border-[var(--cds-border)] border-t pt-5 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				Chapters
			</p>
			{error ? (
				<Notification
					kind="error"
					title="Couldn't load chapters"
					className="mt-4"
				>
					{error}
				</Notification>
			) : !chapters ? (
				<p className="mt-4 text-[var(--cds-text-2)] text-sm">
					Loading chapters…
				</p>
			) : chapters.length === 0 ? (
				<p className="mt-4 text-[var(--cds-text-2)] text-sm">
					No chapters published.
				</p>
			) : (
				<div className="mt-4 divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]">
					{chapters.map((ch) => (
						<Link
							key={ch.id}
							href={`/chapter/${ch.id}`}
							className="group flex items-baseline gap-4 bg-[var(--cds-layer)] px-4 py-2.5 transition-colors hover:bg-[var(--cds-layer-hover)]"
						>
							<span className="w-16 shrink-0 font-mono text-[13px] tabular-nums group-hover:text-[var(--cds-link)]">
								{ch.ordinal}
							</span>
							<span
								className={cn(
									"min-w-0 flex-1 text-sm leading-snug",
									ch.reserved
										? "text-[var(--cds-helper)] italic"
										: "group-hover:underline",
								)}
							>
								{ch.heading || (ch.reserved ? "Reserved" : ch.ordinal)}
							</span>
							{ch.child_count > 0 && (
								<span className="shrink-0 font-mono text-[var(--cds-helper)] text-xs tabular-nums">
									{ch.child_count}
								</span>
							)}
						</Link>
					))}
				</div>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Caselaw — recent decisions with court facets; search is the main way in.
// ---------------------------------------------------------------------------

const PAGE = 25;

function CaselawIndex({ source }: { source: BrowseSource }) {
	const [court, setCourt] = useState("");
	const [data, setData] = useState<CaseListResponse | null>(null);
	const [offset, setOffset] = useState(0);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(false);

	useEffect(() => {
		let cancelled = false;
		setLoading(true);
		setError(null);
		browseCases({
			court: court || null,
			limit: PAGE,
			offset,
			facets: offset === 0,
		})
			.then((r) =>
				!cancelled
					? setData((prev) =>
							offset > 0 && prev
								? {
										...r,
										results: [...prev.results, ...r.results],
										facets: prev.facets ?? r.facets,
									}
								: r,
						)
					: undefined,
			)
			.catch((e) => !cancelled && setError((e as Error).message))
			.finally(() => !cancelled && setLoading(false));
		return () => {
			cancelled = true;
		};
	}, [court, offset]);

	const pickCourt = (id: string) => {
		setData(null);
		setOffset(0);
		setCourt(id);
	};

	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<SourceHeader source={source} />

			<div className="mt-6">
				<Link
					href="/results?q=&doc_type=cases"
					className="inline-flex items-center gap-1.5 font-medium text-[13px] text-[var(--cds-link)] hover:underline"
				>
					<SearchIcon className="size-3.5" />
					Search case law
				</Link>
			</div>

			<div className="mt-8 flex flex-wrap items-center gap-2 border-[var(--cds-border)] border-t pt-5">
				<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
					Court
				</span>
				<FacetChip active={court === ""} onClick={() => pickCourt("")}>
					All courts
				</FacetChip>
				{(data?.facets?.courts ?? []).map((c) => (
					<FacetChip
						key={c.court_id}
						active={court === c.court_id}
						onClick={() => pickCourt(c.court_id)}
					>
						{c.court_name}
						<span className="ml-1.5 font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
							{c.count.toLocaleString()}
						</span>
					</FacetChip>
				))}
			</div>

			<p className="mt-8 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				Recent decisions
			</p>
			{error ? (
				<Notification
					kind="error"
					title="Couldn't load decisions"
					className="mt-4"
				>
					{error}
				</Notification>
			) : !data ? (
				<p className="mt-4 text-[var(--cds-text-2)] text-sm">
					Loading decisions…
				</p>
			) : (
				<>
					<div className="mt-4 divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]">
						{data.results.map((c) => (
							<Link
								key={c.id}
								href={`/case/${c.id}`}
								className="group block bg-[var(--cds-layer)] px-4 py-3 transition-colors hover:bg-[var(--cds-layer-hover)]"
							>
								<span className="block truncate font-medium text-sm group-hover:underline">
									{c.case_name}
								</span>
								<span className="mt-0.5 block truncate text-[var(--cds-text-2)] text-xs">
									{[
										c.citations.join(" · "),
										c.court_name,
										c.date_filed ? fmtEffective(c.date_filed) : "",
									]
										.filter(Boolean)
										.join("  ·  ")}
								</span>
							</Link>
						))}
					</div>
					{data.has_more && (
						<div className="mt-4">
							<BtnGhost
								disabled={loading}
								onClick={() => setOffset(offset + PAGE)}
							>
								{loading ? "Loading…" : "Load more"}
								<ArrowRightIcon className="size-4" />
							</BtnGhost>
						</div>
					)}
				</>
			)}
		</div>
	);
}

function FacetChip({
	active,
	onClick,
	children,
}: {
	active: boolean;
	onClick: () => void;
	children: React.ReactNode;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"flex h-8 items-center px-3 text-[13px] transition-colors",
				active
					? "bg-[var(--cds-layer-selected)] font-semibold"
					: "border border-[var(--cds-border)] text-[var(--cds-text-2)] hover:bg-[var(--cds-layer-hover)]",
			)}
		>
			{children}
		</button>
	);
}
