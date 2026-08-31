// The shared band kit for the /data/coverage/<unit> pages. Every unit page
// composes the same sequence — stat strip, map band, shelf, dark connections
// band, method band, request band — so the series reads as one system and a
// new unit is copy plus a snapshot, not new layout.

import { TextLink } from "@/components/marketing/carbon";
import {
	CoverageMap,
	CoverageMapLegend,
} from "@/components/marketing/coverage/coverage-map";
import { RequestCoverageForm } from "@/components/marketing/coverage/request-coverage";
import { n } from "@/lib/briefs";

export type StatTile = { stat: string; caption: string };

export function StatStrip({ tiles }: { tiles: StatTile[] }) {
	return (
		<section className="bg-white py-14 text-[#161616]">
			<div className="mx-auto grid max-w-7xl gap-x-8 gap-y-8 px-5 sm:grid-cols-2 sm:px-8 lg:grid-cols-4">
				{tiles.map((t, i) => (
					<div
						key={t.caption}
						className={
							i > 0 ? "lg:border-[#e0e0e0] lg:border-l lg:pl-8" : undefined
						}
					>
						<p className="font-mono text-3xl sm:text-4xl">{t.stat}</p>
						<p className="mt-2 text-[#525252] text-[13px]">{t.caption}</p>
					</div>
				))}
			</div>
		</section>
	);
}

export function MapBand({ lede }: { lede: string }) {
	return (
		<section className="bg-white pt-10 pb-4 text-[#161616]">
			<div className="mx-auto max-w-7xl px-5 sm:px-8">
				<h2 className="font-light text-2xl sm:text-3xl">
					Where the library reaches
				</h2>
				<p className="mt-3 max-w-[40em] text-[#525252] text-[15px] leading-relaxed">
					{lede}
				</p>
				<div className="mt-10 grid items-start gap-10 lg:grid-cols-[minmax(0,640px)_minmax(0,1fr)] lg:gap-24">
					<CoverageMap />
					<CoverageMapLegend className="lg:pt-2" />
				</div>
			</div>
		</section>
	);
}

// One source on the shelf. `courts` rows nest under the description for
// case-law sources.
export function ShelfRow({
	name,
	kind,
	desc,
	spec,
	count,
	countNote,
	courts,
	expanding,
}: {
	name: string;
	kind: string;
	desc: string;
	spec: string;
	count: number;
	countNote: string;
	courts?: { name: string; decisions: number }[];
	expanding?: boolean;
}) {
	return (
		<li className="grid gap-x-12 gap-y-4 border-[#e0e0e0] border-b py-7 md:grid-cols-[240px_minmax(0,1fr)_240px]">
			<div>
				<h3 className="font-semibold text-[15px]">{name}</h3>
				<p className="mt-1.5 font-mono text-[#525252] text-[11px] uppercase tracking-[0.14em]">
					{kind}
				</p>
			</div>
			<div>
				<p className="max-w-[46em] text-[#525252] text-sm leading-relaxed">
					{desc}
				</p>
				<p className="mt-3 font-mono text-[12px]">{spec}</p>
				{courts && (
					<ul className="mt-3.5 max-w-[480px]">
						{courts.map((c) => (
							<li
								key={c.name}
								className="flex justify-between gap-4 border-[#e0e0e0] border-t py-2"
							>
								<span className="text-[13px]">{c.name}</span>
								<span className="font-mono text-[12px]">{n(c.decisions)}</span>
							</li>
						))}
					</ul>
				)}
			</div>
			<div className="md:text-right">
				<p className="font-mono text-2xl">{n(count)}</p>
				<p className="mt-1 font-mono text-[#8d8d8d] text-[11px] uppercase tracking-[0.06em]">
					{countNote}
				</p>
				{expanding && (
					<p className="mt-2.5 inline-block border border-[#0043ce] px-1.5 py-0.5 font-mono text-[#0043ce] text-[10px] uppercase tracking-[0.08em]">
						Expanding
					</p>
				)}
			</div>
		</li>
	);
}

