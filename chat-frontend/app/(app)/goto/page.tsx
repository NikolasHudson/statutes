"use client";

// Citation → section redirect. The shared chat lib cites statutes by source
// slug + canonical path (a /browse#/<slug>/<path> deep link); this route
// resolves that pair through /api/browse/resolve and lands on the section reader,
// so assistant answers can link sections without knowing node ids.

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Notification } from "@/components/carbon/primitives";
import { browseResolve } from "@/lib/iowa-browse";

export default function V2GotoPage() {
	return (
		<Suspense
			fallback={
				<p className="px-5 py-10 text-[var(--cds-text-2)] text-sm sm:px-8">
					Resolving citation…
				</p>
			}
		>
			<Resolver />
		</Suspense>
	);
}

function Resolver() {
	const router = useRouter();
	const searchParams = useSearchParams();
	const source = searchParams.get("source") ?? "";
	const cite = searchParams.get("cite") ?? "";
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		if (!source || !cite) {
			setError("Missing source or citation.");
			return;
		}
		let cancelled = false;
		browseResolve(source, cite)
			.then((r) => {
				if (cancelled) return;
				if (r.found) {
					router.replace(
						r.is_chapter ? `/chapter/${r.node_id}` : `/section/${r.node_id}`,
					);
				} else if (r.candidates.length > 0) {
					router.replace(`/section/${r.candidates[0].node_id}`);
				} else {
					setError(`Couldn't resolve “${cite}” in ${source}.`);
				}
			})
			.catch((e) => !cancelled && setError((e as Error).message));
		return () => {
			cancelled = true;
		};
	}, [source, cite, router]);

	return (
		<div className="px-5 py-10 sm:px-8">
			{error ? (
				<Notification
					kind="error"
					title="Citation not found"
					className="max-w-xl"
				>
					{error}{" "}
					<Link href="/" className="text-[var(--cds-link)] hover:underline">
						Back to the Library.
					</Link>
				</Notification>
			) : (
				<p className="text-[var(--cds-text-2)] text-sm">
					Resolving {cite ? `“${cite}”` : "citation"}…
				</p>
			)}
		</div>
	);
}
