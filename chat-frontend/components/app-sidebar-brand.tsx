// Shared brand band for every sidebar: solid primary strip, big HUDSON
// wordmark + beta pill, sized to match the h-16 top bar so the two read as
// one continuous strip. Collapses to a lone "H" inside icon-rail sidebars.

import Link from "next/link";

import { SidebarHeader } from "@/components/ui/sidebar";

export function AppSidebarBrand({ href = "/" }: { href?: string }) {
	return (
		<SidebarHeader className="mb-2 border-b bg-sidebar-primary p-0">
			<Link href={href} className="flex h-16 items-center justify-center px-4">
				<span className="font-extrabold text-2xl text-sidebar-primary-foreground tracking-[0.2em] group-data-[collapsible=icon]:hidden">
					HUDSON
				</span>
				<span className="ms-1.5 rounded-sm bg-sidebar-primary-foreground/15 px-1.5 py-0.5 font-semibold text-[10px] text-sidebar-primary-foreground/90 uppercase tracking-wider group-data-[collapsible=icon]:hidden">
					beta
				</span>
				<span className="hidden font-extrabold text-sidebar-primary-foreground text-xl group-data-[collapsible=icon]:block">
					H
				</span>
			</Link>
		</SidebarHeader>
	);
}
