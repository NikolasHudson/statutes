"use client";

import {
	LayersIcon,
	Loader2Icon,
	type LucideIcon,
	ScrollTextIcon,
	ShieldCheckIcon,
} from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useState,
} from "react";
import { CarbonSignIn } from "@/components/carbon/sign-in";
import { PaywallScreen } from "@/components/paywall";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { BRAND_NAME } from "@/lib/brand";
import { csrfHeaders } from "@/lib/csrf";
import { clearThreadStores } from "@/lib/thread-store";
import { useCredentialsForm } from "@/lib/use-credentials-form";

export type AuthUser = {
	id: number;
	email: string;
	full_name: string;
	first_name: string;
	last_name: string;
	tier: string;
	onboarding_completed: boolean;
	// False when billing enforcement is on and the account holds no live plan
	// (see BILLING_REQUIRE_PAID server-side). Optional so a cached pre-field
	// response defaults to allowed; the server 402s regardless.
	paid_access?: boolean;
	// Staff flag from /api/auth/me — gates the Admin nav + /admin routes.
	is_staff?: boolean;
	// Gates the staff-flag controls on /admin/users. Display-only — the
	// server re-checks superuser on every admin write.
	is_superuser?: boolean;
	// Feature strings the plan includes (apps/api/auth.FEATURES_BY_TIER) — the
	// same source the 402/403 gate reads. Lets the nav hide product entries the
	// account has no plan for without a probe request per product. Display-only,
	// and optional so a cached pre-field response simply shows nothing extra.
	features?: string[];
};

// Session-scoped flag so the first-login redirect into the wizard fires once
// per browser session: after it nudges the user to /onboarding, "Skip for now"
// lands them back in the app for the rest of the session (no redirect loop).
// A fresh session re-nudges until onboarding is actually completed. Keyed per
// user id — sessionStorage outlives logout, so a bare key would let user A's
// nudge suppress user B's after an account switch in the same tab.
const onboardingRedirectKey = (userId: number) =>
	`hlt-onboarding-redirected:${userId}`;

// Routes readable without signing in. Pages here must not call useAuth() —
// they render outside the AuthContext provider, and the onboarding nudge
// skips them. /terms has to be public so the Terms of Service can be read
// before account creation / acceptance; /privacy is its redirect alias.
// Exact matches only — look-alikes like /privacy-policy must NOT be exposed.
const PUBLIC_PATHS = ["/terms", "/privacy"];
// Whole subtrees that are public. The marketing-site mockup lives under
// /home-mockup (landing, articles, etc.) and is entirely public. The open
// casebook reader mockup lives under /casebook-mockup and is shown the same
// way — a public, signed-out-readable prototype for iteration, as are the
// Carbon design explorations: the browse Library home (/browse-carbon-mockup)
// and the full app-in-Carbon suite (/app-carbon-mockup).
//
// /invite/<token> is public for a real reason: an org invitation usually lands
// with someone who has no account yet, and they must be able to see who invited
// them (via the unauthenticated preview endpoint) before signing up. The page
// renders outside this provider in every auth state and runs its own
// /api/auth/me check; accepting still requires a session, enforced server-side.
//
// /start is the signup→checkout wizard the marketing pricing page links to.
// Its visitor has no account yet by definition — the wizard creates one on
// step 02 (its own /api/auth/me check, like /invite) and every billing call it
// makes is session-authenticated server-side.
const PUBLIC_PREFIXES = [
	"/home-mockup",
	"/casebook-mockup",
	"/browse-carbon-mockup",
	"/app-carbon-mockup",
	"/invite",
	"/start",
];

function isPublicPath(pathname: string): boolean {
	if (PUBLIC_PATHS.includes(pathname)) return true;
	return PUBLIC_PREFIXES.some(
		(p) => pathname === p || pathname.startsWith(`${p}/`),
	);
}

