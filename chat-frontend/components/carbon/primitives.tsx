"use client";

// Shared Carbon (IBM design system) primitives — themes, shell chrome, and
// form/content patterns. Serves both the /app-carbon-mockup design suite and
// the functional v2 app (/v2). Token cheatsheet lives in
// docs/carbon-design-system.md.
//
// One markup tree serves both Carbon themes ("white" and "g100"): tokens are
// CSS custom properties applied on the root wrapper by CarbonRoot (a route
// group's layout). The UI-shell header stays g100-dark in both themes, per
// Carbon convention.

import {
	AlertTriangleIcon,
	ArrowRightIcon,
	CheckCircle2Icon,
	CheckIcon,
	ChevronDownIcon,
	InfoIcon,
	type LucideIcon,
	MenuIcon,
	MoonIcon,
	PanelLeftCloseIcon,
	PanelLeftOpenIcon,
	SunIcon,
	XCircleIcon,
} from "lucide-react";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import {
	createContext,
	Fragment,
	useContext,
	useEffect,
	useId,
	useState,
} from "react";
import { appHost } from "@/lib/brand";
import { cn } from "@/lib/utils";

const plexSans = IBM_Plex_Sans({
	weight: ["300", "400", "600"],
	style: ["normal", "italic"],
	subsets: ["latin"],
	variable: "--font-plex-sans",
});

const plexMono = IBM_Plex_Mono({
	weight: ["400"],
	subsets: ["latin"],
	variable: "--font-plex-mono",
});

// ---------------------------------------------------------------------------
// Carbon v11 theme tokens
// ---------------------------------------------------------------------------

export type ThemeName = "white" | "g100";

// App side-nav tokens — Carbon Blue 90 in both themes. Like the g100 shell
// header, the nav is chrome and doesn't follow the content theme; the same
// navy sits against #ffffff and #161616 (SIDEBAR_PLAN.md). Beta tag and
// warning marks stay #f1c21b on it.
const NAV_TOKENS: Record<string, string> = {
	"--cds-nav-bg": "#001d6c", // Blue 90
	"--cds-nav-border": "#002d9c", // Blue 80
	"--cds-nav-hover": "#002d9c",
	"--cds-nav-selected": "#002d9c",
	"--cds-nav-text": "#d0e2ff", // Blue 20
	"--cds-nav-text-active": "#ffffff",
	"--cds-nav-bar": "#78a9ff", // Blue 40 — active item's left bar
	"--cds-nav-helper": "#a6c8ff", // Blue 30 — eyebrows, helper text
	"--cds-nav-avatar-bg": "#78a9ff",
	"--cds-nav-avatar-text": "#001141", // Blue 100
};

export const THEMES: Record<ThemeName, Record<string, string>> = {
	white: {
		...NAV_TOKENS,
		"--cds-bg": "#ffffff",
		"--cds-layer": "#f4f4f4",
		"--cds-layer-hover": "#e8e8e8",
		"--cds-layer-selected": "#e0e0e0",
		"--cds-field": "#f4f4f4",
		"--cds-border": "#e0e0e0",
		"--cds-border-strong": "#8d8d8d",
		"--cds-text": "#161616",
		"--cds-text-2": "#525252",
		"--cds-helper": "#6f6f6f",
		"--cds-placeholder": "#a8a8a8",
		"--cds-link": "#0f62fe",
		// Tinted field (the reader's search): Blue 10 fill, Blue 50 baseline,
		// Blue 70 accents, Blue 20 selected row.
		"--cds-field-tint": "#edf5ff",
		"--cds-field-tint-border": "#4589ff",
		"--cds-tint-text": "#0043ce",
		"--cds-tint-selected": "#d0e2ff",
		"--cds-danger-text": "#da1e28",
		"--cds-success-text": "#24a148",
		"--cds-purple-text": "#6929c4",
	},
	g100: {
		...NAV_TOKENS,
		"--cds-bg": "#161616",
		"--cds-layer": "#262626",
		"--cds-layer-hover": "#333333",
		"--cds-layer-selected": "#393939",
		"--cds-field": "#262626",
		"--cds-border": "#393939",
		"--cds-border-strong": "#6f6f6f",
		"--cds-text": "#f4f4f4",
		"--cds-text-2": "#c6c6c6",
		"--cds-helper": "#8d8d8d",
		"--cds-placeholder": "#6f6f6f",
		"--cds-link": "#78a9ff",
		"--cds-field-tint": "#001141",
		"--cds-field-tint-border": "#4589ff",
		"--cds-tint-text": "#78a9ff",
		"--cds-tint-selected": "#002d9c",
		"--cds-danger-text": "#fa4d56",
		"--cds-success-text": "#42be65",
		"--cds-purple-text": "#be95ff",
	},
};

