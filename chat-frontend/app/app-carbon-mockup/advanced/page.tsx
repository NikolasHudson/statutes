"use client";

// Carbon mockup of the advanced (fielded) search builder (live:
// /browse/advanced). Content-type pills swap the document-field set, exactly
// like the live page; connectors rail on the right; compiled-query preview in
// the submit bar. Static — the Search button doesn't run anything.

import { CornerDownLeftIcon, RotateCcwIcon } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import {
	AppShell,
	BtnGhost,
	BtnPrimary,
	Eyebrow,
	Panel,
	SelectField,
	TextField,
} from "../carbon";

type ContentType =
	| "Cases"
	| "Statutes & Codes"
	| "Regulations"
	| "Court Rules"
	| "Secondary Sources";

const CONTENT_TYPES: ContentType[] = [
	"Cases",
	"Statutes & Codes",
	"Regulations",
	"Court Rules",
	"Secondary Sources",
];

const TERM_BOXES: { label: string; connector: string; placeholder: string }[] =
	[
		{
			label: "All of these terms",
			connector: "AND",
			placeholder: "consumer fraud",
		},
		{
			label: "Any of these terms",
			connector: "OR",
			placeholder: "negligence liability",
		},
		{
			label: "This exact phrase",
			connector: '" "',
			placeholder: "private right of action",
		},
		{
			label: "Without these terms",
			connector: "NOT",
			placeholder: "bankruptcy",
		},
	];

const DATE_PRESETS = [
	"Any time",
	"Last year",
	"Last 5 years",
	"Last 10 years",
	"Custom range",
];

const JURISDICTIONS = [
	"Iowa",
	"All jurisdictions",
	"Federal",
	"All states",
	"California",
	"Illinois",
	"New York",
	"Texas",
];

const CONNECTORS: { op: string; desc: string; example: string }[] = [
	{ op: "AND", desc: "All terms must appear", example: "fraud AND damages" },
	{ op: "OR", desc: "Any term may appear", example: "negligence OR liability" },
	{
		op: '" "',
		desc: "Match an exact phrase",
		example: '"private right of action"',
	},
	{ op: "-", desc: "Exclude a term", example: "fraud -bankruptcy" },
];

