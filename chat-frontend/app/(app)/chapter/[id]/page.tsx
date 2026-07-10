"use client";

// Chapter view — /api/browse/chapters/<id>: the chapter's heading and its
// section list, each row opening the section reader.

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Eyebrow, Notification } from "@/components/carbon/primitives";
import { browseChapter, type ChapterDetail } from "@/lib/iowa-browse";

export default function V2ChapterPage() {
	const params = useParams<{ id: string }>();
	const chapterId = /^\d+$/.test(params.id) ? Number(params.id) : Number.NaN;

	const [chapter, setChapter] = useState<ChapterDetail | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		if (!Number.isFinite(chapterId)) {
			setError("Invalid chapter id.");
			return;
		}
		let cancelled = false;
		setChapter(null);
		setError(null);
		browseChapter(chapterId)
			.then((c) => !cancelled && setChapter(c))
			.catch(
				(e) =>
					!cancelled &&
					setError(e instanceof Error ? e.message : "Failed to load chapter."),
			);
		return () => {
			cancelled = true;
		};
	}, [chapterId]);

	if (!chapter) {
		return (
			<div className="px-5 py-10 sm:px-8">
				{error ? (
					<Notification
						kind="error"
						title="Couldn't load this chapter"
						className="max-w-xl"
					>
						{error}
					</Notification>
				) : (
					<p className="text-[var(--cds-text-2)] text-sm">Loading chapter…</p>
				)}
			</div>
		);
	}

	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<nav className="text-sm">
				<Link
					href="/"
					className="text-[var(--cds-text-2)] hover:text-[var(--cds-link)] hover:underline"
				>
					Library
				</Link>
				<span className="mx-2 text-[var(--cds-helper)]">/</span>
				<Link
					href={`/source/${chapter.source_slug}`}
					className="text-[var(--cds-text-2)] hover:text-[var(--cds-link)] hover:underline"
				>
					{chapter.source_slug === "iowa-court-rules"
						? "Iowa Court Rules"
						: chapter.source_slug === "iowa-admin-code"
							? "Iowa Admin. Code"
							: "Iowa Code"}
				</Link>
				<span className="mx-2 text-[var(--cds-helper)]">/</span>
				<span className="font-semibold">{chapter.ordinal}</span>
			</nav>

			<header className="mt-8">
				<Eyebrow>{chapter.citation}</Eyebrow>
				<h1 className="mt-4 font-light text-3xl sm:text-4xl">
					{chapter.heading || chapter.ordinal}
				</h1>
				{chapter.reserved && (
					<p className="mt-3 text-[var(--cds-text-2)] text-sm italic">
						This chapter is reserved.
					</p>
				)}
			</header>

			<p className="mt-10 border-[var(--cds-border)] border-t pt-5 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				{chapter.source_slug === "iowa-admin-code" ? "Rules" : "Sections"} in
				this chapter — {chapter.children.length}
			</p>
			{chapter.children.length === 0 ? (
				<p className="mt-4 text-[var(--cds-text-2)] text-sm">
					No sections published.
				</p>
			) : (
				<div className="mt-4 divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]">
					{chapter.children.map((c) => (
						<Link
							key={c.id}
							href={`/section/${c.id}`}
							className="group flex items-baseline gap-4 bg-[var(--cds-layer)] px-4 py-2.5 transition-colors hover:bg-[var(--cds-layer-hover)]"
						>
							<span className="w-20 shrink-0 font-mono text-[13px] tabular-nums group-hover:text-[var(--cds-link)]">
								{c.citation.trim().split(/\s+/).pop() || c.ordinal}
							</span>
							<span className="min-w-0 flex-1 text-sm leading-snug group-hover:underline">
								{c.heading || c.ordinal}
							</span>
							{c.division && (
								<span className="hidden shrink-0 text-[var(--cds-helper)] text-xs sm:block">
									{c.division}
								</span>
							)}
						</Link>
					))}
				</div>
			)}
		</div>
	);
}
