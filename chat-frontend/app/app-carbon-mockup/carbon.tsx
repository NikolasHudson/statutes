"use client";

// Carbon shell for the /app-carbon-mockup design suite. The primitives moved
// to components/carbon/primitives.tsx (shared with the functional v2 app);
// this file re-exports them and keeps the mockup-specific chrome: the static
// nav linking every mockup screen and the "not the live app" header note.

import {
	GitCompareArrowsIcon,
	LayoutGridIcon,
	MessageSquareTextIcon,
	ScaleIcon,
	SearchIcon,
	SettingsIcon,
	SlidersHorizontalIcon,
	SparklesIcon,
	UserIcon,
} from "lucide-react";
import {
	type NavGroup,
	ShellHeader as SharedShellHeader,
	SideNav as SharedSideNav,
} from "@/components/carbon/primitives";

export * from "@/components/carbon/primitives";

const NAV: NavGroup[] = [
	{
		group: "Workspace",
		items: [
			{
				href: "/app-carbon-mockup/assistant",
				label: "Assistant",
				icon: MessageSquareTextIcon,
			},
			{
				href: "/browse-carbon-mockup",
				label: "Library",
				icon: SearchIcon,
				detail: "105,355 documents",
			},
			{
				href: "/app-carbon-mockup/results",
				label: "Search results",
				icon: LayoutGridIcon,
			},
			{
				href: "/app-carbon-mockup/advanced",
				label: "Advanced search",
				icon: SlidersHorizontalIcon,
			},
			{
				href: "/app-carbon-mockup/compare",
				label: "Compare editions",
				icon: GitCompareArrowsIcon,
			},
		],
	},
	{
		group: "Reader",
		items: [
			{
				href: "/app-carbon-mockup/case",
				label: "Case reader",
				icon: ScaleIcon,
				detail: "Katko v. Briney (1971)",
			},
		],
	},
	{
		group: "Account",
		items: [
			{
				href: "/app-carbon-mockup/account",
				label: "Settings",
				icon: SettingsIcon,
			},
			{
				href: "/app-carbon-mockup/onboarding",
				label: "Onboarding",
				icon: SparklesIcon,
				detail: "first-run wizard",
			},
			{
				href: "/app-carbon-mockup/signin",
				label: "Sign in",
				icon: UserIcon,
				detail: "signed-out state",
			},
		],
	},
];

export function ShellHeader({
	note = "Carbon mockup — not the live app",
}: {
	note?: string;
}) {
	return (
		<SharedShellHeader
			homeHref="/app-carbon-mockup"
			note={note}
			right={
				<span className="flex size-12 items-center justify-center bg-[#0f62fe] font-semibold text-xs">
					NH
				</span>
			}
		/>
	);
}

export function SideNav({ active }: { active: string }) {
	return <SharedSideNav groups={NAV} active={active} />;
}

// Standard screen chrome: dark shell header + side nav + scrollable main.
// Screens that need their own canvas (sign-in, onboarding) skip this and
// compose ShellHeader directly.
export function AppShell({
	active,
	children,
}: {
	active: string;
	children: React.ReactNode;
}) {
	return (
		<>
			<ShellHeader />
			<div className="flex min-h-0 flex-1">
				<SideNav active={active} />
				<main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
			</div>
		</>
	);
}
