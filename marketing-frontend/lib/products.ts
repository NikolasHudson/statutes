// Canonical product list for the site chrome. Two surfaces render from it:
// the nav's Products mega menu (components/marketing/carbon-nav.tsx) and the
// cross-link strip at the foot of every product page
// (components/marketing/product-family.tsx). Keeping one list means a new
// product — or a renamed one — lands in both places at once.
//
// Two lengths of copy, because the two surfaces need different ones: `tagline`
// is the single line the mega menu shows under a name, `body` the fuller
// sentence the family cards carry. The /products catalog tiles keep their own,
// longer page-level copy — that's an editorial surface, not chrome.
//
// `tier` splits the family the way /products does: two products of our own,
// then the two other doors into Hudson Corpus.

import {
	EDMS_PRODUCT_HREF,
	EMAIL_PRODUCT_HREF,
	MCP_PRODUCT_HREF,
	PRODUCT_HREF,
} from "@/components/marketing/chrome";

export type ProductKey = "corpus" | "edms" | "mcp" | "email";

export type ProductSummary = {
	key: ProductKey;
	tier: "product" | "door";
	/** Category eyebrow, e.g. "Legal research". */
	tag: string;
	title: string;
	/** One line, for the mega menu. */
	tagline: string;
	/** Fuller sentence, for the family cards. */
	body: string;
	cta: string;
	href: string;
};

export const PRODUCTS: ProductSummary[] = [
	{
		key: "corpus",
		tier: "product",
		tag: "Flagship",
		title: "Hudson Corpus",
		tagline: "Grounded legal research in the browser, every citation verified.",
		body: "Grounded legal research in the browser — Iowa Code, court rules, and caselaw with every citation verified against the effective text.",
		cta: "Explore Hudson Corpus",
		href: PRODUCT_HREF,
	},
	{
		key: "edms",
		tier: "product",
		tag: "For court filings",
		title: "Hudson EDMSpro",
		tagline: "Preview and download Iowa EDMS filings, named your way.",
		body: "A Chrome extension for Iowa's EDMS — preview filings beside the docket and download them clean-named, straight from the court to you.",
		cta: "Explore Hudson EDMSpro",
		href: EDMS_PRODUCT_HREF,
	},
	{
		key: "mcp",
		tier: "door",
		tag: "For your AI stack",
		title: "MCP endpoint",
		tagline: "Ten read-only tools for Claude and any MCP client.",
		body: "Hudson Corpus as a production MCP endpoint — ten grounded tools for Claude and any MCP client, keyed and read-only.",
		cta: "Explore the MCP endpoint",
		href: MCP_PRODUCT_HREF,
	},
	{
		key: "email",
		tier: "door",
		tag: "For your inbox",
		title: "Email assistant",
		tagline: "Email a question, get a verified answer by reply.",
		body: "Email a question, get a verified answer back — linked citations, official PDFs on request, no new app to learn.",
		cta: "Explore the assistant",
		href: EMAIL_PRODUCT_HREF,
	},
];
