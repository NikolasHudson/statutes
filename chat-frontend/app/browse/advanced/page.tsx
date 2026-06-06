"use client";

// Full-page Advanced Search — the classic research-tool fielded search builder
// (Westlaw/Lexis style) for the live corpus. Promoted from the /browse-mockup
// design into a real /browse sub-route: universal term boxes (all/any/phrase/
// exclude) over a content-type-aware field grid, date + jurisdiction filters,
// and a connectors/tips rail. Submitting compiles the form into the live
// /browse search params so it runs against the corpus; fields the backend
// doesn't model yet fold into the query as plain terms. Opening this page with
// existing /browse params (q/doc_type/court/status/from/to) seeds the form so a
// search can be refined here without losing what was already typed.

import {
	ChevronRightIcon,
	CornerDownLeftIcon,
	RotateCcwIcon,
	SearchIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { BrowseSidebar } from "@/components/browse/browse-sidebar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
	SidebarInset,
	SidebarProvider,
	SidebarTrigger,
} from "@/components/ui/sidebar";
import { type BrowseSource, browseSources } from "@/lib/iowa-browse";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Content-type model — the available document fields adapt to the type
// ---------------------------------------------------------------------------

type ContentType = "cases" | "statutes" | "regulations" | "rules" | "secondary";

const CONTENT_TYPES: { id: ContentType; label: string }[] = [
	{ id: "cases", label: "Cases" },
	{ id: "statutes", label: "Statutes & Codes" },
	{ id: "regulations", label: "Regulations" },
	{ id: "rules", label: "Court Rules" },
	{ id: "secondary", label: "Secondary Sources" },
];

type FieldDef = {
	id: string;
	label: string;
	kind: "text" | "select";
	placeholder?: string;
	options?: string[];
};

// Field sets per content type. Selects carry an "Any …" first option so an
// untouched select contributes nothing to the query.
const FIELD_SETS: Record<ContentType, FieldDef[]> = {
	cases: [
		{
			id: "name",
			label: "Case name",
			kind: "text",
			placeholder: "State v. Brown",
		},
		{
			id: "citation",
			label: "Citation",
			kind: "text",
			placeholder: "223 N.W.2d 270",
		},
		{
			id: "docket",
			label: "Docket number",
			kind: "text",
			placeholder: "21-1234",
		},
		{
			id: "judge",
			label: "Judge / author",
			kind: "text",
			placeholder: "McDonald",
		},
		{
			id: "attorney",
			label: "Attorney",
			kind: "text",
			placeholder: "Counsel of record",
		},
		{
			id: "court",
			label: "Court",
			kind: "select",
			options: [
				"Any court",
				"Supreme Court of Iowa",
				"Court of Appeals of Iowa",
			],
		},
		{
			id: "status",
			label: "Status",
			kind: "select",
			options: ["Any status", "Published", "Unpublished"],
		},
		{
			id: "cites",
			label: "Cites (authority)",
			kind: "text",
			placeholder: "A citation this case cites",
		},
	],
	statutes: [
		{
			id: "heading",
			label: "Section heading",
			kind: "text",
			placeholder: "Consumer frauds",
		},
		{ id: "citation", label: "Citation", kind: "text", placeholder: "714.16" },
		{ id: "chapter", label: "Chapter", kind: "text", placeholder: "714" },
		{
			id: "title",
			label: "Title / division",
			kind: "text",
			placeholder: "Criminal law",
		},
	],
	regulations: [
		{ id: "heading", label: "Rule heading", kind: "text" },
		{
			id: "citation",
			label: "Citation",
			kind: "text",
			placeholder: "661—10.1",
		},
		{
			id: "agency",
			label: "Agency",
			kind: "text",
			placeholder: "Insurance Division",
		},
	],
	rules: [
		{
			id: "name",
			label: "Rule name",
			kind: "text",
			placeholder: "Form of pleadings",
		},
		{
			id: "citation",
			label: "Citation",
			kind: "text",
			placeholder: "R. Civ. P. 1.402",
		},
		{
			id: "ruleset",
			label: "Rule set",
			kind: "select",
			options: [
				"Any rule set",
				"Civil Procedure",
				"Criminal Procedure",
				"Evidence",
				"Appellate Procedure",
			],
		},
	],
	secondary: [
		{ id: "title", label: "Title", kind: "text" },
		{ id: "author", label: "Author", kind: "text" },
		{
			id: "publication",
			label: "Publication",
			kind: "text",
			placeholder: "Iowa Law Review",
		},
	],
};

