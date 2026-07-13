// Products index — "/products", the nav's Products destination now that the
// family is three strong. One corpus, three doors: each product gets a
// numbered band (alternating ink/light, Carbon register) with a spec row and
// its own visual — Corpus a real screenshot, MCP the client config, Email the
// verified-reply exchange. Server component (carries <metadata>).

import type { Metadata } from "next";
import {
	CarbonPage,
	Eyebrow,
	Frame,
	HairlineLink,
	INK,
	PageHero,
	SectionHead,
	SolidLink,
	TextLink,
} from "@/components/marketing/carbon";
import {
	CONSULTING_HREF,
	CONTACT_HREF,
	EMAIL_PRODUCT_HREF,
	MCP_PRODUCT_HREF,
	PRODUCT_HREF,
} from "@/components/marketing/chrome";
import {
	type CorpusStats,
	corpusSourceNames,
	fetchCorpusStats,
	formatCount,
} from "@/lib/api";
import { APP_URL, MCP_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Products — Hudson Legal Technologies",
	description:
		"One grounded Iowa legal corpus, three doors: Hudson Corpus in the browser, a production MCP endpoint for AI tools, and an assistant that answers your email — every answer verified against the effective text.",
};

export default async function ProductsIndexPage() {
	const stats = await fetchCorpusStats();
	return (
		<CarbonPage>
			<PageHero
				eyebrow="Products"
				title={
					<>
						One corpus.
						<br />
						Three doors.
					</>
				}
				lede="Everything we ship runs on the same grounded system — the Iowa Code, the administrative rules, the court rules, and the caselaw, with every answer verified against the effective text before you see it. Choose the door that fits how you work: a browser, your AI tools, or your inbox."
				actions={
					<>
						<SolidLink href={APP_URL}>Open Hudson Corpus</SolidLink>
						<HairlineLink href={CONSULTING_HREF}>Talk to our team</HairlineLink>
					</>
				}
			/>
			<CorpusBand />
			<McpBand />
			<EmailBand />
			<SharedFoundation stats={stats} />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Shared band scaffolding: SectionHead + lede/specs row + visual + link
// ---------------------------------------------------------------------------

function SpecList({
	specs,
	dark,
}: {
	specs: { term: string; detail: string }[];
	dark?: boolean;
}) {
	return (
		<dl className={cn("border-t", dark ? "border-[#393939]" : "border-border")}>
			{specs.map((s) => (
				<div
					key={s.term}
					className={cn(
						"flex items-baseline justify-between gap-6 border-b py-3.5",
						dark ? "border-[#393939]" : "border-border",
					)}
				>
					<dt
						className={cn(
							"font-mono text-[11px] uppercase tracking-[0.18em]",
							dark ? "text-[#a8a8a8]" : "text-muted-foreground",
						)}
					>
						{s.term}
					</dt>
					<dd className="text-right font-medium text-sm">{s.detail}</dd>
				</div>
			))}
		</dl>
	);
}

// ---------------------------------------------------------------------------
// 01 — Hudson Corpus
// ---------------------------------------------------------------------------

function CorpusBand() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="01"
					label="For the browser"
					title="Hudson Corpus. Research that shows its work."
				/>
				<div className="mt-12 grid gap-12 lg:grid-cols-[1.2fr_1fr] lg:gap-20">
					<p className="max-w-xl text-[17px] text-foreground/80 leading-[1.75]">
						The flagship. Ask a question in plain language; the assistant
						searches the corpus, reads the controlling text, and answers with
						citations that link to the source — each one verified before you see
						it. Browse the library, read the effective text, and search across
						everything from one box.
					</p>
					<SpecList
						specs={[
							{ term: "Surface", detail: "Web app" },
							{ term: "Status", detail: "Live in beta" },
							{ term: "Best for", detail: "Day-to-day research" },
						]}
					/>
				</div>
				<Frame
					src="/marketing/corpus/assistant.png"
					alt="The Hudson Corpus assistant answering a question with verified citations"
					caption="Assistant — answer with verified citations"
					className="mt-12"
				/>
				<div className="mt-12">
					<TextLink href={PRODUCT_HREF}>Explore Hudson Corpus</TextLink>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 02 — The MCP endpoint (a door into Hudson Corpus, not a separate product)
// ---------------------------------------------------------------------------

const MCP_TOOL_NAMES = [
	"lookup_citation",
	"search_statutes",
	"get_version_history",
	"get_section_at_date",
	"get_cross_references",
	"get_definitions",
	"list_recent_amendments",
	"validate_citations",
	"verify_quote",
	"audit_brief",
];

function McpBand() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="02"
					label="For your AI stack"
					title="Hudson Corpus, inside your tools."
					tone="dark"
				/>
				<div className="mt-12 grid gap-12 lg:grid-cols-[1.2fr_1fr] lg:gap-20">
					<p className="max-w-xl text-[#c6c6c6] text-[17px] leading-[1.75]">
						A production MCP endpoint at{" "}
						<span className="font-mono text-[0.95em] text-white">
							{MCP_URL}
						</span>{" "}
						— the same grounded corpus for Claude Desktop, Claude Code, and any
						MCP-capable agent. Ten read-only tools, every response stamped with
						its official source and as-of date.
					</p>
					<SpecList
						dark
						specs={[
							{ term: "Surface", detail: "MCP · streamable HTTP" },
							{ term: "Auth", detail: "OAuth 2.0 · X-API-Key" },
							{ term: "Best for", detail: "Agents & integrations" },
						]}
					/>
				</div>
				<div className="mt-12 flex flex-wrap gap-2">
					{MCP_TOOL_NAMES.map((t) => (
						<span
							key={t}
							className="border border-[#393939] px-3 py-1.5 font-mono text-[12px] text-[#78a9ff]"
						>
							{t}
						</span>
					))}
				</div>
				<div className="mt-12">
					<TextLink href={MCP_PRODUCT_HREF} tone="dark">
						Explore the MCP endpoint
					</TextLink>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 03 — Email assistant
// ---------------------------------------------------------------------------

function EmailBand() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="03"
					label="For your inbox"
					title="Email assistant. Verified answers, by reply."
				/>
				<div className="mt-12 grid gap-12 lg:grid-cols-[1.2fr_1fr] lg:gap-20">
					<p className="max-w-xl text-[17px] text-foreground/80 leading-[1.75]">
						Send a question to the assistant's address and a verified answer
						comes back — citations linked to the source, official PDFs attached
						on request, follow-ups in the same thread. The full verification
						gate runs on every reply before it sends. No new app to learn: it's
						email.
					</p>
					<SpecList
						specs={[
							{ term: "Surface", detail: "Plain email" },
							{ term: "Status", detail: "In pilot — allowlisted" },
							{ term: "Best for", detail: "Questions on the go" },
						]}
					/>
				</div>
				<div className="mt-12">
					<TextLink href={EMAIL_PRODUCT_HREF}>
						Explore the email assistant
					</TextLink>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 04 — The shared foundation + CTA
// ---------------------------------------------------------------------------

// The corpus line is fetched, not typed: the literal that used to live here
// (105,734 documents, three sources) had gone stale in the direction that hurts
// most — it understated the breadth we lead on. See lib/api.ts.
function foundation(stats: CorpusStats): { title: string; body: string }[] {
	return [
		{
			title: "One verified corpus",
			body: `${corpusSourceNames(stats)} — ${formatCount(stats.documents)} documents, semantically indexed, with treatment flags on decisions.`,
		},
		{
			title: "One verification gate",
			body: "Every surface runs the same deterministic citation-and-quote check before an answer reaches you.",
		},
		{
			title: "One source of truth",
			body: "Everything traces to the official publication — effective dates, session laws, and links to legis.iowa.gov.",
		},
	];
}

function SharedFoundation({ stats }: { stats: CorpusStats }) {
	const FOUNDATION = foundation(stats);
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="grid gap-px border border-[#393939] bg-[#393939] lg:grid-cols-3">
					{FOUNDATION.map((f) => (
						<div key={f.title} className="bg-[#161616] p-8">
							<Eyebrow tone="dark">{f.title}</Eyebrow>
							<p className="mt-4 text-[#c6c6c6] text-[14.5px] leading-relaxed">
								{f.body}
							</p>
						</div>
					))}
				</div>
				<div className="mt-16 flex flex-col gap-10 border-[#393939] border-t pt-10 lg:flex-row lg:items-end lg:justify-between">
					<div className="max-w-2xl">
						<h2 className="font-light text-3xl sm:text-4xl">
							Start at whichever door fits.
						</h2>
						<p className="mt-4 text-[#c6c6c6] text-lg leading-relaxed">
							The app is open in beta; MCP keys come with your account; the
							email assistant is in limited pilot — access is granted per
							address.
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						<SolidLink href={APP_URL}>Get started</SolidLink>
						<HairlineLink href={CONTACT_HREF}>Contact us</HairlineLink>
					</div>
				</div>
			</div>
		</section>
	);
}
