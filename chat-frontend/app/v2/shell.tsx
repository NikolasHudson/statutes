"use client";

// App chrome for the functional Carbon rebuild (/v2): dark shell header with
// the signed-in user chip + sign-out, and the side nav over the real v2
// routes. Visual language comes from components/carbon/primitives; the mockup
// suite keeps its own static shell in app/app-carbon-mockup/carbon.tsx.

import {
	GitCompareArrowsIcon,
	LayoutGridIcon,
	LogOutIcon,
	MessageSquareTextIcon,
	ScaleIcon,
	SearchIcon,
	SettingsIcon,
	SlidersHorizontalIcon,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth-gate";
import {
	type NavGroup,
	ShellHeader,
	SideNav,
} from "@/components/carbon/primitives";
import { cn } from "@/lib/utils";

const NAV: NavGroup[] = [
	{
		group: "Workspace",
		items: [
			{ href: "/v2", label: "Library", icon: SearchIcon, exact: true },
			{
				href: "/v2/assistant",
				label: "Assistant",
				icon: MessageSquareTextIcon,
			},
			{ href: "/v2/results", label: "Search results", icon: LayoutGridIcon },
			{
				href: "/v2/advanced",
				label: "Advanced search",
				icon: SlidersHorizontalIcon,
			},
			{
				href: "/v2/compare",
				label: "Compare editions",
				icon: GitCompareArrowsIcon,
			},
		],
	},
	{
		group: "Reader",
		items: [{ href: "/v2/case", label: "Case reader", icon: ScaleIcon }],
	},
	{
		group: "Account",
		items: [{ href: "/v2/account", label: "Settings", icon: SettingsIcon }],
	},
];

function initials(name: string, email: string): string {
	const parts = name.trim().split(/\s+/).filter(Boolean);
	if (parts.length >= 2)
		return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
	if (parts.length === 1 && parts[0]) return parts[0].slice(0, 2).toUpperCase();
	return email.slice(0, 2).toUpperCase();
}

function UserChip() {
	const { user, signOut } = useAuth();
	return (
		<>
			<button
				type="button"
				onClick={() => void signOut()}
				aria-label="Sign out"
				title="Sign out"
				className="flex size-12 items-center justify-center transition-colors hover:bg-[#353535]"
			>
				<LogOutIcon className="size-4" />
			</button>
			<span
				title={user.email}
				className="flex size-12 items-center justify-center bg-[#0f62fe] font-semibold text-xs"
			>
				{initials(user.full_name, user.email)}
			</span>
		</>
	);
}

export function V2Shell({ children }: { children: React.ReactNode }) {
	const pathname = usePathname() ?? "/v2";
	// The onboarding wizard brings its own stepper rail — give it the full
	// canvas instead of the app nav.
	const bare = pathname === "/v2/onboarding";

	// The hamburger means different things per viewport: on md+ it collapses
	// the nav column (more room to read); below md — where the column is
	// hidden by default — it opens the nav as a drawer over the content.
	const [desktopHidden, setDesktopHidden] = useState(false);
	const [mobileOpen, setMobileOpen] = useState(false);
	const onMenu = () => {
		if (window.matchMedia("(min-width: 768px)").matches) {
			setDesktopHidden((h) => !h);
		} else {
			setMobileOpen((o) => !o);
		}
	};
	// Picking a destination closes the mobile drawer.
	useEffect(() => setMobileOpen(false), [pathname]);

	return (
		<>
			<ShellHeader
				homeHref="/v2"
				note="v2 preview"
				right={<UserChip />}
				onMenu={bare ? undefined : onMenu}
			/>
			<div className="flex min-h-0 flex-1">
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
							groups={NAV}
							active={pathname}
							className={cn(
								mobileOpen &&
									"fixed top-12 bottom-0 left-0 z-30 flex bg-[var(--cds-bg)] md:static",
								desktopHidden && "md:hidden",
							)}
						/>
					</>
				)}
				<main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
					{children}
				</main>
			</div>
		</>
	);
}
