import type { MetadataRoute } from "next";

// The app host is deliberately NOT an SEO surface. The marketing apex is the only
// origin we want indexed, so everything here is disallowed — including the pages
// that are readable without an account (/browse, case pages, /terms). Blocking a
// host that serves public content looks like a mistake; it is a decision (2026-07-13),
// taken so the two hosts cannot compete for the same queries.
//
// No sitemap is advertised here for the same reason: the sitemap lives on the
// marketing origin.
export default function robots(): MetadataRoute.Robots {
	return {
		rules: { userAgent: "*", disallow: "/" },
	};
}
