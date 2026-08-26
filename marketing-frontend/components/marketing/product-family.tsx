// Cross-link strip for the product pages: every product page ends with the
// rest of the family, so "Products" never dead-ends on a single page. Ruled
// tiles in the Carbon register, matching the home's WhatWeDo treatment.
//
// The list itself lives in lib/products.ts — shared with the nav's mega menu.

import Link from "next/link";
import { Eyebrow, SectionHead } from "@/components/marketing/carbon";
import { PRODUCTS, type ProductKey } from "@/lib/products";

// Re-exported: the product pages have always imported ProductKey from here.
export type { ProductKey };

export function ProductFamily({
	current,
	n,
}: {
	/** The page we're on — excluded from the strip. */
	current: ProductKey;
	/**
	 * Section number in the page's sequence, e.g. "05". Omitted on the
	 * ibm.com-style product pages, which label their sections rather than
	 * numbering them.
	 */
	n?: string;
}) {
	const rest = PRODUCTS.filter((p) => p.key !== current);
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<SectionHead
					n={n}
					label="More from Hudson"
					title="One platform for Iowa practice."
				/>
				<div className="mt-14 grid divide-y divide-border border border-border lg:grid-cols-3 lg:divide-x lg:divide-y-0">
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
