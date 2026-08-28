"use client";

// Carbon chat turns shared by the full-page Assistant and the per-document
// "Ask about this case" panel in the case reader: the user bubble, the
// research-run progress card, the Markdown answer with citation links
// rewritten into the Carbon readers, and the assistant turn that composes
// them. Presentational only — the streaming loop lives with each surface.

import { CheckIcon, Loader2Icon, PaperclipIcon, XIcon } from "lucide-react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Notification } from "@/components/carbon/primitives";

export type Step = {
	label: string;
	description?: string;
	status: "in-progress" | "completed" | "failed";
};

export type UserMessage = { role: "user"; text: string; attachment?: string };

export type AssistantMessage = {
	role: "assistant";
	text: string;
	steps: Step[];
	elapsedMs?: number;
	failed?: boolean;
};

export function UserBubble({
	children,
	attachment,
}: {
	children: React.ReactNode;
	attachment?: string;
}) {
	return (
		<div className="mt-8 flex justify-end first:mt-0">
			<div className="max-w-[85%]">
				{attachment && (
					<p className="mb-1.5 flex items-center justify-end gap-1.5 font-mono text-[11px] text-[var(--cds-helper)]">
						<PaperclipIcon className="size-3.5" />
						{attachment}
					</p>
				)}
				<div className="whitespace-pre-wrap border border-[var(--cds-border)] bg-[var(--cds-layer)] px-4 py-3 text-sm leading-relaxed">
					{children}
				</div>
			</div>
		</div>
	);
}

export function ProgressCard({
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

// Markdown with Carbon styling. The shared chat lib emits legacy reader
// links — /cases/<id> for decisions, /browse#/<slug>/<path> for statutes —
// so rewrite both into the Carbon readers (statute paths resolve to node
// ids via /goto).
const rewriteHref = (href: string) => {
	if (href.startsWith("/cases/")) return href.replace("/cases/", "/case/");
	const m = /^\/browse#\/([^/]+)\/(.+)$/.exec(href);
	if (m)
		return `/goto?source=${encodeURIComponent(m[1])}&cite=${encodeURIComponent(m[2])}`;
	return href;
};

export function Answer({ text }: { text: string }) {
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

export function AssistantTurn({
	message,
	streaming,
}: {
	message: AssistantMessage;
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
