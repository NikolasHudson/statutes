// Typed API helpers for the org console (/api/org/*) and Stripe billing
// (/api/billing/*), per BILLING_PLAN.md §3–4. Modeled on lib/iowa-admin.ts:
// same session-cookie fetch + AccountError shape, CSRF attached on unsafe
// methods, so callers can branch on the HTTP status (401 signed out, 403 not
// an owner/admin, 503 Stripe not configured).
//
// Billing always attaches to an Organization — every user has at least a
// personal org — so "my subscription" is really "my billing org's
// subscription", and seats are the Stripe quantity.

import { csrfHeaders } from "./csrf";
import { AccountError } from "./iowa-account";

const UNSAFE = /^(POST|PUT|PATCH|DELETE)$/i;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
	const method = init.method ?? "GET";
	const csrf = UNSAFE.test(method) ? await csrfHeaders() : {};
	const r = await fetch(path, {
		credentials: "include",
		...init,
		headers: {
			"Content-Type": "application/json",
			...csrf,
			...(init.headers ?? {}),
		},
	});
	const text = await r.text();
	let body: unknown = null;
	if (text) {
		try {
			body = JSON.parse(text);
		} catch {
			body = text;
		}
	}
	if (!r.ok) {
		const detail =
			(body && typeof body === "object" && "detail" in body
				? String((body as { detail: unknown }).detail)
				: null) ?? r.statusText;
		throw new AccountError(r.status, detail);
	}
	return body as T;
}

// ---------------------------------------------------------------------------
// Shared vocabulary (mirrors apps/tenancy choices)
// ---------------------------------------------------------------------------

export type OrgRole = "owner" | "admin" | "member";

export type OrgStatus =
	| "trial"
	| "active"
	| "past_due"
	| "suspended"
	| "canceled";

export type SubscriptionStatus =
	| "trial"
	| "active"
	| "past_due"
	| "canceled"
	| "unpaid";

export type PlanId = "free" | "solo" | "firm" | "custom";

/** Plans a self-service checkout can buy. `free`/`custom` are not purchasable. */
export type PurchasablePlan = "solo" | "firm";

export const ROLE_OPTIONS: { value: OrgRole; label: string }[] = [
	{ value: "owner", label: "Owner" },
	{ value: "admin", label: "Admin" },
	{ value: "member", label: "Member" },
];

/** Owner/admin may invite, remove, and buy; a plain member is read-only. */
export const canManageOrg = (role: OrgRole | undefined): boolean =>
	role === "owner" || role === "admin";

// ---------------------------------------------------------------------------
// Org console — /api/org
// ---------------------------------------------------------------------------

export type OrgMember = {
	// The *user* id — the path param for /api/org/members/{user_id}.
	id: number;
	email: string;
	full_name: string;
	role: OrgRole;
	joined: string;
};

export type OrgInvitation = {
	id: number;
	email: string;
	role: OrgRole;
	created_at?: string | null;
	expires_at?: string | null;
	invited_by?: string | null;
};

export type OrgConsole = {
	id: number;
	name: string;
	status: OrgStatus;
	is_personal: boolean;
	members: OrgMember[];
	invitations: OrgInvitation[];
	seats_used: number;
	seats_purchased: number;
	my_role: OrgRole;
};

// The plan writes the payload in prose ("pending invitations[]", "seats
// used/purchased") rather than field names, so normalize the two plausible
// spellings once, here, instead of in every component. Seats fall back to the
// member count so a missing field renders a number, never NaN.
type RawOrgConsole = Omit<OrgConsole, "invitations" | "seats_used"> & {
	invitations?: OrgInvitation[];
	pending_invitations?: OrgInvitation[];
	seats_used?: number;
};

function normalizeOrg(raw: RawOrgConsole): OrgConsole {
	const members = raw.members ?? [];
	return {
		...raw,
		members,
		invitations: raw.invitations ?? raw.pending_invitations ?? [],
		seats_used: raw.seats_used ?? members.length,
		seats_purchased: raw.seats_purchased ?? 0,
	};
}

export const getOrg = async (): Promise<OrgConsole> =>
	normalizeOrg(await request<RawOrgConsole>("/api/org"));

