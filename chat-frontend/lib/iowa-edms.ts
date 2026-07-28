// Typed API helpers for Hudson EDMSpro (/api/edms/*).
//
// Same session-cookie fetch + AccountError shape as lib/iowa-account.ts and
// lib/iowa-org.ts, so callers branch on the HTTP status: 402 = no live plan,
// 403 = the plan doesn't include EDMSpro.
//
// Note what is NOT here: nothing that moves a document. v1 ships without cloud
// saving — the extension writes each filing to the machine it runs on — so this
// module only ever touches settings.

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

// ---- types --------------------------------------------------------------

// The server also returns the cloud-destination fields (and the connection
// object) that the cut OneDrive integration uses; v1 has no surface for them, so
// they are left off here rather than typed and ignored.
export type EdmsSettings = {
	naming_template: string;
	crowdsource_opt_in: boolean;
	crowdsource_opt_in_at: string | null;
	filename_tokens: string[];
};

export type EdmsSettingsPatch = Partial<{
	naming_template: string;
	crowdsource_opt_in: boolean;
}>;

export type SafetyList = {
	blocked: { prefix: string; label: string }[];
	note: string;
};

// ---- settings -----------------------------------------------------------

export const getEdmsSettings = () =>
	request<EdmsSettings>("/api/edms/settings");

export const updateEdmsSettings = (patch: EdmsSettingsPatch) =>
	request<EdmsSettings>("/api/edms/settings", {
		method: "PATCH",
		body: JSON.stringify(patch),
	});

export const getSafetyList = () => request<SafetyList>("/api/edms/safety");

// ---- preview ------------------------------------------------------------

// Sample values for the live template previews. The server is the source of
// truth for rendering (apps/edms/routing.py); this mirrors it for display only,
// which is why the sample is fixed and obviously fake rather than pulled from
// the user's real filings.
const SAMPLE: Record<string, string> = {
	"{case_number}": "CVCV012345",
	"{case_num}": "CVCV012345",
	"{case_type}": "CVCV",
	"{docket_num}": "D0064",
	"{doc_title}": "Motion to Dismiss",
	"{doc_type}": "Motion",
	"{filer}": "Smith",
	"{county}": "Polk",
	"{judge}": "Hon. Reynolds",
	"{year}": "2024",
	"{date}": "2024-03-15",
};

export function previewTemplate(
	template: string,
	kind: "folder" | "file",
): string {
	let out = template || "";
	for (const [token, value] of Object.entries(SAMPLE)) {
		out = out.split(token).join(value);
	}
	out = out.replace(/\/+/g, "/").replace(/^\/|\/$/g, "");
	if (kind === "file") {
		out = out
			.replace(/[_\-\s]{2,}/g, "_")
			.replace(/^[_\-.\s]+|[_\-.\s]+$/g, "");
		if (!out.toLowerCase().endsWith(".pdf")) out += ".pdf";
	}
	return out;
}