// Theme-independent action + support colors.
export const BLUE = "#0f62fe";
export const BLUE_HOVER = "#0353e9";
export const BLUE_ACTIVE = "#002d9c";

// ---------------------------------------------------------------------------
// Theme context — CarbonRoot wraps a whole route group (see the group's
// layout.tsx), so the sun/moon toggle carries across screens without
// remounting.
// ---------------------------------------------------------------------------

const ThemeCtx = createContext<{
	theme: ThemeName;
	setTheme: (t: ThemeName) => void;
}>({ theme: "white", setTheme: () => {} });

export const useTheme = () => useContext(ThemeCtx);

export function CarbonRoot({ children }: { children: React.ReactNode }) {
	// Case text is the workhorse surface, so default to the white theme; the
	// header toggle is global to the route group.
	const [theme, setTheme] = useState<ThemeName>("white");
	return (
		<ThemeCtx.Provider value={{ theme, setTheme }}>
			<div
				className={cn(
					"flex h-dvh flex-col bg-[var(--cds-bg)] text-[var(--cds-text)]",
					plexSans.variable,
					plexMono.variable,
				)}
				style={
					{
						...THEMES[theme],
						fontFamily: "var(--font-plex-sans)",
						// font-mono utilities resolve --font-geist-mono in this app, so
						// pointing it at Plex Mono re-skins mono usage inside the suite only.
						"--font-geist-mono": "var(--font-plex-mono)",
					} as React.CSSProperties
				}
			>
				{children}
			</div>
		</ThemeCtx.Provider>
	);
}

// ---------------------------------------------------------------------------
// UI shell — g100-dark header (both themes) + generic side nav
// ---------------------------------------------------------------------------

// The "Beta" chip that rides the wordmark in the shell header and the app
// nav. inline-block keeps a parent link's hover underline from running
// through it.
export function BetaTag() {
	return (
		<span className="ml-2.5 inline-block border border-[#f1c21b] px-1.5 py-px align-[2px] font-mono text-[#f1c21b] text-[10px] uppercase tracking-[0.08em]">
			Beta
		</span>
	);
}

export function ShellHeader({
	homeHref = "/",
	note,
	right,
	onMenu,
	mobileMenuOnly = false,
	themeToggle = true,
	className,
}: {
	homeHref?: string;
	note?: string;
	// Trailing header content (avatar chip, sign-out …); rendered after the
	// theme toggle.
	right?: React.ReactNode;
	// Hamburger click — toggles the side nav where the shell provides one.
	onMenu?: () => void;
	// Show the hamburger below md only (shells that mount their own desktop
	// toggle on the nav edge); the logo takes over its left spacing on md+.
	mobileMenuOnly?: boolean;
	// Hide the header sun/moon switch when the shell surfaces the theme
	// control elsewhere (e.g. the v2 user menu).
	themeToggle?: boolean;
	// Visibility overrides — the app shell hides the header at md+, where the
	// brand lives in the side nav instead.
	className?: string;
}) {
	const { theme, setTheme } = useTheme();
	const next: ThemeName = theme === "g100" ? "white" : "g100";
	return (
		<header
			className={cn(
				"flex h-12 shrink-0 items-center border-[#393939] border-b bg-[#161616] text-white",
				className,
			)}
		>
			{onMenu && (
				<button
					type="button"
					aria-label="Toggle navigation"
					onClick={onMenu}
					className={cn(
						"flex size-12 items-center justify-center transition-colors hover:bg-[#353535]",
						mobileMenuOnly && "md:hidden",
					)}
				>
					<MenuIcon className="size-4" />
				</button>
			)}

			<Link
				href={homeHref}
				className={cn(
					"text-sm hover:underline",
					// Whenever the hamburger isn't occupying the left edge, the
					// logo carries the padding instead.
					!onMenu && "pl-4",
					onMenu && mobileMenuOnly && "md:pl-4",
				)}
			>
				<span className="font-semibold">HUDSON</span>
				<span className="ml-2 text-[#a8a8a8]">Corpus</span>
				<BetaTag />
			</Link>

			{note && (
				<p className="ml-6 hidden font-mono text-[#6f6f6f] text-[11px] uppercase tracking-[0.2em] lg:block">
					{note}
				</p>
			)}

			<div className="ml-auto flex items-center">
				{themeToggle && (
					<>
						<span className="mr-1 hidden font-mono text-[#a8a8a8] text-[11px] sm:block">
							theme: {theme}
						</span>
						<button
							type="button"
							onClick={() => setTheme(next)}
							aria-label={`Switch to ${next} theme`}
							title={`Switch to ${next} theme`}
							className="flex size-12 items-center justify-center transition-colors hover:bg-[#353535]"
						>
							{theme === "g100" ? (
								<SunIcon className="size-4" />
							) : (
								<MoonIcon className="size-4" />
							)}
						</button>
					</>
				)}
				{right}
			</div>
		</header>
	);
}

