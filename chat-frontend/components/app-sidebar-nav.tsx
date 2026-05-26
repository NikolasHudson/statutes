"use client";

// Shared "jump between apps" navigation that sits at the top of every
// route's sidebar content. Highlights the active route via the Next.js
// pathname, so Chat / Browse / Account all stay one click apart no matter
// where you are.

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpenIcon,
  MessagesSquareIcon,
  type LucideIcon,
} from "lucide-react";

import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  // Treat the href as a prefix match so subroutes light up the parent.
  // Special-cased for "/" since prefix-matching that would highlight all.
  exact?: boolean;
};

const ITEMS: NavItem[] = [
  { href: "/", label: "Chat", icon: MessagesSquareIcon, exact: true },
  { href: "/browse", label: "Browse the corpus", icon: BookOpenIcon },
];

export function AppSidebarNav() {
  const pathname = usePathname() ?? "/";
  return (
    <SidebarGroup>
      <SidebarGroupLabel>Navigate</SidebarGroupLabel>
      <SidebarMenu>
        {ITEMS.map((item) => {
          const Icon = item.icon;
          const active = item.exact
            ? pathname === item.href
            : pathname === item.href ||
              pathname.startsWith(`${item.href}/`);
          return (
            <SidebarMenuItem key={item.href}>
              <SidebarMenuButton asChild isActive={active}>
                <Link href={item.href}>
                  <Icon className="size-4" />
                  <span>{item.label}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          );
        })}
      </SidebarMenu>
    </SidebarGroup>
  );
}
