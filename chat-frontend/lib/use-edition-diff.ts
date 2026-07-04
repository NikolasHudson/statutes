"use client";

// State machine for the year-over-year edition diff, shared by the legacy
// component (components/edition-diff.tsx) and the Carbon v2 compare screen
// (app/v2/compare) so the data flow can't drift between skins. Talks to
// /api/browse/{editions,compare,compare/section}.

import { useEffect, useMemo, useState } from "react";
import {
	browseCompare,
	browseCompareSection,
	browseEditions,
	type CompareRef,
	type CompareSummary,
	type Edition,
	type SectionDiff,
} from "@/lib/iowa-browse";

export type Bucket = "amended" | "added" | "repealed";

export const BUCKET_LABEL: Record<Bucket, string> = {
	amended: "Amended",
	added: "Added",
	repealed: "Repealed",
};

export function useEditionDiff({
	source,
	initialNodeId,
	onSection,
}: {
	source: string;
	initialNodeId?: number;
	// Reports the path of the section currently open in the diff, so a parent
	// (e.g. the page's "Browse" link) can return there. null when none is open.
	onSection?: (path: string | null) => void;
}) {
	const [editions, setEditions] = useState<Edition[] | null>(null);
	const [fromYear, setFromYear] = useState<number | null>(null);
	const [toYear, setToYear] = useState<number | null>(null);
	const [loadError, setLoadError] = useState<string | null>(null);

	const [summary, setSummary] = useState<CompareSummary | null>(null);
	const [summaryLoading, setSummaryLoading] = useState(false);
	const [bucket, setBucket] = useState<Bucket>("amended");

	// Seed the selection from a deep-link (?node=…) so opening "Compare" from a
	// section jumps straight to that section's diff.
	const [selected, setSelected] = useState<number | null>(
		initialNodeId ?? null,
	);
	const [diff, setDiff] = useState<SectionDiff | null>(null);
	const [diffLoading, setDiffLoading] = useState(false);

	// Clearing the selection lives in the picker handlers (not the summary
	// effect) so a deep-linked initial selection survives the first load.
	const changeFrom = (y: number) => {
		setSelected(null);
		setDiff(null);
		setFromYear(y);
	};
	const changeTo = (y: number) => {
		setSelected(null);
		setDiff(null);
		setToYear(y);
	};

	// Load the edition list once and seed the default comparison.
	useEffect(() => {
		let alive = true;
		browseEditions(source)
			.then((r) => {
				if (!alive) return;
				setEditions(r.editions);
				if (r.default) {
					setFromYear(r.default.from_year);
					setToYear(r.default.to_year);
				} else if (r.editions.length) {
					setFromYear(r.editions[r.editions.length - 1].year);
					setToYear(r.editions[0].year);
				}
			})
			.catch((e) => alive && setLoadError(String(e?.message ?? e)));
		return () => {
			alive = false;
		};
	}, [source]);

	// Fetch the change summary whenever the comparison pair changes.
	useEffect(() => {
		if (fromYear == null || toYear == null || fromYear === toYear) return;
		let alive = true;
		setSummaryLoading(true);
		browseCompare(source, fromYear, toYear)
			.then((r) => alive && setSummary(r))
			.catch((e) => alive && setLoadError(String(e?.message ?? e)))
			.finally(() => alive && setSummaryLoading(false));
		return () => {
			alive = false;
		};
	}, [source, fromYear, toYear]);

	// When a section is preselected (deep link), switch to the bucket that
	// contains it so the list highlights the open section.
	useEffect(() => {
		if (selected == null || !summary) return;
		const found = (["amended", "added", "repealed"] as Bucket[]).find((b) =>
			summary[b].some((r) => r.node_id === selected),
		);
		if (found) setBucket(found);
	}, [selected, summary]);

	// Fetch the per-section diff when a section is opened.
	// biome-ignore lint/correctness/useExhaustiveDependencies: onSection is a stable setter from the parent; excluded to avoid refetch
	useEffect(() => {
		if (selected == null || fromYear == null || toYear == null) return;
		let alive = true;
		setDiffLoading(true);
		browseCompareSection(selected, fromYear, toYear)
			.then((r) => {
				if (!alive) return;
				setDiff(r);
				onSection?.(r.path);
			})
			.catch((e) => alive && setLoadError(String(e?.message ?? e)))
			.finally(() => alive && setDiffLoading(false));
		return () => {
			alive = false;
		};
	}, [selected, fromYear, toYear]);

	const refs: CompareRef[] = useMemo(
		() => (summary ? summary[bucket] : []),
		[summary, bucket],
	);

	return {
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
	};
}
