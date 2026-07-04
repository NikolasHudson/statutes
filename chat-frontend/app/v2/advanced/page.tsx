"use client";

// v2 advanced search — fielded query builder over the filters the search
// endpoint actually supports (content type, court, status, decided-year
// range). Builds the same /v2/results URL the results rail produces, so the
// two surfaces always agree. Connector syntax (AND/OR/quotes/-exclude) rides
// in the query itself.

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
	type AdvancedFilters,
	EMPTY_FILTERS,
	toSearchFilters,
} from "@/components/browse/advanced-search";
import {
	BtnPrimary,
	Eyebrow,
	Panel,
	SelectField,
	TextField,
} from "@/components/carbon/primitives";
import { buildSearchQuery } from "@/lib/search-url";
import { cn } from "@/lib/utils";

const DOC_TYPES: { id: AdvancedFilters["docType"]; label: string }[] = [
	{ id: "all", label: "All content" },
	{ id: "cases", label: "Cases" },
	{ id: "code", label: "Iowa Code" },
	{ id: "rules", label: "Court Rules" },
];

const COURTS = [
	{ value: "", label: "Any court" },
	{ value: "iowa", label: "Supreme Court of Iowa" },
	{ value: "iowactapp", label: "Court of Appeals of Iowa" },
];

const STATUSES = [
	{ value: "", label: "Any status" },
	{ value: "Published", label: "Published" },
	{ value: "Unpublished", label: "Unpublished" },
];

export default function V2AdvancedPage() {
	const router = useRouter();
	const [query, setQuery] = useState("");
	const [filters, setFilters] = useState<AdvancedFilters>(EMPTY_FILTERS);

	const casesScoped = filters.docType === "all" || filters.docType === "cases";

	const setDocType = (v: AdvancedFilters["docType"]) =>
		setFilters(
			v === "all" || v === "cases"
				? { ...filters, docType: v }
				: {
						...filters,
						docType: v,
						court: "",
						status: "",
						yearFrom: "",
						yearTo: "",
					},
		);

	const run = () => {
		const q = query.trim();
		if (!q) return;
		router.push(`/v2/results?${buildSearchQuery(q, toSearchFilters(filters))}`);
	};

	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<Eyebrow>Fielded search</Eyebrow>
			<h1 className="mt-4 font-light text-3xl sm:text-4xl">Advanced search</h1>
			<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
				Build a scoped query. Everything here maps onto the same search the
				Library box runs — the results page shows these as removable filters.
			</p>

			<form
				className="mt-10 grid max-w-4xl gap-10 lg:grid-cols-[minmax(0,1fr)_18rem]"
				onSubmit={(e) => {
					e.preventDefault();
					run();
				}}
			>
				<div className="min-w-0">
					<TextField
						label="Query"
						placeholder='e.g. "spring gun" AND liability -criminal'
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						helper="Terms and connectors: AND, OR, quoted phrases, -exclude. A bare citation (714.16) jumps straight to the section."
					/>

					<p className="mt-8 mb-2 text-[var(--cds-text-2)] text-xs">
						Content type
					</p>
					<div className="inline-flex flex-wrap border border-[var(--cds-border)]">
						{DOC_TYPES.map((d) => (
							<button
								key={d.id}
								type="button"
								onClick={() => setDocType(d.id)}
								className={cn(
									"flex h-10 items-center px-4 text-[13px] transition-colors",
									filters.docType === d.id
										? "bg-[var(--cds-layer-selected)] font-semibold"
										: "text-[var(--cds-text-2)] hover:bg-[var(--cds-layer-hover)]",
								)}
							>
								{d.label}
							</button>
						))}
					</div>

					<div className="mt-8 grid gap-5 sm:grid-cols-2">
						<SelectField
							label="Court"
							options={COURTS}
							value={filters.court}
							disabled={!casesScoped}
							onChange={(e) =>
								setFilters({ ...filters, court: e.target.value })
							}
						/>
						<SelectField
							label="Precedential status"
							options={STATUSES}
							value={filters.status}
							disabled={!casesScoped}
							onChange={(e) =>
								setFilters({ ...filters, status: e.target.value })
							}
						/>
						<TextField
							label="Decided from (year)"
							inputMode="numeric"
							placeholder="1839"
							value={filters.yearFrom}
							disabled={!casesScoped}
							onChange={(e) =>
								setFilters({ ...filters, yearFrom: e.target.value })
							}
						/>
						<TextField
							label="Decided to (year)"
							inputMode="numeric"
							placeholder="2026"
							value={filters.yearTo}
							disabled={!casesScoped}
							onChange={(e) =>
								setFilters({ ...filters, yearTo: e.target.value })
							}
						/>
					</div>
					{!casesScoped && (
						<p className="mt-2 text-[11px] text-[var(--cds-helper)]">
							Court, status, and year apply to cases.
						</p>
					)}

					<div className="mt-10">
						<BtnPrimary type="submit" disabled={!query.trim()}>
							Search the corpus
						</BtnPrimary>
					</div>
				</div>

				<aside className="space-y-6">
					<Panel title="Connectors">
						<ul className="space-y-2 px-4 py-3 text-[12px] text-[var(--cds-text-2)] leading-snug">
							<li>
								<span className="font-mono">estoppel AND waiver</span> — both
								terms
							</li>
							<li>
								<span className="font-mono">landlord OR lessor</span> — either
								term
							</li>
							<li>
								<span className="font-mono">&ldquo;spring gun&rdquo;</span> —
								exact phrase
							</li>
							<li>
								<span className="font-mono">-criminal</span> — exclude a term
							</li>
						</ul>
					</Panel>
					<Panel title="Scope notes">
						<ul className="space-y-2 px-4 py-3 text-[12px] text-[var(--cds-text-2)] leading-snug">
							<li>Search covers the approved, currently effective corpus.</li>
							<li>
								Caselaw filters (court, status, year) scope the search to
								decisions automatically.
							</li>
						</ul>
					</Panel>
				</aside>
			</form>
		</div>
	);
}
