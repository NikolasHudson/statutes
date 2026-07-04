"use client";

// Carbon mockup of the case reader (live: /cases/[id] + case-console.tsx).
// Westlaw-style three-pane layout restated in Carbon: outline/details rail,
// opinion column with star pagination and footnotes, citator + authorities
// rail. Opinion body is IBM Plex Serif — Carbon's editorial long-form face.
// Demo document: Katko v. Briney. Static data; nothing calls the API.

import {
	CheckIcon,
	CopyIcon,
	ExternalLinkIcon,
	MinusIcon,
	PlusIcon,
	PrinterIcon,
	QuoteIcon,
} from "lucide-react";
import { IBM_Plex_Serif } from "next/font/google";
import Link from "next/link";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { AppShell, KVList, Notification, Panel, Tag } from "../carbon";

const plexSerif = IBM_Plex_Serif({
	weight: ["400", "600"],
	style: ["normal", "italic"],
	subsets: ["latin"],
	variable: "--font-plex-serif",
});

// ---------------------------------------------------------------------------
// Static case data
// ---------------------------------------------------------------------------

const OUTLINE = [
	{ id: "syllabus", label: "Syllabus", depth: 0 },
	{ id: "opinion", label: "Opinion — Moore, C.J.", depth: 0 },
	{ id: "facts", label: "I. Facts", depth: 1 },
	{ id: "law", label: "II. The governing rule", depth: 1 },
	{ id: "holding", label: "III. Disposition", depth: 1 },
	{ id: "dissent", label: "Dissent — Larson, J.", depth: 0 },
];

const DETAILS = [
	["Disposition", "Affirmed"],
	["Posture", "Appeal from jury verdict"],
	["Nature of suit", "Trespass — personal injury"],
	["Panel", "Moore, C.J., and 8 JJ."],
] as const;

const CITED_IN_CORPUS: { name: string; cite: string }[] = [
	{ name: "Hooker v. Miller", cite: "37 Iowa 613 (1873)" },
	{ name: "State v. Vance", cite: "17 Iowa 138 (1864)" },
	{ name: "Phelps v. Hamlett", cite: "207 S.W. 425 (Tex. 1918)" },
];

