"use client";

// App chrome for the Carbon app (SIDEBAR_PLAN.md, SEARCH_BAR_PLAN.md). At md+ every route opens
// with a 48px navy icon rail; resting the pointer on it (or tabbing into it)
// fans a 256px flyout out over the content, and "Keep open" / `[` docks the
// full nav in flow — remembered per user. Below md the dark ShellHeader stays
// as the hamburger bar and the full nav opens as a drawer. Visual language
// comes from components/carbon/primitives; the mockup suite keeps its own
// static shell in app/app-carbon-mockup/carbon.tsx.

import {
	Building2Icon,
	ChartColumnIcon,
	ChevronsUpDownIcon,
	CloudIcon,
	CreditCardIcon,
	GitCompareArrowsIcon,
	LogOutIcon,
	MessageSquareTextIcon,
	MoonIcon,
	NewspaperIcon,
	SearchIcon,
	SettingsIcon,
	SlidersHorizontalIcon,
	SunIcon,
	TriangleAlertIcon,
	UsersIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/auth-gate";
import {
	type NavGroup,
	ShellHeader,
	SideNav,
	useTheme,
} from "@/components/carbon/primitives";
import {
	WorkspaceBar,
	WorkspaceBarProvider,
} from "@/components/carbon/workspace-bar";
import { EDMS_PRODUCT_SHORT_NAME } from "@/lib/brand";
import { loadDocked, saveDocked } from "@/lib/nav-prefs";
import { cn } from "@/lib/utils";

// Library is the reading surface: it stays lit on every route that shows
// corpus text, not just the search home. "/" is matched exactly by isNavActive.
const READING_ROUTES = [
	"/",
	"/case",
	"/section",
	"/chapter",
	"/source",
	"/results",
	"/goto",
];

const NAV: NavGroup[] = [
	{
		group: "Workspace",
		items: [
			{
				href: "/",
				label: "Library",
				icon: SearchIcon,
				exact: true,
				activeFor: READING_ROUTES,
			},
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
	// Every user belongs to an org (a personal one, if nothing else) and every
	// org has a plan, so both entries show for everyone; what each person can
	// actually *do* there depends on their org role, which the server enforces
	// on each call. Settings still lives in the user menu at the foot of the nav.
	{
		group: "Account",
		items: [
			{ href: "/org", label: "Organization", icon: Building2Icon },
			{ href: "/account/billing", label: "Billing", icon: CreditCardIcon },
		],
	},
];

// Nav entry that only appears for plans that include the product. Keyed on the
// feature strings /api/auth/me carries. Display-only: every EDMSpro route
// answers 402/403 on its own, and the page renders an inline "not on your
// plan" panel, so a stale list opens nothing and strands nobody.
const EDMS_ACCOUNT_ITEM = {
	href: "/account/edms",
	label: EDMS_PRODUCT_SHORT_NAME,
	icon: CloudIcon,
};

function navFor(features: string[]): NavGroup[] {
	if (!features.includes("edms")) return NAV;
	return NAV.map((group) =>
		group.group === "Account"
			? { ...group, items: [...group.items, EDMS_ACCOUNT_ITEM] }
			: group,
	);
}

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

// Hover intent. The rail sits on the left edge, where the pointer passes on
// its way to the browser's back button, so a pointer that enters and leaves
// inside OPEN_DELAY never opens anything; once open, CLOSE_DELAY covers the
// hop from the rail into the flyout and small overshoots. Tune on dev, not in
// prod (SIDEBAR_PLAN.md).
const OPEN_DELAY_MS = 150;
const CLOSE_DELAY_MS = 300;

const BETA_COPY =
	"Hudson Corpus is in beta. Verify all citations and quotations against the primary source before relying on them.";

function initials(name: string, email: string): string {
	const parts = name.trim().split(/\s+/).filter(Boolean);
	if (parts.length >= 2)
		return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
	if (parts.length === 1 && parts[0]) return parts[0].slice(0, 2).toUpperCase();
	return email.slice(0, 2).toUpperCase();
}

// True when a keystroke belongs to a field, so global shortcuts stay out of
// the way — same guard as the DocChat "/" shortcut.
function isTypingTarget(target: EventTarget | null): boolean {
	const el = target as HTMLElement | null;
	return !!(
		el &&
		(el.tagName === "INPUT" ||
			el.tagName === "TEXTAREA" ||
			el.tagName === "SELECT" ||
			el.isContentEditable)
	);
}

// Warning-notification-styled beta disclaimer pinned above the user section
// at the foot of the full nav …
function BetaNotice() {
	return (
		<div className="flex gap-3 border-[var(--cds-nav-border)] border-b border-l-[3px] border-l-[#f1c21b] bg-[var(--cds-nav-selected)] py-3 pr-4 pl-3.5">
			<TriangleAlertIcon
				className="mt-0.5 size-4 shrink-0 text-[#f1c21b]"
				strokeWidth={1.5}
			/>
			<p className="text-[var(--cds-nav-text)] text-xs leading-relaxed">
				{BETA_COPY}
			</p>
		</div>
	);
}

// … and its 48px rail cell, which carries the same text as a tooltip.
function BetaRailCell() {
	return (
		<span
			role="note"
			title={BETA_COPY}
			aria-label={BETA_COPY}
			className="flex size-12 items-center justify-center text-[#f1c21b]"
		>
			<TriangleAlertIcon className="size-4" strokeWidth={1.5} />
		</span>
	);
}

// Signed-in user at the foot of the nav; clicking it pops a menu with
// Settings, the theme switch and Log out. `compact` is the rail's 48px avatar
// cell — same menu, popping out to the right instead of upward.
function UserFooter({ compact = false }: { compact?: boolean }) {
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

	const name = user.full_name || user.email;
	const menuItem =
		"flex w-full items-center gap-3 px-4 py-2.5 text-[var(--cds-text-2)] text-sm transition-colors hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]";

	return (
		<div ref={ref} className="relative">
			{open && (
				<div
					role="menu"
					className={cn(
						"absolute border border-[var(--cds-border)] bg-[var(--cds-bg)] py-1 text-[var(--cds-text)]",
						compact
							? "bottom-0 left-full z-40 ml-px w-56 shadow-[2px_0_8px_rgba(0,0,0,0.2)]"
							: "inset-x-0 bottom-full shadow-[0_-2px_8px_rgba(0,0,0,0.2)]",
					)}
				>
					{compact && (
						<div className="border-[var(--cds-border)] border-b px-4 py-2.5">
							<p className="truncate font-semibold text-sm">{name}</p>
							<p className="truncate text-[var(--cds-helper)] text-xs">
								{user.email}
							</p>
						</div>
					)}
					<Link
						href="/account"
						role="menuitem"
						onClick={() => setOpen(false)}
						className={menuItem}
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
						className={menuItem}
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
						className={menuItem}
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
				aria-label={compact ? `Account menu — ${name}` : undefined}
				title={compact ? name : undefined}
				className={cn(
					"flex items-center text-left transition-colors hover:bg-[var(--cds-nav-hover)]",
					compact ? "h-14 w-12 justify-center" : "w-full gap-3 px-3.5 py-3",
				)}
			>
				<span className="flex size-8 shrink-0 items-center justify-center bg-[var(--cds-nav-avatar-bg)] font-semibold text-[var(--cds-nav-avatar-text)] text-xs">
					{initials(user.full_name, user.email)}
				</span>
				{!compact && (
					<>
						<span className="flex min-w-0 flex-1 flex-col">
							<span className="truncate font-semibold text-[var(--cds-nav-text-active)] text-sm">
								{name}
							</span>
							<span className="truncate text-[var(--cds-nav-helper)] text-xs">
								{user.email}
							</span>
						</span>
						<ChevronsUpDownIcon className="size-4 shrink-0 text-[var(--cds-nav-helper)]" />
					</>
				)}
			</button>
		</div>
	);
}

export function V2Shell({ children }: { children: React.ReactNode }) {
	const pathname = usePathname() ?? "/";
	const { user } = useAuth();
	const base = navFor(user.features ?? []);
	const navGroups = user.is_staff ? [...base, ADMIN_NAV] : base;
	// The onboarding wizard brings its own stepper rail — give it the full
	// canvas (and keep the header, since there's no nav to carry the brand).
	const bare = pathname === "/onboarding";

	// Docked = the full nav pinned in flow, remembered per user. The shell only
	// mounts signed-in on the client (AuthGate gates on /api/auth/me), so the
	// initial read from localStorage can't mismatch a server render.
	const [docked, setDockedState] = useState(() => loadDocked(user.id) ?? false);
	useEffect(() => setDockedState(loadDocked(user.id) ?? false), [user.id]);
	// Transient: the flyout over the content while on the rail.
	const [flyoutOpen, setFlyoutOpen] = useState(false);
	// Below md: the drawer the header hamburger opens.
	const [mobileOpen, setMobileOpen] = useState(false);

	const railRef = useRef<HTMLDivElement>(null);
	const openTimer = useRef<number | undefined>(undefined);
	const closeTimer = useRef<number | undefined>(undefined);
	// Up only while Escape hands focus back to the rail toggle, so that
	// programmatic focus doesn't re-open the flyout it just closed.
	const skipFocusOpen = useRef(false);

	const clearTimers = useCallback(() => {
		window.clearTimeout(openTimer.current);
		window.clearTimeout(closeTimer.current);
	}, []);
	useEffect(() => clearTimers, [clearTimers]);

	const setDocked = useCallback(
		(next: boolean) => {
			setDockedState(next);
			saveDocked(user.id, next);
			clearTimers();
			setFlyoutOpen(false);
		},
		[user.id, clearTimers],
	);

	// Picking a destination closes whichever overlay is open.
	// biome-ignore lint/correctness/useExhaustiveDependencies: re-runs on every route change by design
	useEffect(() => {
		setMobileOpen(false);
		setFlyoutOpen(false);
	}, [pathname]);

	// Hover intent (mouse/pen only — a touch "enter" is a tap, handled by the
	// toggle cell). Leaving inside OPEN_DELAY cancels the open, so a sweep
	// across the rail to browser chrome never fans it out.
	const onRailPointerEnter = (e: React.PointerEvent) => {
		if (e.pointerType === "touch") return;
		window.clearTimeout(closeTimer.current);
		if (flyoutOpen) return;
		window.clearTimeout(openTimer.current);
		openTimer.current = window.setTimeout(
			() => setFlyoutOpen(true),
			OPEN_DELAY_MS,
		);
	};
	const onRailPointerLeave = (e: React.PointerEvent) => {
		if (e.pointerType === "touch") return;
		clearTimers();
		closeTimer.current = window.setTimeout(
			() => setFlyoutOpen(false),
			CLOSE_DELAY_MS,
		);
	};
	// Keyboard: tabbing into the rail opens the flyout (focus-visible only, so
	// a mouse click on a rail link doesn't flash it open on the way out).
	const onRailFocus = (e: React.FocusEvent) => {
		if (skipFocusOpen.current) {
			skipFocusOpen.current = false;
			return;
		}
		if (!(e.target as Element).matches?.(":focus-visible")) return;
		clearTimers();
		setFlyoutOpen(true);
	};
	const onRailBlur = (e: React.FocusEvent) => {
		if (railRef.current?.contains(e.relatedTarget as Node | null)) return;
		clearTimers();
		setFlyoutOpen(false);
	};
	const toggleFlyout = () => {
		clearTimers();
		setFlyoutOpen((o) => !o);
	};

	// Flyout open: Escape closes and returns focus to the toggle; a press
	// outside (touch, or a click that beat the close timer) closes.
	useEffect(() => {
		if (!flyoutOpen) return;
		const onKeyDown = (e: KeyboardEvent) => {
			if (e.key !== "Escape") return;
			clearTimers();
			setFlyoutOpen(false);
			const toggle =
				railRef.current?.querySelector<HTMLElement>("[data-rail-toggle]");
			if (
				toggle &&
				toggle !== document.activeElement &&
				railRef.current?.contains(document.activeElement)
			) {
				// Focus events dispatch synchronously, so the guard is only up
				// for the duration of this call and can't swallow a later Tab.
				skipFocusOpen.current = true;
				toggle.focus();
				skipFocusOpen.current = false;
			}
		};
		const onPointerDown = (e: PointerEvent) => {
			if (railRef.current?.contains(e.target as Node)) return;
			clearTimers();
			setFlyoutOpen(false);
		};
		document.addEventListener("keydown", onKeyDown);
		document.addEventListener("pointerdown", onPointerDown);
		return () => {
			document.removeEventListener("keydown", onKeyDown);
			document.removeEventListener("pointerdown", onPointerDown);
		};
	}, [flyoutOpen, clearTimers]);

	// `[` pins/unpins the nav — never from inside a field.
	useEffect(() => {
		if (bare) return;
		const onKeyDown = (e: KeyboardEvent) => {
			if (e.key !== "[" || e.metaKey || e.repeat) return;
			if (isTypingTarget(e.target)) return;
			e.preventDefault();
			setDocked(!docked);
		};
		document.addEventListener("keydown", onKeyDown);
		return () => document.removeEventListener("keydown", onKeyDown);
	}, [bare, docked, setDocked]);

	const fullFooter = (
		<>
			<BetaNotice />
			<UserFooter />
		</>
	);

	return (
		<WorkspaceBarProvider>
			<ShellHeader
				homeHref="/"
				onMenu={bare ? undefined : () => setMobileOpen((o) => !o)}
				mobileMenuOnly
				themeToggle={false}
				className={bare ? undefined : "md:hidden"}
			/>
			<div className="relative flex min-h-0 flex-1">
				{!bare && (
					<>
						{/* Below md: drawer under the header. */}
						{mobileOpen && (
							<>
								<button
									type="button"
									aria-label="Close navigation"
									onClick={() => setMobileOpen(false)}
									className="fixed inset-0 z-20 bg-black/40 md:hidden"
								/>
								<SideNav
									mode="docked"
									brand={false}
									groups={navGroups}
									active={pathname}
									footer={fullFooter}
									className="fixed top-12 bottom-0 left-0 z-30 print:hidden md:hidden"
								/>
							</>
						)}

						{/* md+: docked nav in flow, or the rail with its flyout. */}
						{docked ? (
							<SideNav
								mode="docked"
								groups={navGroups}
								active={pathname}
								footer={fullFooter}
								onToggle={() => setDocked(false)}
								className="hidden print:hidden md:flex"
							/>
						) : (
							// biome-ignore lint/a11y/noStaticElementInteractions: hover/focus region around the rail; the controls inside it are real buttons and links
							<div
								ref={railRef}
								onPointerEnter={onRailPointerEnter}
								onPointerLeave={onRailPointerLeave}
								onFocus={onRailFocus}
								onBlur={onRailBlur}
								className="relative hidden shrink-0 print:hidden md:flex"
							>
								<SideNav
									mode="rail"
									groups={navGroups}
									active={pathname}
									onToggle={toggleFlyout}
									expanded={flyoutOpen}
									railFooter={
										<>
											<BetaRailCell />
											<UserFooter compact />
										</>
									}
								/>
								{/* Always mounted so the rail can grow into the full nav and
								    shrink back: the wrapper animates 48px → 256px while the
								    nav inside stays laid out at 256px, so nothing reflows
								    mid-expansion. Visibility flips only once the collapse
								    has finished (a visibility transition holds "visible"
								    until its end), and the parked nav is inert. */}
								<div
									className={cn(
										"absolute inset-y-0 left-0 z-30 overflow-hidden shadow-[4px_0_12px_rgba(0,0,0,0.24)] transition-[width,visibility] ease-out motion-reduce:transition-none",
										flyoutOpen
											? "visible w-64 duration-200"
											: "invisible w-12 duration-150",
									)}
								>
									<SideNav
										mode="flyout"
										groups={navGroups}
										active={pathname}
										footer={fullFooter}
										onToggle={() => setDocked(true)}
										inert={!flyoutOpen}
										className="h-full"
									/>
								</div>
							</div>
						)}
					</>
				)}
				<main className="flex min-w-0 flex-1 flex-col">
					{/* The workspace bar (SEARCH_BAR_PLAN.md): context · search ·
					    actions on every route. The Library home keeps its hero
					    search instead. */}
					{!bare && pathname !== "/" && <WorkspaceBar />}
					<div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
						{children}
					</div>
				</main>
			</div>
		</WorkspaceBarProvider>
	);
}
