// Product page for Corpus MCP — the Iowa legal corpus as a production MCP
// endpoint, in the Carbon register (see /products/corpus for the pattern).
//
// Copy is grounded in the shipped server (backend/apps/mcp_server): ten
// read-only tools, X-API-Key auth, stateless JSON at corpus.nick.law/mcp.
// Claude Desktop connects through the mcp-remote shim; claude.ai web Custom
// Connectors need OAuth we don't implement yet, so we don't claim it.

import {
	BadgeCheckIcon,
	FileSearchIcon,
	KeyRoundIcon,
	type LucideIcon,
	ScaleIcon,
	ServerIcon,
	ShieldCheckIcon,
} from "lucide-react";
import type { Metadata } from "next";
import {
	CarbonPage,
	HairlineLink,
	INK,
	PageHero,
	SectionHead,
	SolidLink,
} from "@/components/marketing/carbon";
import { CONSULTING_HREF } from "@/components/marketing/chrome";
import { ProductFamily } from "@/components/marketing/product-family";
import { APP_URL, MCP_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Corpus MCP — The Iowa legal corpus in your AI tools",
	description:
		"A production MCP endpoint over the Iowa Code, Court Rules, and caselaw. Ten grounded, read-only tools — citation lookup, hybrid search, version history, brief auditing — for Claude and any MCP client.",
};