const CITING_CASES: {
	name: string;
	cite: string;
	treatment: "green" | "yellow";
}[] = [
	{
		name: "State v. Metcalf",
		cite: "260 N.W.2d 857 (Iowa 1977)",
		treatment: "yellow",
	},
	{
		name: "Nichols v. City of Des Moines",
		cite: "323 N.W.2d 227 (Iowa 1982)",
		treatment: "green",
	},
	{
		name: "Robinette v. Price",
		cite: "616 N.W.2d 440 (Iowa 2000)",
		treatment: "green",
	},
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CaseReaderCarbonMockup() {
	const [fontSize, setFontSize] = useState(16);
	const [copied, setCopied] = useState(false);

	return (
		<AppShell active="/app-carbon-mockup/case">
			<div className={cn("flex h-full min-h-0 flex-col", plexSerif.variable)}>
				<ReaderToolbar
					fontSize={fontSize}
					onFontSize={setFontSize}
					copied={copied}
					onCopy={() => {
						setCopied(true);
						setTimeout(() => setCopied(false), 1500);
					}}
				/>

				<div className="flex min-h-0 flex-1">
					<OutlineRail />

					<article className="min-w-0 flex-1 overflow-y-auto">
						<div className="mx-auto max-w-3xl px-5 py-10 sm:px-8">
							<CaseHeader />
							<OpinionBody fontSize={fontSize} />
						</div>
					</article>

					<CitatorRail />
				</div>
			</div>
		</AppShell>
	);
}

// ---------------------------------------------------------------------------
// Reader toolbar
// ---------------------------------------------------------------------------

function ToolbarButton({
	children,
	...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
	return (
		<button
			type="button"
			{...props}
			className="flex h-9 items-center gap-2 px-3 text-[13px] text-[var(--cds-text-2)] transition-colors hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]"
		>
			{children}
		</button>
	);
}

function ReaderToolbar({
	fontSize,
	onFontSize,
	copied,
	onCopy,
}: {
	fontSize: number;
	onFontSize: (n: number) => void;
	copied: boolean;
	onCopy: () => void;
}) {
	return (
		<div className="flex h-12 shrink-0 items-center gap-1 border-[var(--cds-border)] border-b px-5 sm:px-8">
			<p className="min-w-0 truncate text-sm">
				<Link
					href="/browse-carbon-mockup"
					className="text-[var(--cds-text-2)] hover:text-[var(--cds-link)] hover:underline"
				>
					Iowa Caselaw
				</Link>
				<span className="mx-2 text-[var(--cds-helper)]">/</span>
				<span className="font-semibold">Katko v. Briney</span>
			</p>
			<div className="ml-auto flex items-center gap-1">
				<div className="mr-2 flex items-center border border-[var(--cds-border)]">
					<button
						type="button"
						aria-label="Smaller text"
						onClick={() => onFontSize(Math.max(14, fontSize - 1))}
						className="flex size-9 items-center justify-center transition-colors hover:bg-[var(--cds-layer-hover)]"
					>
						<MinusIcon className="size-3.5" />
					</button>
					<span className="w-10 text-center font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
						{fontSize}px
					</span>
					<button
						type="button"
						aria-label="Larger text"
						onClick={() => onFontSize(Math.min(22, fontSize + 1))}
						className="flex size-9 items-center justify-center transition-colors hover:bg-[var(--cds-layer-hover)]"
					>
						<PlusIcon className="size-3.5" />
					</button>
				</div>
				<ToolbarButton onClick={onCopy}>
					{copied ? (
						<CheckIcon className="size-4 text-[var(--cds-success-text)]" />
					) : (
						<CopyIcon className="size-4" />
					)}
					{copied ? "Copied" : "Copy citation"}
				</ToolbarButton>
				<ToolbarButton>
					<PrinterIcon className="size-4" />
					Print
				</ToolbarButton>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Left rail — outline scroll-spy + details
// ---------------------------------------------------------------------------

function OutlineRail() {
	const [active, setActive] = useState("opinion");
	return (
		<aside className="hidden w-60 shrink-0 flex-col overflow-y-auto border-[var(--cds-border)] border-r py-6 lg:flex">
			<p className="px-4 pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				Outline
			</p>
			{OUTLINE.map((o) => (
				<button
					key={o.id}
					type="button"
					onClick={() => setActive(o.id)}
					className={cn(
						"flex w-full border-l-[3px] py-1.5 pr-3 text-left text-[13px] transition-colors",
						o.depth === 0 ? "pl-3.5" : "pl-8",
						active === o.id
							? "border-[#0f62fe] font-semibold"
							: "border-transparent text-[var(--cds-text-2)] hover:text-[var(--cds-text)]",
					)}
				>
					{o.label}
				</button>
			))}

			<p className="px-4 pt-8 pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				Details
			</p>
			<dl className="text-xs">
				{DETAILS.map(([k, v]) => (
					<div key={k} className="px-4 py-1.5">
						<dt className="text-[var(--cds-helper)]">{k}</dt>
						<dd className="mt-0.5">{v}</dd>
					</div>
				))}
			</dl>
		</aside>
	);
}

// ---------------------------------------------------------------------------
// Case header + citator banner
// ---------------------------------------------------------------------------

function CaseHeader() {
	return (
		<header>
			<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.22em]">
				Supreme Court of Iowa
			</p>
			<h1 className="mt-3 font-light text-3xl sm:text-4xl">Katko v. Briney</h1>
			<p className="mt-2 text-[var(--cds-text-2)] text-sm">
				Marvin Katko, Appellee, v. Edward Briney and Bertha L. Briney,
				Appellants
			</p>
			<p className="mt-3 font-mono text-[13px]">
				183 N.W.2d 657 · 1971 Iowa Sup. LEXIS 758
			</p>
			<p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--cds-text-2)]">
				Decided February 9, 1971 · No. 54169
				<Tag kind="gray">Published</Tag>
			</p>

			<div className="mt-6">
				<Notification kind="success" title="Good law">
					Followed by 41 Iowa decisions; no negative treatment found. Last
					citator pass June 30, 2026.
				</Notification>
			</div>

			<p className="mt-4">
				<a
					href="https://www.courtlistener.com"
					className="inline-flex items-center gap-1.5 text-[13px] text-[var(--cds-link)] hover:underline"
				>
					View on CourtListener
					<ExternalLinkIcon className="size-3.5" />
				</a>
			</p>
		</header>
	);
}

// ---------------------------------------------------------------------------
// Opinion body — Plex Serif, star pagination, footnotes
// ---------------------------------------------------------------------------

function Star({ n }: { n: number }) {
	return (
		<span className="mx-1 font-mono text-[0.8em] text-[var(--cds-link)]">
			[*{n}]
		</span>
	);
}

function Fn({ n }: { n: number }) {
	return (
		<sup className="font-mono text-[0.7em] text-[var(--cds-link)]">{n}</sup>
	);
}

function SectionHeading({
	id,
	children,
}: {
	id: string;
	children: React.ReactNode;
}) {
	return (
		<h2
			id={id}
			className="mt-10 border-[var(--cds-border)] border-t pt-6 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.22em]"
		>
			{children}
		</h2>
	);
}

function OpinionBody({ fontSize }: { fontSize: number }) {
	return (
		<div
			className="[font-family:var(--font-plex-serif)] leading-[1.75]"
			style={{ fontSize }}
		>
			<SectionHeading id="syllabus">Syllabus</SectionHeading>
			<p className="mt-4">
				Action for damages resulting from serious injury caused by a shotgun set
				as a trap in an uninhabited farmhouse against trespassers and thieves.
				The jury returned a verdict for the plaintiff; the owners appeal from
				the judgment entered thereon.
			</p>

			<SectionHeading id="opinion">
				Opinion — Moore, Chief Justice
			</SectionHeading>
			<p className="mt-4">
				The primary issue presented here is whether an owner may protect
				personal property in an unoccupied boarded-up farm house against
				trespassers and thieves by a spring gun capable of inflicting death or
				serious injury.
				<Fn n={1} />
			</p>
			<p className="mt-4">
				<span id="facts" /> Plaintiff&rsquo;s action is for damages resulting
				from serious injury caused by a shot from a 20-gauge spring shotgun set
				by defendants in a bedroom of an old farm house which had been
				uninhabited for several years.
				<Star n={658} /> Plaintiff and his companion had broken and entered the
				house to find and steal old bottles and dated fruit jars which they
				considered antiques.
			</p>
			<p className="mt-4">
				<span id="law" /> The main thrust of defendants&rsquo; defense was that
				&ldquo;the law permits use of a spring gun in a dwelling or warehouse
				for the purpose of preventing the unlawful entry of a burglar or
				thief.&rdquo; Prosser on Torts states the rule:
			</p>
			<blockquote className="mt-4 border-[var(--cds-border-strong)] border-l-2 pl-5 text-[0.95em] italic">
				&ldquo;…the law has always placed a higher value upon human safety than
				upon mere rights in property, it is the accepted rule that there is no
				privilege to use any force calculated to cause death or serious injury
				to repel the threat to land or chattels, unless there is also such a
				threat to the defendant&rsquo;s personal safety as to justify
				self-defense.&rdquo;
			</blockquote>
			<p className="mt-4">
				In{" "}
				<Link
					href="/app-carbon-mockup/case"
					className="text-[var(--cds-link)] hover:underline"
				>
					Hooker v. Miller, 37 Iowa 613
				</Link>
				, we held defendant vineyard owner liable for damages resulting from a
				spring gun shot, although plaintiff was a trespasser and there to steal
				grapes.
				<Fn n={2} /> The facts here are even stronger: the farmhouse was
				<Star n={659} /> unoccupied, and no warning of the device was posted.
			</p>
			<p className="mt-4">
				<span id="holding" /> The judgment entered on the jury&rsquo;s verdict
				of $20,000 actual and $10,000 punitive damages is therefore{" "}
				<strong>affirmed</strong>.
			</p>

			<SectionHeading id="dissent">Dissent — Larson, Justice</SectionHeading>
			<p className="mt-4">
				I respectfully dissent, first, because the majority wrongfully assumes
				that by installing a spring gun the defendants intended to shoot any
				intruder; and second, because it permits punitive damages where the
				plaintiff was engaged in a criminal act at the time of injury.
			</p>

			<div className="mt-12 border-[var(--cds-border)] border-t pt-5 text-[13px] [font-family:var(--font-plex-sans)]">
				<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
					Footnotes
				</p>
				<ol className="mt-3 space-y-2 text-[var(--cds-text-2)]">
					<li>
						<span className="font-mono text-[var(--cds-link)]">1.</span> The
						trap was rigged to a bedroom door and aimed to strike an
						intruder&rsquo;s legs; Briney admitted aiming it lower on advice
						that a higher aim might kill.
					</li>
					<li>
						<span className="font-mono text-[var(--cds-link)]">2.</span> Accord,
						State v. Vance, 17 Iowa 138 (1864) (deadly force unavailable to
						defend property alone).
					</li>
				</ol>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Right rail — citator + cited authorities
// ---------------------------------------------------------------------------

function CaseLinkRow({
	name,
	cite,
	tag,
}: {
	name: string;
	cite: string;
	tag?: React.ReactNode;
}) {
	return (
		<Link
			href="/app-carbon-mockup/case"
			className="group flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-[var(--cds-layer-hover)]"
		>
			<span className="min-w-0 flex-1">
				<span className="block truncate text-[13px] group-hover:underline">
					{name}
				</span>
				<span className="block truncate font-mono text-[var(--cds-helper)] text-[11px]">
					{cite}
				</span>
			</span>
			{tag}
		</Link>
	);
}

function CitatorRail() {
	return (
		<aside className="hidden w-80 shrink-0 space-y-6 overflow-y-auto border-[var(--cds-border)] border-l p-5 xl:block">
			<Panel title="Citator">
				<KVList
					rows={[
						["Cited by", "1,284 decisions"],
						["Followed", "41"],
						["Distinguished", "6"],
						["Negative", "0"],
					]}
				/>
			</Panel>

			<Panel
				title="Citing decisions"
				action={
					<span className="inline-flex items-center gap-1 font-mono text-[11px] text-[var(--cds-helper)]">
						<QuoteIcon className="size-3" />
						top 3
					</span>
				}
			>
				<div className="divide-y divide-[var(--cds-border)]">
					{CITING_CASES.map((c) => (
						<CaseLinkRow
							key={c.name}
							name={c.name}
							cite={c.cite}
							tag={
								<Tag kind={c.treatment}>
									{c.treatment === "green" ? "Followed" : "Distinguished"}
								</Tag>
							}
						/>
					))}
				</div>
				<button
					type="button"
					className="w-full border-[var(--cds-border)] border-t px-4 py-2.5 text-left text-[13px] text-[var(--cds-link)] transition-colors hover:bg-[var(--cds-layer-hover)]"
				>
					All 1,284 citing decisions
				</button>
			</Panel>

			<Panel title="Cited authorities">
				<div className="divide-y divide-[var(--cds-border)]">
					{CITED_IN_CORPUS.map((c) => (
						<CaseLinkRow key={c.name} name={c.name} cite={c.cite} />
					))}
				</div>
				<p className="border-[var(--cds-border)] border-t px-4 py-2.5 text-[var(--cds-helper)] text-[11px]">
					12 additional citations to authorities outside this corpus.
				</p>
			</Panel>

			<Panel title="Ask about this case">
				<div className="p-4">
					<p className="text-[13px] text-[var(--cds-text-2)] leading-snug">
						Open a chat pinned to this decision — press{" "}
						<kbd className="border border-[var(--cds-border)] bg-[var(--cds-layer)] px-1.5 font-mono text-[11px]">
							/
						</kbd>{" "}
						anywhere in the reader.
					</p>
					<Link
						href="/app-carbon-mockup/assistant"
						className="mt-3 inline-flex h-9 items-center gap-3 border border-[var(--cds-link)] px-3 text-[13px] text-[var(--cds-link)] transition-colors hover:bg-[#0f62fe] hover:text-white"
					>
						Chat with this case
					</Link>
				</div>
			</Panel>
		</aside>
	);
}
