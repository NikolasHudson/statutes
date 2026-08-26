// Data brief 001 — The Most-Cited Cases in Iowa. The chart, an introduction
// to it, the full table, and the method: the published face of the citation
// count.
//
// Fully static. Every number in the prose is looked up from the frozen
// snapshots in content/data/ — the fifty and their counts from
// most-cited-cases.json (`manage.py export_data_brief most_cited_cases`), the
// handful of corpus-wide concentration figures from citation-concentration.json
// (frozen from the same corpus snapshot; provenance inside the file) — and the
// page throws at build time if a key or a case goes missing, so a refresh that
// changes the cast fails the build rather than quietly publishing a stale
// sentence.

import type { Metadata } from "next";
import {
	BriefHero,
	BriefTable,
	Methodology,
	PROSE,
} from "@/components/marketing/briefs/blocks";
import { BubbleChart } from "@/components/marketing/briefs/bubble-chart";
import { CarbonPage } from "@/components/marketing/carbon";
import {
	briefNo,
	CITATION_CONCENTRATION,
	concentration,
	formatAsOf,
	MOST_CITED_CASES,
	n,
	pct,
} from "@/lib/briefs";

const snap = MOST_CITED_CASES;
const [fifty] = snap.figures;

// The concentration numbers were cut from the same corpus on the same day as
// the fifty. Hold the two to that: if either is refreshed alone, the page must
// not build with numbers from two corpora.
if (CITATION_CONCENTRATION.as_of !== snap.as_of)
	throw new Error(
		`brief 001: citation-concentration (${CITATION_CONCENTRATION.as_of}) and most-cited-cases (${snap.as_of}) snapshots disagree on as-of`,
	);
if (CITATION_CONCENTRATION.numbers.edges !== snap.totals.edges)
	throw new Error("brief 001: the two snapshots disagree on the edge count");

// Facts read off the fifty themselves.
const top = fifty.bubbles[0];
const byCat = (cat: string) =>
	fifty.bubbles.filter((b) => b.cat === cat).length;
const catLabel = (cat: string) => fifty.categories[cat]?.label ?? cat;
const years = fifty.bubbles.map((b) => Number(b.year));
const oldest = fifty.bubbles.reduce((a, b) => (b.year < a.year ? b : a));
const newest = fifty.bubbles.reduce((a, b) => (b.year > a.year ? b : a));
const supremeCourt = fifty.bubbles.filter(
	(b) => b.court === "Iowa Supreme Court",
).length;
const courtOfAppeals = fifty.bubbles.length - supremeCourt;
const since2000 = years.filter((y) => y >= 2000).length;

// `*case name*` renders italic — the only inline mark the copy uses.
function inline(text: string): React.ReactNode[] {
	return text.split(/(\*[^*]+\*)/g).map((part, i) =>
		part.startsWith("*") && part.endsWith("*") ? (
			// biome-ignore lint/suspicious/noArrayIndexKey: static editorial string, never reordered
			<em key={i}>{part.slice(1, -1)}</em>
		) : (
			part
		),
	);
}

function P({ children, lead = false }: { children: string; lead?: boolean }) {
	return (
		<p
			className={
				lead
					? `${PROSE} mt-6 font-light text-[#f4f4f4] text-xl leading-[1.6] sm:text-[22px] [&_em]:text-[#f4f4f4]`
					: `${PROSE} mt-5 text-[#c6c6c6] text-[16.5px] leading-[1.7] [&_em]:text-[#f4f4f4]`
			}
		>
			{inline(children)}
		</p>
	);
}

export const metadata: Metadata = {
	title: "The Most-Cited Cases in Iowa — Hudson Legal Technologies",
	description:
		`The fifty Iowa decisions Iowa's own appellate courts cite most, counted ` +
		`from ${n(snap.totals.edges)} citations across ${n(snap.totals.decisions)} ` +
		`decisions. Number one is ${top.name}, cited by ${n(top.cites)} opinions. ` +
		`Data brief ${briefNo(snap)}, as of ${formatAsOf(snap.as_of)}.`,
};

