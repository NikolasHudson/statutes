// Page for the MCP endpoint — Hudson Corpus as a production MCP surface, on
// the ibm.com-style product shell (components/marketing/product-page.tsx).
// MCP is a *door* into Hudson Corpus, not a separately-branded product: name it
// for what it is.
//
// Copy is grounded in the shipped server (backend/apps/mcp_server): ten
// read-only tools, stateless JSON at the app's /mcp endpoint, and two ways in —
// an OAuth 2.0 Bearer token or a static X-API-Key (auth.py accepts either).
//
// The OAuth server is real (oauth.py: RFC 8414 discovery, RFC 7591 dynamic
// client registration, authorization code + PKCE S256, refresh with rotation,
// RFC 7009 revocation) — but it is only REACHABLE once the app spec routes
// /oauth and /.well-known to Django (they fall through to the SPA today; see
// DOMAIN_AND_BRAND_PLAN landmine #10). Ship this page only alongside that
// ingress rule, or the copy below advertises a 404.

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
	CodeFrame,
	HairlineLink,
	SolidLink,
} from "@/components/marketing/carbon";
import {
	CONSULTING_HREF,
	CONTACT_HREF,
	PRICING_HREF,
	PRODUCT_HREF,
} from "@/components/marketing/chrome";
import { ProductFamily } from "@/components/marketing/product-family";
import {
	NextStep,
	PlanBand,
	ProductLeadspace,
	ProductSection,
	type UseCase,
	UseCaseGrid,
} from "@/components/marketing/product-page";
import {
	ProductSubnav,
	type SubnavSection,
} from "@/components/marketing/product-subnav";
import { APP_URL, MCP_SERVER_ID, MCP_URL } from "@/lib/site";

export const metadata: Metadata = {
	title: "MCP endpoint — Hudson Corpus in your AI tools",
	description:
		"A production MCP endpoint over the Iowa Code, Court Rules, and caselaw. Ten grounded, read-only tools — citation lookup, hybrid search, version history, brief auditing — for Claude and any MCP client.",
};

const PRODUCT = "MCP endpoint";

const SECTIONS: SubnavSection[] = [
	{ id: "overview", label: "Overview" },
	{ id: "connect", label: "Connect" },
	{ id: "tools", label: "Tools" },
	{ id: "reliability", label: "Reliability" },
	{ id: "use-cases", label: "Use cases" },
	{ id: "pricing", label: "Pricing" },
];

