// Display mapping for the org + billing surfaces (/org, /account/billing,
// /invite/[token]). Lives in lib/ rather than beside a page because the three
// routes sit in different trees and must label plan/status/role identically.
//
// NOTE: no dollar amounts here, ever. Prices live in Stripe (referenced by
// env-configured price IDs) and are shown on the Stripe Checkout page — see
// BILLING_PLAN.md.

import type { TagKind } from "@/components/carbon/primitives";
import type {
	OrgRole,
	OrgStatus,
	PlanId,
	PurchasablePlan,
	SubscriptionStatus,
} from "@/lib/iowa-org";

export const PLAN_TAGS: Record<PlanId, { label: string; kind: TagKind }> = {
	free: { label: "Trial", kind: "gray" },
	solo: { label: "Solo", kind: "blue" },
	firm: { label: "Firm", kind: "purple" },
	custom: { label: "Custom", kind: "gray" },
};

// Subscription status, including the "no subscription row yet" case the
// billing page renders for a brand-new org.
export const SUB_STATUS_TAGS: Record<
	SubscriptionStatus | "none",
	{ label: string; kind: TagKind }
> = {
	none: { label: "No plan", kind: "gray" },
	trial: { label: "Trialing", kind: "blue" },
	active: { label: "Active", kind: "green" },
	past_due: { label: "Past due", kind: "red" },
	canceled: { label: "Canceled", kind: "gray" },
	unpaid: { label: "Unpaid", kind: "red" },
};

export const ORG_STATUS_TAGS: Record<
	OrgStatus,
	{ label: string; kind: TagKind }
> = {
	trial: { label: "Trial", kind: "blue" },
	active: { label: "Active", kind: "green" },
	past_due: { label: "Past due", kind: "red" },
	suspended: { label: "Suspended", kind: "red" },
	canceled: { label: "Canceled", kind: "gray" },
};

export const ROLE_TAGS: Record<OrgRole, { label: string; kind: TagKind }> = {
	owner: { label: "Owner", kind: "purple" },
	admin: { label: "Admin", kind: "blue" },
	member: { label: "Member", kind: "gray" },
};

// What each purchasable plan is *for*. Deliberately price-free: the number the
// user pays is whatever Stripe shows at checkout.
export const PLAN_CARDS: {
	plan: PurchasablePlan;
	name: string;
	tagline: string;
	features: string[];
}[] = [
	{
		plan: "solo",
		name: "Solo",
		tagline: "One practitioner, full corpus.",
		features: [
			"Full corpus — Iowa Code, Court Rules, Admin Code & caselaw",
			"Grounded, cited answers with verification",
			"API keys and MCP access",
			"One seat",
		],
	},
	{
		plan: "firm",
		name: "Firm",
		tagline: "Your whole team on one bill.",
		features: [
			"Everything in Solo",
			"Shared organization with roles",
			"Invite teammates — billed per seat",
			"Seats added or removed any time, prorated",
		],
	},
];

/** A plan the user can buy self-service (free/custom are not purchasable). */
export const isPurchasablePlan = (v: string | null): v is PurchasablePlan =>
	v === "solo" || v === "firm";
