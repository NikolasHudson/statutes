// Server-side client for the backend's public /api/marketing/* surface.
// Only ever imported from server code (route handlers, server components) —
// the browser never talks to the backend directly, which keeps the CSP
// self-only and CORS untouched. In prod the backend shares the app origin
// (corpus.nick.law serves /api/*); in dev set API_ORIGIN=http://localhost:8000.

import { APP_URL } from "@/lib/site";

export const API_ORIGIN = process.env.API_ORIGIN ?? APP_URL;

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

// Articles change rarely; five minutes of staleness is invisible and keeps
// the site serving statically even when the backend hiccups.
const REVALIDATE_S = 300;

export async function fetchArticles(): Promise<ArticleCard[]> {
	try {
		const res = await fetch(`${API_ORIGIN}/api/marketing/articles`, {
			next: { revalidate: REVALIDATE_S },
		});
		if (!res.ok) return [];
		return (await res.json()) as ArticleCard[];
	} catch {
		return []; // backend unreachable — pages fall back to their static shell
	}
}

export async function fetchArticle(
	slug: string,
): Promise<ArticleDetail | null> {
	try {
		const res = await fetch(
			`${API_ORIGIN}/api/marketing/articles/${encodeURIComponent(slug)}`,
			{ next: { revalidate: REVALIDATE_S } },
		);
		if (!res.ok) return null;
		return (await res.json()) as ArticleDetail;
	} catch {
		return null;
	}
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
