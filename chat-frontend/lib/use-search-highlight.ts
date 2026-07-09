// Highlight search terms inside a rendered document via the CSS Custom
// Highlight API (CSS.highlights + ::highlight(search-hit) in globals.css).
// Chosen over wrapping matches in <mark> because it never mutates the DOM —
// React re-renders can't be corrupted by it, and it costs nothing to tear
// down. Browsers without the API (rare by now) simply skip highlighting;
// the reader still works.

import { type RefObject, useEffect, useState } from "react";

// Words that would light up half the page. Terms shorter than 3 chars are
// dropped anyway; this catches the common long ones.
const STOP = new Set([
	"the",
	"and",
	"for",
	"with",
	"that",
	"this",
	"from",
	"was",
	"were",
	"are",
	"has",
	"have",
	"had",
	"not",
	"but",
	"his",
	"her",
	"its",
	"their",
	"who",
	"whether",
	"when",
	"what",
	"does",
	"did",
	"shall",
	"may",
	"must",
	"any",
]);

const MAX_RANGES = 2000;

// Quoted phrases stay whole; remaining words are individual terms.
export function highlightTerms(query: string): string[] {
	const phrases = [...query.matchAll(/"([^"]+)"/g)]
		.map((m) => m[1].trim().toLowerCase())
		.filter(Boolean);
	const rest = query
		.replace(/"[^"]*"/g, " ")
		.toLowerCase()
		.split(/[^\w']+/)
		.filter((t) => t.length >= 3 && !STOP.has(t) && !/^\d+$/.test(t));
	return [...new Set([...phrases, ...rest])];
}

/**
 * Highlights every occurrence of the query's terms inside `container` and
 * scrolls the first occurrence into view (once per query/document). Returns
 * the match count, or null while idle/unsupported.
 */
export function useSearchHighlight(
	container: RefObject<HTMLElement | null>,
	query: string,
	ready: boolean,
): number | null {
	const [matches, setMatches] = useState<number | null>(null);

	useEffect(() => {
		setMatches(null);
		const root = container.current;
		const terms = highlightTerms(query);
		if (!ready || !root || terms.length === 0) return;
		if (typeof CSS === "undefined" || !("highlights" in CSS)) return;

		const ranges: Range[] = [];
		const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
		outer: while (walker.nextNode()) {
			const node = walker.currentNode as Text;
			const text = node.data.toLowerCase();
			for (const term of terms) {
				let at = text.indexOf(term);
				while (at !== -1) {
					const range = new Range();
					range.setStart(node, at);
					range.setEnd(node, at + term.length);
					ranges.push(range);
					if (ranges.length >= MAX_RANGES) break outer;
					at = text.indexOf(term, at + term.length);
				}
			}
		}

		// The ::highlight() rule is injected at runtime: the CSS build pipeline
		// (lightningcss) strips the pseudo-element from the bundled stylesheet,
		// and a raw <style> tag is immune to that. Idempotent by id.
		if (!document.getElementById("search-hit-style")) {
			const style = document.createElement("style");
			style.id = "search-hit-style";
			style.textContent =
				"::highlight(search-hit){background-color:rgba(15,98,254,0.28);}";
			document.head.appendChild(style);
		}

		const registry = (CSS as unknown as { highlights: Map<string, unknown> })
			.highlights;
		if (ranges.length > 0) {
			// Highlight is a runtime global wherever CSS.highlights exists.
			const HL = (globalThis as Record<string, unknown>).Highlight as new (
				...r: Range[]
			) => unknown;
			registry.set("search-hit", new HL(...ranges));
			// Document order = walker order, so ranges[0] is the first hit.
			const el = ranges[0].startContainer.parentElement;
			el?.scrollIntoView({ block: "center" });
		}
		setMatches(ranges.length);
		return () => {
			registry.delete("search-hit");
		};
	}, [container, query, ready]);

	return matches;
}
