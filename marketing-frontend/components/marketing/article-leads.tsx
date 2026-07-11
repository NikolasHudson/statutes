// Bespoke lead figures for individual articles, keyed by slug. Article prose
// comes from markdown (see article-body.tsx), but a hand-built visual that
// carries an article's thesis can't — when a post deserves one, it lives
// here and the article template drops it in under the header.

import { CheckIcon, XIcon } from "lucide-react";
import type { ReactNode } from "react";

export function articleLead(slug: string): ReactNode | null {
	return LEADS[slug] ?? null;
}

const LEADS: Record<string, ReactNode> = {
	// The article's thesis in one glance: an invented citation struck down
	// next to a verified one. Flat on gray-100, hairline #393939 borders,
	// Blue-60/Blue-40 accents; continues the dark header band above it.
	"why-legal-ai-invents-citations": (
		<figure className="max-w-5xl">
			<div className="border border-[#393939] p-6 sm:p-8">
				<p className="font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.22em]">
					The same question, two kinds of answer
				</p>
				<div className="mt-6 space-y-3">
					<div className="flex items-center gap-3 border border-[#393939] px-4 py-3">
						<span className="flex size-6 shrink-0 items-center justify-center border border-[#6f6f6f] text-[#a8a8a8]">
							<XIcon className="size-3.5" strokeWidth={2.5} />
						</span>
						<span className="text-[#a8a8a8] text-[14px] line-through decoration-[#6f6f6f]">
							Smith v. Jefferson County, 482 N.W.2d 119 (Iowa 1994)
						</span>
						<span className="ms-auto hidden shrink-0 font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.16em] sm:block">
							Not in any reporter
						</span>
					</div>
					<div className="flex items-center gap-3 border border-[#393939] px-4 py-3">
						<span className="flex size-6 shrink-0 items-center justify-center bg-[#0f62fe] text-white">
							<CheckIcon className="size-3.5" strokeWidth={2.5} />
						</span>
						<span className="text-[14px] text-white">
							Iowa Code § 714H.5 (2023)
						</span>
						<span className="ms-auto hidden shrink-0 font-mono text-[#78a9ff] text-[11px] uppercase tracking-[0.16em] sm:block">
							Verified against source
						</span>
					</div>
				</div>
			</div>
			<figcaption className="mt-4 text-[#a8a8a8] text-[13px]">
				A confident-looking citation and a real one are indistinguishable until
				something checks them.
			</figcaption>
		</figure>
	),
};
