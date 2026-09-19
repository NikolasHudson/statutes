// Thin fetch helpers for the /api/resources endpoints. Same-origin in dev via
// the Next.js rewrite to Django on :8000. Shapes mirror the payloads built in
// backend/apps/resources/api.py and datasets/sos_entities/api.py — keep them
// in sync.
//
// Resources are reference data, not law: nothing here is a citation, and
// nothing here goes through the citation verification gate. Every route is
// session-authenticated and paywalled server-side, so a 401 means "signed
// out" and a 402 means "no plan" — the pages render both rather than
// retrying.

export class ResourcesError extends Error {
	constructor(
		public status: number,
		message: string,
	) {
		super(message);
	}
}

async function json<T>(path: string, signal?: AbortSignal): Promise<T> {
	const r = await fetch(path, { credentials: "include", signal });
	if (!r.ok) {
		let detail = `HTTP ${r.status}`;
		try {
			const j = (await r.json()) as { detail?: string };
			if (j?.detail) detail = j.detail;
		} catch {
			/* response wasn't JSON */
		}
		throw new ResourcesError(r.status, detail);
	}
	return (await r.json()) as T;
}

export type ResourceDataset = {
	slug: string;
	title: string;
	description: string;
	// "table" = we hold the rows; "external" = a link-out with no local data.
	kind: "table" | "external";
	source_name: string;
	source_url: string;
	license: string;
	attribution_text: string;
	refresh_cadence: string;
	// Date the source published what we hold, not the date we loaded it.
	as_of: string | null;
	// Active rows, or null for kinds with no table of ours.
	row_count: number | null;
};

export type EntityRow = {
	corp_number: string;
	legal_name: string;
	entity_type: string;
	effective_date: string | null;
	registered_agent: string;
	city: string;
	state: string;
	is_active: boolean;
	deactivated_on: string | null;
};

export type EntitySearchResponse = {
	query: string;
	page: number;
	page_size: number;
	total: number;
	// True when the candidate pool filled: render the total as "1,000+".
	total_capped: boolean;
	as_of: string | null;
	results: EntityRow[];
};

export type EntityAddress = {
	address_1: string;
	address_2: string;
	city: string;
	state: string;
	zip: string;
	country?: string;
	lat: number | null;
	lon: number | null;
};

export type EntityDetail = EntityRow & {
	name_normalized: string;
	registered_agent_address: EntityAddress;
	home_office: string;
	home_office_address: EntityAddress;
	first_seen: string;
	last_seen: string;
	// OTHER active entities sharing this registered agent at the same agent
	// ZIP — the row itself is excluded.
	agent_entity_count: number;
	as_of: string | null;
};

export type EntityTypeCount = { type: string; count: number };

export type EntitySearchParams = {
	q?: string;
	agent?: string;
	city?: string;
	zip?: string;
	type?: string;
	include_inactive?: boolean;
	page?: number;
	page_size?: number;
};

function qs(params: Record<string, string | number | boolean | undefined>) {
	const sp = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) {
		if (v === undefined || v === "" || v === false) continue;
		sp.set(k, String(v));
	}
	return sp.toString();
}

export const listResources = (signal?: AbortSignal) =>
	json<{ datasets: ResourceDataset[] }>("/api/resources", signal);

export const searchEntities = (
	params: EntitySearchParams,
	signal?: AbortSignal,
) =>
	json<EntitySearchResponse>(
		`/api/resources/iowa-business-entities/search?${qs(params)}`,
		signal,
	);

export const getEntity = (corpNumber: string, signal?: AbortSignal) =>
	json<EntityDetail>(
		`/api/resources/iowa-business-entities/entities/${encodeURIComponent(corpNumber)}`,
		signal,
	);

export const agentEntities = (
	name: string,
	zip: string,
	page = 1,
	signal?: AbortSignal,
) =>
	json<EntitySearchResponse>(
		`/api/resources/iowa-business-entities/agents?${qs({ name, zip, page })}`,
		signal,
	);

export const entityTypes = (signal?: AbortSignal) =>
	json<{ types: EntityTypeCount[]; as_of: string | null }>(
		"/api/resources/iowa-business-entities/types",
		signal,
	);

// The Secretary of State's own search, for the "verify before you rely on it"
// link every resources page carries.
export const SOS_OFFICIAL_SEARCH =
	"https://sos.iowa.gov/search/business/search.aspx";

// "2026-09-19" → "Sep 19, 2026". Falls back to the input on bad data so the
// UI never shows "Invalid Date".
export function fmtDate(iso: string | null | undefined): string {
	if (!iso) return "";
	const d = new Date(`${iso}T00:00:00`);
	if (Number.isNaN(d.getTime())) return iso;
	return d.toLocaleDateString("en-US", {
		year: "numeric",
		month: "short",
		day: "numeric",
	});
}
