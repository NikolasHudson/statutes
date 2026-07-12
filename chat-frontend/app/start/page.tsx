"use client";

// Self-serve signup wizard — /start?plan=solo|firm
//
// The marketing pricing page lands here. Instead of dropping a brand-new
// visitor on the sign-in gate (confusing: they clicked "Start trial", not
// "Sign in"), this walks them through the whole funnel in order:
//
//   01 Plan     — confirm (or change) the plan they clicked
//   02 Account  — create an account inline, or sign in if they have one
//   03 Checkout — name the firm / pick seats, then off to Stripe Checkout
//
// Public by design (auth-gate.tsx exempts /start): the visitor has no account
// yet. Like /invite it renders OUTSIDE the AuthGate provider and does its own
// /api/auth/me check, so an already-signed-in user skips straight through
// step 02. An org that already holds a live plan is diverted to
// /account/billing instead of being allowed to buy a second subscription.
//
// No dollar amounts live in this file. Prices are Stripe's, shown at checkout.

import { CheckIcon, LockIcon, UserRoundIcon } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import type { AuthUser } from "@/components/auth-gate";
import {
	BtnGhost,
	BtnPrimary,
	BtnSecondary,
	Notification,
	ProgressSteps,
	Tag,
	TextField,
} from "@/components/carbon/primitives";
import { FunnelHero, FunnelPage } from "@/components/funnel-chrome";
import { csrfHeaders } from "@/lib/csrf";
import { AccountError } from "@/lib/iowa-account";
import {
	type BillingSubscription,
	getSubscription,
	type PurchasablePlan,
	renameOrg,
	startCheckout,
} from "@/lib/iowa-org";
import { isPurchasablePlan, PLAN_CARDS } from "@/lib/org-display";
import { clearThreadStores } from "@/lib/thread-store";
import { useCredentialsForm } from "@/lib/use-credentials-form";
import { cn } from "@/lib/utils";

const STEPS = ["Choose your plan", "Create your account", "Checkout"];

// A subscription in one of these states is granting access — the org already
// has a plan and must change it via the billing page, not buy a second one.
const LIVE_STATUSES = new Set(["trial", "active", "past_due"]);

// useSearchParams() must be read inside a Suspense boundary.
export default function StartPage() {
	return (
		<Suspense fallback={null}>
			<StartWizard />
		</Suspense>
	);
}

