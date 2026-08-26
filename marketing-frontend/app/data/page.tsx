// /data — the data-brief series index. An analysis section, not a chart
// gallery: the hero states the series contract (conservative counting,
// frozen numbers, methodology on the page), the latest brief gets the
// featured card, and the pipeline strip shows what's being prepared —
// findings are never teased before their numbers survive review.
//
// When a second brief publishes, the reverse-chronological "All briefs"
// editorial list from the approved index mockup slots in between the
// featured card and the pipeline section (each row: number/date, question
// headline, abstract with the key stat, topic line, and a headline number —
// only sometimes a chart — in the right rail).

import type { Metadata } from "next";
import { FeaturedBrief } from "@/components/marketing/briefs/featured-brief";
import { CarbonPage, PageHero } from "@/components/marketing/carbon";
import { MOST_CITED_CASES } from "@/lib/briefs";

const snap = MOST_CITED_CASES;
const n = (x: number) => x.toLocaleString("en-US");

export const metadata: Metadata = {
	title: "Data briefs — Hudson Legal Technologies",
	description:
		"Original analysis of Iowa law, computed from Hudson Corpus: one question per brief, answered from the full record, frozen and citable, with the methodology on the page.",
};

// The public pipeline. Status lines are honest about what each brief is
// waiting on; a brief is announced here but its findings appear only once
// the numbers survive review.
const PIPELINE: { no: string; title: string; note: string }[] = [
	{
		no: "—",
		title: "Anatomy of authority",
		note: "Depth, breadth, position and lifecycle for the fifty most-cited cases — in review.",
	},
	{
		no: "002",
		title: "Which parts of the Iowa Code change most?",
		note: "Legislative churn by Code title across the 2019–2026 sessions, from 18,723 mapped act-to-Code edges.",
	},
	{
		no: "003",
		title: "The half-life of Iowa precedent",
		note: "How quickly do cited cases age out? The age of every citation in the graph, decade by decade.",
	},
	{
		no: "004",
		title: "Who really regulates Iowa?",
		note: "Statute-to-rule coupling by agency: 22,508 links between the Code and 17,690 administrative rules.",
	},
	{
		no: "005",
		title: "Court output over time",
		note: "Opinions per year, Supreme Court vs. Court of Appeals — pending a check on pre-2008 unpublished-opinion coverage.",
	},
	{
		no: "—",
		title: "The most-overruled cases",
		note: "Waiting on citation-treatment analysis across the graph.",
	},
	{
		no: "—",
		title: "The growth of the Iowa Code",
		note: "Waiting on more historical Code editions in the corpus.",
	},
];

const RULES: { title: string; body: string }[] = [
	{
		title: "An argument, not a dashboard",
		body: "Each brief is a curated piece of analysis with a point of view, frozen when published. No live filters, no drifting numbers — the product is the dashboard; the brief is the argument.",
	},
	{
		title: "The method is on the page",
		body: "Every brief ends with how it was measured and the fine print, and every figure ships with its full data table. If a caveat would embarrass us later, it goes on the page now.",
	},
	{
		title: "Frozen and citable",
		body: "A published brief carries an as-of date and never drifts as the corpus grows. Refreshing one is a deliberate re-export, reviewed line by line.",
	},
];

// The card itself is shared with the marketing home (components/marketing/
// briefs/featured-brief.tsx) — one description of "the latest brief", rendered
// in two places. This wrapper only supplies the band it sits in.
function FeaturedBriefBand() {
	return (
		<section className="bg-[#161616] pb-22 text-white">
			<div className="mx-auto max-w-7xl px-5 sm:px-8">
				<FeaturedBrief />
			</div>
		</section>
	);
}

function Pipeline() {
	return (
		<section className="bg-white py-18 text-[#161616]">
			<div className="mx-auto max-w-7xl px-5 sm:px-8">
				<h2 className="font-light text-3xl tracking-[-0.01em] sm:text-4xl">
					In the pipeline
				</h2>
				<p className="mt-3 max-w-[40em] text-[#525252]">
					Questions we&rsquo;re preparing to answer next. A brief publishes when
					its numbers survive review — each arrives frozen, with an as-of date
					and its method on the page.
				</p>
				<ul className="mt-9 border-[#161616] border-t">
					{PIPELINE.map((p) => (
						<li
							key={p.title}
							className="grid gap-x-10 gap-y-1 border-[#e0e0e0] border-b py-5 md:grid-cols-[110px_minmax(0,22em)_1fr]"
						>
							<span className="font-mono text-[#525252] text-xs uppercase tracking-[0.14em]">
								{p.no === "—" ? "—" : `Brief ${p.no}`}
							</span>
							<span className="font-semibold text-[15px]">{p.title}</span>
							<span className="max-w-[40em] text-[#525252] text-sm leading-relaxed">
								{p.note}
							</span>
						</li>
					))}
				</ul>
			</div>
		</section>
	);
}

function SeriesRules() {
	return (
		<section className="bg-[#f4f4f4] py-16 text-[#161616]">
			<div className="mx-auto max-w-7xl px-5 sm:px-8">
				<p className="font-mono text-[#0f62fe] text-xs uppercase tracking-[0.16em]">
					What a data brief is
				</p>
				<div className="mt-7 grid gap-8 md:grid-cols-3 md:gap-12">
					{RULES.map((r) => (
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

export default function DataIndexPage() {
	return (
		<CarbonPage>
			<PageHero
				eyebrow="Hudson Corpus · Data briefs"
				title="Analysis you can check."
				lede={
					<>
						Each data brief takes one question lawyers actually argue about —
						which cases do the work, what changes, who regulates — and answers
						it from the full record: {n(snap.totals.decisions)} appellate
						decisions, every citation between them, the Iowa Code, and the
						administrative rules beneath it. Figures appear where they help the
						argument; the method and the complete data are always on the page.
					</>
				}
			/>
			<FeaturedBriefBand />
			<Pipeline />
			<SeriesRules />
		</CarbonPage>
	);
}
