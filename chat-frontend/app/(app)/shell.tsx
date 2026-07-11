"use client";

// App chrome for the Carbon app: dark shell header, side nav over the app
// routes, and the signed-in user anchored at the bottom of the nav (opens a
// settings/log-out menu). Visual language comes from components/carbon/primitives; the mockup
// suite keeps its own static shell in app/app-carbon-mockup/carbon.tsx.

import {
	ChartColumnIcon,
	ChevronsUpDownIcon,
	GitCompareArrowsIcon,
	LogOutIcon,
	MessageSquareTextIcon,
	MoonIcon,
	NewspaperIcon,
	PanelLeftCloseIcon,
	PanelLeftOpenIcon,
	SearchIcon,
	SettingsIcon,
	SlidersHorizontalIcon,
	SunIcon,
	TriangleAlertIcon,
	UsersIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/auth-gate";
import {
	type NavGroup,
	ShellHeader,
	SideNav,
	useTheme,
} from "@/components/carbon/primitives";
import { cn } from "@/lib/utils";

const NAV: NavGroup[] = [
	{
		group: "Workspace",
		items: [
			{ href: "/", label: "Library", icon: SearchIcon, exact: true },
			{
				href: "/assistant",
				label: "Assistant",
				icon: MessageSquareTextIcon,
			},
			{
				href: "/advanced",
				label: "Advanced search",
				icon: SlidersHorizontalIcon,
			},
			{
				href: "/compare",
				label: "Compare editions",
				icon: GitCompareArrowsIcon,
			},
		],
	},
];

// Staff-only nav group — appended after the workspace group for users whose
// /api/auth/me carries is_staff.
const ADMIN_NAV: NavGroup = {
	group: "Admin",
	items: [
		{ href: "/admin/usage", label: "Usage & spend", icon: ChartColumnIcon },
		{ href: "/admin/users", label: "Users", icon: UsersIcon },
		{ href: "/admin/articles", label: "Articles", icon: NewspaperIcon },
	],
};

function initials(name: string, email: string): string {
	const parts = name.trim().split(/\s+/).filter(Boolean);
	if (parts.length >= 2)
		return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
	if (parts.length === 1 && parts[0]) return parts[0].slice(0, 2).toUpperCase();
	return email.slice(0, 2).toUpperCase();
}

// Carbon warning-notification-styled beta disclaimer pinned above the user
// section at the foot of the side nav.
function BetaNotice() {
	return (
		<div className="flex gap-3 border-[var(--cds-border)] border-b border-l-[3px] border-l-[#f1c21b] bg-[var(--cds-layer)] py-3 pr-4 pl-3.5">
			<TriangleAlertIcon
				className="mt-0.5 size-4 shrink-0 text-[#f1c21b]"
				strokeWidth={1.5}
			/>
			<p className="text-[var(--cds-text-2)] text-xs leading-relaxed">
				Hudson Corpus is in beta. Verify all citations and quotations against
				the primary source before relying on them.
			</p>
		</div>
	);
}

// Signed-in user at the foot of the side nav; clicking it pops a menu with
// Settings and Log out.
function UserFooter() {
	const { user, signOut } = useAuth();
	const { theme, setTheme } = useTheme();
	const [open, setOpen] = useState(false);
	const ref = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!open) return;
		const onPointerDown = (e: PointerEvent) => {
			if (!ref.current?.contains(e.target as Node)) setOpen(false);
		};
		const onKeyDown = (e: KeyboardEvent) => {
			if (e.key === "Escape") setOpen(false);
		};
		document.addEventListener("pointerdown", onPointerDown);
		document.addEventListener("keydown", onKeyDown);
		return () => {
			document.removeEventListener("pointerdown", onPointerDown);
			document.removeEventListener("keydown", onKeyDown);
		};
	}, [open]);

	return (
		<div ref={ref} className="relative">
			{open && (
				<div
					role="menu"
					className="absolute inset-x-0 bottom-full border border-[var(--cds-border)] bg-[var(--cds-bg)] py-1 shadow-[0_-2px_8px_rgba(0,0,0,0.2)]"
				>
					<Link
						href="/account"
						role="menuitem"
						onClick={() => setOpen(false)}
						className="flex items-center gap-3 px-4 py-2.5 text-[var(--cds-text-2)] text-sm transition-colors hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]"
					>
						<SettingsIcon className="size-4 shrink-0" strokeWidth={1.5} />
						Settings
					</Link>
					<button
						type="button"
						role="menuitem"
						// Theme flips in place — keep the menu open so it's easy to
						// flip back.
						onClick={() => setTheme(theme === "g100" ? "white" : "g100")}
						className="flex w-full items-center gap-3 px-4 py-2.5 text-[var(--cds-text-2)] text-sm transition-colors hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]"
					>
						{theme === "g100" ? (
							<SunIcon className="size-4 shrink-0" strokeWidth={1.5} />
						) : (
							<MoonIcon className="size-4 shrink-0" strokeWidth={1.5} />
						)}
						{theme === "g100" ? "Light theme" : "Dark theme"}
					</button>
					<button
						type="button"
						role="menuitem"
						onClick={() => void signOut()}
						className="flex w-full items-center gap-3 px-4 py-2.5 text-[var(--cds-text-2)] text-sm transition-colors hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]"
					>
						<LogOutIcon className="size-4 shrink-0" strokeWidth={1.5} />
						Log out
					</button>
				</div>
			)}
			<button
				type="button"
				onClick={() => setOpen((o) => !o)}
				aria-haspopup="menu"
				aria-expanded={open}
				className="flex w-full items-center gap-3 px-3.5 py-3 text-left transition-colors hover:bg-[var(--cds-layer-hover)]"
			>
				<span className="flex size-8 shrink-0 items-center justify-center bg-[#0f62fe] font-semibold text-white text-xs">
					{initials(user.full_name, user.email)}
				</span>
				<span className="flex min-w-0 flex-1 flex-col">
					<span className="truncate font-semibold text-sm">
						{user.full_name || user.email}
					</span>
					<span className="truncate text-[var(--cds-helper)] text-xs">
						{user.email}
					</span>
				</span>
				<ChevronsUpDownIcon className="size-4 shrink-0 text-[var(--cds-helper)]" />
			</button>
		</div>
	);
}