export default function McpProductPage() {
	return (
		<CarbonPage>
			<ProductLeadspace
				product={PRODUCT}
				tagline="The Iowa legal corpus, inside your AI tools."
				lede={
					<>
						The corpus behind Hudson research, exposed as a production MCP
						endpoint at{" "}
						<span className="font-mono text-[0.95em] text-white">
							{MCP_URL}
						</span>
						. Ten grounded, read-only tools for Claude Desktop, Claude Code, and
						any MCP-capable agent.
					</>
				}
				actions={
					<>
						<SolidLink href={APP_URL}>Get an API key</SolidLink>
						<HairlineLink href="#tools">See the tools</HairlineLink>
					</>
				}
				visual={
					<CodeFrame
						caption="Claude Code — one command"
						code={CLAUDE_CODE_CMD}
						url={`${MCP_URL.replace(/^https?:\/\//, "")}`}
					/>
				}
			/>
			<ProductSubnav product={PRODUCT} sections={SECTIONS} />
			<Overview />
			<Connect />
			<ToolCatalog />
			<Reliability />
			<UseCases />
			<Pricing />
			<NextStep
				title="Point your agent at the corpus."
				body="Create a key, paste the config, and your assistant is doing grounded Iowa research in minutes. Building something bigger on it? We should talk."
				actions={
					<>
						<SolidLink href={APP_URL}>Get an API key</SolidLink>
						<HairlineLink href={CONSULTING_HREF}>
							Book a consultation
						</HairlineLink>
					</>
				}
				explore={[
					{ label: "Hudson Corpus", href: PRODUCT_HREF },
					{ label: "Pricing", href: PRICING_HREF },
					{ label: "Consulting", href: CONSULTING_HREF },
					{ label: "Contact us", href: CONTACT_HREF },
				]}
			/>
			<ProductFamily current="mcp" />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

function Overview() {
	return (
		<ProductSection
			id="overview"
			label="Overview"
			title="One endpoint, ten grounded tools."
			intro="Everything the research product knows how to do against the Iowa corpus — resolve a citation, search across statutes and decisions, walk a section's version history, audit a brief — offered to your own agent as tools it can call directly."
		>
			<p className="mt-6 max-w-2xl text-[17px] text-foreground/80 leading-[1.75]">
				It is the same retrieval stack the browser product runs on, reached
				through the protocol instead of a page: stateless JSON over HTTPS,
				authenticated per call with an OAuth token or a key you create yourself,
				and read-only from end to end.
			</p>
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Connect — the config is the product shot
// ---------------------------------------------------------------------------

// The env var holding the key in the user's own config. The name is a local
// convention, not part of the protocol, so derive it from the connector key
// rather than spelling the brand out a second time: hudson-corpus →
// HUDSON_CORPUS_KEY. The \${…} below is a literal dollar-brace in the rendered
// JSON (mcp-remote expands it from "env"), not a template interpolation.
const KEY_ENV = `${MCP_SERVER_ID.replace(/-/g, "_").toUpperCase()}_KEY`;

const DESKTOP_CONFIG = `{
  "mcpServers": {
    "${MCP_SERVER_ID}": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "${MCP_URL}",
               "--header", "X-API-Key:\${${KEY_ENV}}"],
      "env": { "${KEY_ENV}": "<your key>" }
    }
  }
}`;

const CLAUDE_CODE_CMD = `claude mcp add --transport http ${MCP_SERVER_ID} \\
  ${MCP_URL} --header "X-API-Key: <your key>"`;

function Connect() {
	return (
		<ProductSection
			id="connect"
			tone="layer"
			label="Connect"
			title="One config block away."
			intro="Two ways in. Clients that speak OAuth 2.0 discover the endpoint, register themselves, and send you through a consent screen — no key to copy. Everything else sends a key you create in your account. Either way the whole corpus shows up in your assistant's tool list."
		>
			<div className="mt-14 grid gap-6 lg:grid-cols-2">
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
						Every request carries either an OAuth{" "}
						<span className="font-mono text-[0.95em]">Bearer</span> token or an{" "}
						<span className="font-mono text-[0.95em]">X-API-Key</span> —
						stateless JSON over HTTPS, so it works the same from a laptop, a CI
						job, or an agent fleet.
					</p>
				</div>
			</div>
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Tools — the ten registered tools, verbatim names
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
		<ProductSection
			id="tools"
			tone="dark"
			label="The tools"
			title="Ten tools. All read-only. All grounded."
			intro="Every response carries an official-source URL and an as-of-date stamp, so an agent can't accidentally cite stale text — the same discipline the human-facing product holds itself to."
		>
			<div className="mt-14 grid gap-px border border-[#393939] bg-[#393939] sm:grid-cols-2">
				{TOOLS.map((t) => (
					<div key={t.name} className="bg-[#161616] p-8">
						<h3 className="font-mono text-[#78a9ff] text-[14px]">{t.name}</h3>
						<p className="mt-3 text-[#c6c6c6] text-[13.5px] leading-relaxed">
							{t.body}
						</p>
					</div>
				))}
			</div>
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Reliability
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
		title: "OAuth 2.0 or a key",
		body: "A full OAuth 2.0 authorization server — dynamic client registration, PKCE, a consent screen, refresh and revocation — or a static key you create and revoke in your account.",
	},
	{
		icon: ShieldCheckIcon,
		title: "Read-only surface",
		body: "Every tool is a read-only query over the corpus. There is no write path — nothing an agent can break.",
	},
];

function Reliability() {
	return (
		<ProductSection
			id="reliability"
			label="Reliability"
			title="Built so agents can't go wrong quietly."
		>
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
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Use cases
// ---------------------------------------------------------------------------

const USE_CASES: UseCase[] = [
	{
		audience: "In your editor",
		title: "Research without leaving the draft.",
		body: "Claude Code and Claude Desktop pick the tools up from your config, so a citation check is a question in the window you are already in.",
	},
	{
		audience: "Firm automation",
		title: "Audit every brief on the way out.",
		body: "audit_brief validates the citations, verifies the quotations, and checks currency in one call — a pass a script can run on every filing.",
	},
	{
		audience: "Current awareness",
		title: "Know what changed since last week.",
		body: "list_recent_amendments turns the sweep somebody used to do by hand into a scheduled job that reports only what moved.",
	},
	{
		audience: "Product teams",
		title: "Ground your own assistant in real law.",
		body: "Stateless JSON over HTTPS, authenticated per call and safe to retry — the retrieval layer you would otherwise have to build and keep current.",
	},
];

function UseCases() {
	return (
		<ProductSection
			id="use-cases"
			tone="layer"
			label="Use cases"
			title="What people point at it."
		>
			<UseCaseGrid items={USE_CASES} tone="light" />
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Pricing
// ---------------------------------------------------------------------------

function Pricing() {
	return (
		<ProductSection
			id="pricing"
			label="Pricing"
			title="Included with your plan."
		>
			<PlanBand included="The MCP endpoint is not billed separately — every plan includes the connector, keys you create and revoke yourself, and the same corpus the browser product reads." />
		</ProductSection>
	);
}
