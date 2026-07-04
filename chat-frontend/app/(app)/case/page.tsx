"use client";

// /case without an id: point at search, since a decision is always opened
// from results or a citing link (/case/<id> is the real reader).

import Link from "next/link";
import { Notification, PageHead } from "@/components/carbon/primitives";

export default function V2CaseIndex() {
	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<PageHead
				eyebrow="Reader"
				title="Case reader"
				lede="Open any decision from search results, or follow a citation link inside an opinion."
			/>
			<Notification
				kind="info"
				title="No case selected"
				className="mt-8 max-w-xl"
			>
				Try a search like{" "}
				<Link
					href="/results?q=spring+gun&doc_type=cases"
					className="text-[var(--cds-link)] hover:underline"
				>
					“spring gun” in cases
				</Link>{" "}
				and open a decision.
			</Notification>
		</div>
	);
}
