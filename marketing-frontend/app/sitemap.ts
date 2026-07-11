import type { MetadataRoute } from "next";
import { fetchArticles } from "@/lib/api";
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
	const articles = await fetchArticles();
	return [
		...STATIC_ROUTES.map((path) => ({ url: `${SITE_URL}${path}` })),
		...articles.map((a) => ({
			url: `${SITE_URL}/articles/${a.slug}`,
			lastModified: a.published_at || undefined,
		})),
	];
}
