// Server-side client for the backend's public API surface (/api/marketing/* for
// articles and the form relays, /api/browse/sources for the corpus numbers).
// Only ever imported from server code (route handlers, server components) — the
// browser never talks to the backend directly, which keeps the CSP self-only and
// CORS untouched. In prod the backend shares the app origin (app.hudsonlegal.tech
// serves /api/*); in dev set API_ORIGIN=http://localhost:8000.

import { APP_URL } from "@/lib/site";

// `||`, not `??`: the Dockerfile turns each build arg into `ENV API_ORIGIN=$API_ORIGIN`,
// so an arg the platform never passed arrives as "" rather than undefined — and
// `??` accepts "". That yields fetch("/api/marketing/contact"), a relative URL
// Node cannot parse, which every catch below would swallow as "backend down".
export const API_ORIGIN = process.env.API_ORIGIN || APP_URL;

export type ArticleCard = {
	slug: string;
	title: string;
	category: string;
	excerpt: string;
	published_at: string;
	read_minutes: number;
};

export type ArticleDetail = ArticleCard & {
	lede: string;
	body_md: string;
	tags: string[];
	author_name: string;
	author_title: string;
};

// One source in the corpus, as /api/browse/sources reports it (public, auth=None).
export type CorpusSource = {
	slug: string;
	name: string;
	abbreviation: string;
	kind: "statutes" | "caselaw";
	entries: number;
	entry_label: string;
};

export type CorpusStats = {
	// Populated sources only, largest first.
	sources: CorpusSource[];
	// Sum of `entries` across them — the number the site advertises.
	documents: number;
};

// Articles change rarely; five minutes of staleness is invisible and keeps
// the site serving statically even when the backend hiccups.
const REVALIDATE_S = 300;

// The site's factual claims — the corpus size, the source list, the sitemap's
// article URLs — are fetched from the backend at BUILD time and frozen into the
// prerendered HTML. So a backend that is merely unreachable during `next build`
// would otherwise produce a perfectly GREEN build that ships a sitemap with no
// articles and a corpus of zero, and nobody would find out from the build log.
//
// Hence two flavours of every fetch: a swallowing one for pages with an honest
// degraded state at RUNTIME, and a strict one for the build-time surfaces that
// decide which pages exist at all. Strictness is scoped to production so
// `next dev` still runs with no backend.
//
// CRITICAL DISTINCTION, learned the hard way: strict means strict-on-ERROR, not
// strict-on-EMPTY. An unreachable backend is a BUILD failure — the build cannot
// know what it is omitting. An empty article list is a legitimate DATA STATE:
// the site is allowed to launch before the first article is published, and prod
// serves exactly that (`/api/marketing/articles` → 200 `[]`) today. Conflating
// them meant an unrelated content gap turned the marketing deploy red and the
// app could not ship at all. Empty is fine; unreachable is not.
const STRICT = process.env.NODE_ENV === "production";

async function getJson<T>(path: string): Promise<T> {
	const res = await fetch(`${API_ORIGIN}${path}`, {
		next: { revalidate: REVALIDATE_S },
	});
	if (!res.ok) {
		throw new Error(`GET ${API_ORIGIN}${path} → HTTP ${res.status}`);
	}
	return (await res.json()) as T;
}

export async function fetchArticles(): Promise<ArticleCard[]> {
	try {
		return await getJson<ArticleCard[]>("/api/marketing/articles");
	} catch {
		return []; // backend unreachable — pages fall back to their static shell
	}
}

// Use from generateStaticParams and the sitemap ONLY: those two decide which
// pages exist at all, and there is no runtime second chance for either.
//
// Rethrows transport/HTTP failures (a build that cannot reach the backend must
// not silently prerender zero article pages) and returns an empty list as a
// valid result (a backend with nothing published yet is a launchable site, not
// a broken build). Callers must therefore handle [] honestly:
//   - sitemap.ts  → emits the static routes and no article URLs.
//   - [slug]      → prerenders no article pages; the route simply has none.
//   - /articles   → renders its empty state (NOT a link to an article that does
//                   not exist on this backend — that dead-link fallback is what
//                   the old strict-on-empty throw existed to prevent).
export async function fetchArticlesStrict(): Promise<ArticleCard[]> {
	if (!STRICT) return fetchArticles();
	return await getJson<ArticleCard[]>("/api/marketing/articles");
}

export async function fetchArticle(
	slug: string,
): Promise<ArticleDetail | null> {
	try {
		return await getJson<ArticleDetail>(
			`/api/marketing/articles/${encodeURIComponent(slug)}`,
		);
	} catch {
		return null;
	}
}

// The corpus numbers the site advertises. Derived, never typed by hand: a
// hardcoded count is stale the day after it is written, and the last one
// (105,734 / 3 sources) had drifted far enough to *understate* our own lead.
export async function fetchCorpusStats(): Promise<CorpusStats> {
	let raw: CorpusSource[];
	try {
		raw = await getJson<CorpusSource[]>("/api/browse/sources");
	} catch (err) {
		if (STRICT) throw err;
		return { sources: [], documents: 0 }; // dev with no backend — pages show "—"
	}

	// Count only sources that actually hold something. Production carries an
	// EMPTY iowa-acts row (the Acts are ingested on dev only), and advertising a
	// source the site does not serve is precisely the kind of claim this whole
	// function exists to make impossible. The same filter picks Acts up by
	// itself the day they are ingested to prod.
	const sources = raw
		.filter((s) => s.entries > 0)
		.sort((a, b) => b.entries - a.entries);
	const documents = sources.reduce((n, s) => n + s.entries, 0);

	if (STRICT && documents === 0) {
		throw new Error(
			`${API_ORIGIN}/api/browse/sources reported an empty corpus. The home and ` +
				"products pages state the document count as fact; a production build " +
				"cannot honestly claim zero.",
		);
	}
	return { sources, documents };
}

// "Iowa Code" → "Code". The jurisdiction is already stated in the copy around
// these lists; repeating it four times reads as filler.
function shortNames(stats: CorpusStats): string[] {
	return stats.sources.map((s) => s.name.replace(/^Iowa\s+/, ""));
}

// Middot form, for spec rows and stat tiles: "Caselaw · Code · Administrative
// Code · Court Rules".
export function corpusSourceNames(stats: CorpusStats): string {
	return shortNames(stats).join(" · ");
}

// Prose form, for running copy and feature bullets: "Caselaw, Code,
// Administrative Code & Court Rules". Same derived truth as corpusSourceNames —
// a sentence just cannot wear middots. Returns "" when the corpus fetch
// degraded (dev, no backend) so callers can pick their own fallback phrasing
// rather than printing an empty list as if it were a claim.
export function corpusSourceProse(stats: CorpusStats): string {
	const names = shortNames(stats);
	if (names.length === 0) return "";
	if (names.length === 1) return names[0];
	return `${names.slice(0, -1).join(", ")} & ${names[names.length - 1]}`;
}

// Thousands separators for the advertised counts. Renders an em dash rather
// than a zero when the corpus fetch degraded (dev, no backend): "0 documents"
// reads as a claim, "—" reads as what it is.
export function formatCount(n: number): string {
	return n > 0 ? n.toLocaleString("en-US") : "—";
}

// American-style date for article headers/cards ("June 24, 2026").
export function formatArticleDate(iso: string): string {
	if (!iso) return "";
	const [y, m, d] = iso.split("-").map(Number);
	return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
		year: "numeric",
		month: "long",
		day: "numeric",
		timeZone: "UTC",
	});
}
