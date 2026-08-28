"use client";

// "Ask about this case" — a compact corpus chat pinned to one document,
// rendered inside the case reader's citator rail (and its drawer below
// xl). Same /api/chat/stream brain and the same Carbon turn components as
// the full-page Assistant; the only differences are the document pin
// (node_id), a fixed model, and no thread persistence — a new case starts a
// fresh conversation (mount one per document, keyed by node id).

import { Loader2Icon, SendIcon, SquareIcon } from "lucide-react";
import dynamic from "next/dynamic";
import {
	type Ref,
	useCallback,
	useEffect,
	useImperativeHandle,
	useRef,
	useState,
} from "react";
import type {
	AssistantMessage,
	Step,
	UserMessage,
} from "@/components/carbon/chat-turns";
import {
	citationsMarkdown,
	linkifyCitations,
	streamChat,
	toolLabel,
} from "@/lib/iowa-chat";
import { cn } from "@/lib/utils";

// Kept to the app default for a quick, focused aside (must be in
// ALLOWED_CHAT_MODELS) — mirrors components/doc-chat.tsx.
const DOC_ASK_MODEL = "gpt-5-mini";

// The turn components drag react-markdown/remark (~140 KB) into whichever
// page imports them. Load them on first use so opening a case never pays
// for Ask until a question is actually asked.
const AssistantTurn = dynamic(
	() => import("@/components/carbon/chat-turns").then((m) => m.AssistantTurn),
	{ ssr: false },
);
const UserBubble = dynamic(
	() => import("@/components/carbon/chat-turns").then((m) => m.UserBubble),
	{ ssr: false },
);

export type DocAskMessage = UserMessage | AssistantMessage;

export function useDocAsk(nodeId: number) {
	const [messages, setMessages] = useState<DocAskMessage[]>([]);
	const [busy, setBusy] = useState(false);
	const abortRef = useRef<AbortController | null>(null);
	const messagesRef = useRef(messages);
	messagesRef.current = messages;

	// Abort an in-flight turn when the reader moves to another case.
	useEffect(() => () => abortRef.current?.abort(), []);

	const send = useCallback(
		async (text: string) => {
			const q = text.trim();
			if (!q || busy) return;
			abortRef.current?.abort();
			const controller = new AbortController();
			abortRef.current = controller;
			setBusy(true);

			const history = [
				...messagesRef.current.map((m) => ({ role: m.role, content: m.text })),
				{ role: "user" as const, content: q },
			];
			setMessages((prev) => [
				...prev,
				{ role: "user", text: q },
				{ role: "assistant", text: "", steps: [] },
			]);

			const startedAt = Date.now();
			const steps: Step[] = [];
			let answer = "";
			let failed = false;
			let raf = 0;
			const flush = () => {
				if (raf) {
					cancelAnimationFrame(raf);
					raf = 0;
				}
				setMessages((prev) => [
					...prev.slice(0, -1),
					{
						role: "assistant",
						text: answer,
						steps: steps.map((s) => ({ ...s })),
						elapsedMs: Date.now() - startedAt,
						failed,
					},
				]);
			};
			// Token deltas arrive far faster than frames; a state update per token
			// re-renders the whole reader, so batch them to one flush per frame.
			const scheduleFlush = () => {
				if (!raf) raf = requestAnimationFrame(flush);
			};
			const completeInProgress = () => {
				for (const s of steps)
					if (s.status === "in-progress") s.status = "completed";
			};

			try {
				let synthesisStarted = false;
				for await (const event of streamChat(
					{
						model: DOC_ASK_MODEL,
						messages: history,
						source_slug: null,
						node_id: nodeId,
					},
					controller.signal,
				)) {
					if (controller.signal.aborted) break;
					if (event.type === "tool_start") {
						completeInProgress();
						const { label, description } = toolLabel(
							event.name,
							event.arguments,
						);
						steps.push({ label, description, status: "in-progress" });
					} else if (event.type === "delta") {
						if (!synthesisStarted) {
							synthesisStarted = true;
							completeInProgress();
						}
						answer += event.text;
					} else if (event.type === "verify_start") {
						completeInProgress();
						steps.push({ label: "Verifying citations", status: "in-progress" });
					} else if (event.type === "verify_done") {
						const r = event.report;
						for (const s of steps) {
							if (s.label === "Verifying citations") {
								s.status = r.ok ? "completed" : "failed";
								s.description = `${r.citations_verified} of ${r.citations_total} citations · ${r.quotes_verified} of ${r.quotes_total} quotes verified`;
							}
						}
					} else if (event.type === "done") {
						completeInProgress();
						const footer = citationsMarkdown(event.tool_calls ?? [], answer);
						answer =
							linkifyCitations(
								answer || "(no answer returned)",
								event.tool_calls ?? [],
							) + footer;
					} else if (event.type === "error") {
						for (const s of steps)
							if (s.status === "in-progress") s.status = "failed";
						failed = true;
						answer = answer || `The request failed: ${event.message}`;
					}
					if (event.type === "delta") scheduleFlush();
					else flush();
					if (event.type === "done" || event.type === "error") break;
				}
			} catch (e) {
				if ((e as Error).name !== "AbortError") {
					failed = true;
					answer = answer || `The request failed: ${(e as Error).message}`;
					flush();
				}
			} finally {
				setBusy(false);
			}
		},
		[busy, nodeId],
	);

	const stop = useCallback(() => abortRef.current?.abort(), []);
	return { messages, busy, send, stop };
}

