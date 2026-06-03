"use client";

import {
	AssistantRuntimeProvider,
	type AttachmentAdapter,
	type ChatModelAdapter,
	useLocalRuntime,
} from "@assistant-ui/react";
import { FileCheckIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ModelSelector } from "@/components/assistant-ui/model-selector";
import { Select } from "@/components/assistant-ui/select";
import { type ComposerTool, Thread } from "@/components/assistant-ui/thread";
import { ThreadListSidebar } from "@/components/assistant-ui/threadlist-sidebar";
import type { ProgressStep } from "@/components/tool-ui/progress-tracker";
import {
	Breadcrumb,
	BreadcrumbItem,
	BreadcrumbList,
	BreadcrumbPage,
	BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import {
	SidebarInset,
	SidebarProvider,
	SidebarTrigger,
} from "@/components/ui/sidebar";
import {
	type BrowseSource,
	citationsMarkdown,
	fetchSources,
	streamChat,
	toolLabel,
} from "@/lib/iowa-chat";
import {
	type CitationFinding,
	streamVerify,
	type VerifyInput,
	type VerifySummary,
} from "@/lib/iowa-verify";

// Chat vs. Verify Document. In verify mode the document the user sends is run
// through the citation verifier and the result renders inline as a checklist
// card (same tool-UI mechanism as the chat progress tracker).
type Mode = "chat" | "verify";

// Tools the user can turn on in the composer (via the slash menu, the Tools
// dropdown, or — for verify — by uploading a document). "Chat" is the absence
// of a tool, so it isn't listed here. Each id must map to a Mode in
// onSelectTool below.
const TOOLS: readonly ComposerTool[] = [
	{
		id: "verify",
		label: "Verify Document",
		description:
			"Check every citation's format and language against the source",
		icon: FileCheckIcon,
	},
];

// Must stay in sync with ALLOWED_CHAT_MODELS in apps/api/chat.py.
const CHAT_MODELS = [
	{
		id: "gpt-5-mini",
		name: "GPT-5 Mini",
		description: "Best accuracy on Iowa Court Rules. Reasoning model.",
	},
	{
		id: "gpt-4o",
		name: "GPT-4o",
		description: "Fast, classic chat model.",
	},
	{
		id: "gpt-4o-mini",
		name: "GPT-4o Mini",
		description: "Cheapest. Acceptable for simple lookups.",
	},
] as const;

const DEFAULT_SCOPE = "iowa-court-rules";
// Radix's <Select.Item> rejects value="" (it reserves the empty string for
// the cleared/placeholder state). Use a sentinel and translate at the API
// boundary instead.
const SCOPE_ALL = "all";

function flattenMessages(
	messages: readonly Parameters<
		ChatModelAdapter["run"]
	>[0]["messages"][number][],
) {
	return messages
		.filter(
			(m) => m.role === "user" || m.role === "assistant" || m.role === "system",
		)
		.map((m) => ({
			role: m.role as "user" | "assistant" | "system",
			content:
				typeof m.content === "string"
					? m.content
					: (m.content ?? [])
							.filter((p) => p.type === "text")
							.map((p) => (p as { type: "text"; text: string }).text)
							.join("\n"),
		}));
}

// File types the document verifier can ingest. PDFs/DOCX are parsed
// server-side by the docling microservice; text/markdown are read directly.
// Both the MIME type and the extension are listed so the composer's accept
// filter matches regardless of what the browser reports for `file.type`.
const VERIFY_ACCEPT = [
	"application/pdf",
	".pdf",
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	".docx",
	"application/msword",
	".doc",
	"text/plain",
	"text/markdown",
	".txt",
	".md",
	".markdown",
	".text",
].join(",");

// Attachment adapter for the chat composer. Without one, assistant-ui throws
// "Attachments are not supported" the moment a file is dropped or picked. We
// extract nothing client-side: the raw File rides along on the attachment
// (CompleteAttachment.file, preserved by the spread in send) and the chat
// adapter forwards it to the verifier, which runs docling on the bytes. The
// text part is just a label so the sent message isn't empty.
const documentAttachmentAdapter: AttachmentAdapter = {
	accept: VERIFY_ACCEPT,
	async add({ file }) {
		return {
			id: `${file.name}-${file.size}`,
			type: "document",
			name: file.name,
			contentType: file.type,
			file,
			status: { type: "requires-action", reason: "composer-send" },
		};
	},
	async send(attachment) {
		return {
			...attachment,
			status: { type: "complete" },
			content: [
				{ type: "text", text: `Attached document: ${attachment.name}` },
			],
		};
	},
	async remove() {},
};

// The File attached to the most recent user message, if any. Uploading a
// document is treated as a verify request regardless of chat/verify mode, so
// the chat adapter checks this before anything else.
function lastUserFile(
	messages: readonly Parameters<
		ChatModelAdapter["run"]
	>[0]["messages"][number][],
): File | null {
	for (let i = messages.length - 1; i >= 0; i--) {
		const m = messages[i];
		if (m.role !== "user") continue;
		const atts = (m as { attachments?: readonly { file?: File }[] })
			.attachments;
		const withFile = atts?.find((a) => a.file instanceof File);
		return withFile?.file ?? null;
	}
	return null;
}

// The last user message's text — the document to verify in verify mode.
function lastUserText(
	messages: readonly Parameters<
		ChatModelAdapter["run"]
	>[0]["messages"][number][],
): string {
	for (let i = messages.length - 1; i >= 0; i--) {
		const m = messages[i];
		if (m.role !== "user") continue;
		const c = m.content;
		return typeof c === "string"
			? c
			: (c ?? [])
					.filter((p) => p.type === "text")
					.map((p) => (p as { type: "text"; text: string }).text)
					.join("\n");
	}
	return "";
}

// Stable tool-call id for the progress tracker so re-emitting on each event
// updates the SAME tool part (assistant-ui dedupes by toolCallId) rather than
// stacking new cards in the message.
const PROGRESS_TOOL_CALL_ID = "iowa-progress";
const VERIFY_TOOL_CALL_ID = "iowa-verify";

type ProgressOutcome =
	| { kind: "running" }
	| { kind: "success" }
	| { kind: "failed"; reason: string }
	| { kind: "cancelled" };

// Verify-mode turn: run the document through the verifier and yield a single
// `verifyDocument` tool part that updates as findings stream in. The Thread
// renders it as a citation checklist card.
async function* runVerifyTurn(
	input: VerifyInput,
	model: string,
	abortSignal: AbortSignal,
) {
	const startedAt = Date.now();
	let findings: CitationFinding[] = [];
	let total: number | null = null;
	let summary: VerifySummary | null = null;
	let state: "running" | "done" | "error" = "running";
	let errorMessage = "";

	const emit = () => ({
		content: [
			{
				type: "tool-call" as const,
				toolCallId: VERIFY_TOOL_CALL_ID,
				toolName: "verifyDocument",
				args: {},
				argsText: "{}",
				result: {
					id: VERIFY_TOOL_CALL_ID,
					findings: findings.map((f) => ({ ...f })),
					total,
					summary,
					state,
					...(errorMessage ? { errorMessage } : {}),
					elapsedTime: Date.now() - startedAt,
				},
			},
		],
	});

	if (!("file" in input) && !input.text.trim()) {
		state = "error";
		errorMessage = "Paste or attach a document to verify its citations.";
		yield emit();
		return;
	}

	yield emit();
	try {
		for await (const ev of streamVerify(input, abortSignal, model)) {
			if (abortSignal.aborted) return;
			switch (ev.type) {
				case "start":
					total = ev.citations_total;
					break;
				case "citation_done":
					findings = [...findings, ev.finding];
					break;
				case "summary":
					summary = {
						total: ev.total,
						green: ev.green,
						yellow: ev.yellow,
						red: ev.red,
					};
					break;
				case "done":
					state = "done";
					break;
				case "error":
					state = "error";
					errorMessage = ev.message;
					break;
			}
			yield emit();
		}
		if (state === "running") {
			state = "done";
			yield emit();
		}
	} catch (e) {
		if ((e as Error).name === "AbortError") return;
		state = "error";
		errorMessage = (e as Error).message ?? String(e);
		yield emit();
	}
}

function makeAdapter(
	getScope: () => {
		model: string;
		sourceSlug: string | null;
		mode: Mode;
		onVerifyDone: () => void;
	},
): ChatModelAdapter {
	return {
		async *run({ messages, abortSignal }) {
			const scope = getScope();
			// An uploaded file is always a document to verify — run docling on it
			// regardless of mode. Otherwise verify mode verifies the pasted text.
			const file = lastUserFile(messages);
			if (file || scope.mode === "verify") {
				const input: VerifyInput = file
					? { file }
					: { text: lastUserText(messages) };
				yield* runVerifyTurn(input, scope.model, abortSignal);
				// One-shot verify mode drops back to chat so the next message isn't
				// silently treated as another document. A file upload in chat mode
				// leaves the mode alone.
				if (scope.mode === "verify") scope.onVerifyDone();
				return;
			}
			const startedAt = Date.now();
			const steps: ProgressStep[] = [];
			let answer = "";
			let synthesisStarted = false;

			const elapsed = () => Date.now() - startedAt;

			const completeInProgress = () => {
				for (const s of steps) {
					if (s.status === "in-progress") s.status = "completed";
				}
			};

			const trackerPart = (outcome: ProgressOutcome) => ({
				type: "tool-call" as const,
				toolCallId: PROGRESS_TOOL_CALL_ID,
				toolName: "trackProgress",
				args: {},
				argsText: "{}",
				result: {
					id: "iowa-progress",
					steps: steps.map((s) => ({ ...s })),
					elapsedTime: elapsed(),
					...(outcome.kind === "success"
						? {
								choice: {
									outcome: "success" as const,
									summary: "Done — answer below.",
									at: new Date().toISOString(),
								},
							}
						: outcome.kind === "failed"
							? {
									choice: {
										outcome: "failed" as const,
										summary: outcome.reason,
										at: new Date().toISOString(),
									},
								}
							: outcome.kind === "cancelled"
								? {
										choice: {
											outcome: "cancelled" as const,
											summary: "Cancelled.",
											at: new Date().toISOString(),
										},
									}
								: {}),
				},
			});

			const yieldState = (outcome: ProgressOutcome = { kind: "running" }) => {
				const parts: Array<
					ReturnType<typeof trackerPart> | { type: "text"; text: string }
				> = [];
				if (steps.length > 0) parts.push(trackerPart(outcome));
				if (answer) parts.push({ type: "text" as const, text: answer });
				return { content: parts };
			};

			try {
				for await (const event of streamChat(
					{
						model: scope.model,
						messages: flattenMessages(messages),
						source_slug: scope.sourceSlug,
					},
					abortSignal,
				)) {
					if (abortSignal.aborted) return;

					if (event.type === "tool_start") {
						completeInProgress();
						const { label, description } = toolLabel(
							event.name,
							event.arguments,
						);
						steps.push({
							id: `step-${steps.length}`,
							label,
							...(description ? { description } : {}),
							status: "in-progress",
						});
						yield yieldState();
					} else if (event.type === "delta") {
						// First delta = synthesis began. Mark any in-progress tool step
						// as complete; the streaming text below the tracker is its own
						// visual cue that drafting is underway — no need for a step.
						if (!synthesisStarted) {
							synthesisStarted = true;
							completeInProgress();
						}
						answer += event.text;
						yield yieldState();
					} else if (event.type === "done") {
						for (const s of steps) {
							if (s.status === "in-progress" || s.status === "pending") {
								s.status = "completed";
							}
						}
						answer =
							(answer || "(no answer returned)") +
							citationsMarkdown(event.tool_calls ?? [], answer);
						yield yieldState({ kind: "success" });
						return;
					} else if (event.type === "error") {
						for (const s of steps) {
							if (s.status === "in-progress") s.status = "failed";
						}
						answer = `The request failed: ${event.message}`;
						yield yieldState({ kind: "failed", reason: event.message });
						return;
					}
				}
			} catch (e) {
				if ((e as Error).name === "AbortError") return;
				for (const s of steps) {
					if (s.status === "in-progress") s.status = "failed";
				}
				answer = `The request failed: ${(e as Error).message ?? String(e)}`;
				yield yieldState({
					kind: "failed",
					reason: (e as Error).message ?? String(e),
				});
			}
		},
	};
}

export const Assistant = () => {
	const [model, setModel] = useState<string>(CHAT_MODELS[0].id);
	const [scope, setScope] = useState<string>(DEFAULT_SCOPE);
	const [mode, setMode] = useState<Mode>("chat");
	const [sources, setSources] = useState<BrowseSource[]>([]);

	useEffect(() => {
		let cancelled = false;
		fetchSources().then((s) => {
			if (!cancelled) setSources(s);
		});
		return () => {
			cancelled = true;
		};
	}, []);

	// Wrap state in a ref-style getter so the adapter (memoized once) always
	// sees the latest model/scope without re-instantiating the runtime.
	const sourceSlug = scope === SCOPE_ALL ? null : scope;
	const onVerifyDone = () => setMode("chat");
	const scopeRef = useMemo(
		() => ({ current: { model, sourceSlug, mode, onVerifyDone } }),
		[],
	);
	scopeRef.current = { model, sourceSlug, mode, onVerifyDone };
	const adapter = useMemo(
		() => makeAdapter(() => scopeRef.current),
		[scopeRef],
	);
	const runtime = useLocalRuntime(adapter, {
		adapters: { attachments: documentAttachmentAdapter },
	});

	const activeSourceName = useMemo(
		() => sources.find((s) => s.slug === scope)?.name ?? "All sources",
		[sources, scope],
	);

	const scopeOptions = useMemo(
		() => [
			{ value: SCOPE_ALL, label: "All sources" },
			...sources.map((s) => ({ value: s.slug, label: s.name })),
		],
		[sources],
	);

	return (
		<AssistantRuntimeProvider runtime={runtime}>
			<SidebarProvider>
				<div className="flex h-dvh w-full pr-0.5">
					<ThreadListSidebar />
					<SidebarInset>
						<header className="flex h-16 shrink-0 items-center gap-3 border-b px-4">
							<SidebarTrigger />
							<Separator orientation="vertical" className="mr-2 h-4" />
							<Breadcrumb>
								<BreadcrumbList>
									<BreadcrumbItem className="hidden md:block">
										Iowa Legal Corpus
									</BreadcrumbItem>
									<BreadcrumbSeparator className="hidden md:block" />
									<BreadcrumbItem>
										<BreadcrumbPage>{activeSourceName}</BreadcrumbPage>
									</BreadcrumbItem>
								</BreadcrumbList>
							</Breadcrumb>

							<div className="ml-auto flex items-center gap-2">
								<Select
									value={scope}
									onValueChange={setScope}
									options={scopeOptions}
									placeholder="Source"
								/>
								<ModelSelector
									models={
										CHAT_MODELS as unknown as {
											id: string;
											name: string;
											description?: string;
										}[]
									}
									value={model}
									onValueChange={setModel}
									size="sm"
									variant="outline"
								/>
							</div>
						</header>
						<div className="flex-1 overflow-hidden">
							<Thread
								composerPlaceholder={
									mode === "verify"
										? "Paste a document to verify its citations…"
										: "Message the assistant — or type / for tools"
								}
								tools={TOOLS}
								activeTool={mode === "verify" ? "verify" : null}
								onSelectTool={(id) =>
									setMode(id === "verify" ? "verify" : "chat")
								}
							/>
						</div>
					</SidebarInset>
				</div>
			</SidebarProvider>
		</AssistantRuntimeProvider>
	);
};
