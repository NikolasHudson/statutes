// /data/coverage/eighth-circuit — the coverage inventory for the federal
// courts above Iowa practice, second unit of the /data/coverage/<unit>
// series. Renders from the frozen snapshot in
// content/data/coverage-eighth-circuit.json
// (`manage.py export_coverage_snapshot eighth-circuit`); the band layout is
// the shared coverage kit, so this file is only the unit's copy and numbers.

import type { Metadata } from "next";
import { CarbonPage, PageHero } from "@/components/marketing/carbon";
import { COVERAGE_IOWA_HREF } from "@/components/marketing/chrome";
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
	COVERAGE_EIGHTH_CIRCUIT,
	formatCounted,
	isoMonthYear,
	isoYear,
} from "@/lib/coverage";

const snap = COVERAGE_EIGHTH_CIRCUIT;

const firstYear = isoYear(snap.historical.first);
const lastYear = isoYear(snap.ca8.last);

export const metadata: Metadata = {
	title: "Coverage: Eighth Circuit — Hudson Legal Technologies",
	description:
		`What Hudson Corpus holds for the Eighth Circuit: ${n(snap.totals.decisions)} decisions ` +
		`of the Court of Appeals, its Bankruptcy Appellate Panel, and Iowa's federal trial ` +
		`courts since ${firstYear}, resolved into Iowa state law by ` +
		`${n(snap.totals.cross_citations)} cross citations.`,
};

export default function CoverageEighthCircuitPage() {
	return (
		<CarbonPage>
			<PageHero
				eyebrow="Data · Coverage · Eighth Circuit"
				title="What we hold for the Eighth Circuit."
				lede={
					<>
						The federal record above Iowa practice: {n(snap.totals.decisions)}{" "}
						decisions of the Court of Appeals for the Eighth Circuit, its
						Bankruptcy Appellate Panel, and Iowa's federal trial courts, counted
						from the live corpus and resolved into Iowa's state reporter,
						citation by citation.
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
					{ stat: n(snap.totals.decisions), caption: "federal decisions" },
					{
						stat: String(lastYear - firstYear),
						caption: `years of decisions, ${firstYear} to ${lastYear}`,
					},
					{
						stat: String(snap.totals.states),
						caption: "states bound by the circuit's holdings",
					},
					{
						stat: n(snap.totals.cross_citations),
						caption:
							"citations resolved between the federal and Iowa reporters",
					},
				]}
			/>
			<MapBand lede="One circuit above seven states. Iowa is where the library goes all the way down." />
			<ShelfSection
				sibling={{
					label: "Coverage: Iowa, the state stack beneath the circuit",
					href: COVERAGE_IOWA_HREF,
				}}
			>
				<ShelfRow
					name="Court of Appeals for the Eighth Circuit"
					kind="Appellate decisions"
					desc="The circuit in full, not an Iowa-only slice: the published decisions of the court whose holdings bind the district courts of seven states, Iowa among them."
					spec={`${n(snap.ca8.decisions)} decisions`}
					count={snap.ca8.decisions}
					countNote={`Decisions · ${isoYear(snap.ca8.first)} to ${isoMonthYear(snap.ca8.last)}`}
				/>
				<ShelfRow
					name="Bankruptcy Appellate Panel"
					kind="Bankruptcy appeals"
					desc="The circuit's appellate panel for bankruptcy cases, from its first published decisions forward."
					spec={`${n(snap.bap.decisions)} decisions`}
					count={snap.bap.decisions}
					countNote={`Decisions · ${isoYear(snap.bap.first)} to ${isoMonthYear(snap.bap.last)}`}
				/>
				<ShelfRow
					name="Iowa's federal trial courts"
					kind="District and bankruptcy courts"
					desc="The Northern and Southern Districts of Iowa and their bankruptcy courts. The backfill toward the present is in progress."
					spec={`${n(snap.iowa_federal.decisions)} decisions`}
					count={snap.iowa_federal.decisions}
					countNote={`Decisions · ${isoYear(snap.iowa_federal.first)} to ${isoMonthYear(snap.iowa_federal.last)}`}
					courts={snap.iowa_federal.courts}
					expanding
				/>
				<ShelfRow
					name="Historical circuit courts"
					kind="Predecessor courts"
					desc="The circuit courts that heard federal cases in Iowa before the modern system, kept for the lineage of the doctrine."
					spec={`${n(snap.historical.decisions)} decisions`}
					count={snap.historical.decisions}
					countNote={`Decisions · ${isoYear(snap.historical.first)} to ${isoMonthYear(snap.historical.last)}`}
				/>
			</ShelfSection>
			<DarkStatBand
				title="Stitched into the state reporter."
				lede="A circuit matters to Iowa lawyers where it touches Iowa law. The corpus resolves citations across the state and federal reporters in both directions, one graph."
				tiles={[
					{
						stat: n(snap.connections.federal_to_iowa),
						caption:
							"citations from federal decisions resolved to Iowa authority",
					},
					{
						stat: n(snap.connections.iowa_to_federal),
						caption:
							"citations from Iowa decisions resolved to the federal courts",
					},
					{
						stat: n(snap.connections.graph_edges),
						caption: "resolved edges in the citation graph across both corpora",
					},
				]}
			/>
			<MethodBand sourcesBody="Decisions come from the public record of the federal and Iowa courts. Nothing is paraphrased." />
			<RequestBand />
		</CarbonPage>
	);
}
