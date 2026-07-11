// Typed API helpers for the staff-only /api/admin/usage/* endpoints that
// power the admin usage dashboard. Modeled on lib/iowa-account.ts — same
// session-cookie fetch + AccountError shape so callers can branch on
// status (401 signed out / 403 not staff). All endpoints are GETs, so no
// CSRF header is needed.

import { AccountError } from "./iowa-account";

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

async function request<T>(path: string): Promise<T> {
	const r = await fetch(path, {
		credentials: "include",
		headers: { "Content-Type": "application/json" },
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
