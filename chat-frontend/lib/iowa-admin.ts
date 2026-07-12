// Typed API helpers for the staff-only /api/admin/* endpoints: the usage
// dashboard (/api/admin/usage/*, GETs) and user management
// (/api/admin/users/*, which also PATCHes). Modeled on lib/iowa-account.ts —
// same session-cookie fetch + AccountError shape so callers can branch on
// status (401 signed out or not staff), with the CSRF header attached on
// unsafe methods.

import { csrfHeaders } from "./csrf";
import { AccountError } from "./iowa-account";

const UNSAFE = /^(POST|PUT|PATCH|DELETE)$/i;

export type UsageRange = 7 | 30 | 90;

export type FeatureSpend = {
	feature: string; // "chat" | "verification" | "email" | "query_rewrite" | …
	cost_usd: number;
	total_tokens: number;
};

export type ModelSpend = {
	model: string;
	total_tokens: number;
	cost_usd: number;
};

export type UsageSummary = {
	days: number;
	start: string; // "2026-06-11"
	end: string;
	prompt_tokens: number;
	completion_tokens: number;
	total_tokens: number;
	cost_usd: number;
	prev_cost_usd: number;
	active_users: number;
	registered_users: number;
	turns: number;
	features: FeatureSpend[];
	models: ModelSpend[];
};

export type UsageDay = {
	date: string; // "2026-07-10" — oldest first, zero-filled
	prompt_tokens: number;
	completion_tokens: number;
	cost_usd: number;
};

export type UsageTier = "free" | "solo" | "firm" | "custom";

export type UsageUserStatus = "ok" | "near" | "capped" | "exempt";

export type UsageUser = {
	id: number;
	email: string;
	name: string;
	tier: UsageTier;
	is_staff: boolean;
	turns: number;
	prompt_tokens: number;
	completion_tokens: number;
	cost_usd: number;
	// Month-to-date monthly-budget figures, regardless of the days filter.
	budget_usd: number | null;
	budget_used_pct: number | null;
	status: UsageUserStatus;
	last_active: string | null;
};

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

// Optional exact-match dimension filters accepted by /summary, /daily and
// /users. In /users, budget_usd/budget_used_pct/status stay unfiltered
// month-to-date figures — only tokens/cost/turns reflect the slice.
export type UsageFilter = {
	feature?: string;
	model?: string;
};

// All-time distinct feature slugs / model names, for dropdown options.
export type UsageFilterOptions = {
	features: string[];
	models: string[];
};

function usageQuery(days: UsageRange, filter?: UsageFilter): string {
	const params = new URLSearchParams({ days: String(days) });
	if (filter?.feature) params.set("feature", filter.feature);
	if (filter?.model) params.set("model", filter.model);
	return params.toString();
}

export const getUsageFilters = () =>
	request<UsageFilterOptions>("/api/admin/usage/filters");

export const getUsageSummary = (days: UsageRange, filter?: UsageFilter) =>
	request<UsageSummary>(`/api/admin/usage/summary?${usageQuery(days, filter)}`);

export const getUsageDaily = (days: UsageRange, filter?: UsageFilter) =>
	request<{ days: UsageDay[] }>(
		`/api/admin/usage/daily?${usageQuery(days, filter)}`,
	);

export const getUsageUsers = (days: UsageRange, filter?: UsageFilter) =>
	request<{ users: UsageUser[] }>(
		`/api/admin/usage/users?${usageQuery(days, filter)}`,
	);

// ---------------------------------------------------------------------------
// User management — /api/admin/users/*
// Mirrors backend apps/api/admin_users.py. Writes require CSRF (handled by
// request()) and are guarded server-side: staff only, superuser required for
// staff-flag changes / edits to staff accounts, all mutations audited.
// ---------------------------------------------------------------------------

export type AdminUserStatusFilter = "" | "active" | "deactivated" | "staff";

export type AdminUserRow = {
	id: number;
	email: string;
	name: string;
	tier: UsageTier;
	is_staff: boolean;
	is_superuser: boolean;
	is_active: boolean;
	date_joined: string;
	last_login: string | null;
	onboarding_completed: boolean;
	active_api_keys: number;
	// Month-to-date spend vs. the monthly budget (usage-dashboard semantics).
	month_cost_usd: number;
	budget_usd: number | null;
	budget_used_pct: number | null;
	budget_status: UsageUserStatus;
};

export type AdminUsersResponse = {
	total: number;
	users: AdminUserRow[];
};

export type AdminApiKey = {
	id: number;
	name: string;
	prefix: string;
	created_at: string;
	last_used_at: string | null;
};

export type AdminUserProfile = {
	organization: string;
	role: string;
	bar_number: string;
	primary_jurisdiction: string;
	phone: string;
	city: string;
	region: string;
	timezone: string;
	tos_version: string;
	tos_accepted_at: string | null;
};

export type AdminAuditEvent = {
	id: number;
	event_type: string;
	outcome: "success" | "failure" | "blocked";
	created_at: string;
	source_ip: string | null;
	detail: Record<string, unknown>;
};