export default function MostCitedCasesPage() {
	return (
		<CarbonPage>
			<div data-print="paper">
				<div data-print="runner" aria-hidden className="hidden">
					<span>The Most-Cited Cases in Iowa · Data brief {briefNo(snap)}</span>
					<span>Hudson Corpus · hudsonlegal.tech</span>
				</div>
				<BriefHero
					no={briefNo(snap)}
					asOf={formatAsOf(snap.as_of)}
					title="The Most-Cited Cases in Iowa"
					dek={`Every citation Iowa's appellate courts have made to their own decisions, counted — and the fifty cases at the top of the list.`}
					kpis={[
						{
							value: n(snap.totals.edges),
							label: "citations counted, opinion to opinion",
						},
						{
							value: n(snap.totals.decisions),
							label: "appellate decisions, published and unpublished",
						},
						{
							value: n(top.cites),
							label: `opinions cite ${top.name}, the most-cited case in Iowa law`,
						},
					]}
				/>

				{/* ---------------------------------------------------- introduction */}
				{/* pt-px: the first paragraph's top margin would otherwise collapse
				    through the section and show the page ground as a white band. */}
				<section className="bg-[#161616] pt-px pb-16 text-white">
					<div className="mx-auto max-w-7xl px-5 sm:px-8">
						<P lead>
							{`Which cases do Iowa's courts actually cite? Not the ones most lawyers would guess. We counted every citation Iowa's appellate courts have made to their own past decisions, ${n(snap.totals.edges)} of them across ${n(snap.totals.decisions)} decisions, published and unpublished, and ranked the cases by how many opinions cite them. These are the fifty at the top.`}
						</P>
						<P>
							{`The list is not a hall of fame. ${byCat("family")} of the fifty are ${catLabel("family").toLowerCase()} cases, most of them appeals from the termination of parental rights; ${byCat("criminal")} are ${catLabel("criminal").toLowerCase()}; ${byCat("civil")} are ${catLabel("civil").toLowerCase()}. The most-cited case in Iowa law is *${top.name}*, a ${top.year} termination decision that ${n(top.cites)} later opinions cite. *Varnum v. Brien*, the most consequential decision the Iowa Supreme Court has issued this century, has been cited ${concentration("varnum_cites")} times and does not make the list.`}
						</P>
						<P>
							{`That is not a paradox. Courts cite what they use, and what an appellate opinion uses most is the standard of review, the framework, the elements of the test: the paragraph it needs before it can reach the merits. A case earns a place on this list by being the cleanest statement of a rule that comes up every week, not by settling a great question once. Frequently cited is not the same as important.`}
						</P>
						<P>
							{`The curve behind the list is steep. Of the ${n(snap.totals.decisions)} decisions, ${n(concentration("never_cited"))}, ${pct(concentration("never_cited_share"))}, have never been cited by any later Iowa opinion. ${concentration("at_least_100")} have been cited a hundred times or more, ${concentration("at_least_500")} have reached five hundred, and ${concentration("at_least_1000")} have passed a thousand. The fifty below are ${concentration("fifty_corpus_share")} percent of the corpus and receive one of every ${concentration("fifty_one_in")} citations Iowa's appellate courts have ever made.`}
						</P>

						<figure className="mt-14">
							<figcaption className="flex flex-wrap items-baseline gap-x-8 gap-y-3 border-[#393939] border-t pt-4">
								<span className="font-mono text-[#a8a8a8] text-xs uppercase tracking-[0.12em]">
									Figure 1 — The fifty
								</span>
								<span className="max-w-[46em] text-[#c6c6c6] text-[15px]">
									The fifty most-cited cases in Iowa law, sized by the number of
									opinions that cite them. Hover or tab to any bubble for its
									full caption, year, court and count; the complete list is in
									Table 1.
								</span>
							</figcaption>
							<BubbleChart figure={fifty} unit="citing opinions" />
						</figure>

						<P>
							{`Two things stand out once the fifty are laid side by side. The first is how new the list is: ${since2000} of the fifty were decided in 2000 or later, and the oldest case on it, *${oldest.name}*, dates only to ${oldest.year}. Iowa's working canon is a recent construction, and it is still being built; the newest member, *${newest.name}*, is from ${newest.year}. The second is where it comes from: ${supremeCourt} of the fifty are Iowa Supreme Court decisions; only ${courtOfAppeals} come from the Court of Appeals.`}
						</P>
					</div>
				</section>

				{/* ---------------------------------------------------------- table 1 */}
				{/* data-print="ink": on paper the whole brief is one ink document, so
				    the sections designed on paper stock are restated in the band's
				    palette rather than printed as light panels inside it. */}
				<section data-print="ink" className="bg-white py-16 text-[#161616]">
					<div className="mx-auto max-w-7xl px-5 sm:px-8">
						<p className="font-mono text-[#0f62fe] text-xs uppercase tracking-[0.16em]">
							Table 1 — The fifty
						</p>
						<h2 className="mt-2 font-light text-3xl tracking-[-0.01em] sm:text-4xl">
							The complete list
						</h2>
						<p className="mt-3 max-w-[46em] text-[#525252]">
							{`Every case in Figure 1, ranked by the number of distinct Iowa appellate opinions that cite it. The table is the record; the chart is the picture of it.`}
						</p>
						<div data-print="scroll">
							<BriefTable
								figure={fifty}
								countHeader="Citing opinions"
								areaHeader="Practice area"
							/>
						</div>
					</div>
				</section>

				<Methodology
					measured={[
						<>
							{`Every citation is an edge in the corpus citation graph: ${n(snap.totals.edges)} of them, drawn from the text of ${n(snap.totals.decisions)} Iowa appellate decisions, published and unpublished. Edges point at `}
							<em>opinion</em>
							{` nodes, so each opinion in a multi-opinion decision counts separately.`}
						</>,
						"A case's count is the number of distinct citing opinions. An opinion that cites the same case five times counts once, so a large number means broad use, not one enthusiastic writer.",
						"Practice areas are assigned per case, one label each, from the subject of the cited decision.",
						"The chart's layout is computed once at export and frozen with the data. The page draws it; nothing on it is recomputed.",
					]}
					finePrint={[
						"Citations counted here are those made by Iowa appellate opinions inside the corpus. Citations by federal courts, other states, briefs, and secondary sources are not counted, so these are floors, not totals.",
						"The corpus is complete on the citing side from 2014 forward and thinner for 2010–2013, so cases whose use peaked before 2014 are undercounted relative to newer ones, and raw counts should not be read as a trend.",
						"Multiple Iowa decisions share captions, so cases were matched on citation and year, never on name.",
						"Frequently cited is not the same as good law. A case on this list may have been limited, superseded by statute, or overruled since it was decided; check its treatment before you cite it.",
					]}
				/>
			</div>
		</CarbonPage>
	);
}