export function V2Shell({ children }: { children: React.ReactNode }) {
	const pathname = usePathname() ?? "/";
	const { user } = useAuth();
	const navGroups = user.is_staff ? [...NAV, ADMIN_NAV] : NAV;
	// The onboarding wizard brings its own stepper rail — give it the full
	// canvas instead of the app nav.
	const bare = pathname === "/onboarding";

	// Two toggles for two viewports: on md+ a button riding the nav's right
	// border collapses the column in place; below md — where the column is
	// hidden by default — the header hamburger opens it as a drawer.
	const [desktopHidden, setDesktopHidden] = useState(false);
	const [mobileOpen, setMobileOpen] = useState(false);
	// Picking a destination closes the mobile drawer.
	useEffect(() => setMobileOpen(false), [pathname]);

	return (
		<>
			<ShellHeader
				homeHref="/"
				onMenu={bare ? undefined : () => setMobileOpen((o) => !o)}
				mobileMenuOnly
				themeToggle={false}
			/>
			<div className="relative flex min-h-0 flex-1">
				{!bare && (
					<>
						{mobileOpen && (
							<button
								type="button"
								aria-label="Close navigation"
								onClick={() => setMobileOpen(false)}
								className="fixed inset-0 z-20 bg-black/40 md:hidden"
							/>
						)}
						<SideNav
							groups={navGroups}
							active={pathname}
							footer={
								<>
									<BetaNotice />
									<UserFooter />
								</>
							}
							className={cn(
								mobileOpen &&
									"fixed top-12 bottom-0 left-0 z-30 flex bg-[var(--cds-bg)] md:static",
								desktopHidden && "md:hidden",
							)}
						/>
						{/* Desktop collapse control — sits on the nav's right border
						    just under the header; parks at the window edge when the
						    column is collapsed. */}
						<button
							type="button"
							aria-label={desktopHidden ? "Show navigation" : "Hide navigation"}
							title={desktopHidden ? "Show navigation" : "Hide navigation"}
							onClick={() => setDesktopHidden((h) => !h)}
							className={cn(
								"absolute top-3 z-10 hidden size-7 items-center justify-center bg-[#0f62fe] text-white transition-colors hover:bg-[#0353e9] md:flex",
								desktopHidden ? "left-0" : "left-64 -translate-x-1/2",
							)}
						>
							{desktopHidden ? (
								<PanelLeftOpenIcon className="size-4" strokeWidth={1.5} />
							) : (
								<PanelLeftCloseIcon className="size-4" strokeWidth={1.5} />
							)}
						</button>
					</>
				)}
				<main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
					{children}
				</main>
			</div>
		</>
	);
}