export function NavGroupLabel({ children }: { children: React.ReactNode }) {
	return (
		<p className="px-4 pt-6 pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
			{children}
		</p>
	);
}

export type NavItem = {
	href: string;
	label: string;
	icon: LucideIcon;
	detail?: string;
	// Match the href exactly instead of as a path prefix — for a group's
	// root item (e.g. "/") that would otherwise swallow every subroute.
	exact?: boolean;
	// Extra path prefixes that light this item ("/" counts only for itself).
	// Lets Library own every reading route (/case/*, /section/* …) without
	// those pages needing nav entries of their own.
	activeFor?: string[];
};

export type NavGroup = {
	group: string;
	items: NavItem[];
};

function underPrefix(path: string, prefix: string): boolean {
	if (prefix === "/") return path === "/";
	return path === prefix || path.startsWith(`${prefix}/`);
}

export function isNavActive(item: NavItem, path: string): boolean {
	if (item.activeFor?.some((p) => underPrefix(path, p))) return true;
	return item.exact ? path === item.href : underPrefix(path, item.href);
}

// The three shapes of the app's navy nav (SIDEBAR_PLAN.md): the 48px icon
// rail every route opens with, the 256px flyout that fans out over the content
// on hover/focus, and the same 256px nav docked in flow when the user pins it.
export type SideNavMode = "rail" | "flyout" | "docked";

