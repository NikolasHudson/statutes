"use client";

// v2 Library home — the search-first entry to the corpus, wired to the live
// /api/browse/sources counts. Design from /browse-carbon-mockup; a search
// routes to /v2/results, a source opens its v2 index (chapters for statutes,
// recent decisions for caselaw).

import {
	ArrowRightIcon,
	GavelIcon,
	LandmarkIcon,
	type LucideIcon,
	ScaleIcon,
	SlidersHorizontalIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
	Eyebrow,
	KVList,
	LineTabs,
	Notification,
	Panel,
} from "@/components/carbon/primitives";
import { CarbonSearchBar } from "@/components/carbon/search-bar";
import { type BrowseSource, browseSources } from "@/lib/iowa-browse";

const SOURCE_ICON: Record<BrowseSource["kind"], LucideIcon> = {
	caselaw: ScaleIcon,
	statutes: LandmarkIcon,
};

// Rules are "statutes"-kind in the API; give them their own glyph by slug.
const iconFor = (s: BrowseSource): LucideIcon =>
	s.slug.includes("rules") ? GavelIcon : SOURCE_ICON[s.kind];

type Scope = "all" | "state" | "federal";

export default function V2LibraryHome() {
	const router = useRouter();
	const [sources, setSources] = useState<BrowseSource[] | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [tab, setTab] = useState<Scope>("all");

	useEffect(() => {
		browseSources()
			.then(setSources)
			.catch((e) => setError((e as Error).message));
	}, []);

	const totalDocs = (sources ?? []).reduce((n, s) => n + s.entries, 0);
	// Everything in the corpus is Iowa (state) today; Federal is honestly empty.
	const shown = tab === "federal" ? [] : (sources ?? []);

	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<Eyebrow>
				{sources
					? `Iowa corpus — ${totalDocs.toLocaleString()} documents`
					: "Iowa corpus"}
			</Eyebrow>
			<h1 className="mt-4 font-light text-3xl sm:text-4xl">Library</h1>
			<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
				Search Iowa case law, statutes, and court rules — one box.
			</p>

			<div className="mt-8">
				<CarbonSearchBar
					onSearch={(q) =>
						router.push(`/v2/results?q=${encodeURIComponent(q)}`)
					}
				/>
				<div className="mt-3">
					<Link
						href="/v2/advanced"
						className="inline-flex items-center gap-1.5 font-medium text-[13px] text-[var(--cds-link)] hover:underline"
					>
						<SlidersHorizontalIcon className="size-3.5" />
						Advanced search
					</Link>
				</div>
			</div>

			<div className="mt-10">
				<LineTabs
					tabs={[
						{
							id: "all" as Scope,
							label: "All content",
							count: sources?.length,
						},
						{ id: "state" as Scope, label: "State", count: sources?.length },
						{ id: "federal" as Scope, label: "Federal", count: 0 },
					]}
					value={tab}
					onChange={setTab}
				/>
			</div>

			<div className="mt-8 grid gap-10 lg:grid-cols-[1fr_17rem] xl:grid-cols-[1fr_20rem]">
				<div className="min-w-0">
					{error ? (
						<Notification kind="error" title="Couldn't load the library">
							{error}
						</Notification>
					) : !sources ? (
						<div className="border border-[var(--cds-border)] px-6 py-14 text-center text-[var(--cds-text-2)] text-sm">
							Loading sources…
						</div>
					) : shown.length === 0 ? (
						<div className="border border-[var(--cds-border)] px-6 py-14 text-center text-[var(--cds-text-2)] text-sm">
							No federal sources yet.
						</div>
					) : (
						<div className="divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]">
							{shown.map((s) => {
								const Icon = iconFor(s);
								return (
									<Link
										key={s.slug}
										href={`/v2/source/${encodeURIComponent(s.slug)}`}
										className="group flex w-full items-center gap-4 bg-[var(--cds-layer)] p-4 text-left transition-colors hover:bg-[var(--cds-layer-hover)] sm:p-5"
									>
										<Icon
											className="size-5 shrink-0 text-[var(--cds-text-2)]"
											strokeWidth={1.5}
										/>
										<span className="flex min-w-0 flex-1 flex-col">
											<span className="truncate font-semibold text-sm">
												{s.name}
											</span>
											<span className="truncate text-[var(--cds-text-2)] text-xs">
												{s.jurisdiction}
											</span>
										</span>
										<span className="shrink-0 whitespace-nowrap font-mono text-[var(--cds-helper)] text-xs tabular-nums">
											{s.entries.toLocaleString()} {s.entry_label}
										</span>
										<ArrowRightIcon className="size-4 shrink-0 text-[var(--cds-link)] transition-transform group-hover:translate-x-0.5" />
									</Link>
								);
							})}
						</div>
					)}
					{shown.length > 0 && (
						<p className="mt-3 text-[var(--cds-helper)] text-xs">
							{shown.length} sources
							{tab !== "all" && ` · ${tab} materials`}
						</p>
					)}
				</div>

				<aside className="space-y-6">
					<Panel title="Coverage">
						<KVList
							rows={[
								["Documents", sources ? totalDocs.toLocaleString() : "…"],
								["Sources", sources ? String(sources.length) : "…"],
								["Jurisdiction", "Iowa"],
							]}
						/>
					</Panel>

					<Panel title="Search tips">
						<ul className="space-y-2 px-4 py-3 text-[12px] text-[var(--cds-text-2)] leading-snug">
							<li>
								Combine terms with <span className="font-mono">AND</span>,{" "}
								<span className="font-mono">OR</span>, and{" "}
								<span className="font-mono">-exclude</span>.
							</li>
							<li>
								Quote an{" "}
								<span className="font-mono">&ldquo;exact phrase&rdquo;</span>.
							</li>
							<li>
								Paste a citation (e.g. <span className="font-mono">714.16</span>
								) to jump straight to it.
							</li>
						</ul>
					</Panel>
				</aside>
			</div>
		</div>
	);
}
