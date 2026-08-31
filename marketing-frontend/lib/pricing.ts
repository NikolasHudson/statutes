// The plan names and prices, in one place.
//
// Two surfaces state them: /pricing (the full tier tiles, with feature lists
// derived from the live corpus) and the Pricing band on every product page —
// the ibm.com product-page pattern, where a plan summary sits on the product
// page itself and links out to the comparison. Two hand-typed copies of "$49"
// is a drift bug waiting to happen on the one page where money changes hands,
// so the strings live here and both surfaces render them.
//
// Launch pricing per PRICING_STRATEGY.md (2026-07-11): Solo $49/mo ($490/yr),
// Firm $149/mo incl. 3 seats +$39/seat, Enterprise custom. Every paid plan
// starts with a 7-day card-up-front trial — there is no free tier.

import { CONSULTING_HREF, PRICING_HREF } from "@/components/marketing/chrome";
import { APP_URL } from "@/lib/site";

// Self-serve checkout is built but stays dark until Stripe is live. Until
// NEXT_PUBLIC_BILLING_LIVE is set, the trial CTAs fall back to beta signup
// (Solo) and the consult form (Firm) instead of the app's checkout page.
export const BILLING_LIVE = process.env.NEXT_PUBLIC_BILLING_LIVE === "1";

export type PlanKey = "solo" | "firm" | "enterprise";

export type Plan = {
	key: PlanKey;
	name: string;
	/** Headline price, or "Custom". */
	price: string;
	/** "/ month" — omitted for Custom. */
	cadence?: string;
	/** The second line under the price: annual rate, seat rate. */
	subPrice?: string;
	tagline: string;
	badge: string;
	/**
	 * Where this plan's own CTA goes. `disabled` renders /pricing's inert
	 * "Planned" treatment — for a tier that is announced but not yet buyable.
	 */
	cta: { label: string; href: string; disabled?: boolean };
};

export const PLANS: Plan[] = [
	{
		key: "solo",
		name: "Solo",
		price: "$49",
		cadence: "/ month",
		subPrice: "or $490 / year, two months free",
		tagline: "For the individual practitioner who lives in research.",
		badge: "7-day free trial",
		// /start is the app's signup→checkout wizard; ?plan pre-selects the plan.
		cta: BILLING_LIVE
			? { label: "Start 7-day free trial", href: `${APP_URL}/start?plan=solo` }
			: { label: "Get started", href: APP_URL },
	},
	{
		key: "firm",
		name: "Firm",
		price: "$149",
		cadence: "/ month",
		subPrice: "includes 3 seats · $39 / month per added seat",
		tagline: "For firms standardizing how the team does research.",
		badge: "7-day free trial",
		cta: BILLING_LIVE
			? { label: "Start 7-day free trial", href: `${APP_URL}/start?plan=firm` }
			: { label: "Talk to us", href: `${CONSULTING_HREF}#contact` },
	},
	{
		key: "enterprise",
		name: "Enterprise",
		price: "Custom",
		tagline: "Bar associations, county attorneys, legal aid & government.",
		badge: "Custom",
		cta: { label: "Talk to us", href: `${CONSULTING_HREF}#contact` },
	},
];

// The honest footnote for the plan bands while billing is dark. Beta users were
// promised prices would be announced before any charge; these pages are that
// announcement, and they say so rather than implying billing is live.
export const PRICING_NOTE = BILLING_LIVE
	? "Every plan starts with a 7-day free trial: card up front, a reminder before the first charge, cancel any time during the trial."
	: "These are announced launch prices. Billing hasn't started: beta access is open, and current users get clear notice well before anything is charged.";

export const COMPARE_PLANS_HREF = PRICING_HREF;