function StartWizard() {
	const planParam = useSearchParams().get("plan");

	const [step, setStep] = useState(0);
	const [plan, setPlan] = useState<PurchasablePlan>(
		isPurchasablePlan(planParam) ? planParam : "solo",
	);
	// "checking" until /api/auth/me answers; null = signed out.
	const [me, setMe] = useState<AuthUser | null | "checking">("checking");
	const [sub, setSub] = useState<BillingSubscription | null>(null);

	const [firmName, setFirmName] = useState("");
	const [seats, setSeats] = useState("3");
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		fetch("/api/auth/me", { credentials: "include" })
			.then((r) => (r.ok ? (r.json() as Promise<AuthUser>) : null))
			.catch(() => null)
			.then((u) => setMe(u));
	}, []);

	// Once signed in (on arrival or mid-wizard), read the billing state: it
	// floors the seat count at the org's real headcount and catches the
	// "already subscribed" case before Stripe does.
	const signedIn = me !== "checking" && me !== null;
	useEffect(() => {
		if (!signedIn) return;
		getSubscription()
			.then((s) => {
				setSub(s);
				setSeats((prev) => {
					const n = Number(prev);
					const floor = Math.max(s.seats_used, 1);
					return String(Math.max(Number.isFinite(n) ? n : 0, floor, 3));
				});
				if (!s.org.is_personal || s.org.name.trim()) {
					setFirmName((prev) => prev || (s.org.is_personal ? "" : s.org.name));
				}
			})
			.catch(() => setSub(null));
	}, [signedIn]);

	const alreadySubscribed =
		sub !== null && sub.plan !== "free" && LIVE_STATUSES.has(sub.status);

	const onSignedIn = useCallback((u: AuthUser) => {
		setMe(u);
		setStep(2);
	}, []);

	// Signing out from a page outside AuthGate's provider: same two steps
	// AuthGate takes, then a reload so the wizard re-runs its session check.
	const switchAccount = useCallback(async () => {
		await fetch("/api/auth/logout", {
			method: "POST",
			headers: await csrfHeaders(),
			credentials: "include",
		}).catch(() => {});
		clearThreadStores();
		window.location.assign(`/start?plan=${plan}`);
	}, [plan]);

	const checkout = useCallback(async () => {
		setBusy(true);
		setError(null);
		try {
			// A firm needs a name before invitations go out — the invite email
			// leads with it, and "Nick (Personal)" makes a bad letterhead.
			const name = firmName.trim();
			if (plan === "firm" && name && name !== sub?.org.name) {
				await renameOrg(name);
			}
			const n = Number(seats);
			const qty =
				plan === "firm" && Number.isFinite(n) && n > 0
					? Math.floor(n)
					: undefined;
			window.location.assign(await startCheckout(plan, qty));
			// Leave `busy` set — the page is on its way to Stripe.
		} catch (e) {
			setError(
				e instanceof AccountError
					? e.detail
					: "Could not reach billing. Please try again.",
			);
			setBusy(false);
		}
	}, [plan, seats, firmName, sub]);

	const next = () => {
		setError(null);
		// Step 02 exists to get a session; with one already, skip it.
		setStep(step === 0 && signedIn ? 2 : step + 1);
	};
	const back = () => {
		setError(null);
		setStep(step === 2 && signedIn ? 0 : Math.max(0, step - 1));
	};

	return (
		<FunnelPage>
			<FunnelHero
				eyebrow="Hudson Corpus — Get started"
				title="Start your 7-day free trial."
				lede={
					<>
						Full access from the first question. A card is required to start,
						you get a reminder before it&rsquo;s charged, and you can cancel any
						time during the trial.
					</>
				}
			/>
			<main className="flex-1">
				<div className="mx-auto w-full max-w-7xl px-5 py-12 sm:px-8 lg:py-16">
					<div className="w-full max-w-2xl">
						<ProgressSteps steps={STEPS} current={step} />

						{error && (
							<Notification
								kind="error"
								title="Something went wrong"
								className="mt-8"
							>
								{error}
							</Notification>
						)}

						<div className="mt-8">
							{step === 0 && (
								<PlanStep
									plan={plan}
									onSelect={setPlan}
									onNext={next}
									checking={me === "checking"}
								/>
							)}
							{step === 1 && !signedIn && (
								<AccountStep onSignedIn={onSignedIn} onBack={back} />
							)}
							{step === 1 && signedIn && (
								// Only reachable by URL fiddling — a signed-in "next" skips
								// to checkout — but render something sane anyway.
								<SignedInCard
									user={me}
									onNext={next}
									onSwitch={switchAccount}
								/>
							)}
							{step === 2 &&
								(signedIn ? (
									alreadySubscribed && sub ? (
										<AlreadySubscribed sub={sub} />
									) : (
										<CheckoutStep
											plan={plan}
											user={me}
											sub={sub}
											firmName={firmName}
											setFirmName={setFirmName}
											seats={seats}
											setSeats={setSeats}
											busy={busy}
											onCheckout={() => void checkout()}
											onBack={back}
											onSwitch={switchAccount}
										/>
									)
								) : (
									// Session evaporated between steps (another tab signed
									// out). Send them back through the account step.
									<AccountStep onSignedIn={onSignedIn} onBack={back} />
								))}
						</div>
					</div>
				</div>
			</main>
		</FunnelPage>
	);
}

// ---------------------------------------------------------------------------
// 01 — Plan
// ---------------------------------------------------------------------------