export function SideNav({
	groups,
	active,
	footer,
	className,
	mode,
	homeHref = "/",
	brand = true,
	onToggle,
	expanded,
	railFooter,
	inert = false,
}: {
	groups: NavGroup[];
	active: string;
	// Content under the bottom rule. The classic column falls back to the host
	// the app is served from — left undefined rather than computed in the
	// signature because the fallback needs `window`: see below.
	footer?: React.ReactNode;
	// Positioning/visibility overrides (e.g. the app shell's mobile drawer /
	// breakpoint gating) — merged after the defaults so they win conflicts.
	className?: string;
	// Navy app-shell modes. Unset → the classic light 256px column the mockup
	// suite still renders.
	mode?: SideNavMode;
	homeHref?: string;
	// flyout/docked: render the wordmark row at the top. The mobile drawer
	// turns it off because the shell header above it already carries the brand.
	brand?: boolean;
	// rail: opens/closes the flyout (tap + keyboard). flyout: the "Keep open"
	// row docks the nav. docked: the collapse control returns to the rail.
	onToggle?: () => void;
	// rail: mirrors the flyout's open state onto the toggle's aria-expanded.
	expanded?: boolean;
	// rail: 48px cells under the bottom rule (beta mark, avatar).
	railFooter?: React.ReactNode;
	// flyout: the shell keeps it mounted so it can animate closed; while
	// parked it must be unreachable by Tab and assistive tech.
	inert?: boolean;
}) {
	// The public mockup routes render this nav on the server, where appHost()
	// has no window and no NEXT_PUBLIC_APP_URL to read, so resolving it during
	// render would hydrate a different string than it served. Fill it in after
	// mount instead, when the two agree.
	const [host, setHost] = useState("");
	useEffect(() => setHost(appHost()), []);

	if (mode === "rail") {
		return (
			<nav
				aria-label="Main"
				className={cn(
					"flex w-12 shrink-0 flex-col border-[var(--cds-nav-border)] border-r bg-[var(--cds-nav-bg)] text-[var(--cds-nav-text)]",
					className,
				)}
			>
				<Link
					href={homeHref}
					title="Hudson Corpus"
					aria-label="Hudson Corpus — home"
					className="flex size-12 shrink-0 items-center justify-center border-[var(--cds-nav-border)] border-b"
				>
					<span className="flex size-7 items-center justify-center bg-white font-semibold text-[13px] text-[var(--cds-nav-bg)] tracking-[0.02em]">
						H
					</span>
				</Link>
				{onToggle && (
					<button
						type="button"
						onClick={onToggle}
						data-rail-toggle
						aria-expanded={expanded}
						aria-label={expanded ? "Hide navigation" : "Show navigation"}
						title={expanded ? "Hide navigation" : "Show navigation"}
						className="flex size-12 shrink-0 items-center justify-center transition-colors hover:bg-[var(--cds-nav-hover)] hover:text-[var(--cds-nav-text-active)]"
					>
						<PanelLeftOpenIcon className="size-4" strokeWidth={1.5} />
					</button>
				)}
				<div className="flex flex-1 flex-col overflow-y-auto pt-2">
					{groups.map((g, gi) => (
						<Fragment key={g.group}>
							{gi > 0 && (
								<span
									aria-hidden
									className="mx-3 my-2 block h-px shrink-0 bg-[var(--cds-nav-border)]"
								/>
							)}
							<div>
								{g.items.map((it) => {
									const isActive = isNavActive(it, active);
									const Icon = it.icon;
									return (
										<Link
											key={it.href}
											href={it.href}
											title={it.label}
											aria-label={it.label}
											aria-current={isActive ? "page" : undefined}
											className={cn(
												"flex size-12 items-center justify-center border-l-[3px] transition-colors",
												isActive
													? "border-[var(--cds-nav-bar)] bg-[var(--cds-nav-selected)] text-[var(--cds-nav-text-active)]"
													: "border-transparent hover:bg-[var(--cds-nav-hover)] hover:text-[var(--cds-nav-text-active)]",
											)}
										>
											<Icon className="size-4" strokeWidth={1.5} />
										</Link>
									);
								})}
							</div>
						</Fragment>
					))}
				</div>
				{railFooter && (
					<div className="flex shrink-0 flex-col border-[var(--cds-nav-border)] border-t">
						{railFooter}
					</div>
				)}
			</nav>
		);
	}

	if (mode === "flyout" || mode === "docked") {
		return (
			<nav
				aria-label="Main"
				inert={inert}
				aria-hidden={inert || undefined}
				className={cn(
					"flex w-64 shrink-0 flex-col border-[var(--cds-nav-border)] border-r bg-[var(--cds-nav-bg)] text-[var(--cds-nav-text)]",
					className,
				)}
			>
				{brand && (
					<div className="flex h-12 shrink-0 items-center border-[var(--cds-nav-border)] border-b pr-2 pl-4 text-[var(--cds-nav-text-active)] text-sm">
						<Link href={homeHref} className="hover:underline">
							<span className="font-semibold">HUDSON</span>
							<span className="ml-2 text-[var(--cds-nav-helper)]">Corpus</span>
							<BetaTag />
						</Link>
						{mode === "docked" && onToggle && (
							<button
								type="button"
								onClick={onToggle}
								aria-label="Collapse navigation to rail"
								title="Collapse to rail  [ "
								className="ml-auto flex size-8 items-center justify-center text-[var(--cds-nav-text)] transition-colors hover:bg-[var(--cds-nav-hover)] hover:text-[var(--cds-nav-text-active)]"
							>
								<PanelLeftCloseIcon className="size-4" strokeWidth={1.5} />
							</button>
						)}
					</div>
				)}
				{mode === "flyout" && onToggle && (
					<button
						type="button"
						onClick={onToggle}
						className="flex h-12 shrink-0 items-center gap-3 border-[var(--cds-nav-border)] border-b px-3.5 text-[13px] transition-colors hover:bg-[var(--cds-nav-hover)] hover:text-[var(--cds-nav-text-active)]"
					>
						<PanelLeftCloseIcon className="size-4 shrink-0" strokeWidth={1.5} />
						<span>Keep open</span>
						<kbd className="ml-auto font-mono text-[11px] text-[var(--cds-nav-helper)]">
							[
						</kbd>
					</button>
				)}
				<div className="flex-1 overflow-y-auto">
					{groups.map((g) => (
						<div key={g.group}>
							<p className="px-4 pt-6 pb-2 font-mono text-[11px] text-[var(--cds-nav-helper)] uppercase tracking-[0.18em]">
								{g.group}
							</p>
							{g.items.map((it) => {
								const isActive = isNavActive(it, active);
								const Icon = it.icon;
								return (
									<Link
										key={it.href}
										href={it.href}
										aria-current={isActive ? "page" : undefined}
										className={cn(
											"flex w-full items-start gap-3 border-l-[3px] px-3.5 py-2 text-left transition-colors",
											isActive
												? "border-[var(--cds-nav-bar)] bg-[var(--cds-nav-selected)] text-[var(--cds-nav-text-active)]"
												: "border-transparent hover:bg-[var(--cds-nav-hover)] hover:text-[var(--cds-nav-text-active)]",
										)}
									>
										<Icon
											className="mt-0.5 size-4 shrink-0"
											strokeWidth={1.5}
										/>
										<span className="flex min-w-0 flex-col">
											<span
												className={cn(
													"truncate text-sm",
													isActive && "font-semibold",
												)}
											>
												{it.label}
											</span>
											{it.detail && (
												<span className="truncate text-[var(--cds-nav-helper)] text-xs tabular-nums">
													{it.detail}
												</span>
											)}
										</span>
									</Link>
								);
							})}
						</div>
					))}
				</div>
				{footer && (
					<div className="shrink-0 border-[var(--cds-nav-border)] border-t">
						{footer}
					</div>
				)}
			</nav>
		);
	}

	// Classic light column (mockup suite).
	const content = footer ?? (host ? `${host} · beta` : "beta");
	return (
		<nav
			className={cn(
				"hidden w-64 shrink-0 flex-col overflow-y-auto border-[var(--cds-border)] border-r md:flex",
				className,
			)}
		>
			<div className="flex-1">
				{groups.map((g) => (
					<div key={g.group}>
						<NavGroupLabel>{g.group}</NavGroupLabel>
						{g.items.map((it) => {
							const isActive = isNavActive(it, active);
							const Icon = it.icon;
							return (
								<Link
									key={it.href}
									href={it.href}
									className={cn(
										"flex w-full items-start gap-3 border-l-[3px] px-3.5 py-2 text-left transition-colors",
										isActive
											? "border-[#0f62fe] bg-[var(--cds-layer-selected)]"
											: "border-transparent text-[var(--cds-text-2)] hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]",
									)}
								>
									<Icon className="mt-0.5 size-4 shrink-0" strokeWidth={1.5} />
									<span className="flex min-w-0 flex-col">
										<span
											className={cn(
												"truncate text-sm",
												isActive && "font-semibold",
											)}
										>
											{it.label}
										</span>
										{it.detail && (
											<span className="truncate text-[var(--cds-helper)] text-xs tabular-nums">
												{it.detail}
											</span>
										)}
									</span>
								</Link>
							);
						})}
					</div>
				))}
			</div>

			<div className="border-[var(--cds-border)] border-t">
				{typeof content === "string" ? (
					<p className="px-4 py-4 font-mono text-[11px] text-[var(--cds-helper)]">
						{content}
					</p>
				) : (
					content
				)}
			</div>
		</nav>
	);
}

// ---------------------------------------------------------------------------
// Editorial primitives
// ---------------------------------------------------------------------------

export function Eyebrow({ children }: { children: React.ReactNode }) {
	return (
		<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.22em]">
			{children}
		</p>
	);
}