// Surfaces still on the legacy (shadcn) skin, kept as the fallback app after
// the Carbon swap: the classic assistant + account/onboarding under /classic,
// and the browse/case/verify readers that never moved. They get the legacy
// sign-in screen and the legacy onboarding wizard.
const LEGACY_PREFIXES = ["/classic", "/browse", "/cases", "/verify"];

function isLegacyPath(pathname: string): boolean {
	return LEGACY_PREFIXES.some(
		(p) => pathname === p || pathname.startsWith(`${p}/`),
	);
}

// Routes an unpaid account may still use: billing lives under /account, and
// /org is how a firm member sees whose subscription they're waiting on. The
// public prefixes (incl. /start) never reach the paywall check at all.
const PAYWALL_EXEMPT_PREFIXES = ["/account", "/org"];

function isPaywallExempt(pathname: string): boolean {
	return PAYWALL_EXEMPT_PREFIXES.some(
		(p) => pathname === p || pathname.startsWith(`${p}/`),
	);
}

type AuthContextValue = {
	user: AuthUser;
	signOut: () => Promise<void>;
	// Apply a freshly-fetched user (e.g. after a profile PATCH) to the
	// context so the sidebar avatar / welcome name update without a reload.
	setUser: (u: AuthUser) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** Read the current signed-in user. Safe to call anywhere inside <AuthGate>. */
export function useAuth(): AuthContextValue {
	const ctx = useContext(AuthContext);
	if (!ctx) {
		throw new Error("useAuth() must be used inside <AuthGate>");
	}
	return ctx;
}

export function AuthGate({ children }: { children: ReactNode }) {
	const [status, setStatus] = useState<"checking" | "signed-in" | "signed-out">(
		"checking",
	);
	const [user, setUser] = useState<AuthUser | null>(null);
	const router = useRouter();
	const pathname = usePathname();

	useEffect(() => {
		let cancelled = false;
		fetch("/api/auth/me", { credentials: "include" })
			.then((r) => (r.ok ? r.json() : null))
			.then((u: AuthUser | null) => {
				if (cancelled) return;
				if (u) {
					setUser(u);
					setStatus("signed-in");
				} else {
					setStatus("signed-out");
				}
			})
			.catch(() => !cancelled && setStatus("signed-out"));
		return () => {
			cancelled = true;
		};
	}, []);

	// First-login nudge: route a not-yet-onboarded user into the wizard, once per
	// session (see onboardingRedirectKey) so skipping out isn't a redirect loop.
	// Public pages are exempt — someone reading /terms before accepting them must
	// not be yanked into the wizard (the nudge waits for their next navigation,
	// since landing on a public page doesn't consume the once-per-session key).
	useEffect(() => {
		if (status !== "signed-in" || !user) return;
		// An unpaid account is headed for the paywall, not the onboarding
		// wizard — don't burn the once-per-session nudge on it.
		if (user.paid_access === false) return;
		if (user.onboarding_completed) return;
		if (
			pathname === "/onboarding" ||
			pathname === "/classic/onboarding" ||
			isPublicPath(pathname)
		)
			return;
		const key = onboardingRedirectKey(user.id);
		if (sessionStorage.getItem(key)) return;
		sessionStorage.setItem(key, "1");
		// Each skin keeps its own wizard so the nudge doesn't yank a user on
		// the Carbon app back into the legacy UI (or vice versa).
		router.replace(
			isLegacyPath(pathname) ? "/classic/onboarding" : "/onboarding",
		);
	}, [status, user, pathname, router]);

	const signOut = useCallback(async () => {
		await fetch("/api/auth/logout", {
			method: "POST",
			headers: await csrfHeaders(),
			credentials: "include",
		});
		// Chat threads live only in localStorage, which outlives the session —
		// on a shared machine "signed out" must mean the next person at the
		// keyboard cannot read your research, so wipe them all.
		clearThreadStores();
		setStatus("signed-out");
		setUser(null);
	}, []);

	// Public pages render outside the provider in every auth state, so they
	// load instantly (no "Checking session…" flash) and never bounce to the
	// sign-in screen.
	if (isPublicPath(pathname)) {
		return <>{children}</>;
	}

	if (status === "checking") {
		return (
			<div className="flex h-dvh items-center justify-center text-muted-foreground text-sm">
				Checking session…
			</div>
		);
	}

	if (status === "signed-out") {
		const onSignedIn = (u: AuthUser) => {
			setUser(u);
			setStatus("signed-in");
		};
		// The Carbon sign-in is the default; the legacy surfaces keep the
		// legacy screen. Both render the same useCredentialsForm brain, so
		// auth behavior stays identical.
		if (isLegacyPath(pathname)) {
			return <SignInScreen onSignedIn={onSignedIn} />;
		}
		return <CarbonSignIn onSignedIn={onSignedIn} />;
	}

	// No live plan → paywall instead of the app (except the billing/org
	// surfaces the user needs in order to fix exactly that).
	if (user && user.paid_access === false && !isPaywallExempt(pathname)) {
		return <PaywallScreen user={user} onUser={setUser} signOut={signOut} />;
	}

	return (
		<AuthContext.Provider value={{ user: user!, signOut, setUser }}>
			{children}
		</AuthContext.Provider>
	);
}

// ---------------------------------------------------------------------------
// Sign-in / register screen — split layout mirroring the original Vite app
// ---------------------------------------------------------------------------

type Feature = { icon: LucideIcon; title: string; body: string };

const FEATURES: Feature[] = [
	{
		icon: ShieldCheckIcon,
		title: "Reviewed & grounded",
		body: "Every answer is traced to the currently effective, human-reviewed text.",
	},
	{
		icon: ScrollTextIcon,
		title: "Full citations",
		body: "Citation, effective date, and enacting session law on every provision.",
	},
	{
		icon: LayersIcon,
		title: "Hybrid search",
		body: "FTS + pg_trgm + pgvector embeddings fused with Reciprocal Rank Fusion.",
	},
];

function SignInScreen({ onSignedIn }: { onSignedIn: (u: AuthUser) => void }) {
	// All submit/validation behavior lives in the shared hook (also used by
	// the Carbon v2 sign-in); this component is only the legacy skin.
	const {
		mode,
		toggleMode,
		email,
		setEmail,
		password,
		setPassword,
		fullName,
		setFullName,
		busy,
		error,
		onSubmit,
	} = useCredentialsForm(onSignedIn);

	const title = mode === "register" ? "Create your account" : "Sign in";
	const cta = mode === "register" ? "Create account" : "Sign in";
	const subhead =
		mode === "register"
			? `Get an API key to use ${BRAND_NAME} from Claude Desktop or your own integration.`
			: "Sign in to chat with the Iowa Code and Court Rules.";
	const otherLabel =
		mode === "register"
			? "Already have an account? Sign in"
			: "New here? Create an account";

	return (
		<div className="grid h-dvh w-full grid-cols-1 bg-background text-foreground md:grid-cols-2 lg:grid-cols-[1.05fr_1fr]">
			{/* Left — branded panel */}
			<div
				className="relative hidden flex-col justify-between overflow-hidden px-8 py-8 text-white md:flex md:px-12 md:py-12"
				style={{
					backgroundColor: "#1f3a5f",
					backgroundImage: "url(/login-bg.webp)",
					backgroundSize: "cover",
					backgroundPosition: "center",
				}}
			>
				{/* Gradient scrim so copy stays legible over any photo. */}
				<div
					aria-hidden
					className="pointer-events-none absolute inset-0"
					style={{
						backgroundImage:
							"linear-gradient(135deg, rgba(31,58,95,0.95) 0%, rgba(31,58,95,0.80) 45%, rgba(15,29,48,0.60) 100%)",
					}}
				/>

				<div className="relative">
					<span className="font-semibold text-[11px] tracking-[0.18em] uppercase text-white/70">
						Hudson Legal Tech
					</span>
				</div>

				<div className="relative max-w-md">
					{/* Black banner block, same treatment as the corpus reader. */}
					<div className="mb-6 inline-block bg-black px-5 py-3 text-white">
						<div className="font-bold text-2xl leading-tight tracking-[0.04em] uppercase md:text-3xl">
							Iowa Statutes
							<br />& Court Rules
						</div>
					</div>

					<p className="mb-7 max-w-sm text-base leading-relaxed text-white/90">
						A grounded, citable interface to the Iowa Code and Court Rules —
						built for practitioners who need the effective text, not a guess.
					</p>

					<ul className="space-y-4">
						{FEATURES.map((f) => {
							const Icon = f.icon;
							return (
								<li key={f.title} className="flex items-start gap-3">
									<div className="flex size-9 shrink-0 items-center justify-center rounded-full border border-white/25 bg-white/10">
										<Icon className="size-4 text-white" />
									</div>
									<div>
										<div className="font-semibold text-[15px] text-white">
											{f.title}
										</div>
										<div className="mt-0.5 text-[13px] leading-relaxed text-white/75">
											{f.body}
										</div>
									</div>
								</li>
							);
						})}
					</ul>
				</div>

				<p className="relative text-[12px] text-white/60">
					Sourced from legis.iowa.gov · Not a substitute for the official
					publication.
				</p>
			</div>

			{/* Right — form */}
			<div className="flex items-center justify-center overflow-y-auto px-4 py-10 sm:px-10">
				<div className="w-full max-w-sm">
					<div className="mb-1 font-semibold text-[11px] tracking-[0.18em] uppercase text-muted-foreground md:hidden">
						Hudson Legal Tech
					</div>
					<h1 className="font-bold text-2xl tracking-tight text-foreground">
						{title}
					</h1>
					<p className="mt-1.5 text-muted-foreground text-sm">{subhead}</p>

					{error && (
						<div className="mt-5 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-destructive text-sm">
							{error}
						</div>
					)}

					<form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
						{mode === "register" && (
							<label className="block">
								<span className="font-medium text-sm">
									Full name{" "}
									<span className="text-muted-foreground text-xs">
										(optional)
									</span>
								</span>
								<Input
									value={fullName}
									onChange={(e) => setFullName(e.target.value)}
									disabled={busy}
									autoComplete="name"
									className="mt-1.5"
								/>
							</label>
						)}
						<label className="block">
							<span className="font-medium text-sm">Email</span>
							<Input
								type="email"
								value={email}
								onChange={(e) => setEmail(e.target.value)}
								required
								disabled={busy}
								autoComplete={mode === "register" ? "email" : "username"}
								className="mt-1.5"
							/>
						</label>
						<label className="block">
							<span className="font-medium text-sm">Password</span>
							<Input
								type="password"
								value={password}
								onChange={(e) => setPassword(e.target.value)}
								required
								disabled={busy}
								autoComplete={
									mode === "register" ? "new-password" : "current-password"
								}
								className="mt-1.5"
							/>
							{mode === "register" && (
								<p className="mt-1 text-muted-foreground text-xs">
									At least 8 characters.
								</p>
							)}
						</label>

						<Button
							type="submit"
							disabled={busy}
							size="lg"
							className="mt-2 w-full"
						>
							{busy && <Loader2Icon className="size-4 animate-spin" />}
							{busy ? "Working…" : cta}
						</Button>

						{mode === "register" && (
							<p className="text-center text-muted-foreground text-xs">
								By creating an account you agree to the{" "}
								<a
									href="/terms"
									target="_blank"
									className="text-primary underline underline-offset-2"
									rel="noopener"
								>
									Terms of Service
								</a>
								.
							</p>
						)}

						<button
							type="button"
							onClick={toggleMode}
							className="self-center text-primary text-sm underline-offset-2 hover:underline"
						>
							{otherLabel}
						</button>
					</form>
				</div>
			</div>
		</div>
	);
}
