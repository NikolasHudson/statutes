"use client";

// Open Casebook — student reader (hero mockup)
// =============================================
//
// Self-contained on its own route (/casebook-mockup), registered as public in
// auth-gate so it renders for signed-out visitors with no flash — same pattern
// as /home-mockup.
//
// This is the "replaces your $300 textbook" experience: a professor-authored,
// free, open-licensed casebook that a student reads in the browser. It reads
// like a real law book — wide case text with the professor's notes in the
// margin — and quietly carries two things a printed casebook can't: a small
// currency line on each case/statute (still good law?), and an optional
// "Ask the book" study helper that answers with citations into the book.
//
// The data shapes below (Casebook → Section → Item, with item `kind`) are a
// deliberate sketch of the models we'd add server-side: Casebook, Section,
// CasebookItem(kind), Annotation. Authoring/cloning is a separate surface.
//
// Content note: the opinion text is an *edited, illustrative* excerpt for the
// mockup (as real casebooks abridge) — not a verbatim reporter transcription.

import {
	BadgeCheckIcon,
	BookmarkIcon,
	BookOpenIcon,
	ChevronDownIcon,
	ChevronRightIcon,
	GraduationCapIcon,
	HighlighterIcon,
	type LucideIcon,
	MessageSquareIcon,
	PenLineIcon,
	PrinterIcon,
	QuoteIcon,
	ScaleIcon,
	ScrollTextIcon,
	SendIcon,
	XIcon,
} from "lucide-react";
import Link from "next/link";
import { type ReactNode, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Casebook structure — the TOC. Maps to Section + CasebookItem(kind) server-side.
// ---------------------------------------------------------------------------

type ItemKind = "note" | "case" | "statute";

type Section = {
	id: string;
	label: string;
	kind: ItemKind;
	meta?: string; // citation / short descriptor shown under the label
};

type Chapter = {
	id: string;
	number: string;
	title: string;
	sections: Section[];
};

const CHAPTERS: Chapter[] = [
	{
		id: "ch2",
		number: "2",
		title: "Possession & the Right to Exclude",
		sections: [
			{
				id: "2-1",
				label: "Pierson v. Post",
				kind: "case",
				meta: "3 Cai. R. 175",
			},
			{ id: "2-2", label: "Notes: Capture & Custom", kind: "note" },
		],
	},
	{
		id: "ch3",
		number: "3",
		title: "Acquisition by Adverse Possession",
		sections: [
			{ id: "3-1", label: "The Doctrine in Brief", kind: "note" },
			{
				id: "3-2",
				label: "Carpenter v. Ruperto",
				kind: "case",
				meta: "315 N.W.2d 782 (Iowa 1982)",
			},
			{
				id: "3-3",
				label: "Iowa Code § 614.17A",
				kind: "statute",
				meta: "Claims to real estate",
			},
			{ id: "3-4", label: "Notes & Questions", kind: "note" },
		],
	},
	{
		id: "ch4",
		number: "4",
		title: "Tacking & Successive Possession",
		sections: [
			{ id: "4-1", label: "The Tacking Requirement", kind: "note" },
			{
				id: "4-2",
				label: "Howard v. Kunto",
				kind: "case",
				meta: "477 P.2d 210",
			},
		],
	},
];

const ALL_SECTIONS = CHAPTERS.flatMap((c) =>
	c.sections.map((s) => ({ ...s, chapter: c })),
);

const KIND_ICON: Record<ItemKind, LucideIcon> = {
	note: BookOpenIcon,
	case: ScaleIcon,
	statute: ScrollTextIcon,
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CasebookReader() {
	const [activeId, setActiveId] = useState("3-2"); // default to the hero case
	const [chatOpen, setChatOpen] = useState(false);

	const active = ALL_SECTIONS.find((s) => s.id === activeId) ?? ALL_SECTIONS[0];

	return (
		<div className="min-h-dvh bg-background text-foreground">
			<TopBar onAsk={() => setChatOpen(true)} />

			<div className="mx-auto flex max-w-[1440px]">
				<Toc activeId={activeId} onSelect={setActiveId} />

				<main className="min-w-0 flex-1">
					{/* Wide reading measure that fills the window; on xl we reserve a
					    right gutter (xl:pr-80) so the professor's margin notes can float
					    into it, the way a real casebook sets marginalia beside the text. */}
					<div className="mx-auto w-full max-w-[82rem] px-6 py-10 sm:px-10 lg:py-14 xl:pr-80">
						<SectionContent
							id={active.id}
							chapterTitle={active.chapter.title}
						/>

						<SectionFooterNav activeId={activeId} onSelect={setActiveId} />
					</div>
				</main>
			</div>

			<AskTheBook
				open={chatOpen}
				onOpen={() => setChatOpen(true)}
				onClose={() => setChatOpen(false)}
				context={active.label}
			/>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Top bar — brand, book title, free badge, reader actions, ask button
// ---------------------------------------------------------------------------

function TopBar({ onAsk }: { onAsk: () => void }) {
	return (
		<header className="sticky top-0 z-30 border-border border-b bg-card/85 backdrop-blur">
			<div className="mx-auto flex max-w-[1440px] items-center gap-4 px-4 py-2.5 sm:px-6">
				{/* Brand — the black HUDSON banner, reused from the app chrome */}
				<div className="flex items-center gap-2.5">
					<span className="bg-black px-2.5 py-1 font-bold text-[13px] text-white uppercase tracking-[0.06em]">
						Hudson
					</span>
					<span className="hidden font-medium text-[12px] text-muted-foreground uppercase tracking-[0.16em] sm:inline">
						Open Casebooks
					</span>
				</div>

				<div className="mx-1 hidden h-5 w-px bg-border sm:block" />

				{/* Book title + free badge */}
				<div className="flex min-w-0 items-center gap-2.5">
					<span className="truncate font-semibold text-[14px] tracking-tight">
						Iowa Property Law
					</span>
					<span className="hidden items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-semibold text-[11px] text-emerald-700 md:inline-flex">
						Free · Open
					</span>
				</div>

				<div className="ml-auto flex items-center gap-1">
					<IconAction icon={BookmarkIcon} label="Save" />
					<IconAction icon={PrinterIcon} label="Print" />
					{/* Professor-only in reality; here it's the way into the authoring view. */}
					<Button
						asChild
						size="sm"
						variant="ghost"
						className="ml-1 hidden sm:inline-flex"
					>
						<Link href="/casebook-mockup/edit">
							<PenLineIcon className="size-4" />
							Edit
						</Link>
					</Button>
					<Button size="sm" variant="outline" onClick={onAsk}>
						Ask a question
					</Button>
				</div>
			</div>
		</header>
	);
}

function IconAction({
	icon: Icon,
	label,
}: {
	icon: LucideIcon;
	label: string;
}) {
	return (
		<button
			type="button"
			title={label}
			className="hidden size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground sm:flex"
		>
			<Icon className="size-4" />
		</button>
	);
}

// ---------------------------------------------------------------------------
// Table of contents — left rail. Author byline + adoption band on top.
// ---------------------------------------------------------------------------

function Toc({
	activeId,
	onSelect,
}: {
	activeId: string;
	onSelect: (id: string) => void;
}) {
	return (
		<aside className="sticky top-[57px] hidden h-[calc(100dvh-57px)] w-72 shrink-0 overflow-y-auto border-border border-r bg-sidebar/40 lg:block">
			{/* Author / vetting — the editorial trust signal */}
			<div className="border-border border-b px-5 py-5">
				<div className="font-bold text-[17px] leading-snug tracking-tight">
					Iowa Property Law
				</div>
				<div className="mt-0.5 text-[12px] text-muted-foreground">
					Cases, Statutes &amp; Practice · 2026 ed.
				</div>

				<div className="mt-4 flex items-start gap-2.5">
					<div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 font-semibold text-[12px] text-primary">
						DW
					</div>
					<div className="min-w-0">
						<div className="flex items-center gap-1 font-medium text-[13px]">
							Prof. Dana R. Whitfield
							<BadgeCheckIcon className="size-3.5 text-primary" />
						</div>
						<div className="text-[11px] text-muted-foreground leading-tight">
							Verified · Iowa Bar #18342
						</div>
					</div>
				</div>

				<div className="mt-4 flex items-center gap-2 rounded-lg bg-emerald-50 px-2.5 py-2 text-emerald-800">
					<GraduationCapIcon className="size-4 shrink-0" />
					<span className="text-[11px] leading-tight">
						Assigned in <span className="font-semibold">LAW 5210</span> ·
						replaces a $329 casebook
					</span>
				</div>
			</div>

			{/* Chapter / section tree */}
			<nav className="px-3 py-4">
				{CHAPTERS.map((c) => (
					<TocChapter
						key={c.id}
						chapter={c}
						activeId={activeId}
						onSelect={onSelect}
					/>
				))}
			</nav>
		</aside>
	);
}

function TocChapter({
	chapter,
	activeId,
	onSelect,
}: {
	chapter: Chapter;
	activeId: string;
	onSelect: (id: string) => void;
}) {
	const hasActive = chapter.sections.some((s) => s.id === activeId);
	const [open, setOpen] = useState(hasActive);

	return (
		<div className="mb-1">
			<button
				type="button"
				onClick={() => setOpen((o) => !o)}
				className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-secondary"
			>
				{open ? (
					<ChevronDownIcon className="size-3.5 shrink-0 text-muted-foreground" />
				) : (
					<ChevronRightIcon className="size-3.5 shrink-0 text-muted-foreground" />
				)}
				<span className="font-semibold text-[11px] text-muted-foreground uppercase tracking-wider">
					Ch. {chapter.number}
				</span>
				<span className="truncate font-medium text-[12.5px]">
					{chapter.title}
				</span>
			</button>

			{open && (
				<ul className="mt-0.5 mb-2 ml-3 border-border border-l pl-2">
					{chapter.sections.map((s) => {
						const Icon = KIND_ICON[s.kind];
						const isActive = s.id === activeId;
						return (
							<li key={s.id}>
								<button
									type="button"
									onClick={() => onSelect(s.id)}
									className={cn(
										"flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
										isActive
											? "bg-primary/10 text-primary"
											: "text-foreground/80 hover:bg-secondary",
									)}
								>
									<Icon
										className={cn(
											"mt-0.5 size-3.5 shrink-0",
											isActive ? "text-primary" : "text-muted-foreground",
										)}
									/>
									<span className="min-w-0">
										<span
											className={cn(
												"block text-[13px] leading-snug",
												isActive && "font-semibold",
											)}
										>
											{s.label}
										</span>
										{s.meta && (
											<span className="block text-[11px] text-muted-foreground leading-tight">
												{s.meta}
											</span>
										)}
									</span>
								</button>
							</li>
						);
					})}
				</ul>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Reading pane — switches on the active section. Annotation primitives below.
// ---------------------------------------------------------------------------

function SectionContent({
	id,
	chapterTitle,
}: {
	id: string;
	chapterTitle: string;
}) {
	switch (id) {
		case "3-1":
			return <DoctrineInBrief />;
		case "3-2":
			return <CarpenterCase />;
		case "3-3":
			return <StatuteSection />;
		case "3-4":
			return <NotesAndQuestions />;
		default:
			return <Placeholder chapterTitle={chapterTitle} />;
	}
}

// --- 3.1 — professor-authored doctrinal intro --------------------------------

function DoctrineInBrief() {
	return (
		<article>
			<Kicker>Chapter 3 · Adverse Possession</Kicker>
			<h1 className="mt-2 font-bold text-3xl tracking-tight">
				The Doctrine in Brief
			</h1>

			<Prose>
				<p>
					Adverse possession turns a trespasser into an owner. If a person
					occupies land that belongs to another for long enough, and in the
					right way, the law extinguishes the true owner's right to eject them
					and vests title in the possessor. In Iowa the limitations period runs{" "}
					<Cite kind="statute">Iowa Code § 614.1(5)</Cite> — ten years for the
					recovery of real property.
				</p>
			</Prose>

			<Headnote>
				Read the elements below as a checklist. As you work through{" "}
				<em>Carpenter v. Ruperto</em>, ask which element the claimant failed —
				and why Iowa, unlike many states, makes the possessor's state of mind
				part of the test.
			</Headnote>

			<Prose>
				<p>Possession must be:</p>
				<ol className="mt-2 space-y-1.5">
					<li>
						<strong>Hostile</strong> — under a claim of right, not with the
						owner's permission;
					</li>
					<li>
						<strong>Actual</strong> — real use of the land, as an owner would;
					</li>
					<li>
						<strong>Open and notorious</strong> — visible enough to put the
						owner on notice;
					</li>
					<li>
						<strong>Exclusive</strong> — not shared with the true owner or the
						public; and
					</li>
					<li>
						<strong>Continuous</strong> for the full statutory period.
					</li>
				</ol>
			</Prose>
		</article>
	);
}

// --- 3.2 — the hero: a case with annotations, elision, treatment badge -------

function CarpenterCase() {
	return (
		<article>
			<Kicker>Chapter 3 · Adverse Possession</Kicker>

			<ResourceHeader
				title="Carpenter v. Ruperto"
				citations={[
					{ text: "315 N.W.2d 782", kind: "case" },
					{ text: "(Iowa 1982)", kind: "case" },
				]}
				court="Supreme Court of Iowa"
				date="Decided Feb. 17, 1982"
			/>

			<TreatmentBadge />

			<Headnote>
				The plaintiff cleared, graded, and used a strip of her neighbor's land
				for well over ten years — yet lost. Watch for the moment the court
				shifts from <em>what she did</em> to <em>what she knew</em>.
			</Headnote>

			<Prose>
				<p>
					<Speaker>McCORMICK, J.</Speaker> This is an action to quiet title to a
					disputed strip of land. The plaintiff, Virginia Carpenter, sought to
					establish ownership by adverse possession of a tract lying just north
					of her residential lot and south of the defendants' farmland. The
					trial court denied her claim, and she appeals.
				</p>

				<p>
					The facts are largely undisputed. After buying her lot in 1951,
					Carpenter cleared the adjoining ground, hauled in fill, planted a
					garden, and over the years treated the strip as her own. Her use was{" "}
					<Hi>open, continuous, and exclusive</Hi> for far longer than the
					ten-year period of <Cite kind="statute">§ 614.1(5)</Cite>.
				</p>
			</Prose>

			<MarginNote>
				She satisfies four of the five elements without difficulty. The whole
				case turns on the fifth — <strong>claim of right</strong>.
			</MarginNote>

			<Prose>
				<p>
					The dispositive question is whether her possession was under a{" "}
					<Hi>good-faith claim of right</Hi>. The evidence showed that Carpenter
					knew the disputed ground was not within her deed. She testified that
					she used it anyway, "intending to acquire it" precisely because she
					believed no one else was using it.
				</p>
			</Prose>

			<Elision label="¶¶ 9–14 omitted — survey testimony and chain of title" />

			<Prose>
				<p>
					We have long held that one who takes possession knowing the land
					belongs to another, and intending to take it regardless of the true
					owner's rights, does not possess under a good-faith claim of right.
					See <Cite kind="case">Goewey v. Urig</Cite>. A claim of right is not a
					euphemism for a knowing trespasser's hope of acquisition. To hold
					otherwise would <Hi color="violet">reward the deliberate squatter</Hi>{" "}
					over the honest but mistaken occupant the doctrine was built to
					protect.
				</p>

				<p>
					Because Carpenter possessed the strip with knowledge that it was not
					hers and with no honest belief in her title, she cannot satisfy the
					good-faith requirement. The decree denying her claim is{" "}
					<strong>affirmed</strong>.
				</p>
			</Prose>

			<MarginNote tone="contrast">
				Iowa's good-faith rule is the minority position. Most states (the
				"Connecticut" / objective view) ignore the possessor's state of mind
				entirely — hostility is measured by conduct, not conscience. We return
				to this split in <em>Note 2</em>.
			</MarginNote>
		</article>
	);
}

// --- 3.3 — a statute, with effective-date currency + a prof note -------------

function StatuteSection() {
	return (
		<article>
			<Kicker>Chapter 3 · Adverse Possession</Kicker>

			<ResourceHeader
				title="Iowa Code § 614.17A"
				citations={[{ text: "§ 614.17A", kind: "statute" }]}
				court="Claims to real estate based on possession"
				date="Effective July 1, 1992"
			/>

			<TreatmentBadge label="In force" />

			<div className="mt-6 rounded-xl border border-border bg-secondary/30 p-5 font-serif text-[15px] leading-relaxed">
				<p>
					<span className="font-semibold">1.</span> After July 1, 1992, an
					action shall not be maintained in a court, either at law or in equity,
					in order to recover or establish an interest in or claim to real
					estate if all the following conditions are satisfied:
				</p>
				<p className="mt-3 pl-5">
					<span className="font-semibold">a.</span> The action is based upon a
					claim arising more than ten years earlier or existing for more than
					ten years.
				</p>
				<p className="mt-2 pl-5">
					<span className="font-semibold">b.</span> The person and the person's
					predecessors in interest have been in continuous, open possession of
					the real estate for a period of ten years or more …
				</p>
			</div>

			<MarginNote>
				Pair this with <Cite kind="statute">§ 614.1(5)</Cite>: the limitations
				period and the possession bar work together. Note the statute speaks to{" "}
				<em>possession</em> and silence on the possessor's good faith — that
				element is judge-made, from cases like <em>Carpenter</em>.
			</MarginNote>
		</article>
	);
}

// --- 3.4 — notes & questions --------------------------------------------------

function NotesAndQuestions() {
	return (
		<article>
			<Kicker>Chapter 3 · Adverse Possession</Kicker>
			<h1 className="mt-2 font-bold text-3xl tracking-tight">
				Notes &amp; Questions
			</h1>

			<NoteItem n={1} title="What, exactly, did Carpenter do wrong?">
				She met four of the five elements decisively. Articulate the rule of{" "}
				<em>Carpenter</em> in one sentence. Would the outcome change if she had{" "}
				<em>mistakenly</em> believed the strip was within her deed?
			</NoteItem>

			<NoteItem n={2} title="The good-faith split">
				Iowa follows the minority "Maine" rule, looking to the possessor's state
				of mind. Most states follow the objective "Connecticut" rule. Which
				better serves the purposes of adverse possession — quieting stale
				titles, or rewarding productive use? Consider how each rule treats the
				honest mistaken occupant versus the knowing squatter.
			</NoteItem>

			<NoteItem n={3} title="Drafting around the doctrine">
				A client owns vacant land next to an encroaching neighbor. Using{" "}
				<Cite kind="statute">§ 614.17A</Cite>, what is the simplest step that
				resets the clock and defeats a possession claim?
			</NoteItem>
		</article>
	);
}

function Placeholder({ chapterTitle }: { chapterTitle: string }) {
	return (
		<article className="py-10 text-center">
			<BookOpenIcon className="mx-auto size-10 text-muted-foreground/50" />
			<h1 className="mt-4 font-bold text-2xl tracking-tight">{chapterTitle}</h1>
			<p className="mx-auto mt-2 max-w-sm text-muted-foreground text-sm leading-relaxed">
				This section of the casebook is part of the same structure — a mix of
				edited opinions, statutes, and the professor's own notes. Select{" "}
				<span className="font-medium text-foreground">
					Carpenter v. Ruperto
				</span>{" "}
				in the contents to see a fully annotated chapter.
			</p>
		</article>
	);
}

// ---------------------------------------------------------------------------
// Annotation & reading primitives
// ---------------------------------------------------------------------------

function Kicker({ children }: { children: ReactNode }) {
	return (
		<div className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
			{children}
		</div>
	);
}

function Prose({ children }: { children: ReactNode }) {
	return (
		<div className="mt-5 space-y-4 font-serif text-[16px] text-foreground/90 leading-[1.75]">
			{children}
		</div>
	);
}

function Speaker({ children }: { children: ReactNode }) {
	return (
		<span className="font-sans font-semibold text-[13px] uppercase tracking-wide">
			{children}{" "}
		</span>
	);
}

// A professor highlight over the source text. amber = emphasis, violet = a
// passage the note margin discusses.
function Hi({
	children,
	color = "amber",
}: {
	children: ReactNode;
	color?: "amber" | "violet";
}) {
	return (
		<mark
			className={cn(
				"rounded-[3px] px-0.5 underline decoration-2 underline-offset-2",
				color === "amber"
					? "bg-amber-100 text-foreground decoration-amber-400"
					: "bg-violet-100 text-foreground decoration-violet-400",
			)}
		>
			{children}
		</mark>
	);
}

// Inline citation chip — same language as the app (statute=blue, case=violet),
// here standing in for a real, resolvable link into the corpus.
function Cite({
	children,
	kind = "statute",
}: {
	children: ReactNode;
	kind?: "statute" | "case";
}) {
	return (
		<button
			type="button"
			className={cn(
				"mx-0.5 inline-flex items-center gap-1 rounded border px-1.5 py-px align-baseline font-sans font-medium text-[12px] no-underline transition-colors",
				kind === "case"
					? "border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100"
					: "border-primary/20 bg-primary/10 text-primary hover:bg-primary/15",
			)}
		>
			{kind === "case" ? (
				<ScaleIcon className="size-3" />
			) : (
				<ScrollTextIcon className="size-3" />
			)}
			{children}
		</button>
	);
}

// Editor's framing box at the head of a resource.
function Headnote({ children }: { children: ReactNode }) {
	return (
		<div className="mt-6 rounded-xl border border-primary/15 bg-primary/[0.04] p-4">
			<div className="flex items-center gap-1.5 font-semibold text-[11px] text-primary uppercase tracking-wider">
				<QuoteIcon className="size-3.5" />
				Editor's note
			</div>
			<p className="mt-1.5 text-[14px] text-foreground/80 leading-relaxed">
				{children}
			</p>
		</div>
	);
}

// A margin annotation tied to the adjacent passage — the vetted author's voice.
function MarginNote({
	children,
	tone = "default",
}: {
	children: ReactNode;
	tone?: "default" | "contrast";
}) {
	const contrast = tone === "contrast";
	return (
		<aside
			className={cn(
				// On xl the note floats into the reserved right gutter (xl:pr-80 on the
				// reading column); below xl it sits inline in the text flow.
				"my-5 border-l-2 py-1 pl-4 xl:clear-right xl:float-right xl:my-3 xl:-mr-80 xl:w-72",
				contrast ? "border-violet-300" : "border-amber-300",
			)}
		>
			<div
				className={cn(
					"flex items-center gap-1.5 font-medium text-[11px] uppercase tracking-wider",
					contrast ? "text-violet-700" : "text-amber-700",
				)}
			>
				<HighlighterIcon className="size-3" />
				{contrast ? "On the split" : "Prof. Whitfield"}
			</div>
			<p className="mt-1 text-[13.5px] text-foreground/75 italic leading-relaxed">
				{children}
			</p>
		</aside>
	);
}

// Casebook elision — text the editor cut, shown honestly.
function Elision({ label }: { label: string }) {
	return (
		<div className="my-6 flex items-center gap-3 text-muted-foreground">
			<div className="h-px flex-1 bg-border" />
			<span className="font-sans text-[12px] italic">[ {label} ]</span>
			<div className="h-px flex-1 bg-border" />
		</div>
	);
}

function NoteItem({
	n,
	title,
	children,
}: {
	n: number;
	title: string;
	children: ReactNode;
}) {
	return (
		<div className="mt-6 border-border border-t pt-5 first:mt-5">
			<div className="flex items-baseline gap-2.5">
				<span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-secondary font-semibold text-[12px] text-foreground tabular-nums">
					{n}
				</span>
				<h3 className="font-semibold text-[16px] tracking-tight">{title}</h3>
			</div>
			<p className="mt-2 pl-[2.1rem] text-[14.5px] text-foreground/80 leading-relaxed">
				{children}
			</p>
		</div>
	);
}

// Resource header — case/statute name, citation chips, court, date.
function ResourceHeader({
	title,
	citations,
	court,
	date,
}: {
	title: string;
	citations: { text: string; kind: "case" | "statute" }[];
	court: string;
	date: string;
}) {
	return (
		<div className="mt-2">
			<h1 className="font-bold text-3xl italic tracking-tight">{title}</h1>
			<div className="mt-2.5 flex flex-wrap items-center gap-1.5">
				{citations.map((c) => (
					<Cite key={c.text} kind={c.kind}>
						{c.text}
					</Cite>
				))}
			</div>
			<div className="mt-2 text-[13px] text-muted-foreground">
				{court} · {date}
			</div>
		</div>
	);
}

// A quiet currency line — the one thing a printed casebook can't tell you:
// is this still good law? Editorial in tone, not a verification widget.
function TreatmentBadge({
	label = "Good law",
	asOf = "June 2026",
}: {
	label?: string;
	asOf?: string;
}) {
	return (
		<div className="mt-4 flex items-center gap-2 text-[12.5px]">
			<span className="size-2 rounded-full bg-emerald-500" />
			<span className="font-semibold text-emerald-700">{label}</span>
			<span className="text-muted-foreground">in Iowa · as of {asOf}</span>
		</div>
	);
}

// Prev / next within the flattened reading order.
function SectionFooterNav({
	activeId,
	onSelect,
}: {
	activeId: string;
	onSelect: (id: string) => void;
}) {
	const idx = ALL_SECTIONS.findIndex((s) => s.id === activeId);
	const prev = ALL_SECTIONS[idx - 1];
	const next = ALL_SECTIONS[idx + 1];
	return (
		<div className="mt-12 flex items-center justify-between gap-3 border-border border-t pt-6">
			{prev ? (
				<button
					type="button"
					onClick={() => onSelect(prev.id)}
					className="group flex max-w-[45%] items-center gap-2 text-left"
				>
					<ChevronRightIcon className="size-4 rotate-180 text-muted-foreground" />
					<span className="min-w-0">
						<span className="block text-[11px] text-muted-foreground uppercase tracking-wider">
							Previous
						</span>
						<span className="block truncate text-[13px] font-medium group-hover:text-primary">
							{prev.label}
						</span>
					</span>
				</button>
			) : (
				<span />
			)}
			{next && (
				<button
					type="button"
					onClick={() => onSelect(next.id)}
					className="group flex max-w-[45%] items-center gap-2 text-right"
				>
					<span className="min-w-0">
						<span className="block text-[11px] text-muted-foreground uppercase tracking-wider">
							Next
						</span>
						<span className="block truncate text-[13px] font-medium group-hover:text-primary">
							{next.label}
						</span>
					</span>
					<ChevronRightIcon className="size-4 text-muted-foreground" />
				</button>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Ask a question — an optional, low-key study helper that answers with
// citations into this book. Quiet launcher → docked panel. Canned but live.
// ---------------------------------------------------------------------------

type ChatTurn = { id: string; role: "user" | "assistant"; node: ReactNode };

const SEED_TURNS: ChatTurn[] = [
	{
		id: "seed-q",
		role: "user",
		node: "If Carpenter possessed the strip for more than ten years, why did she lose?",
	},
	{
		id: "seed-a",
		role: "assistant",
		node: (
			<>
				<p>
					Because Iowa requires a <strong>good-faith claim of right</strong>,
					and she failed it. She satisfied the open, continuous, exclusive, and
					durational elements — but she <em>knew</em> the strip was not within
					her deed and possessed it anyway. Under{" "}
					<Cite kind="case">Carpenter v. Ruperto</Cite>, knowing possession
					defeats the good-faith requirement.
				</p>
				<p className="mt-2">
					The ten-year clock of <Cite kind="statute">§ 614.1(5)</Cite> is
					necessary but not sufficient — Iowa, unlike most states, also weighs
					the possessor's state of mind.
				</p>
			</>
		),
	},
];

function AskTheBook({
	open,
	onOpen,
	onClose,
	context,
}: {
	open: boolean;
	onOpen: () => void;
	onClose: () => void;
	context: string;
}) {
	const [turns, setTurns] = useState<ChatTurn[]>(SEED_TURNS);
	const [draft, setDraft] = useState("");
	const turnSeq = useRef(0);

	const send = () => {
		const q = draft.trim();
		if (!q) return;
		setDraft("");
		turnSeq.current += 1;
		const n = turnSeq.current;
		setTurns((t) => [
			...t,
			{ id: `q-${n}`, role: "user", node: q },
			{
				id: `a-${n}`,
				role: "assistant",
				node: (
					<>
						<p>
							Good question. The authority on point here is{" "}
							<Cite kind="case">Carpenter v. Ruperto</Cite>, read alongside{" "}
							<Cite kind="statute">§ 614.1(5)</Cite> — see the discussion and
							the notes that follow in this section.
						</p>
					</>
				),
			},
		]);
	};

	if (!open) {
		return (
			<button
				type="button"
				onClick={onOpen}
				className="fixed right-5 bottom-5 z-40 flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2.5 font-medium text-[13px] text-foreground shadow-md transition-colors hover:bg-secondary"
			>
				<MessageSquareIcon className="size-4 text-muted-foreground" />
				Ask a question
			</button>
		);
	}

	return (
		<div className="fixed right-5 bottom-5 z-40 flex h-[560px] max-h-[calc(100dvh-2.5rem)] w-[380px] max-w-[calc(100vw-2.5rem)] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
			{/* header */}
			<div className="flex items-center gap-2 border-border border-b bg-secondary/50 px-4 py-3">
				<span className="flex size-7 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
					<MessageSquareIcon className="size-4" />
				</span>
				<div className="min-w-0 flex-1">
					<div className="font-semibold text-[13px] leading-tight">
						Ask a question
					</div>
					<div className="truncate text-[11px] text-muted-foreground leading-tight">
						Reading: {context}
					</div>
				</div>
				<button
					type="button"
					onClick={onClose}
					className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
				>
					<XIcon className="size-4" />
				</button>
			</div>

			{/* transcript */}
			<div className="flex-1 space-y-3 overflow-y-auto px-3.5 py-4">
				{turns.map((t) =>
					t.role === "user" ? (
						<div key={t.id} className="flex justify-end">
							<div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-[13px] text-primary-foreground leading-relaxed">
								{t.node}
							</div>
						</div>
					) : (
						<div key={t.id}>
							<div className="rounded-2xl rounded-bl-sm bg-secondary/70 px-3.5 py-2.5 text-[13px] leading-relaxed">
								{t.node}
							</div>
						</div>
					),
				)}
			</div>

			{/* suggestion + composer */}
			<div className="border-border border-t px-3 py-3">
				<div className="mb-2 flex flex-wrap gap-1.5">
					<Suggestion onClick={setDraft}>
						Compare the Maine &amp; Connecticut rules
					</Suggestion>
					<Suggestion onClick={setDraft}>
						What resets the 10-year clock?
					</Suggestion>
				</div>
				<div className="flex items-end gap-2">
					<textarea
						rows={1}
						value={draft}
						onChange={(e) => setDraft(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === "Enter" && !e.shiftKey) {
								e.preventDefault();
								send();
							}
						}}
						placeholder="Ask about this case…"
						className="max-h-24 min-h-9 flex-1 resize-none rounded-lg border border-border bg-background px-3 py-2 text-[13px] outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
					/>
					<Button size="icon" onClick={send} disabled={!draft.trim()}>
						<SendIcon className="size-4" />
					</Button>
				</div>
				<div className="mt-2 text-center text-[10.5px] text-muted-foreground">
					Answers cite the cases and statutes in this book
				</div>
			</div>
		</div>
	);
}

function Suggestion({
	children,
	onClick,
}: {
	children: ReactNode;
	onClick: (text: string) => void;
}) {
	return (
		<button
			type="button"
			onClick={() =>
				onClick(typeof children === "string" ? children : String(children))
			}
			className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary/50 px-2.5 py-1 text-[11.5px] text-foreground/80 transition-colors hover:bg-secondary"
		>
			{children}
		</button>
	);
}
