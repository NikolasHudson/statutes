"use client";

// v2 Assistant — corpus-grounded chat in Carbon, streaming from the real
// /api/chat/stream endpoint via lib/iowa-chat.ts (same brain as the legacy
// assistant: tool progress labels, inline citation links, Sources footer).
// Adds what the mockup promised: thread rail (localStorage), scope + model
// controls, live retrieval progress, and a real "Verifying citations" step
// fed by the backend's deterministic verification gate. The Verify Document
// tool (docling uploads) stays on the legacy "/" assistant for now.

import {
	CheckIcon,
	Loader2Icon,
	PlusIcon,
	SendIcon,
	SquareIcon,
	XIcon,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
	NavGroupLabel,
	Notification,
	SelectField,
} from "@/components/carbon/primitives";
import {
	type BrowseSource,
	CHAT_MODELS,
	citationsMarkdown,
	fetchSources,
	linkifyCitations,
	streamChat,
	toolLabel,
} from "@/lib/iowa-chat";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Thread model — persisted to localStorage so chats survive a reload.
// ---------------------------------------------------------------------------

type Step = {
	label: string;
	description?: string;
	status: "in-progress" | "completed" | "failed";
};

type ChatMessage =
	| { role: "user"; text: string }
	| {
			role: "assistant";
			text: string;
			steps: Step[];
			elapsedMs?: number;
			failed?: boolean;
	  };

type ThreadData = {
	id: string;
	title: string;
	updatedAt: number;
	messages: ChatMessage[];
};

const STORE_KEY = "hlt-v2-threads";

function loadThreads(): ThreadData[] {
	try {
		const raw = localStorage.getItem(STORE_KEY);
		if (!raw) return [];
		const parsed = JSON.parse(raw) as ThreadData[];
		return Array.isArray(parsed) ? parsed : [];
	} catch {
		return [];
	}
}

function saveThreads(threads: ThreadData[]) {
	try {
		// Cap storage: most recent 50 threads.
		localStorage.setItem(STORE_KEY, JSON.stringify(threads.slice(0, 50)));
	} catch {
		/* storage full/unavailable — chat still works, just unsaved */
	}
}

