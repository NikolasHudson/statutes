"use client";

// Client shell for /cases/<decision node id>: fetch the case, then render the
// three-pane <CaseConsole/> inside the shared site chrome — the collapsible
// BrowseSidebar on the left and a topbar (sidebar trigger + breadcrumb) at the
// top, so reading an opinion keeps the same navigation as the rest of the site.
// Loading/error states show the same shell with a minimal topbar so the user
// can navigate away while the (potentially large) opinion loads.

import { AlertCircleIcon, Loader2Icon } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { BrowseSidebar } from "@/components/browse/browse-sidebar";
import { CaseConsole } from "@/components/case-console";
import { DocChat } from "@/components/doc-chat";
import {
	Breadcrumb,
	BreadcrumbItem,
	BreadcrumbLink,
	BreadcrumbList,
	BreadcrumbPage,
	BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import {
	SidebarInset,
	SidebarProvider,
	SidebarTrigger,
} from "@/components/ui/sidebar";
import {
	type BrowseSource,
	browseCase,
	browseSources,
	type CaseDetail,
} from "@/lib/iowa-browse";

export default function CasePage() {
	const params = useParams<{ id: string }>();
	const router = useRouter();
	// Strict integer id, mirroring app/browse/compare/page.tsx — a malformed
	// segment becomes NaN and is caught by the guard below.
	const nodeId = /^\d+$/.test(params.id) ? Number(params.id) : Number.NaN;

	const [data, setData] = useState<CaseDetail | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(true);

	// Sources power the shared site sidebar's flat source list — fetched once so
	// the reader keeps full navigational parity with /browse.
	const [sources, setSources] = useState<BrowseSource[] | null>(null);
	const [sourcesError, setSourcesError] = useState<string | null>(null);

	useEffect(() => {
		if (!Number.isFinite(nodeId)) {
			setError("Invalid case id.");
			setLoading(false);
			return;
		}
		let cancelled = false;
		setLoading(true);
		setError(null);
		// Clear the prior case so nothing stale shows while the next one loads
		// (cited-case links reuse this same route + component instance).
		setData(null);
		browseCase(nodeId)
			.then((d) => {
				if (!cancelled) setData(d);
			})
			.catch((e) => {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "Failed to load case.");
			})
			.finally(() => {
				if (!cancelled) setLoading(false);
			});
		return () => {
			cancelled = true;
		};
	}, [nodeId]);

	useEffect(() => {
		let cancelled = false;
		browseSources()
			.then((s) => !cancelled && setSources(s))
			.catch((e) => {
				if (!cancelled)
					setSourcesError(
						e instanceof Error ? e.message : "Failed to load corpus sources.",
					);
			});
		return () => {
			cancelled = true;
		};
	}, []);

	// Sidebar navigation routes back into /browse: "Search the corpus" / the
	// brand home go to the search landing; a source opens via the ?source= deep
	// link the browse page resolves on mount.
	const goBrowse = useCallback(() => router.push("/browse"), [router]);
	const openSource = useCallback(
		(slug: string) => router.push(`/browse?source=${slug}`),
		[router],
	);

	return (
		<SidebarProvider defaultOpen={false}>
			<div className="flex h-dvh w-full pr-0.5">
				<BrowseSidebar
					sources={sources}
					sourcesError={sourcesError}
					mode="browse"
					activeSlug={null}
					onHome={goBrowse}
					onOpenSource={openSource}
				/>
				<SidebarInset>
					{data ? (
						<>
							<CaseConsole data={data} />
							{/* Press "/" anywhere on the page to chat about this decision. */}
							<DocChat
								nodeId={data.id}
								title={data.case_name}
								citation={data.citations?.[0]}
								kind="case"
							/>
						</>
					) : (
						<>
							<header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
								<SidebarTrigger />
								<Separator orientation="vertical" className="mx-1 h-5" />
								<Breadcrumb>
									<BreadcrumbList className="flex-nowrap">
										<BreadcrumbItem>
											<BreadcrumbLink asChild>
												<Link href="/browse">Browse the corpus</Link>
											</BreadcrumbLink>
										</BreadcrumbItem>
										<BreadcrumbSeparator />
										<BreadcrumbItem>
											<BreadcrumbPage>Case</BreadcrumbPage>
										</BreadcrumbItem>
									</BreadcrumbList>
								</Breadcrumb>
							</header>
							<div className="mx-auto w-full max-w-3xl px-4 py-6">
								{error ? (
									<div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm">
										<AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
										<span>{error}</span>
									</div>
								) : loading ? (
									<div className="flex items-center gap-2 rounded-md border border-dashed p-4 text-muted-foreground text-sm">
										<Loader2Icon className="size-4 animate-spin" />
										Loading case…
									</div>
								) : null}
							</div>
						</>
					)}
				</SidebarInset>
			</div>
		</SidebarProvider>
	);
}
