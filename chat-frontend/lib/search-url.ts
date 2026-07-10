// URL <-> search-state adapters, shared by every search surface (the legacy
// /browse page and the Carbon v2 screens) so a search URL means the same
// thing everywhere. The query and filters live in the query string so the
// browser back button restores them and a search is shareable. `from`/`to`
// are the year inputs widened to full ISO bounds.

import type { AdvancedFilters } from "@/components/browse/advanced-search";
import type { SearchFilters } from "@/lib/iowa-browse";

export function buildSearchQuery(
	q: string,
	sf: SearchFilters,
	mode?: string | null,
	sort?: string | null,
): string {
	const p = new URLSearchParams();
	p.set("q", q);
	if (sf.doc_type) p.set("doc_type", sf.doc_type);
	if (sf.court) p.set("court", sf.court);
	if (sf.status) p.set("status", sf.status);
	if (sf.date_from) p.set("from", sf.date_from);
	if (sf.date_to) p.set("to", sf.date_to);
	if (mode) p.set("mode", mode);
	if (sort && sort !== "relevance") p.set("sort", sort);
	return p.toString();
}

// The explicit search-mode override ("tc" | "natural"); null = auto-detect.
export function modeFromParams(sp: URLSearchParams): string | null {
	const m = sp.get("mode");
	return m === "tc" || m === "natural" ? m : null;
}

// The sort order; "relevance" is the default and never appears in the URL.
export function sortFromParams(sp: URLSearchParams): string {
	const s = sp.get("sort");
	return s === "date_desc" || s === "date_asc" ? s : "relevance";
}

export function searchFiltersFromParams(sp: URLSearchParams): SearchFilters {
	return {
		doc_type: sp.get("doc_type"),
		court: sp.get("court"),
		status: sp.get("status"),
		date_from: sp.get("from"),
		date_to: sp.get("to"),
	};
}

// Reconstruct the advanced-search panel inputs from the URL.
export function advancedFromParams(sp: URLSearchParams): AdvancedFilters {
	const dt = sp.get("doc_type");
	return {
		docType:
			dt === "code" ||
			dt === "admin" ||
			dt === "acts" ||
			dt === "rules" ||
			dt === "cases"
				? dt
				: "all",
		court: sp.get("court") ?? "",
		status: sp.get("status") ?? "",
		yearFrom: (sp.get("from") ?? "").slice(0, 4),
		yearTo: (sp.get("to") ?? "").slice(0, 4),
	};
}
