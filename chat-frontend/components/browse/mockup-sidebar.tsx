"use client";

// Shared sidebar chrome for the /browse-mockup design mockups (the Library home
// and the Advanced-search page). Kept separate from the live app sidebar so
// mockup-only navigation (e.g. the advanced-search route) never leaks into
// production. The brand links back to the mockup home so the set is self-
// navigable.

import {
	BookOpenIcon,
	GavelIcon,
	LandmarkIcon,
	type LucideIcon,
	ScaleIcon,
	SlidersHorizontalIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppSidebarFooter } from "@/components/app-sidebar-footer";
import { AppSidebarNav } from "@/components/app-sidebar-nav";
import {
	Sidebar,
	SidebarContent,
	SidebarFooter,
	SidebarGroup,
	SidebarGroupLabel,
	SidebarHeader,
	SidebarMenu,
	SidebarMenuButton,
	SidebarMenuItem,
	SidebarRail,
} from "@/components/ui/sidebar";

const BROWSE_LINKS: { href: string; label: string; icon: LucideIcon }[] = [
	{ href: "/browse", label: "Case Law", icon: ScaleIcon },
	{ href: "/browse", label: "Statutes & Codes", icon: LandmarkIcon },
	{ href: "/browse", label: "Court Rules", icon: GavelIcon },
	{
		href: "/browse-mockup/advanced",
		label: "Advanced search",
		icon: SlidersHorizontalIcon,
	},
];

export function MockupSidebar() {
	const pathname = usePathname() ?? "";
	return (
		<Sidebar>
			<SidebarHeader className="mb-2 border-b">
				<SidebarMenu>
					<SidebarMenuItem>
						<SidebarMenuButton size="lg" asChild>
							<Link href="/browse-mockup">
								<div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
									<BookOpenIcon className="size-4" />
								</div>
								<div className="me-6 flex flex-col gap-0.5 leading-none">
									<span className="font-semibold">Hudson Legal Tech</span>
									<span className="text-sidebar-foreground/60 text-xs">
										Library
									</span>
								</div>
							</Link>
						</SidebarMenuButton>
					</SidebarMenuItem>
				</SidebarMenu>
			</SidebarHeader>

			<SidebarContent className="px-2">
				<AppSidebarNav />

				<SidebarGroup>
					<SidebarGroupLabel>Browse</SidebarGroupLabel>
					<SidebarMenu>
						{BROWSE_LINKS.map((l) => {
							const Icon = l.icon;
							// Only the mockup-owned routes light up; the /browse deep-links
							// never match a mockup pathname.
							const active =
								l.href !== "/browse" && pathname.startsWith(l.href);
							return (
								<SidebarMenuItem key={l.label}>
									<SidebarMenuButton
										asChild
										isActive={active}
										tooltip={l.label}
									>
										<Link href={l.href}>
											<Icon className="size-4" />
											<span>{l.label}</span>
										</Link>
									</SidebarMenuButton>
								</SidebarMenuItem>
							);
						})}
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