export type DocAskHandle = { focus: () => void };

export function DocAskPanel({
	title,
	citation,
	messages,
	busy,
	onSend,
	onStop,
	handleRef,
	className,
}: {
	title: string;
	citation?: string;
	messages: DocAskMessage[];
	busy: boolean;
	onSend: (text: string) => void;
	onStop: () => void;
	// Lets the reader focus the composer from the toolbar button / "/" key.
	handleRef?: Ref<DocAskHandle>;
	className?: string;
}) {
	const [draft, setDraft] = useState("");
	const taRef = useRef<HTMLTextAreaElement>(null);
	const scrollRef = useRef<HTMLDivElement>(null);

	useImperativeHandle(handleRef, () => ({
		focus: () => taRef.current?.focus(),
	}));

	// Grow with content up to ~5 lines; shrink back after submit.
	// biome-ignore lint/correctness/useExhaustiveDependencies: draft drives the resize
	useEffect(() => {
		const el = taRef.current;
		if (!el) return;
		el.style.height = "auto";
		el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
	}, [draft]);

	// Follow the stream.
	// biome-ignore lint/correctness/useExhaustiveDependencies: messages drive the scroll
	useEffect(() => {
		const el = scrollRef.current;
		if (el) el.scrollTop = el.scrollHeight;
	}, [messages]);

	const canSubmit = !busy && !!draft.trim();
	const submit = () => {
		if (!canSubmit) return;
		const t = draft.trim();
		setDraft("");
		onSend(t);
	};

	const suggestions = [
		`Summarize the holding of ${title}.`,
		"Which later decisions rely on this case, and for what?",
		"What facts were essential to the court's reasoning?",
	];

	return (
		<div className={cn("flex min-h-0 flex-1 flex-col", className)}>
			<div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
				{messages.length === 0 ? (
					<div>
						<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
							Ask about this case
						</p>
						<p className="mt-2 text-[13px] text-[var(--cds-text-2)] leading-relaxed">
							Answers are researched against the opinion text and the corpus,
							then citation-checked before display.
							{citation ? (
								<>
									{" "}
									Pinned to{" "}
									<span className="font-mono text-[var(--cds-text)]">
										{citation}
									</span>
									.
								</>
							) : null}
						</p>
						<div className="mt-4 space-y-px border border-[var(--cds-border)] bg-[var(--cds-border)]">
							{suggestions.map((s) => (
								<button
									key={s}
									type="button"
									onClick={() => onSend(s)}
									className="block w-full bg-[var(--cds-layer)] px-3 py-2.5 text-left text-[13px] transition-colors hover:bg-[var(--cds-layer-hover)]"
								>
									{s}
								</button>
							))}
						</div>
					</div>
				) : (
					<div className="text-[14px] [&_.space-y-4]:text-[14px]">
						{messages.map((m, i) =>
							m.role === "user" ? (
								// biome-ignore lint/suspicious/noArrayIndexKey: append-only message list
								<UserBubble key={i}>{m.text}</UserBubble>
							) : (
								<AssistantTurn
									// biome-ignore lint/suspicious/noArrayIndexKey: append-only message list
									key={i}
									message={m}
									streaming={busy && i === messages.length - 1}
								/>
							),
						)}
					</div>
				)}
			</div>
			<div className="shrink-0 border-[var(--cds-border)] border-t p-3">
				<div className="flex items-end gap-2 border border-[var(--cds-border)] bg-[var(--cds-field)] focus-within:border-[#0f62fe]">
					<textarea
						ref={taRef}
						rows={1}
						value={draft}
						onChange={(e) => setDraft(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === "Enter" && !e.shiftKey) {
								e.preventDefault();
								submit();
							}
						}}
						placeholder={`Ask about ${citation || title}…`}
						aria-label="Ask about this case"
						className="min-h-10 flex-1 resize-none bg-transparent px-3 py-2.5 text-[13px] leading-5 outline-none placeholder:text-[var(--cds-placeholder)]"
					/>
					{busy ? (
						<button
							type="button"
							onClick={onStop}
							aria-label="Stop"
							className="flex size-10 shrink-0 items-center justify-center text-[var(--cds-text-2)] transition-colors hover:bg-[var(--cds-layer-hover)]"
						>
							<SquareIcon className="size-4" />
						</button>
					) : (
						<button
							type="button"
							onClick={submit}
							disabled={!canSubmit}
							aria-label="Send"
							className="flex size-10 shrink-0 items-center justify-center bg-[#0f62fe] text-white transition-colors hover:bg-[#0353e9] disabled:bg-transparent disabled:text-[var(--cds-placeholder)]"
						>
							{busy ? (
								<Loader2Icon className="size-4 animate-spin" />
							) : (
								<SendIcon className="size-4" />
							)}
						</button>
					)}
				</div>
				<p className="mt-2 font-mono text-[10px] text-[var(--cds-helper)]">
					Enter to send · Shift+Enter for a new line
				</p>
			</div>
		</div>
	);
}