export default function McpProductPage() {
	return (
		<CarbonPage>
			<Hero />
			<Connect />
			<ToolCatalog />
			<Guarantees />
			<CtaBand />
			<ProductFamily current="mcp" n="04" />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero() {
	return (
		<PageHero
			eyebrow="Products — Corpus MCP"
			title={
				<>
					The Iowa legal corpus,
					<br />
					inside your AI tools.
				</>
			}
			lede={
				<>
					The corpus behind Hudson research, exposed as a production MCP
					endpoint at{" "}
					<span className="font-mono text-[0.95em] text-white">{MCP_URL}</span>.
					Ten grounded, read-only tools — citation lookup, hybrid search,
					version history, brief auditing — for Claude Desktop, Claude Code, and
					any MCP-capable agent.
				</>
			}
			actions={
				<>
					<SolidLink href={APP_URL}>Get an API key</SolidLink>
					<HairlineLink href="#tools">See the tools</HairlineLink>
				</>
			}
		/>
	);
}

// ---------------------------------------------------------------------------
// 01 — Connect: the config is the product shot
// ---------------------------------------------------------------------------

const DESKTOP_CONFIG = `{
  "mcpServers": {
    "iowa-legal-corpus": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "${MCP_URL}",
               "--header", "X-API-Key:\${IOWA_LEGAL_CORPUS_KEY}"],
      "env": { "IOWA_LEGAL_CORPUS_KEY": "<your key>" }
    }
  }
}`;

const CLAUDE_CODE_CMD = `claude mcp add --transport http iowa-legal-corpus \\
  ${MCP_URL} --header "X-API-Key: <your key>"`;

function CodeFrame({ caption, code }: { caption: string; code: string }) {
	return (
		<figure className="border border-border bg-card">
			<figcaption className="flex items-center justify-between gap-4 border-border border-b px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
				<span className="truncate">{caption}</span>
				<span className="shrink-0">corpus.nick.law/mcp</span>
			</figcaption>
			<pre className="overflow-x-auto bg-[#161616] p-5 font-mono text-[13px] text-[#e0e0e0] leading-relaxed">
				<code>{code}</code>
			</pre>
		</figure>
	);
}

function Connect() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead n="01" label="Connect" title="One config block away." />
				<p className="mt-10 max-w-xl text-[17px] text-foreground/80 leading-[1.75]">
					Create a key in your account, paste one block of config, and the whole
					corpus shows up in your assistant's tool list. Claude Desktop connects
					through the{" "}
					<span className="font-mono text-[0.95em]">mcp-remote</span> shim;
					Claude Code and other HTTP-native clients connect directly.
				</p>
				<div className="mt-12 grid gap-6 lg:grid-cols-2">
					<CodeFrame
						caption="Claude Desktop — claude_desktop_config.json"
						code={DESKTOP_CONFIG}
					/>
					<div className="flex flex-col gap-6">
						<CodeFrame
							caption="Claude Code — one command"
							code={CLAUDE_CODE_CMD}
						/>
						<p className="border-border border-t pt-5 text-[14px] text-foreground/85 leading-relaxed">
							Every request is authenticated with your{" "}
							<span className="font-mono text-[0.95em]">X-API-Key</span> —
							stateless JSON over HTTPS, so it works the same from a laptop, a
							CI job, or an agent fleet.
						</p>
					</div>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 02 — Tool catalog: the ten registered tools, verbatim names
// ---------------------------------------------------------------------------

type Tool = { name: string; body: string };

const TOOLS: Tool[] = [
	{
		name: "lookup_citation",
		body: "A precise citation — '714.16', '§ 714.16(2)(a)', 'Chapter 232' — returns the current text. Ambiguous cites return candidates, never a silent substitute.",
	},
	{
		name: "search_statutes",
		body: "Hybrid semantic search across the Code, court rules, and caselaw — full-text + fuzzy + vector, reranked. Case hits carry good-law treatment flags.",
	},
	{
		name: "get_version_history",
		body: "Every version of a section with effective dates and the session law that enacted each change.",
	},
	{
		name: "get_section_at_date",
		body: "The text of a section as it stood on a given date — for the facts as they were, not as they are.",
	},
	{
		name: "get_cross_references",
		body: "Every provision that cites a section, so a change's blast radius is one call away.",
	},
	{
		name: "get_definitions",
		body: "Defined terms in scope for a chapter or across the Code — the statutory meaning, not the dictionary's.",
	},
	{
		name: "list_recent_amendments",
		body: "Everything that changed since a date — the current-awareness sweep, as a tool call.",
	},
	{
		name: "validate_citations",
		body: "Every citation in a block of text, checked against the corpus and flagged valid, repealed, or unresolvable.",
	},
	{
		name: "verify_quote",
		body: "A quoted passage checked verbatim against the cited source — the anti-hallucination primitive.",
	},
	{
		name: "audit_brief",
		body: "The full pass over a brief: citations validated, quotes verified, currency checked — one call.",
	},
];

function ToolCatalog() {
	return (
		<section id="tools" className={cn("scroll-mt-20 text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="02"
					label="The tools"
					title="Ten tools. All read-only. All grounded."
					tone="dark"
				/>
				<p className="mt-10 max-w-xl text-[#c6c6c6] text-[17px] leading-[1.75]">
					Every response carries an official-source URL and an as-of-date stamp,
					so an agent can't accidentally cite stale text — the same discipline
					the human-facing product holds itself to.
				</p>
				<div className="mt-14 grid gap-px border border-[#393939] bg-[#393939] sm:grid-cols-2">
					{TOOLS.map((t) => (
						<div key={t.name} className="bg-[#161616] p-8">
							<h3 className="font-mono text-[14px] text-[#78a9ff]">{t.name}</h3>
							<p className="mt-3 text-[#c6c6c6] text-[13.5px] leading-relaxed">
								{t.body}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 03 — Guarantees
// ---------------------------------------------------------------------------

type Guarantee = { icon: LucideIcon; title: string; body: string };

const GUARANTEES: Guarantee[] = [
	{
		icon: BadgeCheckIcon,
		title: "Stamped, sourced responses",
		body: "official_url, as_of_date, and effective dates on every response — the provenance travels with the data.",
	},
	{
		icon: ScaleIcon,
		title: "Treatment-aware caselaw",
		body: "Case hits carry good-law flags — overruled and superseded decisions are marked before your agent relies on them.",
	},
	{
		icon: FileSearchIcon,
		title: "Candidates, not guesses",
		body: "When a citation doesn't resolve unambiguously, the tool returns the candidate list. A silent substitution is a bug class we refuse by design.",
	},
	{
		icon: ServerIcon,
		title: "Stateless by design",
		body: "Plain JSON over HTTPS, no sessions to manage — every call independently authenticated and safe to retry.",
	},
	{
		icon: KeyRoundIcon,
		title: "Keyed, tiered access",
		body: "Keys are created and revoked in your account. Beta keys include lookup and search; the full toolset comes with paid tiers at launch.",
	},
	{
		icon: ShieldCheckIcon,
		title: "Read-only surface",
		body: "Every tool is a read-only query over the corpus. There is no write path — nothing an agent can break.",
	},
];

function Guarantees() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="03"
					label="Under the hood"
					title="Built so agents can't go wrong quietly."
				/>
				<div className="mt-14 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
					{GUARANTEES.map((g) => {
						const Icon = g.icon;
						return (
							<div key={g.title} className="bg-card p-8">
								<Icon className="size-5" strokeWidth={1.5} aria-hidden />
								<h3 className="mt-6 font-semibold text-[15px]">{g.title}</h3>
								<p className="mt-2 text-[13.5px] text-muted-foreground leading-relaxed">
									{g.body}
								</p>
							</div>
						);
					})}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 04 — CTA band
// ---------------------------------------------------------------------------

function CtaBand() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="flex flex-col gap-10 border-[#393939] border-t pt-10 lg:flex-row lg:items-end lg:justify-between">
					<div className="max-w-2xl">
						<h2 className="font-light text-3xl sm:text-4xl">
							Point your agent at the corpus.
						</h2>
						<p className="mt-4 text-[#c6c6c6] text-lg leading-relaxed">
							Create a key, paste the config, and your assistant is doing
							grounded Iowa research in minutes. Building something bigger on
							it? We should talk.
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						<SolidLink href={APP_URL}>Get an API key</SolidLink>
						<HairlineLink href={CONSULTING_HREF}>
							Book a consultation
						</HairlineLink>
					</div>
				</div>
			</div>
		</section>
	);
}