function PlanStep({
	plan,
	onSelect,
	onNext,
	checking,
}: {
	plan: PurchasablePlan;
	onSelect: (p: PurchasablePlan) => void;
	onNext: () => void;
	checking: boolean;
}) {
	return (
		<section>
			<div className="grid gap-5 sm:grid-cols-2">
				{PLAN_CARDS.map((card) => {
					const selected = plan === card.plan;
					return (
						<button
							key={card.plan}
							type="button"
							aria-pressed={selected}
							onClick={() => onSelect(card.plan)}
							className={cn(
								"flex flex-col border bg-[var(--cds-layer)] p-5 text-left transition-colors",
								selected
									? "border-[#0f62fe] border-t-[3px]"
									: "border-[var(--cds-border)] hover:border-[var(--cds-text-2)]",
							)}
						>
							<div className="flex w-full items-center justify-between gap-2">
								<h2 className="font-light text-xl">{card.name}</h2>
								{selected && <Tag kind="blue">Selected</Tag>}
							</div>
							<p className="mt-1 text-[13px] text-[var(--cds-text-2)]">
								{card.tagline}
							</p>
							<ul className="mt-4 w-full">
								{card.features.map((f) => (
									<li
										key={f}
										className="flex items-start gap-2 border-[var(--cds-border)] border-t py-2.5 text-[13px]"
									>
										<CheckIcon
											aria-hidden
											className="mt-0.5 size-3.5 shrink-0 text-[var(--cds-helper)]"
											strokeWidth={2}
										/>
										{f}
									</li>
								))}
							</ul>
						</button>
					);
				})}
			</div>
			<p className="mt-4 text-[var(--cds-helper)] text-xs leading-relaxed">
				Both plans start with a 7-day free trial. The price is shown at
				checkout, before you confirm anything.
			</p>
			<div className="mt-8">
				<BtnPrimary size="lg" disabled={checking} onClick={onNext}>
					{checking ? "One moment…" : "Continue"}
				</BtnPrimary>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 02 — Account: inline register (default) or sign-in, same brain as the gate
// ---------------------------------------------------------------------------

function AccountStep({
	onSignedIn,
	onBack,
}: {
	onSignedIn: (u: AuthUser) => void;
	onBack: () => void;
}) {
	const form = useCredentialsForm(onSignedIn, "register");
	const register = form.mode === "register";

	return (
		<section className="max-w-md">
			<h2 className="flex items-center gap-2 font-light text-2xl">
				<UserRoundIcon
					className="size-5 text-[var(--cds-helper)]"
					strokeWidth={1.5}
				/>
				{register ? "Create your account" : "Sign in"}
			</h2>
			<p className="mt-2 text-[14px] text-[var(--cds-text-2)] leading-relaxed">
				{register
					? "Your trial attaches to this account — you'll use it to sign in from anywhere."
					: "Welcome back. Sign in and we'll take you straight to checkout."}
			</p>

			{form.error && (
				<Notification
					kind="error"
					title={register ? "Couldn't create the account" : "Sign-in failed"}
					className="mt-5"
				>
					{form.error}
				</Notification>
			)}

			<form className="mt-6 space-y-5" onSubmit={form.onSubmit}>
				{register && (
					<TextField
						id="start-name"
						label="Full name"
						autoComplete="name"
						value={form.fullName}
						onChange={(e) => form.setFullName(e.target.value)}
						disabled={form.busy}
					/>
				)}
				<TextField
					id="start-email"
					label="Email"
					type="email"
					placeholder="you@firm.com"
					required
					autoComplete={register ? "email" : "username"}
					value={form.email}
					onChange={(e) => form.setEmail(e.target.value)}
					disabled={form.busy}
				/>
				<TextField
					id="start-password"
					label="Password"
					type="password"
					required
					autoComplete={register ? "new-password" : "current-password"}
					helper={register ? "At least 8 characters." : undefined}
					value={form.password}
					onChange={(e) => form.setPassword(e.target.value)}
					disabled={form.busy}
				/>
				<div className="flex flex-wrap gap-3 pt-1">
					<BtnPrimary type="submit" size="lg" disabled={form.busy}>
						{form.busy
							? "Working…"
							: register
								? "Create account & continue"
								: "Sign in & continue"}
					</BtnPrimary>
					<BtnGhost size="lg" type="button" onClick={onBack}>
						Back
					</BtnGhost>
				</div>
			</form>

			{register && (
				<p className="mt-4 text-[var(--cds-helper)] text-xs leading-relaxed">
					By creating an account you agree to the{" "}
					<a
						href="/terms"
						target="_blank"
						rel="noopener"
						className="text-[var(--cds-link)] hover:underline"
					>
						Terms of Service
					</a>
					.
				</p>
			)}

			<div className="mt-8 border-[var(--cds-border)] border-t pt-5">
				<button
					type="button"
					onClick={form.toggleMode}
					className="text-[13px] text-[var(--cds-link)] hover:underline"
				>
					{register
						? "Already have an account? Sign in"
						: "New here? Create an account"}
				</button>
			</div>
		</section>
	);
}

function SignedInCard({
	user,
	onNext,
	onSwitch,
}: {
	user: AuthUser;
	onNext: () => void;
	onSwitch: () => void;
}) {
	return (
		<section className="max-w-md">
			<Notification kind="success" title={`Signed in as ${user.email}`}>
				You&rsquo;re ready for checkout.
			</Notification>
			<div className="mt-6 flex flex-wrap gap-3">
				<BtnPrimary size="lg" onClick={onNext}>
					Continue
				</BtnPrimary>
				<BtnSecondary size="lg" onClick={onSwitch}>
					Use a different account
				</BtnSecondary>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 03 — Checkout: firm details, then the Stripe door
// ---------------------------------------------------------------------------

function CheckoutStep({
	plan,
	user,
	sub,
	firmName,
	setFirmName,
	seats,
	setSeats,
	busy,
	onCheckout,
	onBack,
	onSwitch,
}: {
	plan: PurchasablePlan;
	user: AuthUser;
	sub: BillingSubscription | null;
	firmName: string;
	setFirmName: (v: string) => void;
	seats: string;
	setSeats: (v: string) => void;
	busy: boolean;
	onCheckout: () => void;
	onBack: () => void;
	onSwitch: () => void;
}) {
	const card = PLAN_CARDS.find((c) => c.plan === plan) ?? PLAN_CARDS[0];
	const seatFloor = Math.max(sub?.seats_used ?? 1, 1);

	return (
		<section className="max-w-lg">
			<h2 className="font-light text-2xl">Almost there</h2>
			<p className="mt-2 text-[14px] text-[var(--cds-text-2)] leading-relaxed">
				Review the plan, then finish on Stripe&rsquo;s secure checkout page —
				the price and the trial terms are shown there before you confirm.
			</p>

			<div className="mt-6 border border-[var(--cds-border)] bg-[var(--cds-layer)]">
				<div className="flex flex-wrap items-center gap-3 border-[var(--cds-border)] border-b px-5 py-4">
					<span className="font-light text-xl">{card.name}</span>
					<Tag kind="blue">7-day free trial</Tag>
				</div>
				<div className="space-y-1 px-5 py-4 text-[13px] text-[var(--cds-text-2)]">
					<p>
						Account:{" "}
						<span className="text-[var(--cds-text)]">{user.email}</span>{" "}
						<button
							type="button"
							onClick={onSwitch}
							className="text-[var(--cds-link)] hover:underline"
						>
							(change)
						</button>
					</p>
					<p>
						Trial: 7 days free, then the plan renews monthly. Reminder email
						before your first charge; cancel anytime during the trial.
					</p>
				</div>

				{plan === "firm" && (
					<div className="space-y-5 border-[var(--cds-border)] border-t px-5 py-5">
						<TextField
							id="start-firm-name"
							label="Firm or team name"
							placeholder="e.g. Hudson & Associates"
							helper="Shown on invitations when you add teammates. You can change it later."
							value={firmName}
							onChange={(e) => setFirmName(e.target.value)}
							disabled={busy}
						/>
						<TextField
							id="start-seats"
							label="Seats"
							type="number"
							min={seatFloor}
							step={1}
							value={seats}
							onChange={(e) => setSeats(e.target.value)}
							helper="One per attorney or staff member. Add or remove seats any time — changes are prorated."
							className="w-36"
							disabled={busy}
						/>
					</div>
				)}
			</div>

			<div className="mt-8 flex flex-wrap items-center gap-3">
				<BtnPrimary size="lg" disabled={busy} onClick={onCheckout}>
					{busy ? "Taking you to Stripe…" : "Continue to secure checkout"}
				</BtnPrimary>
				<BtnGhost size="lg" disabled={busy} onClick={onBack}>
					Back
				</BtnGhost>
			</div>
			<p className="mt-4 flex items-center gap-1.5 text-[var(--cds-helper)] text-xs">
				<LockIcon className="size-3.5" strokeWidth={1.5} aria-hidden />
				Payment is handled by Stripe. We never see your card.
			</p>
		</section>
	);
}

function AlreadySubscribed({ sub }: { sub: BillingSubscription }) {
	return (
		<section className="max-w-lg">
			<Notification kind="info" title={`${sub.org.name} already has a plan`}>
				Your organization is already subscribed. Change plans, seats, or payment
				details from the billing page instead of starting a new checkout.
			</Notification>
			<div className="mt-6 flex flex-wrap gap-3">
				<Link href="/account/billing">
					<BtnPrimary size="lg">Go to billing</BtnPrimary>
				</Link>
				<Link href="/">
					<BtnSecondary size="lg">Start researching</BtnSecondary>
				</Link>
			</div>
		</section>
	);
}
