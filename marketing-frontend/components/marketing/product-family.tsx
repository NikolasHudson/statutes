// Cross-link strip for the product pages: every product page ends with the
// rest of the family, so "Products" never dead-ends on a single page. Ruled
// tiles in the Carbon register, matching the home's WhatWeDo treatment.

import Link from "next/link";
import { Eyebrow, SectionHead } from "@/components/marketing/carbon";
import {
	EMAIL_PRODUCT_HREF,
	MCP_PRODUCT_HREF,
	PRODUCT_HREF,
} from "@/components/marketing/chrome";

export type ProductKey = "corpus" | "mcp" | "email";

const PRODUCTS: {
	key: ProductKey;
	tag: string;
	title: string;
	body: string;
	cta: string;
	href: string;
}[] = [
	{
		key: "corpus",
		tag: "Flagship",
		title: "Hudson Corpus",
		body: "Grounded legal research in the browser — Iowa Code, court rules, and caselaw with every citation verified against the effective text.",
		cta: "Explore Hudson Corpus",
		href: PRODUCT_HREF,
	},
	{
		key: "mcp",
		tag: "For your AI stack",
		title: "MCP endpoint",
		body: "Hudson Corpus as a production MCP endpoint — ten grounded tools for Claude and any MCP client, keyed and read-only.",
		cta: "Explore the MCP endpoint",
		href: MCP_PRODUCT_HREF,
	},
	{
		key: "email",
		tag: "For your inbox",
		title: "Email assistant",
		body: "Email a question, get a verified answer back — linked citations, official PDFs on request, no new app to learn.",
		cta: "Explore the assistant",
		href: EMAIL_PRODUCT_HREF,
	},
];

export function ProductFamily({
	current,
	n,
}: {
	/** The page we're on — excluded from the strip. */
	current: ProductKey;
	/** Section number in the page's sequence, e.g. "05". */
	n: string;
}) {
	const rest = PRODUCTS.filter((p) => p.key !== current);
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<SectionHead
					n={n}
					label="More from Hudson"
					title="One corpus. Three doors."
				/>
				<div className="mt-14 grid divide-y divide-border border border-border sm:grid-cols-2 sm:divide-x sm:divide-y-0">
					{rest.map((p) => (
						<Link
							key={p.key}
							href={p.href}
							className="group flex min-h-[220px] flex-col bg-card p-8 transition-colors hover:bg-[#e8e8e8]"
						>
							<Eyebrow>{p.tag}</Eyebrow>
							<h3 className="mt-5 text-2xl">{p.title}</h3>
							<p className="mt-3 text-[15px] text-muted-foreground leading-relaxed">
								{p.body}
							</p>
							<span className="mt-auto flex items-center justify-between pt-8 font-medium text-[#0f62fe] text-sm">
								{p.cta}
								<span
									aria-hidden
									className="transition-transform group-hover:translate-x-0.5"
								>
									→
								</span>
							</span>
						</Link>
					))}
				</div>
			</div>
		</section>
	);
}