// The shelf band: heading, method sentence, the rows, and a trailing link to
// the sibling coverage unit so the series interlinks.
export function ShelfSection({
	sibling,
	children,
}: {
	sibling: { label: string; href: string };
	children: React.ReactNode;
}) {
	return (
		<section className="bg-white pt-10 pb-20 text-[#161616]">
			<div className="mx-auto max-w-7xl px-5 sm:px-8">
				<h2 className="font-light text-2xl sm:text-3xl">
					The shelf, source by source
				</h2>
				<p className="mt-3 max-w-[40em] text-[#525252] text-[15px] leading-relaxed">
					Every count on this page is computed from the corpus itself, not
					estimated. Where a source is still growing, the row says so.
				</p>
				<ul className="mt-9 border-[#161616] border-t">{children}</ul>
				<div className="mt-8">
					<TextLink href={sibling.href}>{sibling.label}</TextLink>
				</div>
			</div>
		</section>
	);
}

export function DarkStatBand({
	title,
	lede,
	tiles,
}: {
	title: string;
	lede: string;
	tiles: StatTile[];
}) {
	return (
		<section className="bg-[#161616] py-18 text-white">
			<div className="mx-auto max-w-7xl px-5 sm:px-8">
				<h2 className="font-light text-2xl sm:text-3xl">{title}</h2>
				<p className="mt-4 max-w-[42em] text-[#c6c6c6] text-[15px] leading-relaxed">
					{lede}
				</p>
				<div className="mt-11 grid gap-x-8 gap-y-8 sm:grid-cols-3">
					{tiles.map((t, i) => (
						<div
							key={t.caption}
							className={
								i > 0 ? "sm:border-[#393939] sm:border-l sm:pl-8" : undefined
							}
						>
							<p className="font-mono text-2xl sm:text-3xl">{t.stat}</p>
							<p className="mt-2 text-[#a8a8a8] text-[13px] leading-relaxed">
								{t.caption}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

const METHOD_SOURCES_DEFAULT =
	"Statutes, rules, and session laws come from legis.iowa.gov. Decisions come from the public record of the courts. Nothing is paraphrased.";

export function MethodBand({
	sourcesBody = METHOD_SOURCES_DEFAULT,
}: {
	sourcesBody?: string;
}) {
	const items: { title: string; body: string }[] = [
		{
			title: "Counted, not estimated",
			body: "Every figure is computed from the corpus itself, as of the date at the top of the page. No survey numbers, no vendor claims.",
		},
		{ title: "The official record", body: sourcesBody },
		{
			title: "Kept current",
			body: "New opinions land continuously and new editions are added on publication. When the counts move, this page restates them with a new as-of date.",
		},
	];
	return (
		<section className="bg-[#f4f4f4] py-16 text-[#161616]">
			<div className="mx-auto max-w-7xl px-5 sm:px-8">
				<p className="font-mono text-[#0f62fe] text-xs uppercase tracking-[0.16em]">
					How this page counts
				</p>
				<div className="mt-7 grid gap-8 md:grid-cols-3 md:gap-12">
					{items.map((r) => (
						<div key={r.title}>
							<div aria-hidden className="w-6 border-[#0f62fe] border-t-2" />
							<h3 className="mt-3.5 font-semibold text-[15px]">{r.title}</h3>
							<p className="mt-2.5 max-w-[26em] text-[#525252] text-sm leading-relaxed">
								{r.body}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

export function RequestBand() {
	return (
		<section
			id="request"
			className="scroll-mt-16 bg-white py-18 text-[#161616]"
		>
			<div className="mx-auto max-w-7xl px-5 sm:px-8">
				<h2 className="font-light text-2xl sm:text-3xl">
					Where should the map grow next?
				</h2>
				<p className="mt-3 max-w-[40em] text-[#525252] text-[15px] leading-relaxed">
					If your practice needs a source we do not hold yet, another state, a
					federal court, an agency's rules, ask for it. Requests steer the
					ingestion queue.
				</p>
				<RequestCoverageForm />
			</div>
		</section>
	);
}
