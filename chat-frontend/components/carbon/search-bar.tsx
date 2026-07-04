"use client";

// Carbon fluid search bar — square field + primary submit, shared by the v2
// Library home and results screens. Uncontrolled-ish: local draft state,
// submits the trimmed query upward.

import { ArrowRightIcon, SearchIcon } from "lucide-react";
import { useEffect, useState } from "react";

export function CarbonSearchBar({
	initial = "",
	placeholder = "Search by keyword, citation, or party name…",
	onSearch,
}: {
	initial?: string;
	placeholder?: string;
	onSearch: (q: string) => void;
}) {
	const [draft, setDraft] = useState(initial);
	// Re-sync when the URL-driven query changes (back button, new search).
	useEffect(() => setDraft(initial), [initial]);

	return (
		<form
			className="flex items-stretch"
			onSubmit={(e) => {
				e.preventDefault();
				const q = draft.trim();
				if (q) onSearch(q);
			}}
		>
			<div className="relative flex flex-1 items-center border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] focus-within:outline-2 focus-within:-outline-offset-2 focus-within:outline-[#0f62fe]">
				<SearchIcon className="pointer-events-none absolute left-4 size-4 text-[var(--cds-text-2)]" />
				<input
					value={draft}
					onChange={(e) => setDraft(e.target.value)}
					placeholder={placeholder}
					aria-label="Search the corpus"
					className="h-12 w-full bg-transparent pr-4 pl-11 text-sm outline-none placeholder:text-[var(--cds-placeholder)]"
				/>
			</div>
			<button
				type="submit"
				className="flex h-12 items-center gap-8 bg-[#0f62fe] px-5 text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c]"
			>
				Search
				<ArrowRightIcon className="size-4" />
			</button>
		</form>
	);
}
