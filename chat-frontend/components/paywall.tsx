"use client";

// Full-screen paywall for a signed-in account with no live plan
// (me.paid_access === false — only possible once BILLING_REQUIRE_PAID is on).
// Rendered by AuthGate in place of the app, except under /account and /org so
// the user can always reach billing and their org console. Display-only: every
// interactive endpoint re-enforces with 402 server-side.

import Link from "next/link";
import { useEffect } from "react";
import type { AuthUser } from "@/components/auth-gate";
import {
	BtnGhost,
	BtnPrimary,
	BtnSecondary,
} from "@/components/carbon/primitives";
import { FunnelHero, FunnelPage } from "@/components/funnel-chrome";

export function PaywallScreen({
	user,
	onUser,
	signOut,
}: {
	user: AuthUser;
	onUser: (u: AuthUser) => void;
	signOut: () => Promise<void>;
}) {
	// Absorb a return from Stripe Checkout: the webhook that grants the plan
	// races the redirect back into the app, and the gate's /me snapshot may
	// predate it. One refetch on mount un-sticks the common case; the buttons
	// below cover the rest.
	useEffect(() => {
		fetch("/api/auth/me", { credentials: "include" })
			.then((r) => (r.ok ? (r.json() as Promise<AuthUser>) : null))
			.then((u) => u && onUser(u))
			.catch(() => {});
	}, [onUser]);

	return (
		<FunnelPage>
			<FunnelHero
				eyebrow="Hudson Corpus — Subscription"
				title="Your plan isn't active."
				lede="Research chat, search, and the citator need an active plan. Start your 7-day free trial to continue — or, if you just subscribed, your access is on its way and will appear in a moment."
			/>
			<main className="flex-1">
				<div className="mx-auto w-full max-w-7xl px-5 py-12 sm:px-8 lg:py-16">
					<div className="max-w-2xl">
						<p className="text-[14px] text-[var(--cds-text-2)] leading-relaxed">
							Signed in as{" "}
							<span className="text-[var(--cds-text)]">{user.email}</span>.
							Reading the law stays free — statute, rule, and case pages are
							public. A plan unlocks the interactive layer.
						</p>
						<div className="mt-8 flex flex-wrap items-center gap-3">
							<Link href="/start">
								<BtnPrimary size="lg">Start your free trial</BtnPrimary>
							</Link>
							<Link href="/account/billing">
								<BtnSecondary size="lg">Manage billing</BtnSecondary>
							</Link>
							<BtnGhost size="lg" onClick={() => void signOut()}>
								Sign out
							</BtnGhost>
						</div>
						<p className="mt-6 max-w-lg text-[var(--cds-helper)] text-xs leading-relaxed">
							Part of a firm? Your access comes from your organization&rsquo;s
							subscription — ask an owner or admin of your org, or check{" "}
							<Link
								href="/org"
								className="text-[var(--cds-link)] hover:underline"
							>
								your organization
							</Link>
							.
						</p>
					</div>
				</div>
			</main>
		</FunnelPage>
	);
}
