"use client";

// Index of the Carbon app-mockup suite — one card per screen so the whole
// exploration can be walked without knowing the routes. Design exploration
// only; nothing here touches the live app.

import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";
import { AppShell, Eyebrow, Tag } from "./carbon";

const SCREENS: {
	href: string;
	n: string;
	name: string;
	blurb: string;
	status?: string;
}[] = [
	{
		href: "/app-carbon-mockup/assistant",
		n: "01",
		name: "Assistant",
		blurb:
			"Corpus-grounded chat: thread rail, scope + model controls, retrieval progress, verified answer with pinned authorities.",
	},
	{
		href: "/browse-carbon-mockup",
		n: "02",
		name: "Library",
		blurb:
			"Browse home — one search box over 105,355 Iowa documents, flat source list, coverage rail.",
		status: "existing mockup",
	},
	{
		href: "/app-carbon-mockup/results",
		n: "03",
		name: "Search results",
		blurb:
			"Results list with refine rail: content type, court, status, decided-year histogram, cited authorities.",
	},
	{
		href: "/app-carbon-mockup/case",
		n: "04",
		name: "Case reader",
		blurb:
			"Three-pane decision reader: outline, opinion text with star pagination, citator treatment and cited authorities.",
	},
	{
		href: "/app-carbon-mockup/advanced",
		n: "05",
		name: "Advanced search",
		blurb:
			"Fielded query builder — terms and connectors, per-content-type document fields, date and jurisdiction.",
	},
	{
		href: "/app-carbon-mockup/compare",
		n: "06",
		name: "Compare editions",
		blurb:
			"Year-over-year Iowa Code diff: amended / added / repealed buckets, inline and side-by-side views.",
	},
	{
		href: "/app-carbon-mockup/account",
		n: "07",
		name: "Account settings",
		blurb:
			"Profile, practice, preferences, password, API keys, and MCP configuration in Carbon form patterns.",
	},
	{
		href: "/app-carbon-mockup/onboarding",
		n: "08",
		name: "Onboarding",
		blurb:
			"Six-step first-run wizard with Carbon progress indicator, theme picker, and terms acceptance.",
	},
	{
		href: "/app-carbon-mockup/signin",
		n: "09",
		name: "Sign in",
		blurb:
			"Signed-out gate: dark brand panel with the product promise, square form column.",
	},
];

export default function AppCarbonMockupIndex() {
	return (
		<AppShell active="/app-carbon-mockup">
			<div className="px-5 py-10 sm:px-8 lg:py-14">
				<Eyebrow>Design exploration — IBM Carbon v11</Eyebrow>
				<h1 className="mt-4 max-w-3xl font-light text-3xl sm:text-4xl">
					The Hudson app, restated in Carbon
				</h1>
				<p className="mt-3 max-w-2xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
					Every screen of the live app rebuilt in the IBM design language —
					square geometry, hairline rules, Plex type, one blue. Static data
					throughout; use the sun/moon toggle to proof both themes. Token
					reference lives in{" "}
					<span className="font-mono text-[13px]">
						docs/carbon-design-system.md
					</span>
					.
				</p>

				<div className="mt-10 grid gap-px border border-[var(--cds-border)] bg-[var(--cds-border)] sm:grid-cols-2 xl:grid-cols-3">
					{SCREENS.map((s) => (
						<Link
							key={s.href}
							href={s.href}
							className="group flex min-h-44 flex-col bg-[var(--cds-layer)] p-5 transition-colors hover:bg-[var(--cds-layer-hover)]"
						>
							<div className="flex items-center justify-between">
								<span className="font-mono text-[11px] text-[var(--cds-helper)]">
									{s.n}
								</span>
								{s.status && <Tag kind="outline">{s.status}</Tag>}
							</div>
							<h2 className="mt-3 font-semibold text-sm">{s.name}</h2>
							<p className="mt-1.5 text-[13px] text-[var(--cds-text-2)] leading-snug">
								{s.blurb}
							</p>
							<ArrowRightIcon className="mt-auto size-4 self-end text-[var(--cds-link)] transition-transform group-hover:translate-x-0.5" />
						</Link>
					))}
				</div>
			</div>
		</AppShell>
	);
}
