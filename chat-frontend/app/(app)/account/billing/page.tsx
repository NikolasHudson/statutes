"use client";

// Account · Billing — the org's plan, seats, and the two Stripe doors
// (Checkout for an upgrade, the Billing Portal for everything after).
// Billing always attaches to an Organization, so this page reads
// /api/billing/subscription for the *billing org*, not the user.
//
// Owner/admin can act; a plain member sees the same state read-only. The
// can_manage flag only decides what renders — the server re-checks the role on
// every checkout/portal call.
//
// Arriving from the marketing pricing page with ?plan=solo|firm pre-selects
// that plan and, when the user is allowed to buy it, sends them straight to
// Stripe Checkout.
//
// No dollar amounts live in this file. Prices are Stripe's, shown at checkout.

import { CheckIcon, CreditCardIcon, ExternalLinkIcon } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
	BtnPrimary,
	BtnSecondary,
	Eyebrow,
	KVList,
	Notification,
	Panel,
	Tag,
	TextField,
} from "@/components/carbon/primitives";
import { AccountError, fmtDate } from "@/lib/iowa-account";
import {
	type BillingSubscription,
	getSubscription,
	openBillingPortal,
	type PurchasablePlan,
	startCheckout,
} from "@/lib/iowa-org";
import {
	isPurchasablePlan,
	PLAN_CARDS,
	PLAN_TAGS,
	SUB_STATUS_TAGS,
} from "@/lib/org-display";
import { cn } from "@/lib/utils";

// Default grace window from BILLING_PAST_DUE_GRACE_DAYS. Only used when the
// server sends past_due_since without a computed deadline.
const DEFAULT_GRACE_DAYS = 7;

// A plan is granting access right now (as opposed to canceled/unpaid/none).
const LIVE_STATUSES = new Set(["trial", "active", "past_due"]);

// When a past_due org actually loses access. Prefers a server-computed
// deadline; falls back to the anchor + grace window; null if neither is sent.
function graceDeadline(sub: BillingSubscription): string | null {
	if (sub.grace_ends_at) return sub.grace_ends_at;
	if (!sub.past_due_since) return null;
	const d = new Date(sub.past_due_since);
	if (Number.isNaN(d.getTime())) return null;
	d.setDate(d.getDate() + (sub.grace_days ?? DEFAULT_GRACE_DAYS));
	return d.toISOString();
}

// useSearchParams() must be read inside a Suspense boundary.
export default function BillingPage() {
	return (
		<Suspense
			fallback={
				<Wrap>
					<p className="text-[var(--cds-text-2)] text-sm">Loading billing…</p>
				</Wrap>
			}
		>
			<BillingScreen />
		</Suspense>
	);
}

function Wrap({ children }: { children: React.ReactNode }) {
	return (
		<div className="mx-auto w-full max-w-[1100px] px-5 py-10 sm:px-8">
			{children}
		</div>
	);
}