const newThread = (): ThreadData => ({
	id: `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
	title: "New chat",
	updatedAt: Date.now(),
	messages: [],
});

const SCOPE_ALL = "all";

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function V2AssistantPage() {
	const [threads, setThreads] = useState<ThreadData[] | null>(null);
	const [activeId, setActiveId] = useState<string | null>(null);
	const [model, setModel] = useState<string>(CHAT_MODELS[0].id);
	const [scope, setScope] = useState<string>(SCOPE_ALL);
	const [sources, setSources] = useState<BrowseSource[]>([]);
	const [busy, setBusy] = useState(false);
	const abortRef = useRef<AbortController | null>(null);
	const scrollRef = useRef<HTMLDivElement>(null);

	// Hydrate threads from localStorage on the client only.
	useEffect(() => {
		const loaded = loadThreads();
		const first = loaded[0] ?? newThread();
		setThreads(loaded.length ? loaded : [first]);
		setActiveId(first.id);
	}, []);

	useEffect(() => {
		fetchSources().then(setSources);
		return () => abortRef.current?.abort();
	}, []);

	const active = threads?.find((t) => t.id === activeId) ?? null;

	// All thread mutations flow through here so persistence can't be missed.
	const mutate = useCallback((fn: (prev: ThreadData[]) => ThreadData[]) => {
		setThreads((prev) => {
			const next = fn(prev ?? []);
			saveThreads(next);
			return next;
		});
	}, []);

	const patchThread = useCallback(
		(id: string, fn: (t: ThreadData) => ThreadData) =>
			mutate((prev) => prev.map((t) => (t.id === id ? fn(t) : t))),
		[mutate],
	);

	const scrollToEnd = () => {
		const el = scrollRef.current;
		if (el) el.scrollTop = el.scrollHeight;
	};

	const send = useCallback(
		async (text: string) => {
			if (!active || busy) return;
			const threadId = active.id;
			abortRef.current?.abort();
			const controller = new AbortController();
			abortRef.current = controller;
			setBusy(true);

			// Seed the turn: user message + empty assistant message to stream into.
			const history = [...active.messages, { role: "user" as const, text }];
			patchThread(threadId, (t) => ({
				...t,
				title: t.messages.length === 0 ? text.slice(0, 60) : t.title,
				updatedAt: Date.now(),
				messages: [...history, { role: "assistant", text: "", steps: [] }],
			}));

			const startedAt = Date.now();
			const steps: Step[] = [];
			let answer = "";
			let failed = false;

			const flush = () => {
				patchThread(threadId, (t) => ({
					...t,
					updatedAt: Date.now(),
					messages: [
						...t.messages.slice(0, -1),
						{
							role: "assistant",
							text: answer,
							steps: steps.map((s) => ({ ...s })),
							elapsedMs: Date.now() - startedAt,
							failed,
						},
					],
				}));
				requestAnimationFrame(scrollToEnd);
			};

			const completeInProgress = () => {
				for (const s of steps)
					if (s.status === "in-progress") s.status = "completed";
			};

			try {
				let synthesisStarted = false;
				for await (const event of streamChat(
					{
						model,
						messages: history.map((m) => ({ role: m.role, content: m.text })),
						source_slug: scope === SCOPE_ALL ? null : scope,
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
						steps.push({
							label: "Verifying citations",
							status: "in-progress",
						});
					} else if (event.type === "verify_done") {
						const r = event.report;
						for (const s of steps) {
							if (s.label === "Verifying citations") {
								s.status = r.ok ? "completed" : "failed";
								s.description = `${r.citations_verified} of ${r.citations_total} citations · ${r.quotes_verified} of ${r.quotes_total} quotes verified`;
							}
						}
					} else if (event.type === "done") {
						for (const s of steps)
							if (s.status === "in-progress") s.status = "completed";
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
					flush();
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
		[active, busy, model, scope, patchThread],
	);

	const stop = () => abortRef.current?.abort();

	if (!threads || !active) {
		return (
			<p className="px-5 py-10 text-[var(--cds-text-2)] text-sm sm:px-8">
				Loading…
			</p>
		);
	}

	const activeSourceName =
		sources.find((s) => s.slug === scope)?.name ?? "All sources";

	return (
		<div className="flex h-full min-h-0">
			<ThreadRail
				threads={threads}
				activeId={active.id}
				disabled={busy}
				onNew={() => {
					const t = newThread();
					mutate((prev) => [t, ...prev]);
					setActiveId(t.id);
				}}
				onPick={setActiveId}
				onDelete={(id) => {
					mutate((prev) => {
						const next = prev.filter((t) => t.id !== id);
						return next.length ? next : [newThread()];
					});
					if (id === active.id) setActiveId(null);
				}}
			/>

			<div className="flex min-w-0 flex-1 flex-col">
				{/* Header — scope + model */}
				<header className="flex h-14 shrink-0 items-center gap-3 border-[var(--cds-border)] border-b px-5 sm:px-8">
					<p className="min-w-0 truncate text-sm">
						<span className="text-[var(--cds-text-2)]">Iowa Legal Corpus</span>
						<span className="mx-2 text-[var(--cds-helper)]">/</span>
						<span className="font-semibold">{activeSourceName}</span>
					</p>
					<div className="ml-auto flex items-center gap-2">
						<SelectField
							aria-label="Search scope"
							options={[
								{ value: SCOPE_ALL, label: "All sources" },
								...sources.map((s) => ({ value: s.slug, label: s.name })),
							]}
							value={scope}
							onChange={(e) => setScope(e.target.value)}
							className="w-44"
						/>
						<SelectField
							aria-label="Model"
							options={CHAT_MODELS.map((m) => ({
								value: m.id,
								label: m.name,
							}))}
							value={model}
							onChange={(e) => setModel(e.target.value)}
							className="w-36"
						/>
					</div>
				</header>

				{/* Thread */}
				<div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
					<div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
						{active.messages.length === 0 ? (
							<EmptyState onAsk={send} />
						) : (
							active.messages.map((m, i) =>
								m.role === "user" ? (
									// biome-ignore lint/suspicious/noArrayIndexKey: append-only message list
									<UserBubble key={i}>{m.text}</UserBubble>
								) : (
									<AssistantTurn
										// biome-ignore lint/suspicious/noArrayIndexKey: append-only message list
										key={i}
										message={m}
										streaming={busy && i === active.messages.length - 1}
									/>
								),
							)
						)}
					</div>
				</div>

				<Composer busy={busy} onSend={send} onStop={stop} />
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Thread rail
// ---------------------------------------------------------------------------

function ThreadRail({
	threads,
	activeId,
	disabled,
	onNew,
	onPick,
	onDelete,
}: {
	threads: ThreadData[];
	activeId: string;
	disabled: boolean;
	onNew: () => void;
	onPick: (id: string) => void;
	onDelete: (id: string) => void;
}) {
	const dayMs = 24 * 60 * 60 * 1000;
	const today = threads.filter((t) => Date.now() - t.updatedAt < dayMs);
	const earlier = threads.filter((t) => Date.now() - t.updatedAt >= dayMs);

	const group = (label: string, items: ThreadData[]) =>
		items.length > 0 && (
			<div key={label}>
				<NavGroupLabel>{label}</NavGroupLabel>
				{items.map((t) => (
					<div
						key={t.id}
						className={cn(
							"group flex w-full items-center border-l-[3px] transition-colors",
							t.id === activeId
								? "border-[#0f62fe] bg-[var(--cds-layer-selected)]"
								: "border-transparent hover:bg-[var(--cds-layer-hover)]",
						)}
					>
						<button
							type="button"
							disabled={disabled}
							onClick={() => onPick(t.id)}
							className={cn(
								"min-w-0 flex-1 truncate px-3.5 py-2 text-left text-sm",
								t.id === activeId
									? "font-semibold"
									: "text-[var(--cds-text-2)]",
							)}
						>
							{t.title}
						</button>
						<button
							type="button"
							aria-label={`Delete chat "${t.title}"`}
							onClick={() => onDelete(t.id)}
							className="mr-1 hidden size-7 shrink-0 items-center justify-center text-[var(--cds-helper)] hover:text-[var(--cds-danger-text)] group-hover:flex"
						>
							<XIcon className="size-3.5" />
						</button>
					</div>
				))}
			</div>
		);

	return (
		<aside className="hidden w-64 shrink-0 flex-col border-[var(--cds-border)] border-r xl:flex">
			<div className="p-4">
				<button
					type="button"
					onClick={onNew}
					className="flex h-10 w-full items-center justify-between gap-3 bg-[#0f62fe] px-4 text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c]"
				>
					New chat
					<PlusIcon className="size-4" />
				</button>
			</div>
			<div className="min-h-0 flex-1 overflow-y-auto pb-4">
				{group("Today", today)}
				{group("Earlier", earlier)}
			</div>
		</aside>
	);
}

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

function UserBubble({ children }: { children: React.ReactNode }) {
	return (
		<div className="mt-8 flex justify-end first:mt-0">
			<div className="max-w-[85%] whitespace-pre-wrap border border-[var(--cds-border)] bg-[var(--cds-layer)] px-4 py-3 text-sm leading-relaxed">
				{children}
			</div>
		</div>
	);
}

function ProgressCard({
	steps,
	elapsedMs,
	running,
}: {
	steps: Step[];
	elapsedMs?: number;
	running: boolean;
}) {
	if (steps.length === 0) return null;
	return (
		<div className="mt-6 border border-[var(--cds-border)]">
			<header className="flex items-center justify-between border-[var(--cds-border)] border-b px-4 py-2.5">
				<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
					Research run
				</span>
				<span className="font-mono text-[11px] text-[var(--cds-helper)] tabular-nums">
					{elapsedMs !== undefined ? `${(elapsedMs / 1000).toFixed(1)} s` : ""}
				</span>
			</header>
			<ol className="divide-y divide-[var(--cds-border)]">
				{steps.map((s, i) => (
					// biome-ignore lint/suspicious/noArrayIndexKey: append-only step list
					<li key={i} className="flex items-center gap-3 px-4 py-2.5">
						{s.status === "in-progress" && running ? (
							<Loader2Icon className="size-4 shrink-0 animate-spin text-[var(--cds-link)]" />
						) : s.status === "failed" ? (
							<XIcon
								className="size-4 shrink-0 text-[var(--cds-danger-text)]"
								strokeWidth={2.5}
							/>
						) : (
							<CheckIcon
								className="size-4 shrink-0 text-[var(--cds-success-text)]"
								strokeWidth={2.5}
							/>
						)}
						<span className="text-sm">{s.label}</span>
						{s.description && (
							<span className="ml-auto truncate font-mono text-[11px] text-[var(--cds-helper)]">
								{s.description}
							</span>
						)}
					</li>
				))}
			</ol>
		</div>
	);
}

// Markdown with Carbon styling. Case links produced by the shared chat lib
// point at the legacy reader (/cases/<id>); rewrite them into the v2 reader.
const rewriteHref = (href: string) =>
	href.startsWith("/cases/") ? href.replace("/cases/", "/v2/case/") : href;

function Answer({ text }: { text: string }) {
	return (
		<div className="space-y-4 text-[15px] leading-relaxed [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5">
			<ReactMarkdown
				remarkPlugins={[remarkGfm]}
				components={{
					a: ({ href, children }) => (
						<Link
							href={rewriteHref(href ?? "#")}
							className="text-[var(--cds-link)] hover:underline"
						>
							{children}
						</Link>
					),
					p: ({ children }) => <p className="mt-4 first:mt-0">{children}</p>,
					hr: () => <hr className="mt-6 border-[var(--cds-border)] border-t" />,
					blockquote: ({ children }) => (
						<blockquote className="mt-4 border-[var(--cds-border-strong)] border-l-2 pl-5 italic">
							{children}
						</blockquote>
					),
					code: ({ children }) => (
						<code className="bg-[var(--cds-layer)] px-1 py-0.5 font-mono text-[0.85em]">
							{children}
						</code>
					),
					h1: ({ children }) => (
						<p className="mt-6 font-semibold text-base">{children}</p>
					),
					h2: ({ children }) => (
						<p className="mt-6 font-semibold text-base">{children}</p>
					),
					h3: ({ children }) => (
						<p className="mt-5 font-semibold text-[15px]">{children}</p>
					),
				}}
			>
				{text}
			</ReactMarkdown>
		</div>
	);
}

function AssistantTurn({
	message,
	streaming,
}: {
	message: Extract<ChatMessage, { role: "assistant" }>;
	streaming: boolean;
}) {
	return (
		<div className="mt-6">
			<ProgressCard
				steps={message.steps}
				elapsedMs={message.elapsedMs}
				running={streaming}
			/>
			{message.failed && message.text.startsWith("The request failed") ? (
				<Notification kind="error" title="Request failed" className="mt-6">
					{message.text.replace(/^The request failed: /, "")}
				</Notification>
			) : message.text ? (
				<div className="mt-6">
					<Answer text={message.text} />
				</div>
			) : streaming && message.steps.length === 0 ? (
				<p className="mt-6 flex items-center gap-2 text-[var(--cds-text-2)] text-sm">
					<Loader2Icon className="size-4 animate-spin" /> Thinking…
				</p>
			) : null}
		</div>
	);
}

function EmptyState({ onAsk }: { onAsk: (q: string) => void }) {
	const suggestions = [
		"Can a landowner in Iowa use a spring gun to protect an unoccupied farmhouse?",
		"What are the elements of consumer fraud under Iowa Code § 714.16?",
		"When must an answer be served under the Iowa Rules of Civil Procedure?",
	];
	return (
		<div className="py-10">
			<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.22em]">
				Corpus-grounded chat
			</p>
			<h1 className="mt-4 font-light text-3xl">Ask the Iowa corpus</h1>
			<p className="mt-3 max-w-lg text-[15px] text-[var(--cds-text-2)] leading-relaxed">
				Answers are researched live against statutes, court rules, and case law,
				then verified against the source text before display.
			</p>
			<div className="mt-8 space-y-px border border-[var(--cds-border)] bg-[var(--cds-border)]">
				{suggestions.map((s) => (
					<button
						key={s}
						type="button"
						onClick={() => onAsk(s)}
						className="block w-full bg-[var(--cds-layer)] px-4 py-3 text-left text-sm transition-colors hover:bg-[var(--cds-layer-hover)]"
					>
						{s}
					</button>
				))}
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Composer
// ---------------------------------------------------------------------------

function Composer({
	busy,
	onSend,
	onStop,
}: {
	busy: boolean;
	onSend: (text: string) => void;
	onStop: () => void;
}) {
	const [draft, setDraft] = useState("");
	const submit = () => {
		const t = draft.trim();
		if (!t || busy) return;
		setDraft("");
		onSend(t);
	};
	return (
		<div className="shrink-0 border-[var(--cds-border)] border-t px-5 py-4 sm:px-8">
			<div className="mx-auto max-w-3xl">
				<form
					className="flex items-stretch border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] focus-within:outline-2 focus-within:-outline-offset-2 focus-within:outline-[#0f62fe]"
					onSubmit={(e) => {
						e.preventDefault();
						submit();
					}}
				>
					<input
						value={draft}
						onChange={(e) => setDraft(e.target.value)}
						placeholder="Message the assistant…"
						aria-label="Message the assistant"
						className="h-12 w-full bg-transparent px-4 text-sm outline-none placeholder:text-[var(--cds-placeholder)]"
					/>
					{busy ? (
						<button
							type="button"
							onClick={onStop}
							aria-label="Stop"
							title="Stop"
							className="flex w-12 shrink-0 items-center justify-center bg-[#da1e28] text-white transition-colors hover:bg-[#b81922]"
						>
							<SquareIcon className="size-4" />
						</button>
					) : (
						<button
							type="submit"
							aria-label="Send"
							disabled={!draft.trim()}
							className="flex w-12 shrink-0 items-center justify-center bg-[#0f62fe] text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c] disabled:bg-[var(--cds-layer-selected)] disabled:text-[var(--cds-helper)]"
						>
							<SendIcon className="size-4" />
						</button>
					)}
				</form>
				<p className="mt-2.5 text-right text-[11px] text-[var(--cds-helper)]">
					Answers are verified against source text before display. Verify
					Document (uploads) lives in the classic assistant for now.
				</p>
			</div>
		</div>
	);
}