// Backend `doc_type` alias per content type (null → not modeled yet; the query
// still runs unscoped). Reversed below to seed the form from a /browse URL.
const DOC_TYPE: Record<ContentType, string | null> = {
	cases: "cases",
	statutes: "code",
	rules: "rules",
	regulations: null,
	secondary: null,
};

const CONTENT_TYPE_BY_DOC: Record<string, ContentType> = {
	cases: "cases",
	code: "statutes",
	rules: "rules",
};

// court <select> label <-> backend `court` slug.
const COURT_SLUG: Record<string, string> = {
	"Supreme Court of Iowa": "iowa",
	"Court of Appeals of Iowa": "iowactapp",
};
const COURT_LABEL_BY_SLUG: Record<string, string> = {
	iowa: "Supreme Court of Iowa",
	iowactapp: "Court of Appeals of Iowa",
};

const TERM_FIELDS = [
	{
		id: "all",
		label: "All of these terms",
		hint: "AND",
		placeholder: "consumer fraud",
	},
	{
		id: "any",
		label: "Any of these terms",
		hint: "OR",
		placeholder: "negligence liability",
	},
	{
		id: "phrase",
		label: "This exact phrase",
		hint: "“ ”",
		placeholder: "private right of action",
	},
	{
		id: "exclude",
		label: "Without these terms",
		hint: "NOT",
		placeholder: "bankruptcy",
	},
] as const;

type TermId = (typeof TERM_FIELDS)[number]["id"];

const CURRENT_YEAR = new Date().getFullYear();
const MIN_YEAR = 1839;

const DATE_PRESETS: { id: string; label: string; from?: number }[] = [
	{ id: "any", label: "Any time" },
	{ id: "1", label: "Last year", from: CURRENT_YEAR - 1 },
	{ id: "5", label: "Last 5 years", from: CURRENT_YEAR - 5 },
	{ id: "10", label: "Last 10 years", from: CURRENT_YEAR - 10 },
	{ id: "custom", label: "Custom range" },
];

const JURISDICTIONS = [
	"All jurisdictions",
	"Federal",
	"Iowa",
	"All states",
	"California",
	"Illinois",
	"New York",
	"Texas",
];

