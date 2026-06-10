"use client";

// Shared sidebar chrome for the live corpus browser. Used by both /browse and
// /browse/advanced so the two routes present the same flat, clickable source
// list (no tree) and the same Search / Advanced-search entry points. The
// "Search the corpus" item is driven by the page's derived `mode`; the
// "Advanced search" item lights up purely from the pathname so it works on the
// standalone /browse/advanced route too.

import {
	AlertCircleIcon,
	BookOpenIcon,
	Loader2Icon,
	SearchIcon,
	SlidersHorizontalIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppSidebarBrand } from "@/components/app-sidebar-brand";
import { AppSidebarFooter } from "@/components/app-sidebar-footer";
import { AppSidebarNav } from "@/components/app-sidebar-nav";
import { SOURCE_ICON } from "@/components/browse/advanced-search";
import {
	Sidebar,
	SidebarContent,
	SidebarFooter,
	SidebarGroup,
	SidebarGroupLabel,
	SidebarMenu,
	SidebarMenuButton,
	SidebarMenuItem,
	SidebarRail,
	useSidebar,
} from "@/components/ui/sidebar";
import type { BrowseSource } from "@/lib/iowa-browse";

export type BrowseMode = "home" | "search" | "browse";

export function BrowseSidebar({
	sources,
	sourcesError,
	mode,
	activeSlug,
	onHome,
	onOpenSource,
}: {
	sources: BrowseSource[] | null;
	sourcesError: string | null;
	mode: BrowseMode;
	activeSlug: string | null;
	onHome: () => void;
	onOpenSource: (slug: string) => void;
}) {
	// The advanced-search page is its own route; light its entry from the path so
	// the sidebar stays correct whether it's rendered on /browse or /browse/advanced.
	const advancedActive = (usePathname() ?? "").startsWith("/browse/advanced");

	// Collapse to an icon rail by default (the page mounts with defaultOpen=false)
	// and expand on hover, recollapsing when the pointer leaves — so the reading
	// area keeps the width until the user reaches for navigation. Hover only makes
	// sense on desktop; on mobile the sidebar is an off-canvas sheet, so skip the
	// handlers there (they'd be passed to a non-DOM node).
	const { setOpen, isMobile } = useSidebar();
	const hoverProps = isMobile
		? {}
		: {
				onMouseEnter: () => setOpen(true),
				onMouseLeave: () => setOpen(false),
			};

	return (
		<Sidebar collapsible="icon" className="print:hidden" {...hoverProps}>
			<AppSidebarBrand />

			{/* px-2 insets the labelled menu when expanded; drop it when collapsed
			    so the 2rem buttons sit centered in the 3rem icon rail (the group's
			    own p-2 then centers them) instead of being pushed right. */}
			<SidebarContent className="px-2 group-data-[collapsible=icon]:px-0">
				<AppSidebarNav />

				<SidebarGroup>
					<SidebarGroupLabel>Search</SidebarGroupLabel>
					<SidebarMenu>
						<SidebarMenuItem>
							<SidebarMenuButton
								onClick={onHome}
								isActive={
									!advancedActive && (mode === "home" || mode === "search")
								}
							>
								<SearchIcon className="size-4" />
								<span>Search the corpus</span>
							</SidebarMenuButton>
						</SidebarMenuItem>
						<SidebarMenuItem>
							<SidebarMenuButton asChild isActive={advancedActive}>
								<Link href="/browse/advanced">
									<SlidersHorizontalIcon className="size-4" />
									<span>Advanced search</span>
								</Link>
							</SidebarMenuButton>
						</SidebarMenuItem>
					</SidebarMenu>
				</SidebarGroup>

				<SidebarGroup>
					<SidebarGroupLabel>Sources</SidebarGroupLabel>
					<SidebarMenu>
						{sourcesError ? (
							<div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-2 text-destructive text-xs">
								<AlertCircleIcon className="mt-0.5 size-3.5 shrink-0" />
								<span>{sourcesError}</span>
							</div>
						) : !sources ? (
							<div className="flex items-center gap-2 px-2 py-3 text-sidebar-foreground/60 text-xs">
								<Loader2Icon className="size-3.5 animate-spin" />
								<span>Loading sources…</span>
							</div>
						) : (
							sources.map((src) => {
								const Icon = SOURCE_ICON[src.slug] ?? BookOpenIcon;
								return (
									<SidebarMenuItem key={src.slug}>
										<SidebarMenuButton
											onClick={() => onOpenSource(src.slug)}
											isActive={activeSlug === src.slug}
											// items-start/mt-0.5 top-align the icon against the
											// two-line name+count when expanded; recenter both when
											// collapsed so the icon is centered in the rail.
											className="h-auto items-start py-2 group-data-[collapsible=icon]:items-center"
											tooltip={src.name}
										>
											<Icon className="mt-0.5 size-4 shrink-0 group-data-[collapsible=icon]:mt-0" />
											<div className="flex min-w-0 flex-col">
												<span className="truncate font-medium">{src.name}</span>
												<span className="text-sidebar-foreground/50 text-xs">
													{src.entries.toLocaleString()}{" "}
													{src.entry_label.toLowerCase()}
												</span>
											</div>
										</SidebarMenuButton>
									</SidebarMenuItem>
								);
							})
						)}
					</SidebarMenu>
				</SidebarGroup>
			</SidebarContent>

			<SidebarRail />

			<SidebarFooter className="border-t">
				<AppSidebarFooter />
			</SidebarFooter>
		</Sidebar>
	);
}
