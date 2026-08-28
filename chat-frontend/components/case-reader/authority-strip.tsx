"use client";

// The authority strip under the caption — Treatment · Cited by · Cites — so
// the first glance answers "is this good law, and does anyone rely on it?"
// Treatment is honest about what the citator is: a phrase-based pass over
// citing opinions. "No negative treatment" means none was FOUND, and the
// helper says what was checked.

import {
	CircleAlertIcon,
	CircleCheckIcon,
	CircleDashedIcon,
} from "lucide-react";
import { memo, type ReactNode } from "react";
import type { CaseDetail } from "@/lib/iowa-browse";
import { cn } from "@/lib/utils";
import {
	courtShort,
	fmtMonthYear,
	mostRecent,
	prettyLabel,
	shortName,
} from "./format";

export const AuthorityStrip = memo(function AuthorityStrip({
	data,
	onCitedBy,
	onCites,
}: {
	data: CaseDetail;
	onCitedBy: () => void;
	onCites: () => void;
}) {
	const t = data.treatment;
	const negative = t && t.status === "negative";
	const caution = t && t.status === "caution";
	const recent = mostRecent(data.citing_decisions);
	const inCorpus = data.cited_cases.length;
	const outside = data.external_citation_count;
	const names = data.cited_cases.slice(0, 5).map((c) => shortName(c.case_name));

	let treatmentIcon: ReactNode;
	let treatmentValue: string;
	let treatmentHelp: string;
	if (negative || caution) {
		treatmentIcon = (
			<CircleAlertIcon
				className={cn(
					"size-4",
					negative ? "text-[var(--cds-danger-text)]" : "text-[#b28600]",
				)}
			/>
		);
		treatmentValue = negative ? "Negative treatment" : "Caution";
		treatmentHelp = `${prettyLabel(t)}${t.by_citation ? ` by ${t.by_citation}` : ""}`;
	} else if (data.citing_count > 0) {
		treatmentIcon = (
			<CircleCheckIcon className="size-4 text-[var(--cds-success-text)]" />
		);
		treatmentValue = "No negative treatment";
		treatmentHelp = `Checked against ${data.citing_count.toLocaleString()} citing decision${data.citing_count === 1 ? "" : "s"}`;
	} else {
		treatmentIcon = (
			<CircleDashedIcon className="size-4 text-[var(--cds-helper)]" />
		);
		treatmentValue = "No citing decisions";
		treatmentHelp = "Nothing in the corpus cites this case yet";
	}

	return (
		<div className="mt-6 grid border border-[var(--cds-border)] md:grid-cols-3">
			<Cell
				label="Treatment"
				value={
					<span
						className={cn(
							"flex items-center gap-1.5",
							negative && "text-[var(--cds-danger-text)]",
						)}
					>
						{treatmentIcon}
						{treatmentValue}
					</span>
				}
				help={treatmentHelp}
				onClick={onCitedBy}
			/>
			<Cell
				label="Cited by"
				value={`${data.citing_count.toLocaleString()} decision${data.citing_count === 1 ? "" : "s"}`}
				help={
					recent
						? `Most recent ${fmtMonthYear(recent.date_filed)} · ${courtShort(recent.court_id, recent.court_name)}`
						: "Citation graph refreshes with the bulk reload"
				}
				onClick={onCitedBy}
			/>
			<Cell
				label="Cites"
				value={`${inCorpus} in corpus · ${outside} outside`}
				help={
					names.length ? names.join(", ") : "No in-corpus authorities cited"
				}
				onClick={onCites}
				last
			/>
		</div>
	);
});

function Cell({
	label,
	value,
	help,
	onClick,
	last,
}: {
	label: string;
	value: ReactNode;
	help: string;
	onClick: () => void;
	last?: boolean;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"flex flex-col gap-1 border-[var(--cds-border)] border-b px-4 py-3 text-left transition-colors hover:bg-[var(--cds-layer-hover)] md:border-r md:border-b-0",
				last && "border-b-0 md:border-r-0",
			)}
		>
			<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				{label}
			</span>
			<span className="font-semibold text-[14px] leading-[1.4]">{value}</span>
			<span className="line-clamp-2 text-[12px] text-[var(--cds-text-2)] leading-[1.4]">
				{help}
			</span>
		</button>
	);
}
