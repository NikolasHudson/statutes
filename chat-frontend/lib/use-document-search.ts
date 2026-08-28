// Find-in-document for a reader page, wired to the workspace bar's search
// field. The page keeps the highlighter (useSearchHighlight over its
// scrolling article) and hands the bar a handle: the field pushes its
// debounced text in through `setQuery`, reads `matches` back, and walks the
// highlight ranges itself. `seed` is the ?q= a results click-through
// arrives with; clearing strips it from the URL.

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
	type RefObject,
	useCallback,
	useEffect,
	useMemo,
	useState,
} from "react";
import {
	type DocumentSearch,
	useDocumentSearchHandle,
} from "@/components/carbon/workspace-bar";
import { useSearchHighlight } from "@/lib/use-search-highlight";

export function useDocumentSearch(
	container: RefObject<HTMLElement | null>,
	seed: string,
	label: string,
): number | null {
	const router = useRouter();
	const pathname = usePathname();
	const hasUrlQuery = !!useSearchParams().get("q");
	const [query, setQuery] = useState(seed);
	useEffect(() => setQuery(seed), [seed]);
	const matches = useSearchHighlight(container, query, true);

	const clear = useCallback(() => {
		setQuery("");
		if (hasUrlQuery) router.replace(pathname);
	}, [hasUrlQuery, router, pathname]);

	const handle = useMemo<DocumentSearch>(
		() => ({ label, seed, matches, setQuery, clear }),
		[label, seed, matches, clear],
	);
	useDocumentSearchHandle(handle);
	return matches;
}
