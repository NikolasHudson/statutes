"use client";

// Shared sidebar footer used across /chat, /browse, and /account. Contains
// the theme toggle on top and the user identity + sign-out below — the two
// chrome elements every authed route needs.

import Link from "next/link";
import { ChevronRightIcon, LogOutIcon, MoonIcon, SunIcon } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useAuth } from "@/components/auth-gate";
import { useTheme } from "@/components/theme-provider";

export function AppSidebarFooter() {
  return (
    <>
      <ThemeToggleMenuItem />
      <SidebarUserMenu />
    </>
  );
}

function ThemeToggleMenuItem() {
  const { theme, toggle } = useTheme();
  const isDark = theme === "dark";
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton
          onClick={toggle}
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
        >
          {isDark ? (
            <SunIcon className="size-4" />
          ) : (
            <MoonIcon className="size-4" />
          )}
          <span>{isDark ? "Light mode" : "Dark mode"}</span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}

// Two-character avatar fallback: first letters of the first two name parts
// (split on space / dot / @). Falls back to the first two chars of the
// source so an unusual email still renders something.
function initialsFor(user: { full_name: string; email: string }): string {
  const source = (user.full_name || user.email || "?").trim();
  if (!source) return "?";
  const parts = source.split(/[\s.@]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

function SidebarUserMenu() {
  const { user, signOut } = useAuth();
  const primary = user.full_name?.trim() || user.email;
  const secondary = user.full_name ? user.email : user.tier;

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton size="lg" asChild>
          <Link
            href="/account"
            className="cursor-pointer pe-9"
            title="Manage account"
          >
            <Avatar className="size-8">
              <AvatarFallback className="bg-sidebar-primary font-semibold text-sidebar-primary-foreground text-xs">
                {initialsFor(user)}
              </AvatarFallback>
            </Avatar>
            <div className="flex min-w-0 flex-1 flex-col gap-0.5 leading-none">
              <span className="truncate font-semibold text-sm" title={primary}>
                {primary}
              </span>
              <span
                className="truncate text-muted-foreground text-xs"
                title={secondary}
              >
                {secondary}
              </span>
            </div>
            <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground/70" />
          </Link>
        </SidebarMenuButton>
        <SidebarMenuAction
          aria-label="Sign out"
          title="Sign out"
          onClick={signOut}
          className="top-1/2 -translate-y-1/2"
        >
          <LogOutIcon />
        </SidebarMenuAction>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
