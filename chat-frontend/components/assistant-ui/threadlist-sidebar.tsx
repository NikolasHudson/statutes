"use client";

import { ClockIcon } from "lucide-react";
import type * as React from "react";
import { AppSidebarBrand } from "@/components/app-sidebar-brand";
import { AppSidebarFooter } from "@/components/app-sidebar-footer";
import { AppSidebarNav } from "@/components/app-sidebar-nav";
import { ThreadList } from "@/components/assistant-ui/thread-list";
import {
	Sidebar,
	SidebarContent,
	SidebarFooter,
	SidebarRail,
} from "@/components/ui/sidebar";

export function ThreadListSidebar({
	...props
}: React.ComponentProps<typeof Sidebar>) {
	return (
		<Sidebar {...props}>
			<AppSidebarBrand />
			<SidebarContent className="aui-sidebar-content px-2">
				<AppSidebarNav />
				<ThreadList />
				<ThreadHistoryComingSoon />
			</SidebarContent>
			<SidebarRail />
			<SidebarFooter className="aui-sidebar-footer border-t">
				<AppSidebarFooter />
			</SidebarFooter>
		</Sidebar>
	);
}

function ThreadHistoryComingSoon() {
	return (
		<div className="mt-3 rounded-lg border border-sidebar-border/60 border-dashed bg-sidebar-accent/30 px-3 py-3">
			<div className="flex items-center gap-2 text-sidebar-foreground/80">
				<ClockIcon className="size-3.5" />
				<span className="font-medium text-xs uppercase tracking-wide">
					Coming soon
				</span>
			</div>
			<p className="mt-1.5 text-sidebar-foreground/70 text-xs leading-relaxed">
				Saved conversations land here. Soon you&apos;ll be able to revisit past
				threads and keep discussing them.
			</p>
		</div>
	);
}