export function PageHead({
	eyebrow,
	title,
	lede,
}: {
	eyebrow: string;
	title: string;
	lede?: string;
}) {
	return (
		<header>
			<Eyebrow>{eyebrow}</Eyebrow>
			<h1 className="mt-4 font-light text-3xl sm:text-4xl">{title}</h1>
			{lede && (
				<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
					{lede}
				</p>
			)}
		</header>
	);
}

// ---------------------------------------------------------------------------
// Buttons — square, label left, generous trailing gap
// ---------------------------------------------------------------------------

type BtnSize = "md" | "lg";
const btnSize = (s: BtnSize) => (s === "lg" ? "h-12 px-5" : "h-10 px-4");

export function BtnPrimary({
	children,
	size = "lg",
	arrow = true,
	className,
	...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
	size?: BtnSize;
	arrow?: boolean;
}) {
	return (
		<button
			type="button"
			{...props}
			className={cn(
				"inline-flex items-center gap-8 bg-[#0f62fe] text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c] disabled:cursor-not-allowed disabled:bg-[var(--cds-layer-selected)] disabled:text-[var(--cds-helper)]",
				btnSize(size),
				className,
			)}
		>
			{children}
			{arrow && <ArrowRightIcon className="size-4" />}
		</button>
	);
}

export function BtnSecondary({
	children,
	size = "lg",
	className,
	...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { size?: BtnSize }) {
	return (
		<button
			type="button"
			{...props}
			className={cn(
				"inline-flex items-center gap-3 border border-[var(--cds-link)] text-[var(--cds-link)] text-sm transition-colors hover:bg-[#0f62fe] hover:text-white",
				btnSize(size),
				className,
			)}
		>
			{children}
		</button>
	);
}

export function BtnGhost({
	children,
	size = "md",
	className,
	...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { size?: BtnSize }) {
	return (
		<button
			type="button"
			{...props}
			className={cn(
				"inline-flex items-center gap-2 text-[var(--cds-link)] text-sm transition-colors hover:bg-[var(--cds-layer-hover)]",
				btnSize(size),
				className,
			)}
		>
			{children}
		</button>
	);
}

export function BtnDanger({
	children,
	size = "md",
	className,
	...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { size?: BtnSize }) {
	return (
		<button
			type="button"
			{...props}
			className={cn(
				"inline-flex items-center gap-3 bg-[#da1e28] text-sm text-white transition-colors hover:bg-[#b81922]",
				btnSize(size),
				className,
			)}
		>
			{children}
		</button>
	);
}

// ---------------------------------------------------------------------------
// Form fields — Carbon fluid inputs: field bg, strong bottom rule, no radius
// ---------------------------------------------------------------------------

export function FieldLabel({
	children,
	htmlFor,
}: {
	children: React.ReactNode;
	htmlFor?: string;
}) {
	return (
		<label
			htmlFor={htmlFor}
			className="mb-2 block text-[var(--cds-text-2)] text-xs"
		>
			{children}
		</label>
	);
}

export function TextField({
	label,
	helper,
	className,
	id: idProp,
	...props
}: React.ComponentPropsWithRef<"input"> & {
	label?: string;
	helper?: string;
}) {
	// ComponentPropsWithRef, not InputHTMLAttributes: React 19 passes `ref`
	// through as an ordinary prop, and callers that drive the caret (the EDMSpro
	// template fields insert a token where you clicked) need it to reach the
	// input. It rides along in ...props.
	// Always associate the label with the input, generating an id if none given.
	const autoId = useId();
	const id = idProp ?? (label ? autoId : undefined);
	return (
		<div className={className}>
			{label && <FieldLabel htmlFor={id}>{label}</FieldLabel>}
			<input
				id={id}
				{...props}
				className="h-10 w-full border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] px-4 text-sm outline-none placeholder:text-[var(--cds-placeholder)] focus:outline-2 focus:-outline-offset-2 focus:outline-[#0f62fe]"
			/>
			{helper && (
				<p className="mt-1.5 text-[var(--cds-helper)] text-xs">{helper}</p>
			)}
		</div>
	);
}

export function TextAreaField({
	label,
	helper,
	className,
	id: idProp,
	...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
	label?: string;
	helper?: string;
}) {
	const autoId = useId();
	const id = idProp ?? (label ? autoId : undefined);
	return (
		<div className={className}>
			{label && <FieldLabel htmlFor={id}>{label}</FieldLabel>}
			<textarea
				id={id}
				{...props}
				className="w-full border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] px-4 py-3 text-sm outline-none placeholder:text-[var(--cds-placeholder)] focus:outline-2 focus:-outline-offset-2 focus:outline-[#0f62fe]"
			/>
			{helper && (
				<p className="mt-1.5 text-[var(--cds-helper)] text-xs">{helper}</p>
			)}
		</div>
	);
}

export function SelectField({
	label,
	options,
	className,
	id: idProp,
	...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
	label?: string;
	// Plain strings (value === label) or value/label pairs.
	options: (string | { value: string; label: string })[];
}) {
	const autoId = useId();
	const id = idProp ?? (label ? autoId : undefined);
	return (
		<div className={className}>
			{label && <FieldLabel htmlFor={id}>{label}</FieldLabel>}
			<div className="relative">
				<select
					id={id}
					{...props}
					className="h-10 w-full appearance-none border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] px-4 pr-10 text-sm outline-none focus:outline-2 focus:-outline-offset-2 focus:outline-[#0f62fe]"
				>
					{options.map((o) => {
						const { value, label: l } =
							typeof o === "string" ? { value: o, label: o } : o;
						return (
							<option key={value} value={value}>
								{l}
							</option>
						);
					})}
				</select>
				<ChevronDownIcon className="pointer-events-none absolute top-3 right-4 size-4 text-[var(--cds-text-2)]" />
			</div>
		</div>
	);
}

export function CheckboxRow({
	label,
	detail,
	checked,
	onChange,
}: {
	label: React.ReactNode;
	detail?: string;
	checked: boolean;
	onChange: (v: boolean) => void;
}) {
	return (
		<label className="group flex w-full cursor-pointer items-start gap-3 py-1.5 text-left">
			<input
				type="checkbox"
				checked={checked}
				onChange={(e) => onChange(e.target.checked)}
				className="sr-only"
			/>
			<span
				className={cn(
					"mt-0.5 flex size-4 shrink-0 items-center justify-center border transition-colors",
					checked
						? "border-[var(--cds-text)] bg-[var(--cds-text)]"
						: "border-[var(--cds-border-strong)] group-hover:border-[var(--cds-text)]",
				)}
			>
				{checked && (
					<CheckIcon className="size-3 text-[var(--cds-bg)]" strokeWidth={3} />
				)}
			</span>
			<span className="min-w-0">
				<span className="block text-sm">{label}</span>
				{detail && (
					<span className="block text-[var(--cds-helper)] text-xs">
						{detail}
					</span>
				)}
			</span>
		</label>
	);
}

export function ToggleRow({
	label,
	detail,
	on,
	onChange,
}: {
	label: string;
	detail?: string;
	on: boolean;
	onChange: (v: boolean) => void;
}) {
	return (
		<div className="flex items-center justify-between gap-6 py-3">
			<div className="min-w-0">
				<p className="text-sm">{label}</p>
				{detail && (
					<p className="mt-0.5 text-[var(--cds-helper)] text-xs">{detail}</p>
				)}
			</div>
			<button
				type="button"
				role="switch"
				aria-checked={on}
				aria-label={label}
				onClick={() => onChange(!on)}
				className={cn(
					"relative h-6 w-12 shrink-0 rounded-full transition-colors",
					on ? "bg-[#24a148]" : "bg-[var(--cds-border-strong)]",
				)}
			>
				<span
					className={cn(
						"absolute top-[3px] size-[18px] rounded-full bg-white transition-[left]",
						on ? "left-[27px]" : "left-[3px]",
					)}
				/>
			</button>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Tabs — Carbon line tabs
// ---------------------------------------------------------------------------

export function LineTabs<T extends string>({
	tabs,
	value,
	onChange,
}: {
	tabs: { id: T; label: string; count?: number }[];
	value: T;
	onChange: (t: T) => void;
}) {
	return (
		<div className="border-[var(--cds-border)] border-b">
			<div className="flex gap-8 overflow-x-auto">
				{tabs.map((t) => {
					const active = t.id === value;
					return (
						<button
							key={t.id}
							type="button"
							onClick={() => onChange(t.id)}
							className={cn(
								"-mb-px shrink-0 border-b-2 px-0.5 pb-2.5 text-[13px] transition-colors",
								active
									? "border-[#0f62fe] font-semibold"
									: "border-transparent text-[var(--cds-text-2)] hover:border-[var(--cds-border-strong)] hover:text-[var(--cds-text)]",
							)}
						>
							{t.label}
							{t.count !== undefined && (
								<span className="ml-1.5 text-[var(--cds-helper)] tabular-nums">
									{t.count}
								</span>
							)}
						</button>
					);
				})}
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Tags — square, status colors per docs/carbon-design-system.md
// ---------------------------------------------------------------------------

export type TagKind =
	| "gray"
	| "blue"
	| "green"
	| "red"
	| "yellow"
	| "purple"
	| "outline";

const TAG_STYLES: Record<TagKind, string> = {
	gray: "bg-[var(--cds-layer)] border border-[var(--cds-border)] text-[var(--cds-text-2)]",
	blue: "bg-[#0f62fe]/15 text-[var(--cds-link)]",
	purple: "bg-[#8a3ffc]/15 text-[var(--cds-purple-text)]",
	green: "bg-[#24a148]/15 text-[var(--cds-success-text)]",
	red: "bg-[#da1e28]/15 text-[var(--cds-danger-text)]",
	yellow: "bg-[#f1c21b]/20 text-[var(--cds-text)]",
	outline: "border border-[var(--cds-border-strong)] text-[var(--cds-text-2)]",
};

export function Tag({
	kind = "gray",
	children,
	className,
}: {
	kind?: TagKind;
	children: React.ReactNode;
	className?: string;
}) {
	return (
		<span
			className={cn(
				"inline-flex h-6 items-center gap-1.5 px-2 text-xs whitespace-nowrap",
				TAG_STYLES[kind],
				className,
			)}
		>
			{children}
		</span>
	);
}

// ---------------------------------------------------------------------------
// Panels + key-value structured lists
// ---------------------------------------------------------------------------

export function Panel({
	title,
	action,
	children,
	className,
}: {
	title: string;
	action?: React.ReactNode;
	children: React.ReactNode;
	className?: string;
}) {
	return (
		<section className={cn("border border-[var(--cds-border)]", className)}>
			<header className="flex items-center justify-between gap-3 border-[var(--cds-border)] border-b px-4 py-2.5">
				<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
					{title}
				</span>
				{action}
			</header>
			{children}
		</section>
	);
}

export function KVList({
	rows,
}: {
	rows: readonly (readonly [string, React.ReactNode])[];
}) {
	return (
		<dl className="divide-y divide-[var(--cds-border)] text-xs">
			{rows.map(([label, value]) => (
				<div
					key={label}
					className="flex items-center justify-between gap-3 px-4 py-2.5"
				>
					<dt className="shrink-0 text-[var(--cds-text-2)]">{label}</dt>
					<dd className="min-w-0 text-right font-medium tabular-nums">
						{value}
					</dd>
				</div>
			))}
		</dl>
	);
}

// ---------------------------------------------------------------------------
// Inline notification — 3px status accent, icon, title + body
// ---------------------------------------------------------------------------

export type NotifKind = "error" | "success" | "warning" | "info";

const NOTIF: Record<
	NotifKind,
	{ icon: LucideIcon; accent: string; iconCls: string }
> = {
	error: {
		icon: XCircleIcon,
		accent: "border-l-[#da1e28]",
		iconCls: "text-[var(--cds-danger-text)]",
	},
	success: {
		icon: CheckCircle2Icon,
		accent: "border-l-[#24a148]",
		iconCls: "text-[var(--cds-success-text)]",
	},
	warning: {
		icon: AlertTriangleIcon,
		accent: "border-l-[#f1c21b]",
		iconCls: "text-[#f1c21b]",
	},
	info: {
		icon: InfoIcon,
		accent: "border-l-[#0f62fe]",
		iconCls: "text-[var(--cds-link)]",
	},
};

export function Notification({
	kind,
	title,
	children,
	action,
	className,
}: {
	kind: NotifKind;
	title: string;
	children?: React.ReactNode;
	action?: React.ReactNode;
	className?: string;
}) {
	const spec = NOTIF[kind];
	const Icon = spec.icon;
	return (
		<div
			className={cn(
				"flex items-start gap-3 border border-[var(--cds-border)] border-l-[3px] bg-[var(--cds-layer)] px-4 py-3",
				spec.accent,
				className,
			)}
		>
			<Icon className={cn("mt-0.5 size-4 shrink-0", spec.iconCls)} />
			<div className="min-w-0 flex-1 text-sm">
				<p className="font-semibold">{title}</p>
				{children && (
					<div className="mt-0.5 text-[var(--cds-text-2)]">{children}</div>
				)}
			</div>
			{action}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Progress indicator — Carbon horizontal steps (onboarding wizard)
// ---------------------------------------------------------------------------

export function ProgressSteps({
	steps,
	current,
}: {
	steps: string[];
	current: number;
}) {
	return (
		<ol className="flex">
			{steps.map((label, i) => {
				const done = i < current;
				const active = i === current;
				return (
					<li
						key={label}
						className={cn(
							"flex-1 border-t-2 pt-3 pr-4",
							done || active
								? "border-[#0f62fe]"
								: "border-[var(--cds-border)]",
						)}
					>
						<p className="flex items-center gap-1.5 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.14em]">
							{done ? (
								<CheckIcon
									className="size-3 text-[var(--cds-link)]"
									strokeWidth={3}
								/>
							) : (
								`0${i + 1}`
							)}
						</p>
						<p
							className={cn(
								"mt-1 text-[13px]",
								active
									? "font-semibold"
									: done
										? ""
										: "text-[var(--cds-text-2)]",
							)}
						>
							{label}
						</p>
					</li>
				);
			})}
		</ol>
	);
}