function BillingScreen() {
	const planParam = useSearchParams().get("plan");
	const preselected = isPurchasablePlan(planParam) ? planParam : null;

	const [sub, setSub] = useState<BillingSubscription | null>(null);
	const [error, setError] = useState<Error | null>(null);
	// Stripe errors (403 not an owner, 503 not configured) surface in a banner
	// without dropping the loaded page.
	const [actionError, setActionError] = useState<string | null>(null);
	const [redirecting, setRedirecting] = useState(false);

	const [plan, setPlan] = useState<PurchasablePlan>(preselected ?? "solo");
	const [seats, setSeats] = useState("");
	// The ?plan= auto-checkout fires at most once per mount, even if the
	// subscription re-loads.
	const autoStarted = useRef(false);

	useEffect(() => {
		getSubscription()
			.then((s) => {
				setSub(s);
				setError(null);
				setSeats(String(Math.max(s.seats_used, s.seats_purchased, 1)));
			})
			.catch((e) => setError(e as Error));
	}, []);

	// Send the browser to a Stripe-hosted page. Leaves `redirecting` set on
	// success — the page is on its way out.
	const toStripe = useCallback(async (open: () => Promise<string>) => {
		setRedirecting(true);
		setActionError(null);
		try {
			window.location.assign(await open());
		} catch (e) {
			setActionError(
				e instanceof AccountError ? e.detail : "Could not reach billing.",
			);
			setRedirecting(false);
		}
	}, []);

	const checkout = useCallback(
		(p: PurchasablePlan, requested?: string) => {
			const n = Number(requested);
			const qty = Number.isFinite(n) && n > 0 ? Math.floor(n) : undefined;
			return toStripe(() => startCheckout(p, p === "firm" ? qty : undefined));
		},
		[toStripe],
	);

	// Landing here from the pricing page: the user already picked a plan, so
	// don't make them pick it again. Skipped when they can't buy (member) or
	// already hold that plan — those cases fall through to the picker below.
	const live = sub !== null && LIVE_STATUSES.has(sub.status);
	const alreadyOnPlan = live && sub?.plan === preselected;
	useEffect(() => {
		if (!sub || !preselected || autoStarted.current) return;
		if (!sub.can_manage || alreadyOnPlan) return;
		autoStarted.current = true;
		void checkout(
			preselected,
			preselected === "firm"
				? String(Math.max(sub.seats_used, sub.seats_purchased, 1))
				: undefined,
		);
	}, [sub, preselected, alreadyOnPlan, checkout]);

	const httpStatus = error instanceof AccountError ? error.status : null;

	if (httpStatus === 401) {
		return (
			<Wrap>
				<Notification kind="error" title="Signed out" className="max-w-xl">
					Sign in again to see your plan.
				</Notification>
			</Wrap>
		);
	}
	if (error && !sub) {
		return (
			<Wrap>
				<Notification
					kind="error"
					title="Couldn't load billing"
					className="max-w-xl"
				>
					{error.message}
				</Notification>
			</Wrap>
		);
	}
	if (!sub) {
		return (
			<Wrap>
				<p className="text-[var(--cds-text-2)] text-sm">Loading billing…</p>
			</Wrap>
		);
	}

	const planTag = PLAN_TAGS[sub.plan] ?? PLAN_TAGS.free;
	const statusTag = SUB_STATUS_TAGS[sub.status] ?? SUB_STATUS_TAGS.none;
	const pastDue = sub.status === "past_due";
	const deadline = pastDue ? graceDeadline(sub) : null;
	// The portal only exists for an org Stripe knows about. A comped plan (no
	// Stripe subscription) has no portal, so don't offer a door that 400s.
	const hasStripeBilling = sub.plan !== "free" && sub.status !== "none";

	const planRows: [string, React.ReactNode][] = [
		["Organization", sub.org.name],
		[
			sub.cancel_at_period_end ? "Access ends" : "Renews",
			sub.current_period_end ? fmtDate(sub.current_period_end) : "—",
		],
		["Seats purchased", sub.seats_purchased || "—"],
		["Seats in use", sub.seats_used],
	];
	if (sub.status === "trial" && sub.trial_end) {
		planRows.splice(2, 0, ["Trial ends", fmtDate(sub.trial_end)]);
	}

	return (
		<Wrap>
			<header>
				<Eyebrow>Account — Billing</Eyebrow>
				<h1 className="mt-4 font-light text-3xl sm:text-4xl">Billing</h1>
				<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
					Your plan, seats, and invoices for{" "}
					<span className="text-[var(--cds-text)]">{sub.org.name}</span>.
					Billing attaches to the organization — everyone in it shares one plan
					and one bill.
				</p>
			</header>

			{pastDue && (
				<Notification
					kind="error"
					title="Payment failed — your plan is past due"
					className="mt-8 border-l-[6px]"
					action={
						sub.can_manage ? (
							<BtnSecondary
								size="md"
								disabled={redirecting}
								onClick={() => void toStripe(openBillingPortal)}
							>
								Update payment method
							</BtnSecondary>
						) : undefined
					}
				>
					{deadline ? (
						<>
							Stripe couldn&rsquo;t charge the card on file. Everyone in{" "}
							{sub.org.name} keeps full access until{" "}
							<span className="font-semibold text-[var(--cds-text)]">
								{fmtDate(deadline)}
							</span>
							, after which the organization drops to the free tier.
						</>
					) : (
						<>
							Stripe couldn&rsquo;t charge the card on file. Access continues
							for a short grace period and then drops to the free tier.
						</>
					)}
					{!sub.can_manage &&
						" Ask an owner or admin to update the payment method."}
				</Notification>
			)}

			{actionError && (
				<Notification
					kind="error"
					title="Couldn't reach billing"
					className="mt-6"
				>
					{actionError}
				</Notification>
			)}

			{redirecting && (
				<Notification
					kind="info"
					title="Taking you to Stripe…"
					className="mt-6"
				>
					Payment is handled by Stripe. We never see your card.
				</Notification>
			)}

			{!sub.can_manage && (
				<Notification kind="info" title="Read only" className="mt-6 max-w-2xl">
					Only an owner or admin of {sub.org.name} can change the plan or open
					the billing portal.
				</Notification>
			)}

			{alreadyOnPlan && (
				<Notification
					kind="info"
					title={`You're already on the ${planTag.label} plan`}
					className="mt-6 max-w-2xl"
				>
					Use the billing portal to change seats, payment method, or cancel.
				</Notification>
			)}

			<div
				className={cn(
					"mt-8 grid gap-6 lg:grid-cols-[3fr_2fr]",
					redirecting && "pointer-events-none opacity-60",
				)}
			>
				<Panel title="Current plan">
					<div className="flex flex-wrap items-center gap-3 border-[var(--cds-border)] border-b px-4 py-4">
						<span className="font-light text-2xl">{planTag.label}</span>
						<Tag kind={statusTag.kind}>{statusTag.label}</Tag>
						{sub.cancel_at_period_end && (
							<Tag kind="yellow">Cancels at period end</Tag>
						)}
					</div>
					<KVList rows={planRows} />
					{sub.can_manage && hasStripeBilling && (
						<div className="border-[var(--cds-border)] border-t p-4">
							<BtnSecondary
								size="md"
								disabled={redirecting}
								onClick={() => void toStripe(openBillingPortal)}
							>
								<CreditCardIcon className="size-4" strokeWidth={1.5} />
								Manage billing
								<ExternalLinkIcon
									className="size-3.5 text-[var(--cds-helper)]"
									strokeWidth={1.5}
								/>
							</BtnSecondary>
							<p className="mt-2 text-[var(--cds-helper)] text-xs">
								Payment method, invoices, receipts, and cancellation live in the
								Stripe billing portal.
							</p>
						</div>
					)}
				</Panel>

				<Panel title="Seats">
					<div className="px-4 py-4">
						<p className="font-light text-2xl tabular-nums">
							{sub.seats_used}
							<span className="text-[var(--cds-helper)] text-base">
								{" "}
								/ {sub.seats_purchased || sub.seats_used} used
							</span>
						</p>
						<p className="mt-2 text-[13px] text-[var(--cds-text-2)] leading-relaxed">
							Every member of {sub.org.name} takes a seat. Adding a member adds
							a seat and changes your bill; removing one frees it.
						</p>
						<Link
							href="/org"
							className="mt-3 inline-flex text-[13px] text-[var(--cds-link)] hover:underline"
						>
							Manage members →
						</Link>
					</div>
				</Panel>
			</div>

			{sub.can_manage && (
				<section className="mt-12">
					<h2 className="font-semibold text-sm uppercase tracking-wide">
						{sub.plan === "free" ? "Choose a plan" : "Change plan"}
					</h2>
					<p className="mt-1 max-w-2xl text-[13px] text-[var(--cds-text-2)]">
						Checkout is handled by Stripe — the current price is shown there
						before you pay. You can change or cancel any time from the billing
						portal.
					</p>
					<div className="mt-6 grid gap-6 md:grid-cols-2">
						{PLAN_CARDS.map((card) => {
							const current = live && sub.plan === card.plan;
							const selected = plan === card.plan;
							return (
								<div
									key={card.plan}
									className={cn(
										"flex flex-col border bg-[var(--cds-layer)] p-5",
										selected
											? "border-[#0f62fe] border-t-[3px]"
											: "border-[var(--cds-border)]",
									)}
								>
									<div className="flex items-center gap-2">
										<h3 className="font-light text-xl">{card.name}</h3>
										{current && <Tag kind="green">Current</Tag>}
									</div>
									<p className="mt-1 text-[13px] text-[var(--cds-text-2)]">
										{card.tagline}
									</p>
									<ul className="mt-4 flex-1">
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

									{card.plan === "firm" && (
										<TextField
											label="Seats"
											type="number"
											min={Math.max(sub.seats_used, 1)}
											step={1}
											value={seats}
											onChange={(e) => {
												setPlan("firm");
												setSeats(e.target.value);
											}}
											helper={`At least ${Math.max(sub.seats_used, 1)} — one per member of ${sub.org.name}.`}
											className="mt-5 w-36"
										/>
									)}

									<div className="mt-5">
										{current ? (
											<BtnSecondary
												size="md"
												disabled={redirecting || !hasStripeBilling}
												onClick={() => void toStripe(openBillingPortal)}
											>
												Manage billing
											</BtnSecondary>
										) : (
											<BtnPrimary
												size="md"
												arrow={false}
												disabled={redirecting}
												onClick={() => {
													setPlan(card.plan);
													void checkout(card.plan, seats);
												}}
											>
												{redirecting && selected
													? "Redirecting…"
													: `Upgrade to ${card.name}`}
											</BtnPrimary>
										)}
									</div>
								</div>
							);
						})}
					</div>
					<p className="mt-6 text-[var(--cds-helper)] text-xs">
						Need something bigger — a custom corpus, SSO, or an enterprise
						agreement?{" "}
						<a
							href="mailto:nick@nickhudson.me"
							className="text-[var(--cds-link)] hover:underline"
						>
							Talk to us
						</a>
						.
					</p>
				</section>
			)}
		</Wrap>
	);
}
