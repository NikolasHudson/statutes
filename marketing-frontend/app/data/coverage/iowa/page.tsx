// /data/coverage/iowa — the coverage inventory for Iowa, first page of the
// /data/coverage/<unit> series. An SEO page with the data-brief contract
// behind it: every number renders from the frozen snapshot in
// content/data/coverage-iowa.json (`manage.py export_coverage_snapshot iowa`),
// so the page never drifts from what was actually counted, and a refresh is
// a reviewed git diff. The band layout lives in the shared coverage kit
// (components/marketing/coverage/bands.tsx); this file is the unit's copy
// and numbers.

import type { Metadata } from "next";
import { CarbonPage, PageHero } from "@/components/marketing/carbon";
import { COVERAGE_EIGHTH_CIRCUIT_HREF } from "@/components/marketing/chrome";
import {
	DarkStatBand,
	MapBand,
	MethodBand,
	RequestBand,
	ShelfRow,
	ShelfSection,
	StatStrip,
} from "@/components/marketing/coverage/bands";
import { n } from "@/lib/briefs";
import {
	COVERAGE_IOWA,
	formatCounted,
	isoMonthYear,
	isoYear,
	ordinal,
} from "@/lib/coverage";

const snap = COVERAGE_IOWA;

const iaFirst = isoYear(snap.iowa_caselaw.first);
const spanYears = isoYear(snap.iowa_caselaw.last) - iaFirst;

export const metadata: Metadata = {
	title: "Coverage: Iowa — Hudson Legal Technologies",
	description:
		`What Hudson Corpus holds for Iowa law: the Iowa Code, the Iowa Administrative Code, ` +
		`the Iowa Acts, the court rules, and ${n(snap.totals.decisions)} court decisions since ` +
		`${iaFirst}: ${n(snap.totals.authorities)} primary authorities, ` +
		`counted from the live corpus and connected by citation and cross reference.`,
};