const TIPS = [
	"Boxes are joined with the right connectors for you.",
	"Put a citation in the Citation field to jump straight to a section.",
	"Switch content type to see the fields that apply.",
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdvancedSearchCarbonMockup() {
	const [type, setType] = useState<ContentType>("Cases");
	const [datePreset, setDatePreset] = useState("Any time");

	return (
		<AppShell active="/app-carbon-mockup/advanced">
			<div className="px-5 py-10 sm:px-8 lg:py-14">
				<div className="flex flex-wrap items-end justify-between gap-4">
					<div>
						<Eyebrow>Search — fielded query builder</Eyebrow>
						<h1 className="mt-4 font-light text-3xl sm:text-4xl">
							Advanced search
						</h1>
						<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
							Build a precise query with fielded terms, connectors, and filters.
							Fields adapt to the selected content type.
						</p>
					</div>
					<BtnGhost>
						<RotateCcwIcon className="size-4" />
						Reset
					</BtnGhost>
				</div>

				<div className="mt-10 grid gap-10 lg:grid-cols-[1fr_17rem] xl:grid-cols-[1fr_19rem]">
					<div className="min-w-0 space-y-10">
						{/* Content type */}
						<FormSection
							title="Content type"
							desc="Determines the document fields below."
						>
							<div className="flex flex-wrap gap-px border border-[var(--cds-border)] bg-[var(--cds-border)]">
								{CONTENT_TYPES.map((t) => (
									<button
										key={t}
										type="button"
										onClick={() => setType(t)}
										className={cn(
											"h-10 flex-1 whitespace-nowrap px-4 text-[13px] transition-colors",
											t === type
												? "bg-[#0f62fe] font-semibold text-white"
												: "bg-[var(--cds-layer)] text-[var(--cds-text-2)] hover:bg-[var(--cds-layer-hover)]",
										)}
									>
										{t}
									</button>
								))}
							</div>
						</FormSection>

						{/* Search terms */}
						<FormSection
							title="Search terms"
							desc="Combined automatically with the right connectors."
						>
							<div className="grid gap-5 sm:grid-cols-2">
								{TERM_BOXES.map((t) => (
									<div key={t.label}>
										<div className="mb-2 flex items-baseline justify-between">
											<span className="text-[var(--cds-text-2)] text-xs">
												{t.label}
											</span>
											<span className="font-mono text-[11px] text-[var(--cds-helper)]">
												{t.connector}
											</span>
										</div>
										<input
											placeholder={t.placeholder}
											className="h-10 w-full border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] px-4 text-sm outline-none placeholder:text-[var(--cds-placeholder)] focus:outline-2 focus:-outline-offset-2 focus:outline-[#0f62fe]"
										/>
									</div>
								))}
							</div>
						</FormSection>

						{/* Document fields — swap by content type */}
						<FormSection title="Document fields" desc={`${type} fields`}>
							<DocumentFields type={type} />
						</FormSection>

						{/* Date */}
						<FormSection title="Date">
							<div className="flex flex-wrap gap-2">
								{DATE_PRESETS.map((p) => (
									<button
										key={p}
										type="button"
										onClick={() => setDatePreset(p)}
										className={cn(
											"h-8 border px-3 text-[13px] transition-colors",
											p === datePreset
												? "border-[#0f62fe] bg-[#0f62fe]/10 font-medium text-[var(--cds-link)]"
												: "border-[var(--cds-border)] text-[var(--cds-text-2)] hover:border-[var(--cds-border-strong)]",
										)}
									>
										{p}
									</button>
								))}
							</div>
							{datePreset === "Custom range" && (
								<div className="mt-4 grid max-w-xs grid-cols-2 gap-4">
									<TextField
										label="From year"
										placeholder="1839"
										inputMode="numeric"
									/>
									<TextField
										label="To year"
										placeholder="2026"
										inputMode="numeric"
									/>
								</div>
							)}
						</FormSection>

						{/* Jurisdiction */}
						<FormSection title="Jurisdiction">
							<SelectField
								options={JURISDICTIONS}
								className="max-w-xs"
								aria-label="Jurisdiction"
							/>
							<p className="mt-2 text-[var(--cds-helper)] text-xs">
								Corpus currently covers Iowa; multi-jurisdiction is on the
								roadmap.
							</p>
						</FormSection>

						{/* Submit bar */}
						<div className="flex flex-wrap items-center justify-between gap-4 border border-[var(--cds-border)] bg-[var(--cds-layer)] p-4">
							<p className="min-w-0 text-[13px] text-[var(--cds-text-2)]">
								Query:{" "}
								<span className="font-mono text-[var(--cds-text)]">
									&ldquo;spring gun&rdquo; AND (liability OR damages)
									court:supreme-court-of-iowa
								</span>
							</p>
							<BtnPrimary size="md">Search</BtnPrimary>
						</div>
					</div>

					{/* Right rail */}
					<aside className="space-y-6">
						<Panel title="Connectors">
							<dl className="divide-y divide-[var(--cds-border)]">
								{CONNECTORS.map((c) => (
									<div key={c.op} className="px-4 py-2.5">
										<div className="flex items-baseline gap-3">
											<dt className="w-10 shrink-0 font-mono text-[13px] text-[var(--cds-link)]">
												{c.op}
											</dt>
											<dd className="text-[13px]">{c.desc}</dd>
										</div>
										<p className="mt-0.5 pl-[3.25rem] font-mono text-[11px] text-[var(--cds-helper)]">
											{c.example}
										</p>
									</div>
								))}
							</dl>
						</Panel>

						<Panel title="Tips">
							<ul className="space-y-3 px-4 py-3">
								{TIPS.map((t) => (
									<li
										key={t}
										className="flex gap-2.5 text-[12px] text-[var(--cds-text-2)] leading-snug"
									>
										<CornerDownLeftIcon className="mt-0.5 size-3.5 shrink-0 text-[var(--cds-helper)]" />
										{t}
									</li>
								))}
							</ul>
						</Panel>
					</aside>
				</div>
			</div>
		</AppShell>
	);
}

// ---------------------------------------------------------------------------
// Section + per-type field sets
// ---------------------------------------------------------------------------

function FormSection({
	title,
	desc,
	children,
}: {
	title: string;
	desc?: string;
	children: React.ReactNode;
}) {
	return (
		<section className="border-[var(--cds-border)] border-t pt-5">
			<div className="mb-5 flex items-baseline justify-between gap-4">
				<h2 className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
					{title}
				</h2>
				{desc && <p className="text-[var(--cds-helper)] text-xs">{desc}</p>}
			</div>
			{children}
		</section>
	);
}

function DocumentFields({ type }: { type: ContentType }) {
	if (type === "Cases") {
		return (
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField label="Case name" placeholder="State v. Brown" />
				<TextField label="Citation" placeholder="223 N.W.2d 270" />
				<TextField label="Docket number" placeholder="21-1234" />
				<TextField label="Judge / author" placeholder="McDonald" />
				<TextField label="Attorney" placeholder="Counsel of record" />
				<SelectField
					label="Court"
					options={[
						"Any court",
						"Supreme Court of Iowa",
						"Court of Appeals of Iowa",
					]}
				/>
				<SelectField
					label="Status"
					options={["Any status", "Published", "Unpublished"]}
				/>
				<TextField
					label="Cites (authority)"
					placeholder="A citation this case cites"
				/>
			</div>
		);
	}
	if (type === "Statutes & Codes") {
		return (
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField label="Section heading" placeholder="Consumer frauds" />
				<TextField label="Citation" placeholder="714.16" />
				<TextField label="Chapter" placeholder="714" />
				<TextField label="Title / division" placeholder="Criminal law" />
			</div>
		);
	}
	if (type === "Regulations") {
		return (
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField label="Rule heading" placeholder="Licensing procedures" />
				<TextField label="Citation" placeholder="661—10.1" />
				<TextField label="Agency" placeholder="Insurance Division" />
			</div>
		);
	}
	if (type === "Court Rules") {
		return (
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField label="Rule name" placeholder="Form of pleadings" />
				<TextField label="Citation" placeholder="R. Civ. P. 1.402" />
				<SelectField
					label="Rule set"
					options={[
						"Any rule set",
						"Civil Procedure",
						"Criminal Procedure",
						"Evidence",
						"Appellate Procedure",
					]}
				/>
			</div>
		);
	}
	return (
		<div className="grid gap-5 sm:grid-cols-2">
			<TextField label="Title" placeholder="Premises liability in Iowa" />
			<TextField label="Author" placeholder="Author name" />
			<TextField label="Publication" placeholder="Iowa Law Review" />
		</div>
	);
}
