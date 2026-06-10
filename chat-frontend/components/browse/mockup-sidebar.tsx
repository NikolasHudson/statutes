"use client";

// Shared sidebar chrome for the /browse-mockup design mockups (the Library home
// and the Advanced-search page). Kept separate from the live app sidebar so
// mockup-only navigation (e.g. the advanced-search route) never leaks into
// production. The brand links back to the mockup home so the set is self-
// navigable.

import {
	GavelIcon,
	LandmarkIcon,
	type LucideIcon,
	ScaleIcon,
	SlidersHorizontalIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppSidebarBrand } from "@/components/app-sidebar-brand";
import { AppSidebarFooter } from "@/components/app-sidebar-footer";
import { AppSidebarNav } from "@/components/app-sidebar-nav";
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
			<AppSidebarBrand href="/browse-mockup" />

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
