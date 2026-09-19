"use client";

// Pieces shared by every Resources page. Two of them are load-bearing rather
// than decorative:
//
// * ProvenanceStrip — this is reference data, not law. Every page says where
//   it came from, when it was published, and that the Secretary of State is
//   the record to rely on. It is never rendered as a citation.
// * StatusPill — the source lists active entities only, so "not here any
//   more" is all we can honestly say. The pill says exactly that, with the
//   date we first noticed, instead of implying a dissolution we did not see.

import { ExternalLinkIcon } from "lucide-react";
import Link from "next/link";
import { Tag } from "@/components/carbon/primitives";
import { fmtDate, SOS_OFFICIAL_SEARCH } from "@/lib/iowa-resources";

export function ProvenanceStrip({
	asOf,
	attribution,
	className,
}: {
	// Omit on pages that show several datasets at once; pass null for a
	// dataset that has never been loaded.
	asOf?: string | null;
	attribution?: string;
	className?: string;
}) {
	const freshness =
		asOf === undefined
			? ""
			: asOf
				? `Data as of ${fmtDate(asOf)}.`
				: "Not yet loaded.";
	return (
		<p
			className={`border-[var(--cds-border)] border-t pt-4 text-[var(--cds-helper)] text-xs leading-relaxed ${className ?? ""}`}
		>
			{attribution ??
				"Source: Iowa Secretary of State via Iowa Data Hub. CC BY 4.0."}{" "}
			{freshness} Not an official record; verify with the{" "}
			<a
				className="text-[var(--cds-link)] underline underline-offset-2"
				href={SOS_OFFICIAL_SEARCH}
				target="_blank"
				rel="noreferrer"
			>
				Secretary of State
				<ExternalLinkIcon className="ml-1 inline size-3 align-[-1px]" />
			</a>{" "}
			before relying on it.
		</p>
	);
}

export function StatusPill({
	isActive,
	deactivatedOn,
}: {
	isActive: boolean;
	deactivatedOn: string | null;
}) {
	if (isActive) return <Tag kind="green">Active</Tag>;
	return (
		<Tag kind="yellow">
			{deactivatedOn
				? `No longer listed as active since ${fmtDate(deactivatedOn)}`
				: "No longer listed as active"}
		</Tag>
	);
}

// One results table, used by the search page and by the detail page's
// registered-agent reverse lookup. Horizontally scrollable so a phone gets a
// real table rather than a squeezed one.
export function EntityTable({
	rows,
	emptyLabel = "No entities matched.",
}: {
	rows: {
		corp_number: string;
		legal_name: string;
		entity_type: string;
		registered_agent: string;
		city: string;
		state: string;
		is_active: boolean;
		deactivated_on: string | null;
	}[];
	emptyLabel?: string;
}) {
	if (rows.length === 0) {
		return (
			<p className="px-4 py-6 text-[var(--cds-text-2)] text-sm">{emptyLabel}</p>
		);
	}
	return (
		<div className="overflow-x-auto">
			<table className="w-full min-w-[46rem] border-collapse text-sm">
				<thead>
					<tr className="border-[var(--cds-border)] border-b text-left">
						{[
							"Name",
							"Type",
							"Corp no.",
							"City",
							"Registered agent",
							"Status",
						].map((h) => (
							<th
								key={h}
								className="px-4 py-2.5 font-mono font-normal text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.14em]"
							>
								{h}
							</th>
						))}
					</tr>
				</thead>
				<tbody>
					{rows.map((row) => (
						<tr
							key={row.corp_number}
							className="border-[var(--cds-border)] border-b last:border-b-0 hover:bg-[var(--cds-layer)]"
						>
							<td className="px-4 py-3">
								<Link
									className="text-[var(--cds-link)] hover:underline"
									href={`/resources/iowa-business-entities/${row.corp_number}`}
								>
									{row.legal_name}
								</Link>
							</td>
							<td className="px-4 py-3 text-[var(--cds-text-2)] text-xs">
								{row.entity_type}
							</td>
							<td className="px-4 py-3 tabular-nums">{row.corp_number}</td>
							<td className="px-4 py-3 text-[var(--cds-text-2)]">
								{[row.city, row.state].filter(Boolean).join(", ")}
							</td>
							<td className="px-4 py-3 text-[var(--cds-text-2)]">
								{row.registered_agent || "—"}
							</td>
							<td className="px-4 py-3">
								<StatusPill
									isActive={row.is_active}
									deactivatedOn={row.deactivated_on}
								/>
							</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}