export default function CoverageIowaPage() {
	const acts = snap.iowa_acts;
	const fedFirst = isoYear(snap.federal_caselaw.first);
	const iowaCourts = snap.iowa_caselaw.courts.map((c) =>
		c.key === "supreme"
			? { ...c, name: `${c.name}, ${iaFirst} to present` }
			: c,
	);
	const fedCourts = snap.federal_caselaw.courts.map((c) =>
		c.key === "historical"
			? { ...c, name: `${c.name}, ${fedFirst} forward` }
			: c,
	);

	return (
		<CarbonPage>
			<PageHero
				eyebrow="Data · Coverage · Iowa"
				title="What we hold for Iowa."
				lede={
					<>
						The complete inventory of Hudson Corpus for Iowa law:{" "}
						{n(snap.totals.authorities)} primary authorities spanning {iaFirst}{" "}
						to this month, counted from the live corpus and connected by
						citation and cross reference. This page states exactly what is on
						the shelf, source by source.
					</>
				}
				actions={
					<p className="font-mono text-[#6f6f6f] text-[11px] uppercase tracking-[0.1em]">
						Counted {formatCounted(snap.as_of)}
					</p>
				}
			/>
			<StatStrip
				tiles={[
					{ stat: n(snap.totals.authorities), caption: "primary authorities" },
					{
						stat: String(spanYears),
						caption: `years of decisions, ${iaFirst} to ${isoYear(snap.iowa_caselaw.last)}`,
					},
					{
						stat: String(snap.totals.sources),
						caption: "sources of law, statutes to case law",
					},
					{
						stat: n(snap.totals.connections),
						caption: "mapped connections between them",
					},
				]}
			/>
			<MapBand lede="Deep on Iowa, current on the federal courts above it, and honest about the rest." />
			<ShelfSection
				sibling={{
					label: "Coverage: Eighth Circuit, the federal courts above the stack",
					href: COVERAGE_EIGHTH_CIRCUIT_HREF,
				}}
			>
				<ShelfRow
					name="Iowa Code"
					kind="Statutes"
					desc={`The codified statutes of the State of Iowa, structured to the section, with the ${snap.iowa_code.edition_years.join(" and ")} editions held side by side for year over year comparison.`}
					spec={`${n(snap.iowa_code.sections)} sections · ${n(snap.iowa_code.chapters)} chapters · ${snap.iowa_code.edition_years.length} editions`}
					count={snap.iowa_code.sections}
					countNote={`Sections · current through the ${Math.max(...snap.iowa_code.edition_years)} edition`}
				/>
				<ShelfRow
					name="Iowa Administrative Code"
					kind="Regulations"
					desc="Every agency rule in force, structured to the rule and tied back to the statutes each rule implements."
					spec={`${n(snap.iowa_admin_code.rules)} rules · ${n(snap.iowa_admin_code.chapters)} chapters · ${snap.iowa_admin_code.agencies} agencies`}
					count={snap.iowa_admin_code.rules}
					countNote={`Rules · all ${snap.iowa_admin_code.agencies} agencies`}
				/>
				<ShelfRow
					name="Iowa Acts"
					kind="Session laws"
					desc={`Session laws as enacted by the ${ordinal(acts.first_ga)} through ${ordinal(acts.last_ga)} General Assemblies, ${acts.first_year} to ${acts.last_year}, each act mapped to the Code sections it creates or amends.`}
					spec={`${n(acts.sections)} sections · ${n(acts.chapters)} enacted chapters · ${acts.sessions} sessions`}
					count={acts.sections}
					countNote={`Sections · sessions ${acts.first_year} to ${acts.last_year}`}
				/>
				<ShelfRow
					name="Iowa Court Rules"
					kind="Rules of court"
					desc="The rules governing practice in Iowa's courts, structured to the rule."
					spec={`${n(snap.iowa_court_rules.rules)} rules · ${n(snap.iowa_court_rules.chapters)} chapters`}
					count={snap.iowa_court_rules.rules}
					countNote="Rules"
				/>
				<ShelfRow
					name="Iowa case law"
					kind={`Decisions since ${iaFirst}`}
					desc="The decisions of Iowa's appellate courts, from the territorial Supreme Court's first reported opinions forward, with the citation graph and treatment analysis across all of them."
					spec={`${n(snap.iowa_caselaw.decisions)} decisions`}
					count={snap.iowa_caselaw.decisions}
					countNote={`Decisions · ${iaFirst} to ${isoMonthYear(snap.iowa_caselaw.last)}`}
					courts={iowaCourts}
				/>
				<ShelfRow
					name="Federal courts"
					kind={`Decisions since ${fedFirst}`}
					desc="The federal decisions that bind Iowa practice: the Eighth Circuit in full, Iowa's district and bankruptcy courts, and the circuit courts that preceded them."
					spec={`${n(snap.federal_caselaw.decisions)} decisions`}
					count={snap.federal_caselaw.decisions}
					countNote={`Decisions · ${fedFirst} to ${isoMonthYear(snap.federal_caselaw.last)}`}
					courts={fedCourts}
					expanding
				/>
			</ShelfSection>
			<DarkStatBand
				title="Connected, not just collected."
				lede="A coverage list tells you what is on the shelf. The corpus also holds how it fits together: which rules implement which statutes, which acts rewrote which sections, and which opinions cite, follow, or undercut which."
				tiles={[
					{
						stat: n(snap.connections.statute_rule),
						caption:
							"references between Code sections and the administrative rules that implement them",
					},
					{
						stat: n(snap.connections.act_code),
						caption:
							"edges from session laws to the Code sections they create or amend",
					},
					{
						stat: "Every opinion",
						caption:
							"in the citation graph, with treatment analysis of how later courts received it",
					},
				]}
			/>
			<MethodBand />
			<RequestBand />
		</CarbonPage>
	);
}