// Where the user's tier comes from. `tier` is a derived cache of the billing
// state, so the thing staff actually edit is the COMPED plan: a staff-granted
// subscription on the user's personal org. `source: "stripe"` means a real
// paying customer — their plan is changed in Stripe, and PATCHing it here 409s.
export type AdminPlanSource = "comped" | "stripe" | "none";

export type AdminOrgGrant = {
	org_id: number;
	org_name: string;
	plan: UsageTier;
};

export type AdminUserPlan = {
	comped_plan: UsageTier; // "free" = not comped
	source: AdminPlanSource;
	status: string; // subscription status; "none" when there is no row
	editable: boolean; // false = Stripe owns it
	org_id: number | null;
	org_name: string;
	org_status: string;
	// Orgs OTHER than their personal one that grant them a plan (a firm seat) —
	// why a user can be `firm` with no comp, and why un-comping may not drop them.
	other_grants: AdminOrgGrant[];
};

export type AdminUserDetail = {
	user: AdminUserRow;
	first_name: string;
	last_name: string;
	// Per-user override of the tier's monthly budget; null = tier default.
	monthly_budget_override_usd: number | null;
	plan: AdminUserPlan;
	profile: AdminUserProfile;
	api_keys: AdminApiKey[];
	usage: {
		month_cost_usd: number;
		days30_cost_usd: number;
		days30_tokens: number;
		last_llm_activity: string | null;
	};
	events: AdminAuditEvent[];
	// UI hints only — the server re-checks both on every write.
	can_edit: boolean;
	can_edit_staff_flag: boolean;
};

// All optional; monthly_budget_usd: null clears the per-user override.
// `tier` is NOT patchable — it is derived from billing; comp with comped_plan
// ("free" un-comps). A Stripe-billed plan refuses the change with a 409.
export type AdminUserPatch = {
	comped_plan?: UsageTier;
	monthly_budget_usd?: number | null;
	is_active?: boolean;
	is_staff?: boolean;
};

export const getAdminUsers = (opts: {
	q?: string;
	tier?: string;
	status?: AdminUserStatusFilter;
	limit?: number;
	offset?: number;
}) => {
	const params = new URLSearchParams();
	if (opts.q) params.set("q", opts.q);
	if (opts.tier) params.set("tier", opts.tier);
	if (opts.status) params.set("status", opts.status);
	if (opts.limit) params.set("limit", String(opts.limit));
	if (opts.offset) params.set("offset", String(opts.offset));
	const qs = params.toString();
	return request<AdminUsersResponse>(`/api/admin/users${qs ? `?${qs}` : ""}`);
};

export const getAdminUser = (id: number) =>
	request<AdminUserDetail>(`/api/admin/users/${id}`);

export const patchAdminUser = (id: number, data: AdminUserPatch) =>
	request<AdminUserDetail>(`/api/admin/users/${id}`, {
		method: "PATCH",
		body: JSON.stringify(data),
	});

export const revokeAdminUserKey = (userId: number, keyId: number) =>
	request<{ status: string; id: number }>(
		`/api/admin/users/${userId}/api-keys/${keyId}/revoke`,
		{ method: "POST" },
	);

// ---------------------------------------------------------------------------
// Marketing articles — /api/admin/articles/*
// Mirrors backend apps/api/admin_articles.py. Rows are marketing.Article —
// what the public marketing site serves. source_path non-empty = the row is
// synced from a markdown file in the repo and import_articles will overwrite
// admin edits on its next run.
// ---------------------------------------------------------------------------

export type AdminArticleRow = {
	id: number;
	slug: string;
	title: string;
	category: string;
	published: boolean;
	published_at: string | null; // "2026-06-24"
	read_minutes: number;
	updated_at: string;
	source_path: string;
};

export type AdminArticleDetail = AdminArticleRow & {
	lede: string;
	excerpt: string;
	body_md: string;
	tags: string[];
	author_name: string;
	author_title: string;
};

export type AdminArticleIn = {
	title: string;
	slug?: string; // omit/blank = derived from the title
	category?: string;
	lede?: string;
	excerpt?: string;
	body_md?: string;
	tags?: string[];
	author_name?: string;
	author_title?: string;
	published?: boolean;
	published_at?: string | null;
	read_minutes?: number; // 0 = auto from word count
};

export type AdminArticlePatch = Partial<AdminArticleIn>;

export const getAdminArticles = () =>
	request<AdminArticleRow[]>("/api/admin/articles");

export const getAdminArticle = (id: number) =>
	request<AdminArticleDetail>(`/api/admin/articles/${id}`);

export const createAdminArticle = (data: AdminArticleIn) =>
	request<AdminArticleDetail>("/api/admin/articles", {
		method: "POST",
		body: JSON.stringify(data),
	});

export const patchAdminArticle = (id: number, data: AdminArticlePatch) =>
	request<AdminArticleDetail>(`/api/admin/articles/${id}`, {
		method: "PATCH",
		body: JSON.stringify(data),
	});

export const deleteAdminArticle = (id: number) =>
	request<{ status: string; id: number }>(`/api/admin/articles/${id}`, {
		method: "DELETE",
	});
