"use client";

import type * as React from "react";
import Link from "next/link";
import { ClockIcon, MessagesSquare } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { ThreadList } from "@/components/assistant-ui/thread-list";
import { AppSidebarFooter } from "@/components/app-sidebar-footer";
import { AppSidebarNav } from "@/components/app-sidebar-nav";

export function ThreadListSidebar({
  ...props
}: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar {...props}>
      <SidebarHeader className="aui-sidebar-header mb-2 border-b">
        <div className="aui-sidebar-header-content flex items-center justify-between">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" asChild>
                <Link href="/">
                  <div className="aui-sidebar-header-icon-wrapper flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                    <MessagesSquare className="aui-sidebar-header-icon size-4" />
                  </div>
                  <div className="aui-sidebar-header-heading me-6 flex flex-col gap-0.5 leading-none">
                    <span className="aui-sidebar-header-title font-semibold">
                      Hudson Legal Tech
                    </span>
                  </div>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </div>
      </SidebarHeader>
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
        Saved conversations land here. Soon you&apos;ll be able to revisit
        past threads and keep discussing them.
      </p>
    </div>
  );
}