const CONNECTORS = [
	{ op: "AND", desc: "All terms must appear", example: "fraud AND damages" },
	{ op: "OR", desc: "Any term may appear", example: "negligence OR liability" },
	{
		op: "“ ”",
		desc: "Match an exact phrase",
		example: "“private right of action”",
	},
	{ op: "-", desc: "Exclude a term", example: "fraud -bankruptcy" },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

// useSearchParams() must be read inside a Suspense boundary.
export default function AdvancedSearchPage() {
	return (
		<Suspense
			fallback={
				<div className="grid h-dvh place-items-center text-muted-foreground text-sm">
					Loading…
				</div>
			}
		>
			<AdvancedSearchPageInner />
		</Suspense>
	);
}

function AdvancedSearchPageInner() {
	const router = useRouter();
	const searchParams = useSearchParams();

	// ---- sidebar data (shared corpus sidebar) -----------------------------
	const [sources, setSources] = useState<BrowseSource[] | null>(null);
	const [sourcesError, setSourcesError] = useState<string | null>(null);
	useEffect(() => {
		let cancelled = false;
		browseSources()
			.then((s) => !cancelled && setSources(s))
			.catch((e) => {
				if (cancelled) return;
				setSourcesError(
					e instanceof Error ? e.message : "Failed to load corpus sources.",
				);
			});
		return () => {
			cancelled = true;
		};
	}, []);

	// ---- form state, seeded once from the incoming /browse params ----------
	const [contentType, setContentType] = useState<ContentType>(() => {
		const dt = searchParams.get("doc_type");
		return (dt && CONTENT_TYPE_BY_DOC[dt]) || "cases";
	});
	const [terms, setTerms] = useState<Record<TermId, string>>(() => ({
		all: searchParams.get("q") ?? "",
		any: "",
		phrase: "",
		exclude: "",
	}));
	const [fields, setFields] = useState<Record<string, string>>(() => {
		const seed: Record<string, string> = {};
		const court = searchParams.get("court");
		if (court && COURT_LABEL_BY_SLUG[court])
			seed.court = COURT_LABEL_BY_SLUG[court];
		const status = searchParams.get("status");
		if (status) seed.status = status;
		return seed;
	});
	const seededFrom = (searchParams.get("from") ?? "").slice(0, 4);
	const seededTo = (searchParams.get("to") ?? "").slice(0, 4);
	const [datePreset, setDatePreset] = useState(
		seededFrom || seededTo ? "custom" : "any",
	);
	const [yearFrom, setYearFrom] = useState(seededFrom);
	const [yearTo, setYearTo] = useState(seededTo);
	const [jurisdiction, setJurisdiction] = useState(JURISDICTIONS[2]); // Iowa

	const activeFields = FIELD_SETS[contentType];

	// Switching content type drops the previous type's field values so a stale
	// court/docket can't ride along with an unrelated search.
	const changeContentType = (t: ContentType) => {
		setContentType(t);
		setFields({});
	};

	const setTerm = (id: TermId, v: string) =>
		setTerms((p) => ({ ...p, [id]: v }));
	const setField = (id: string, v: string) =>
		setFields((p) => ({ ...p, [id]: v }));

	const applyPreset = (id: string) => {
		setDatePreset(id);
		const preset = DATE_PRESETS.find((p) => p.id === id);
		if (id === "any") {
			setYearFrom("");
			setYearTo("");
		} else if (preset?.from) {
			setYearFrom(String(preset.from));
			setYearTo(String(CURRENT_YEAR));
		}
	};

	const reset = () => {
		setTerms({ all: "", any: "", phrase: "", exclude: "" });
		setFields({});
		setDatePreset("any");
		setYearFrom("");
		setYearTo("");
	};

	// ---- sidebar nav -> back into the live browser ------------------------
	const onHome = () => router.push("/browse");
	const onOpenSource = (slug: string) =>
		router.push(`/browse?source=${encodeURIComponent(slug)}`);

	// Compile the form into a single query string + the structured params the
	// backend understands. A live preview of the query is shown to the user.
	const compiled = useMemo(() => {
		const parts: string[] = [];
		if (terms.all.trim()) parts.push(terms.all.trim());
		if (terms.phrase.trim()) parts.push(`"${terms.phrase.trim()}"`);
		if (terms.any.trim())
			parts.push(terms.any.trim().split(/\s+/).join(" OR "));
		if (terms.exclude.trim())
			parts.push(
				terms.exclude
					.trim()
					.split(/\s+/)
					.map((w) => `-${w}`)
					.join(" "),
			);
		// Fold free-text field values into the query as plain terms (phrase-quoted
		// when they contain a space so a case name stays together).
		for (const f of activeFields) {
			if (f.kind !== "text") continue;
			const v = fields[f.id]?.trim();
			if (v) parts.push(/\s/.test(v) ? `"${v}"` : v);
		}
		return parts.join(" ").trim();
	}, [terms, fields, activeFields]);

	const submit = () => {
		const params = new URLSearchParams();
		if (compiled) params.set("q", compiled);
		const docType = DOC_TYPE[contentType];
		if (docType) params.set("doc_type", docType);
		if (contentType === "cases") {
			const court = COURT_SLUG[fields.court ?? ""];
			if (court) params.set("court", court);
			const status = fields.status;
			if (status && status !== "Any status") params.set("status", status);
		}
		if (/^\d{4}$/.test(yearFrom)) params.set("from", `${yearFrom}-01-01`);
		if (/^\d{4}$/.test(yearTo)) params.set("to", `${yearTo}-12-31`);
		const qs = params.toString();
		router.push(qs ? `/browse?${qs}` : "/browse");
	};

	return (
		<SidebarProvider defaultOpen={false}>
			<div className="flex h-dvh w-full pr-0.5">
				<BrowseSidebar
					sources={sources}
					sourcesError={sourcesError}
					mode="home"
					activeSlug={null}
					onHome={onHome}
					onOpenSource={onOpenSource}
				/>
				<SidebarInset>
					<header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
						<SidebarTrigger />
						<Separator orientation="vertical" className="mr-1 h-4" />
						<Link
							href="/browse"
							className="text-muted-foreground text-sm hover:text-foreground"
						>
							Browse the corpus
						</Link>
						<ChevronRightIcon className="size-3.5 text-muted-foreground/50" />
						<span className="font-medium text-sm">Advanced Search</span>
						<Button
							variant="ghost"
							size="sm"
							onClick={reset}
							className="ml-auto text-muted-foreground"
						>
							<RotateCcwIcon className="size-3.5" />
							<span className="hidden sm:inline">Reset</span>
						</Button>
						<Button size="sm" onClick={submit}>
							<SearchIcon className="size-3.5" />
							Search
						</Button>
					</header>

					<main className="min-w-0 flex-1 overflow-y-auto">
						<form
							className="mx-auto max-w-6xl px-5 py-5"
							onSubmit={(e) => {
								e.preventDefault();
								submit();
							}}
						>
							<h1 className="font-semibold text-xl tracking-tight">
								Advanced Search
							</h1>
							<p className="mt-0.5 text-muted-foreground text-xs">
								Build a precise query with fielded terms, connectors, and
								filters. Fields adapt to the selected content type.
							</p>

							<div className="mt-4 grid gap-5 lg:grid-cols-[1fr_18rem]">
								{/* ---- Left: the form -------------------------------- */}
								<div className="min-w-0 space-y-4">
									{/* Content type */}
									<Section
										title="Content type"
										desc="Determines the document fields below."
									>
										<div className="flex flex-wrap gap-1 p-3">
											{CONTENT_TYPES.map((t) => (
												<button
													key={t.id}
													type="button"
													onClick={() => changeContentType(t.id)}
													className={cn(
														"rounded-md px-3 py-1.5 font-medium text-[13px] transition-colors",
														t.id === contentType
															? "bg-primary text-primary-foreground"
															: "text-muted-foreground hover:bg-accent hover:text-foreground",
													)}
												>
													{t.label}
												</button>
											))}
										</div>
									</Section>

									{/* Terms */}
									<Section
										title="Search terms"
										desc="Combined automatically with the right connectors."
									>
										<div className="grid gap-3 p-3 sm:grid-cols-2">
											{TERM_FIELDS.map((t) => (
												<label
													key={t.id}
													htmlFor={`term-${t.id}`}
													className="flex flex-col gap-1"
												>
													<span className="flex items-center justify-between">
														<FieldLabel>{t.label}</FieldLabel>
														<span className="font-mono text-[10px] text-muted-foreground">
															{t.hint}
														</span>
													</span>
													<Input
														id={`term-${t.id}`}
														value={terms[t.id]}
														onChange={(e) => setTerm(t.id, e.target.value)}
														placeholder={t.placeholder}
														className="h-9"
													/>
												</label>
											))}
										</div>
									</Section>

									{/* Document fields */}
									<Section
										title="Document fields"
										desc={`${CONTENT_TYPES.find((c) => c.id === contentType)?.label} fields`}
									>
										<div className="grid gap-3 p-3 sm:grid-cols-2">
											{activeFields.map((f) => (
												<label
													key={f.id}
													htmlFor={`field-${f.id}`}
													className="flex flex-col gap-1"
												>
													<FieldLabel>{f.label}</FieldLabel>
													{f.kind === "select" ? (
														<select
															id={`field-${f.id}`}
															value={fields[f.id] ?? f.options?.[0] ?? ""}
															onChange={(e) => setField(f.id, e.target.value)}
															className="h-9 cursor-pointer rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
														>
															{f.options?.map((o) => (
																<option key={o} value={o}>
																	{o}
																</option>
															))}
														</select>
													) : (
														<Input
															id={`field-${f.id}`}
															value={fields[f.id] ?? ""}
															onChange={(e) => setField(f.id, e.target.value)}
															placeholder={f.placeholder}
															className="h-9"
														/>
													)}
												</label>
											))}
										</div>
									</Section>

									{/* Date + jurisdiction */}
									<div className="grid gap-4 sm:grid-cols-2">
										<Section title="Date">
											<div className="space-y-3 p-3">
												<div className="flex flex-wrap gap-1">
													{DATE_PRESETS.map((p) => (
														<button
															key={p.id}
															type="button"
															onClick={() => applyPreset(p.id)}
															className={cn(
																"rounded-md border px-2 py-1 text-xs transition-colors",
																datePreset === p.id
																	? "border-foreground bg-foreground text-background"
																	: "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
															)}
														>
															{p.label}
														</button>
													))}
												</div>
												<div className="flex items-center gap-2">
													<Input
														type="number"
														inputMode="numeric"
														min={MIN_YEAR}
														max={CURRENT_YEAR}
														placeholder="From"
														value={yearFrom}
														onChange={(e) => {
															setYearFrom(e.target.value);
															setDatePreset("custom");
														}}
														className="h-9 w-24"
													/>
													<span className="text-muted-foreground text-sm">
														to
													</span>
													<Input
														type="number"
														inputMode="numeric"
														min={MIN_YEAR}
														max={CURRENT_YEAR}
														placeholder="To"
														value={yearTo}
														onChange={(e) => {
															setYearTo(e.target.value);
															setDatePreset("custom");
														}}
														className="h-9 w-24"
													/>
												</div>
											</div>
										</Section>

										<Section title="Jurisdiction">
											<div className="p-3">
												<select
													value={jurisdiction}
													onChange={(e) => setJurisdiction(e.target.value)}
													className="h-9 w-full cursor-pointer rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
												>
													{JURISDICTIONS.map((j) => (
														<option key={j} value={j}>
															{j}
														</option>
													))}
												</select>
												<p className="mt-2 text-[11px] text-muted-foreground">
													Corpus currently covers Iowa; multi-jurisdiction is on
													the roadmap.
												</p>
											</div>
										</Section>
									</div>

									{/* Submit bar */}
									<div className="flex items-center justify-between gap-3 rounded-lg border bg-muted/30 px-3 py-2.5">
										<p className="min-w-0 truncate text-muted-foreground text-xs">
											{compiled ? (
												<>
													Query:{" "}
													<span className="font-mono text-foreground">
														{compiled}
													</span>
												</>
											) : (
												"Enter terms or fields to build your query."
											)}
										</p>
										<div className="flex shrink-0 items-center gap-2">
											<Button
												type="button"
												variant="ghost"
												size="sm"
												onClick={reset}
											>
												Reset
											</Button>
											<Button type="submit" size="sm">
												<SearchIcon className="size-3.5" />
												Search
											</Button>
										</div>
									</div>
								</div>

								{/* ---- Right: connectors + tips ---------------------- */}
								<aside className="space-y-4">
									<Section title="Connectors">
										<ul className="divide-y">
											{CONNECTORS.map((c) => (
												<li key={c.op} className="px-3 py-2">
													<div className="flex items-center gap-2">
														<code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground">
															{c.op}
														</code>
														<span className="text-[13px]">{c.desc}</span>
													</div>
													<div className="mt-1 font-mono text-[11px] text-muted-foreground">
														{c.example}
													</div>
												</li>
											))}
										</ul>
									</Section>

									<Section title="Tips">
										<ul className="space-y-2 px-3 py-2.5 text-[12px] text-muted-foreground leading-snug">
											<li className="flex gap-2">
												<CornerDownLeftIcon className="mt-0.5 size-3.5 shrink-0" />
												The term boxes are joined for you — no need to type
												operators.
											</li>
											<li className="flex gap-2">
												<CornerDownLeftIcon className="mt-0.5 size-3.5 shrink-0" />
												Put a citation in the Citation field to jump straight to
												a section.
											</li>
											<li className="flex gap-2">
												<CornerDownLeftIcon className="mt-0.5 size-3.5 shrink-0" />
												Switch content type to see the fields that apply.
											</li>
										</ul>
									</Section>
								</aside>
							</div>
						</form>
					</main>
				</SidebarInset>
			</div>
		</SidebarProvider>
	);
}

// ---------------------------------------------------------------------------
// Bits
// ---------------------------------------------------------------------------

function Section({
	title,
	desc,
	children,
}: {
	title: string;
	desc?: string;
	children: React.ReactNode;
}) {
	return (
		<section className="overflow-hidden rounded-lg border bg-card">
			<header className="flex items-baseline justify-between gap-3 border-b px-3 py-2">
				<h2 className="font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
					{title}
				</h2>
				{desc && (
					<span className="truncate text-[11px] text-muted-foreground/80">
						{desc}
					</span>
				)}
			</header>
			{children}
		</section>
	);
}

function FieldLabel({ children }: { children: React.ReactNode }) {
	return (
		<span className="font-medium text-foreground/80 text-xs">{children}</span>
	);
}
