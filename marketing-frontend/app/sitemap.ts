import type { MetadataRoute } from "next";
import { fetchArticlesStrict } from "@/lib/api";
import { SITE_URL } from "@/lib/site";

const STATIC_ROUTES = [
	"",
	"/about",
	"/articles",
	"/consulting",
	"/contact",
	"/pricing",
	"/products",
	"/products/corpus",
	"/products/mcp",
	"/products/email",
];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
	// Strict: the sitemap is generated once, at build. If the backend is
	// unreachable then, the swallowing fetch would hand back an empty list and
	// this would ship a sitemap advertising ten pages and no articles — green
	// build, silently de-indexed content. Fail the build instead.
	const articles = await fetchArticlesStrict();
	return [
		...STATIC_ROUTES.map((path) => ({ url: `${SITE_URL}${path}` })),
		...articles.map((a) => ({
			url: `${SITE_URL}/articles/${a.slug}`,
			lastModified: a.published_at || undefined,
		})),
	];
}
