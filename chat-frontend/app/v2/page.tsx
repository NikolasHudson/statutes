"use client";

// Temporary v2 home: build-status index of the Carbon rebuild. Each card is a
// real /v2 route; "wired" means the screen runs against live data. This page
// is replaced by the real search-first Library home once search is wired.

import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/components/auth-gate";
import { Eyebrow, Tag } from "@/components/carbon/primitives";

const SCREENS: {
	href: string;
	n: string;
	name: string;
	blurb: string;
	wired: boolean;
}[] = [
	{
		href: "/v2/assistant",
		n: "01",
		name: "Assistant",
		blurb:
			"Corpus-grounded chat: thread rail, scope + model controls, retrieval progress, verified answer with pinned authorities.",
		wired: false,
	},
	{
		href: "/v2/results",
		n: "02",
		name: "Search results",
		blurb:
			"Results list with refine rail: content type, court, status, decided-year histogram, cited authorities.",
		wired: false,
	},
	{
		href: "/v2/case",
		n: "03",
		name: "Case reader",
		blurb:
			"Three-pane decision reader: outline, opinion text with star pagination, citator treatment and cited authorities.",
		wired: false,
	},
	{
		href: "/v2/advanced",
		n: "04",
		name: "Advanced search",
		blurb:
			"Fielded query builder — terms and connectors, per-content-type document fields, date and jurisdiction.",
		wired: false,
	},
	{
		href: "/v2/compare",
		n: "05",
		name: "Compare editions",
		blurb:
			"Year-over-year Iowa Code diff: amended / added / repealed buckets, inline and side-by-side views.",
		wired: false,
	},
	{
		href: "/v2/account",
		n: "06",
		name: "Account settings",
		blurb:
			"Profile, practice, preferences, password, API keys, and MCP configuration.",
		wired: false,
	},
];

export default function V2Home() {
	const { user } = useAuth();
	const firstName = user.first_name || user.full_name || user.email;
	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<Eyebrow>Hudson Corpus — v2 preview</Eyebrow>
			<h1 className="mt-4 max-w-3xl font-light text-3xl sm:text-4xl">
				Welcome back, {firstName}
			</h1>
			<p className="mt-3 max-w-2xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
				The functional Carbon rebuild of the app, wired screen by screen against
				the live corpus. The classic app stays untouched at{" "}
				<Link href="/" className="text-[var(--cds-link)] hover:underline">
					corpus.nick.law
				</Link>{" "}
				until this version has earned the swap; the static designs live at{" "}
				<Link
					href="/app-carbon-mockup"
					className="text-[var(--cds-link)] hover:underline"
				>
					/app-carbon-mockup
				</Link>
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
							{s.wired ? (
								<Tag kind="green">wired</Tag>
							) : (
								<Tag kind="outline">design only</Tag>
							)}
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
	);
}