export const renameOrg = async (name: string): Promise<OrgConsole> =>
	normalizeOrg(
		await request<RawOrgConsole>("/api/org", {
			method: "PATCH",
			body: JSON.stringify({ name }),
		}),
	);

// Mutations below return whatever the server sends; every caller re-reads
// getOrg() afterwards, so the console can't drift from the server's view of
// seats/roles.

export const inviteMember = (email: string, role: OrgRole) =>
	request<OrgInvitation>("/api/org/invitations", {
		method: "POST",
		body: JSON.stringify({ email, role }),
	});

export const revokeInvitation = (id: number) =>
	request<unknown>(`/api/org/invitations/${id}`, { method: "DELETE" });

export const changeMemberRole = (userId: number, role: OrgRole) =>
	request<unknown>(`/api/org/members/${userId}`, {
		method: "PATCH",
		body: JSON.stringify({ role }),
	});

export const removeMember = (userId: number) =>
	request<unknown>(`/api/org/members/${userId}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Invitations — the preview is the one unauthenticated endpoint in this file
// ---------------------------------------------------------------------------

export type OrgInvitePreview = {
	org_name: string;
	email: string;
	role: OrgRole;
	// Who sent it — an email or display name, if the server has one.
	inviter: string | null;
	// False once accepted, revoked, or expired.
	valid: boolean;
	expires_at: string | null;
};

type RawInvitePreview = Partial<OrgInvitePreview> & {
	org?: { name?: string } | null;
	invited_by?: string | null;
};

export const getInvitePreview = async (
	token: string,
): Promise<OrgInvitePreview> => {
	const raw = await request<RawInvitePreview>(
		`/api/org/invitations/${encodeURIComponent(token)}`,
	);
	return {
		org_name: raw.org_name ?? raw.org?.name ?? "an organization",
		email: raw.email ?? "",
		role: raw.role ?? "member",
		inviter: raw.inviter ?? raw.invited_by ?? null,
		valid: raw.valid ?? true,
		expires_at: raw.expires_at ?? null,
	};
};

export const acceptInvitation = (token: string) =>
	request<unknown>(`/api/org/invitations/${encodeURIComponent(token)}/accept`, {
		method: "POST",
	});

// ---------------------------------------------------------------------------
// Billing — /api/billing
// ---------------------------------------------------------------------------

export type BillingOrgRef = {
	id: number;
	name: string;
	is_personal: boolean;
	status: OrgStatus;
};

export type BillingSubscription = {
	org: BillingOrgRef;
	plan: PlanId;
	// "none" covers an org that has never had a subscription row.
	status: SubscriptionStatus | "none";
	seats_used: number;
	seats_purchased: number;
	current_period_end: string | null;
	cancel_at_period_end: boolean;
	trial_end?: string | null;
	// past_due grace window. The server may send the computed deadline
	// (grace_ends_at) or just the anchor + window; the page renders whichever
	// it gets, and stays silent about the date if it gets neither.
	past_due_since?: string | null;
	grace_ends_at?: string | null;
	grace_days?: number;
	// UI hint only — the server re-checks owner/admin on checkout + portal.
	can_manage: boolean;
};

export const getSubscription = () =>
	request<BillingSubscription>("/api/billing/subscription");

// Checkout/portal both answer with a Stripe-hosted URL the browser must land
// on. Accept the obvious aliases so a field-name mismatch can't strand a user
// mid-upgrade.
type StripeUrl = { url?: string; checkout_url?: string; portal_url?: string };

function stripeUrl(r: StripeUrl): string {
	const url = r.url ?? r.checkout_url ?? r.portal_url;
	if (!url) throw new AccountError(502, "Billing returned no redirect URL.");
	return url;
}

/** Stripe Checkout Session for an upgrade. Owner/admin only (server-enforced). */
export const startCheckout = async (
	plan: PurchasablePlan,
	seats?: number,
): Promise<string> =>
	stripeUrl(
		await request<StripeUrl>("/api/billing/checkout", {
			method: "POST",
			body: JSON.stringify(seats ? { plan, seats } : { plan }),
		}),
	);

/** Stripe Billing Portal session (payment method, invoices, cancellation). */
export const openBillingPortal = async (): Promise<string> =>
	stripeUrl(
		await request<StripeUrl>("/api/billing/portal", { method: "POST" }),
	);
