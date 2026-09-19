"use client";

// Resources index — the datasets a lawyer uses alongside legal research that
// are not themselves law. Rendered entirely from GET /api/resources, so
// adding a dataset is a backend migration and nothing here changes.

import { DatabaseIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Notification, PageHead, Panel } from "@/components/carbon/primitives";
import { ProvenanceStrip } from "@/components/resources/provenance";
import {
	fmtDate,
	listResources,
	type ResourceDataset,
	ResourcesError,
} from "@/lib/iowa-resources";

export default function ResourcesIndexPage() {
	const [datasets, setDatasets] = useState<ResourceDataset[] | null>(null);
	const [error, setError] = useState<ResourcesError | Error | null>(null);

	useEffect(() => {
		const controller = new AbortController();
		listResources(controller.signal)
			.then((d) => setDatasets(d.datasets))
			.catch((e) => {
				if (controller.signal.aborted) return;
				setError(e as Error);
			});
		return () => controller.abort();
	}, []);

	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<PageHead
				eyebrow="Reference data"
				title="Resources"
				lede="Public registries that sit beside legal research. These are records, not law — nothing here is citable authority, and nothing here feeds search or the citator."
			/>

			{error && (
				<Notification
					className="mt-8 max-w-2xl"
					kind={
						error instanceof ResourcesError && error.status === 402
							? "warning"
							: "error"
					}
					title={
						error instanceof ResourcesError && error.status === 402
							? "Resources needs an active plan"
							: "Could not load resources"
					}
				>
					{error.message}
				</Notification>
			)}

			{datasets === null && !error && (
				<p className="mt-8 text-[var(--cds-text-2)] text-sm">Loading…</p>
			)}

			{datasets?.length === 0 && (
				<p className="mt-8 text-[var(--cds-text-2)] text-sm">
					No datasets are available yet.
				</p>
			)}

			<div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
				{datasets?.map((d) => (
					<Link
						key={d.slug}
						href={`/resources/${d.slug}`}
						className="group block focus:outline-2 focus:-outline-offset-2 focus:outline-[#0f62fe]"
					>
						<Panel
							title={d.source_name || "Reference data"}
							// The section is the flex column, not the body: h-full on
							// the body would measure 100% of a box it does not start
							// at, and push the footer row out past the card border.
							className="flex h-full flex-col transition-colors group-hover:border-[var(--cds-border-strong)]"
						>
							<div className="flex flex-1 flex-col gap-4 p-4">
								<div className="flex items-start gap-3">
									<DatabaseIcon
										className="mt-0.5 size-4 shrink-0 text-[var(--cds-link)]"
										strokeWidth={1.5}
									/>
									<h2 className="font-medium text-[15px] group-hover:text-[var(--cds-link)]">
										{d.title}
									</h2>
								</div>
								<p className="text-[13px] text-[var(--cds-text-2)] leading-relaxed">
									{d.description}
								</p>
								<dl className="mt-auto grid grid-cols-2 gap-2 border-[var(--cds-border)] border-t pt-3 text-xs">
									<div>
										<dt className="text-[var(--cds-helper)]">Records</dt>
										<dd className="tabular-nums">
											{d.row_count === null
												? "—"
												: d.row_count.toLocaleString("en-US")}
										</dd>
									</div>
									<div>
										<dt className="text-[var(--cds-helper)]">Data as of</dt>
										<dd>{d.as_of ? fmtDate(d.as_of) : "Not yet loaded"}</dd>
									</div>
								</dl>
							</div>
						</Panel>
					</Link>
				))}
			</div>

			{datasets && datasets.length > 0 && (
				<div className="mt-10 max-w-3xl">
					<ProvenanceStrip
						attribution={datasets
							.map((d) => d.attribution_text)
							.filter(Boolean)
							.join(" ")}
					/>
				</div>
			)}
		</div>
	);
}
