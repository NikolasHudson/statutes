"use client";

// Placeholder for v2 screens that aren't wired to live data yet. Keeps every
// nav destination real (no 404s) while the rebuild lands screen by screen.
// Delete once all screens are wired.

import Link from "next/link";
import { Notification, PageHead } from "@/components/carbon/primitives";

export function NotWiredYet({
	title,
	mockupHref,
}: {
	title: string;
	mockupHref: string;
}) {
	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<PageHead eyebrow="v2 preview" title={title} />
			<Notification kind="info" title="Not wired yet" className="mt-8 max-w-xl">
				This screen hasn't been connected to live data. The static design is at{" "}
				<Link
					href={mockupHref}
					className="text-[var(--cds-link)] hover:underline"
				>
					{mockupHref}
				</Link>
				.
			</Notification>
		</div>
	);
}
