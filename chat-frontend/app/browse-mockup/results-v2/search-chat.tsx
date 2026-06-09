"use client";

// Floating chat widget for the search-results v2 mockup. Bottom-right launcher
// that opens a right-docked panel running the REAL corpus assistant — the same
// /api/chat pipeline as the full-page Assistant and the per-document DocChat
// (runChatTurnParts), just corpus-wide (sourceSlug=null, no pinned node). This
// is the "wire it into real results" piece: the assistant searches the live
// corpus, so a question about the current query gets grounded answers, not a
// canned support reply. Seeded with the active query so the first ask has
// context.

import {
	AssistantRuntimeProvider,
	type ChatModelAdapter,
	useLocalRuntime,
} from "@assistant-ui/react";
import { MessagesSquareIcon, SparklesIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { Thread } from "@/components/assistant-ui/thread";
import {
	Sheet,
	SheetContent,
	SheetDescription,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";
import { runChatTurnParts } from "@/lib/chat-run";

// Kept to the app default reasoning model (must be in ALLOWED_CHAT_MODELS),
// matching the per-document panel — this is a quick aside, not the full console.
const SEARCH_CHAT_MODEL = "gpt-5-mini";

// Corpus-wide adapter: no source restriction, no pinned node, so the assistant
// can pull cases, statutes, and rules across the whole corpus.
const corpusAdapter: ChatModelAdapter = {
	async *run({ messages, abortSignal }) {
		yield* runChatTurnParts(
			{ model: SEARCH_CHAT_MODEL, sourceSlug: null, nodeId: null },
			messages,
			abortSignal,
		);
	},
};

export function SearchChatWidget({ query }: { query: string }) {
	const [open, setOpen] = useState(false);
	const runtime = useLocalRuntime(useMemo(() => corpusAdapter, []));

	return (
		<>
			{/* Floating launcher — bottom-right, above the chat panel */}
			<button
				type="button"
				onClick={() => setOpen(true)}
				aria-label="Ask the research assistant"
				className="fixed right-5 bottom-5 z-40 flex items-center gap-2 rounded-full bg-primary py-3 pr-4 pl-3.5 font-medium text-primary-foreground text-sm shadow-lg transition hover:brightness-110"
			>
				<MessagesSquareIcon className="size-5" />
				<span className="hidden sm:inline">Ask the assistant</span>
			</button>

			<Sheet open={open} onOpenChange={setOpen}>
				<SheetContent
					side="right"
					className="flex w-full flex-col gap-0 p-0 sm:max-w-xl"
				>
					<SheetHeader className="gap-1 border-b px-4 py-3 pr-12">
						<SheetTitle className="flex items-center gap-2 text-sm">
							<SparklesIcon className="size-4 text-primary" />
							Research assistant
						</SheetTitle>
						<SheetDescription className="truncate text-xs">
							Grounded in the Iowa corpus — ask about{" "}
							<span className="font-medium text-foreground">
								&ldquo;{query}&rdquo;
							</span>{" "}
							or anything else.
						</SheetDescription>
					</SheetHeader>
					<div className="min-h-0 flex-1">
						<AssistantRuntimeProvider runtime={runtime}>
							<Thread composerPlaceholder={`Ask about ${query}…`} />
						</AssistantRuntimeProvider>
					</div>
				</SheetContent>
			</Sheet>
		</>
	);
}
