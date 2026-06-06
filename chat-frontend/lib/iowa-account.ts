// Typed API helpers for /api/auth/* (profile + password) and
// /api/account/api-keys (list / create / revoke). Same shapes as the
// existing Vite frontend's api.ts — keep them in sync.

import type { AuthUser } from "@/components/auth-gate";
import { csrfHeaders } from "./csrf";

// Methods that mutate state need a CSRF token; safe reads (GET/HEAD) don't.
const UNSAFE = /^(POST|PUT|PATCH|DELETE)$/i;

export type APIKey = {
	id: number;
	name: string;
	prefix: string;
	created_at: string;
	last_used_at: string | null;
};

export type CreatedAPIKey = APIKey & { raw_key: string };

export type PublicConfig = {
	mcp_host: string | null;
	source: "explicit" | "codespaces" | "unset";
};

export class AccountError extends Error {
	constructor(
		public status: number,
		public detail: string,
	) {
		super(detail);
	}
}

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

// ---- profile + password -------------------------------------------------

export const updateProfile = (data: { full_name?: string; email?: string }) =>
	request<AuthUser>("/api/auth/me", {
		method: "PATCH",
		body: JSON.stringify(data),
	});

export const changePassword = (data: {
	current_password: string;
	new_password: string;
}) =>
	request<{ status: string }>("/api/auth/change-password", {
		method: "POST",
		body: JSON.stringify(data),
	});

// ---- API keys -----------------------------------------------------------

export const listKeys = () => request<APIKey[]>("/api/account/api-keys");

// ---- settings (profile + preferences + onboarding) ----------------------

// Mirrors backend apps/api/accounts.py:SettingsOut. The enum-backed fields
// (role/theme/default_search_scope/citation_style) carry the server's choice
// *values*, not display labels — the onboarding UI maps them to labels.
export type UserSettings = {
	first_name: string;
	last_name: string;
	email: string; // read-only here; the login email changes via updateProfile()
	phone: string;
	address_line1: string;
	address_line2: string;
	city: string;
	region: string;
	postal_code: string;
	country: string;
	organization: string;
	role: string;
	bar_number: string;
	primary_jurisdiction: string;
	timezone: string;
	theme: string;
	default_search_scope: string;
	citation_style: string;
	verify_citations: boolean;
	weekly_digest: boolean;
	product_news: boolean;
	onboarding_completed: boolean;
	tos_version: string;
	tos_accepted_at: string | null;
	current_tos_version: string;
};

// Everything the client may PATCH. The server owns email + onboarding/ToS
// state, so those are not patchable here (email → updateProfile; ToS →
// completeOnboarding).
export type UserSettingsPatch = Partial<
	Omit<
		UserSettings,
		| "email"
		| "onboarding_completed"
		| "tos_version"
		| "tos_accepted_at"
		| "current_tos_version"
	>
>;

export const getSettings = () => request<UserSettings>("/api/account/settings");

export const updateSettings = (patch: UserSettingsPatch) =>
	request<UserSettings>("/api/account/settings", {
		method: "PATCH",
		body: JSON.stringify(patch),
	});

// Accept the ToS + mark onboarding done. The server stamps its own current
// version; passing one lets it reject a stale client (400) before recording.
export const completeOnboarding = (tosVersion?: string) =>
	request<UserSettings>("/api/account/onboarding/complete", {
		method: "POST",
		body: JSON.stringify(tosVersion ? { tos_version: tosVersion } : {}),
	});

export const createKey = (name: string) =>
	request<CreatedAPIKey>("/api/account/api-keys", {
		method: "POST",
		body: JSON.stringify({ name }),
	});

export const revokeKey = (id: number) =>
	request<{ status: string; id: number }>(`/api/account/api-keys/${id}`, {
		method: "DELETE",
	});

// ---- public config ------------------------------------------------------

export const fetchPublicConfig = () => request<PublicConfig>("/api/config");

// ---- formatting helpers -------------------------------------------------

export function fmtDateTime(iso: string | null | undefined): string {
	if (!iso) return "—";
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return iso;
	return d.toLocaleString("en-US", {
		year: "numeric",
		month: "short",
		day: "numeric",
		hour: "numeric",
		minute: "2-digit",
	});
}

export function fmtDate(iso: string | null | undefined): string {
	if (!iso) return "—";
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return iso;
	return d.toLocaleDateString("en-US", {
		year: "numeric",
		month: "short",
		day: "numeric",
	});
}
