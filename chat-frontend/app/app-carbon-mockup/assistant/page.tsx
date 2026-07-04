"use client";

// Carbon mockup of the Assistant (chat) screen. Mirrors the live "/" page:
// thread-list rail, breadcrumb header with source-scope + model controls, a
// message thread with the retrieval progress tracker and a verified answer,
// the Verify Document checklist card, and the composer with the tools row.
// Static data throughout — nothing calls the API.

import {
	CheckIcon,
	ChevronDownIcon,
	CircleAlertIcon,
	FileCheckIcon,
	PaperclipIcon,
	PenLineIcon,
	PlusIcon,
	SearchIcon,
	SendIcon,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { AppShell, NavGroupLabel, Panel, Tag } from "../carbon";

// ---------------------------------------------------------------------------
// Static thread data
// ---------------------------------------------------------------------------

const THREADS: {
	group: string;
	items: { title: string; active?: boolean }[];
}[] = [
	{
		group: "Today",
		items: [
			{ title: "Spring guns & premises defense", active: true },
			{ title: "Rule 1.402 pleading form" },
		],
	},
	{
		group: "Previous 7 days",
		items: [
			{ title: "Consumer fraud — § 714.16 elements" },
			{ title: "Verify: MSJ brief citations" },
			{ title: "Adverse possession color of title" },
		],
	},
];

const PROGRESS_STEPS: { label: string; detail: string }[] = [
	{
		label: "Searching the corpus",
		detail: "hybrid search · 105,355 documents",
	},
	{ label: "Reading top authorities", detail: "8 passages across 5 documents" },
	{ label: "Drafting answer", detail: "gpt-5-mini" },
	{ label: "Verifying citations", detail: "4 of 4 citations verified" },
];

const AUTHORITIES: {
	name: string;
	cite: string;
	kind: "case" | "code";
	treatment?: "good" | "caution";
}[] = [
	{
		name: "Katko v. Briney",
		cite: "183 N.W.2d 657 (Iowa 1971)",
		kind: "case",
		treatment: "good",
	},
	{ name: "Iowa Code § 704.4", cite: "Defense of property", kind: "code" },
	{
		name: "Iowa Code § 704.5",
		cite: "Aiding another in defense",
		kind: "code",
	},
	{
		name: "Hooker v. Miller",
		cite: "37 Iowa 613 (1873)",
		kind: "case",
		treatment: "good",
	},
];

const VERIFY_FINDINGS: {
	cite: string;
	status: "green" | "yellow" | "red";
	note: string;
}[] = [
	{
		cite: "Katko v. Briney, 183 N.W.2d 657, 660 (Iowa 1971)",
		status: "green",
		note: "Resolves; quoted language matches the opinion.",
	},
	{
		cite: "Iowa Code § 704.4 (2025)",
		status: "green",
		note: "Resolves to the current edition.",
	},
	{
		cite: "State v. Metcalf, 260 N.W.2d 857 (Iowa 1977)",
		status: "yellow",
		note: "Resolves, but the paraphrase overstates the holding — review.",
	},
	{
		cite: "Bird v. Holbrook, 4 Bing. 628 (C.P. 1828)",
		status: "red",
		note: "Outside the corpus — cannot verify against source text.",
	},
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AssistantCarbonMockup() {
	return (
		<AppShell active="/app-carbon-mockup/assistant">
			<div className="flex h-full min-h-0">
				<ThreadRail />

				<div className="flex min-w-0 flex-1 flex-col">
					<ChatHeader />

					<div className="min-h-0 flex-1 overflow-y-auto">
						<div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
							<UserMessage>
								Can a landowner in Iowa use a spring gun to protect an
								unoccupied farmhouse?
							</UserMessage>

							<ProgressCard />

							<AssistantMessage />

							<UserMessage attachment="motion-summary-judgment.docx">
								Verify the citations in this draft before I file it.
							</UserMessage>

							<VerifyCard />
						</div>
					</div>

					<Composer />
				</div>
			</div>
		</AppShell>
	);
}

// ---------------------------------------------------------------------------
// Thread rail — Carbon side-nav register, one level in from the app nav
// ---------------------------------------------------------------------------

function ThreadRail() {
	return (
		<aside className="hidden w-64 shrink-0 flex-col border-[var(--cds-border)] border-r xl:flex">
			<div className="p-4">
				<button
					type="button"
					className="flex h-10 w-full items-center justify-between gap-3 bg-[#0f62fe] px-4 text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c]"
				>
					New chat
					<PlusIcon className="size-4" />
				</button>
			</div>
			<div className="min-h-0 flex-1 overflow-y-auto pb-4">
				{THREADS.map((g) => (
					<div key={g.group}>
						<NavGroupLabel>{g.group}</NavGroupLabel>
						{g.items.map((t) => (
							<button
								key={t.title}
								type="button"
								className={cn(
									"flex w-full items-center gap-3 border-l-[3px] px-3.5 py-2 text-left text-sm transition-colors",
									t.active
										? "border-[#0f62fe] bg-[var(--cds-layer-selected)] font-semibold"
										: "border-transparent text-[var(--cds-text-2)] hover:bg-[var(--cds-layer-hover)] hover:text-[var(--cds-text)]",
								)}
							>
								<span className="truncate">{t.title}</span>
							</button>
						))}
					</div>
				))}
			</div>
		</aside>
	);
}

// ---------------------------------------------------------------------------
// Header — breadcrumb + scope/model dropdowns (static)
// ---------------------------------------------------------------------------

function HeaderSelect({ label, value }: { label: string; value: string }) {
	return (
		<button
			type="button"
			className="flex h-8 items-center gap-2 border border-[var(--cds-border)] px-3 text-[13px] transition-colors hover:bg-[var(--cds-layer-hover)]"
		>
			<span className="text-[var(--cds-helper)] text-xs">{label}</span>
			<span className="font-medium">{value}</span>
			<ChevronDownIcon className="size-3.5 text-[var(--cds-text-2)]" />
		</button>
	);
}

function ChatHeader() {
	return (
		<header className="flex h-14 shrink-0 items-center gap-3 border-[var(--cds-border)] border-b px-5 sm:px-8">
			<p className="min-w-0 truncate text-sm">
				<span className="text-[var(--cds-text-2)]">Iowa Legal Corpus</span>
				<span className="mx-2 text-[var(--cds-helper)]">/</span>
				<span className="font-semibold">All sources</span>
			</p>
			<div className="ml-auto flex items-center gap-2">
				<HeaderSelect label="Scope" value="All sources" />
				<HeaderSelect label="Model" value="GPT-5 Mini" />
			</div>
		</header>
	);
}

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

function UserMessage({
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
				<div className="border border-[var(--cds-border)] bg-[var(--cds-layer)] px-4 py-3 text-sm leading-relaxed">
					{children}
				</div>
			</div>
		</div>
	);
}

function ProgressCard() {
	return (
		<div className="mt-6 border border-[var(--cds-border)]">
			<header className="flex items-center justify-between border-[var(--cds-border)] border-b px-4 py-2.5">
				<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
					Research run
				</span>
				<span className="font-mono text-[11px] text-[var(--cds-helper)]">
					4.2 s
				</span>
			</header>
			<ol className="divide-y divide-[var(--cds-border)]">
				{PROGRESS_STEPS.map((s) => (
					<li key={s.label} className="flex items-center gap-3 px-4 py-2.5">
						<CheckIcon
							className="size-4 shrink-0 text-[var(--cds-success-text)]"
							strokeWidth={2.5}
						/>
						<span className="text-sm">{s.label}</span>
						<span className="ml-auto truncate font-mono text-[var(--cds-helper)] text-[11px]">
							{s.detail}
						</span>
					</li>
				))}
			</ol>
		</div>
	);
}

function CiteLink({ children }: { children: React.ReactNode }) {
	return (
		<Link
			href="/app-carbon-mockup/case"
			className="text-[var(--cds-link)] hover:underline"
		>
			{children}
		</Link>
	);
}

function AssistantMessage() {
	return (
		<div className="mt-6">
			<div className="space-y-4 text-[15px] leading-relaxed">
				<p>
					No. Iowa law does not permit deadly mechanical devices to protect
					unoccupied property. In{" "}
					<CiteLink>Katko v. Briney, 183 N.W.2d 657 (Iowa 1971)</CiteLink>, the
					Iowa Supreme Court affirmed a damages award against owners who rigged
					a spring gun in an unoccupied farmhouse, holding that the value of
					human life outweighs a possessor&rsquo;s interest in unoccupied
					premises — deadly force may not be used against a mere trespasser.
				</p>
				<p>
					The rule is now statutory. Under{" "}
					<CiteLink>Iowa Code § 704.4</CiteLink>, a person may use
					&ldquo;reasonable force&rdquo; to protect property, and reasonable
					force generally excludes force intended or likely to cause death or
					serious injury unless a person&rsquo;s safety is also at stake. A
					device that fires blindly cannot judge that necessity, which is
					precisely why <CiteLink>Katko</CiteLink> — following the older
					trespass cases like{" "}
					<CiteLink>Hooker v. Miller, 37 Iowa 613 (1873)</CiteLink> — treats
					spring guns as per se unreasonable for unoccupied buildings.
				</p>
			</div>

			<div className="mt-6">
				<Panel title="Authorities cited — 4 verified">
					<ul className="divide-y divide-[var(--cds-border)]">
						{AUTHORITIES.map((a) => (
							<li key={a.name}>
								<Link
									href="/app-carbon-mockup/case"
									className="group flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-[var(--cds-layer-hover)]"
								>
									<Tag kind={a.kind === "case" ? "blue" : "gray"}>
										{a.kind === "case" ? "Case" : "Iowa Code"}
									</Tag>
									<span className="min-w-0 flex-1">
										<span className="block truncate font-medium text-sm group-hover:underline">
											{a.name}
										</span>
										<span className="block truncate font-mono text-[var(--cds-helper)] text-[11px]">
											{a.cite}
										</span>
									</span>
									{a.treatment === "good" && (
										<Tag kind="green">
											<CheckIcon className="size-3" strokeWidth={2.5} />
											Good law
										</Tag>
									)}
								</Link>
							</li>
						))}
					</ul>
				</Panel>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Verify Document checklist card
// ---------------------------------------------------------------------------

const VERIFY_STATUS: Record<
	"green" | "yellow" | "red",
	{ label: string; cls: string }
> = {
	green: { label: "Verified", cls: "text-[var(--cds-success-text)]" },
	yellow: { label: "Review", cls: "text-[#b28600]" },
	red: { label: "Problem", cls: "text-[var(--cds-danger-text)]" },
};

function VerifyCard() {
	return (
		<div className="mt-6 border border-[var(--cds-border)]">
			<header className="flex items-center gap-3 border-[var(--cds-border)] border-b px-4 py-2.5">
				<FileCheckIcon className="size-4 text-[var(--cds-text-2)]" />
				<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
					Verify document — 4 citations
				</span>
				<span className="ml-auto flex items-center gap-2">
					<Tag kind="green">2 verified</Tag>
					<Tag kind="yellow">1 review</Tag>
					<Tag kind="red">1 problem</Tag>
				</span>
			</header>
			<ul className="divide-y divide-[var(--cds-border)]">
				{VERIFY_FINDINGS.map((f) => {
					const s = VERIFY_STATUS[f.status];
					return (
						<li key={f.cite} className="flex items-start gap-3 px-4 py-3">
							{f.status === "green" ? (
								<CheckIcon
									className={cn("mt-0.5 size-4 shrink-0", s.cls)}
									strokeWidth={2.5}
								/>
							) : (
								<CircleAlertIcon
									className={cn("mt-0.5 size-4 shrink-0", s.cls)}
								/>
							)}
							<span className="min-w-0 flex-1">
								<span className="block font-mono text-[13px]">{f.cite}</span>
								<span className="block text-[var(--cds-text-2)] text-xs">
									{f.note}
								</span>
							</span>
							<span
								className={cn(
									"shrink-0 font-mono text-[11px] uppercase tracking-[0.14em]",
									s.cls,
								)}
							>
								{s.label}
							</span>
						</li>
					);
				})}
			</ul>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Composer — fluid field with tools row
// ---------------------------------------------------------------------------

function Composer() {
	return (
		<div className="shrink-0 border-[var(--cds-border)] border-t px-5 py-4 sm:px-8">
			<div className="mx-auto max-w-3xl">
				<div className="flex items-stretch border-[var(--cds-border-strong)] border-b bg-[var(--cds-field)] focus-within:outline-2 focus-within:-outline-offset-2 focus-within:outline-[#0f62fe]">
					<input
						placeholder="Message the assistant — or type / for tools"
						aria-label="Message the assistant"
						className="h-12 w-full bg-transparent px-4 text-sm outline-none placeholder:text-[var(--cds-placeholder)]"
					/>
					<button
						type="button"
						aria-label="Attach a document"
						className="flex w-12 shrink-0 items-center justify-center text-[var(--cds-text-2)] transition-colors hover:bg-[var(--cds-layer-hover)]"
					>
						<PaperclipIcon className="size-4" />
					</button>
					<button
						type="button"
						aria-label="Send"
						className="flex w-12 shrink-0 items-center justify-center bg-[#0f62fe] text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c]"
					>
						<SendIcon className="size-4" />
					</button>
				</div>

				<div className="mt-2.5 flex flex-wrap items-center gap-2">
					<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.14em]">
						Tools
					</span>
					<button
						type="button"
						className="flex h-7 items-center gap-1.5 border border-[var(--cds-border)] px-2.5 text-xs transition-colors hover:bg-[var(--cds-layer-hover)]"
					>
						<FileCheckIcon className="size-3.5" />
						Verify Document
					</button>
					<button
						type="button"
						className="flex h-7 items-center gap-1.5 border border-[var(--cds-border)] px-2.5 text-xs transition-colors hover:bg-[var(--cds-layer-hover)]"
					>
						<SearchIcon className="size-3.5" />
						Search the corpus
					</button>
					<button
						type="button"
						className="flex h-7 items-center gap-1.5 border border-[var(--cds-border)] px-2.5 text-xs transition-colors hover:bg-[var(--cds-layer-hover)]"
					>
						<PenLineIcon className="size-3.5" />
						Draft from authority
					</button>
					<span className="ml-auto hidden text-[var(--cds-helper)] text-[11px] sm:block">
						Answers are verified against source text before display.
					</span>
				</div>
			</div>
		</div>
	);
}
