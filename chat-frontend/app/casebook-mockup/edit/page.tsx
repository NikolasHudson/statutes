"use client";

// Open Casebook — professor authoring view (mockup)
// =================================================
//
// The contribution surface, paired with the student reader at /casebook-mockup.
// Same book, same bookish look — but in "editing" mode. It demonstrates the two
// actions a professor does most, and the two Nick asked to see:
//
//   1. ADD A PAGE — the "+ Add" menu in the contents: pull a case or statute
//      from the library (search → insert), or write a new note page.
//   2. ADD A COMMENT — select a passage in an opinion and write a margin note
//      for your students (Google-Docs-style: highlight + a comment in the rail).
//
// Everything here is client-side state so the flows actually work; the data
// shapes mirror the models we'd add server-side (Casebook → Section →
// CasebookItem(kind) + Annotation). Opinion text is an illustrative excerpt.

import {
	ArrowLeftIcon,
	BadgeCheckIcon,
	BookOpenIcon,
	CheckIcon,
	ChevronDownIcon,
	ChevronRightIcon,
	EyeIcon,
	FileTextIcon,
	GripVerticalIcon,
	HighlighterIcon,
	LinkIcon,
	type LucideIcon,
	MessageSquareIcon,
	PlusIcon,
	QuoteIcon,
	ScaleIcon,
	ScrollTextIcon,
	SearchIcon,
	Trash2Icon,
	XIcon,
} from "lucide-react";
import Link from "next/link";
import { type ReactNode, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Book structure (editable). Maps to Section + CasebookItem(kind) server-side.
// ---------------------------------------------------------------------------

type ItemKind = "note" | "case" | "statute" | "link";

type Item = { id: string; label: string; kind: ItemKind; meta?: string };
type Chapter = { id: string; number: string; title: string; items: Item[] };

const INITIAL_CHAPTERS: Chapter[] = [
	{
		id: "ch3",
		number: "3",
		title: "Acquisition by Adverse Possession",
		items: [
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
		items: [{ id: "4-1", label: "The Tacking Requirement", kind: "note" }],
	},
];

const KIND_ICON: Record<ItemKind, LucideIcon> = {
	note: BookOpenIcon,
	case: ScaleIcon,
	statute: ScrollTextIcon,
	link: LinkIcon,
};

// The "library" the Add panel searches — our live corpus, here a small
// illustrative slice of Iowa property authority.
type LibraryEntry = {
	id: string;
	kind: "case" | "statute" | "secondary";
	name: string;
	citation: string;
	sub: string;
	topic: string;
};

const LIBRARY: LibraryEntry[] = [
	{
		id: "lib-sorensen",
		kind: "case",
		name: "Sorensen v. Knott",
		citation: "320 N.W.2d 645",
		sub: "Supreme Court of Iowa · 1982",
		topic: "adverse possession · boundary by acquiescence",
	},
	{
		id: "lib-mitchell",
		kind: "case",
		name: "Mitchell v. Hawkins",
		citation: "612 N.W.2d 89",
		sub: "Supreme Court of Iowa · 2000",
		topic: "adverse possession · color of title",
	},
	{
		id: "lib-6141",
		kind: "statute",
		name: "Iowa Code § 614.1",
		citation: "§ 614.1(5)",
		sub: "Periods of limitation · ten years for real property",
		topic: "adverse possession · limitations",
	},
	{
		id: "lib-61417",
		kind: "statute",
		name: "Iowa Code § 614.17",
		citation: "§ 614.17",
		sub: "Claims to real estate based on possession",
		topic: "adverse possession · possession bar",
	},
	{
		id: "lib-restatement",
		kind: "secondary",
		name: "Restatement (First) of Property § 458",
		citation: "Restatement § 458",
		sub: "Secondary · elements of adverse possession",
		topic: "adverse possession · elements",
	},
	{
		id: "lib-pierson",
		kind: "case",
		name: "Pierson v. Post",
		citation: "3 Cai. R. 175",
		sub: "Supreme Court of New York · 1805",
		topic: "capture · first possession",
	},
];

const KIND_LABEL: Record<LibraryEntry["kind"], string> = {
	case: "Case",
	statute: "Statute",
	secondary: "Secondary",
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function EditCasebook() {
	const [chapters, setChapters] = useState<Chapter[]>(INITIAL_CHAPTERS);
	const [activeId, setActiveId] = useState("3-2"); // the comment-flow demo case
	const [libraryFor, setLibraryFor] = useState<string | null>(null); // chapter id
	const seq = useRef(0);

	const allItems = chapters.flatMap((c) => c.items);
	const active = allItems.find((i) => i.id === activeId) ?? allItems[0];

	const addItem = (chapterId: string, item: Item, select = true) => {
		setChapters((cs) =>
			cs.map((c) =>
				c.id === chapterId ? { ...c, items: [...c.items, item] } : c,
			),
		);
		if (select) setActiveId(item.id);
	};

	const writeNote = (chapterId: string) => {
		seq.current += 1;
		addItem(chapterId, {
			id: `note-${seq.current}`,
			label: "Untitled note",
			kind: "note",
		});
	};

	const addLink = (chapterId: string) => {
		seq.current += 1;
		addItem(chapterId, {
			id: `link-${seq.current}`,
			label: "New web link",
			kind: "link",
			meta: "External source",
		});
	};

	const addFromLibrary = (chapterId: string, entry: LibraryEntry) => {
		seq.current += 1;
		addItem(
			chapterId,
			{
				id: `lib-${seq.current}`,
				label: entry.name,
				kind: entry.kind === "secondary" ? "note" : entry.kind,
				meta: entry.citation,
			},
			false,
		);
	};

	return (
		<div className="min-h-dvh bg-background text-foreground">
			<EditorTopBar />

			<div className="mx-auto flex max-w-[1440px]">
				<EditToc
					chapters={chapters}
					activeId={activeId}
					onSelect={setActiveId}
					onWriteNote={writeNote}
					onAddLink={addLink}
					onOpenLibrary={setLibraryFor}
				/>

				<main className="min-w-0 flex-1">
					<div className="mx-auto w-full max-w-[82rem] px-6 py-8 sm:px-10 lg:py-10">
						<Canvas
							item={active}
							onInsertFromLibrary={() => setLibraryFor(chapters[0]?.id ?? null)}
						/>
					</div>
				</main>
			</div>

			{libraryFor && (
				<LibraryPanel
					existing={new Set(allItems.map((i) => i.label))}
					onAdd={(entry) => addFromLibrary(libraryFor, entry)}
					onClose={() => setLibraryFor(null)}
				/>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Top bar — editing mode: back, title + "Editing" pill, preview, publish
// ---------------------------------------------------------------------------

function EditorTopBar() {
	return (
		<header className="sticky top-0 z-30 border-border border-b bg-card/85 backdrop-blur">
			<div className="mx-auto flex max-w-[1440px] items-center gap-3 px-4 py-2.5 sm:px-6">
				<Link
					href="/casebook-mockup"
					className="flex items-center gap-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
				>
					<ArrowLeftIcon className="size-4" />
					<span className="hidden sm:inline">Back</span>
				</Link>

				<div className="mx-1 h-5 w-px bg-border" />

				<span className="bg-black px-2.5 py-1 font-bold text-[13px] text-white uppercase tracking-[0.06em]">
					Hudson
				</span>

				<div className="flex min-w-0 items-center gap-2.5">
					<span className="truncate font-semibold text-[14px] tracking-tight">
						Iowa Property Law
					</span>
					<span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 font-semibold text-[11px] text-amber-700">
						<PenLikeDot />
						Editing
					</span>
				</div>

				<div className="ml-auto flex items-center gap-2">
					<span className="hidden text-[12px] text-muted-foreground sm:inline">
						Draft · saved
					</span>
					<Button asChild size="sm" variant="outline">
						<Link href="/casebook-mockup">
							<EyeIcon className="size-4" />
							Preview
						</Link>
					</Button>
					<Button size="sm">Publish</Button>
				</div>
			</div>
		</header>
	);
}

function PenLikeDot() {
	return <span className="size-1.5 rounded-full bg-amber-500" />;
}

// ---------------------------------------------------------------------------
// Contents (left rail) — reorder handles + the "+ Add" menu per chapter
// ---------------------------------------------------------------------------

function EditToc({
	chapters,
	activeId,
	onSelect,
	onWriteNote,
	onAddLink,
	onOpenLibrary,
}: {
	chapters: Chapter[];
	activeId: string;
	onSelect: (id: string) => void;
	onWriteNote: (chapterId: string) => void;
	onAddLink: (chapterId: string) => void;
	onOpenLibrary: (chapterId: string) => void;
}) {
	return (
		<aside className="sticky top-[57px] hidden h-[calc(100dvh-57px)] w-72 shrink-0 overflow-y-auto border-border border-r bg-sidebar/40 lg:block">
			<div className="border-border border-b px-5 py-4">
				<div className="font-bold text-[16px] leading-snug tracking-tight">
					Contents
				</div>
				<div className="mt-2.5 flex items-center gap-2 text-[12px] text-muted-foreground">
					<span className="flex size-6 items-center justify-center rounded-full bg-primary/10 font-semibold text-[11px] text-primary">
						DW
					</span>
					<span className="flex items-center gap-1">
						Editing as Prof. Whitfield
						<BadgeCheckIcon className="size-3.5 text-primary" />
					</span>
				</div>
			</div>

			<nav className="px-3 py-3">
				{chapters.map((c) => (
					<TocChapter
						key={c.id}
						chapter={c}
						activeId={activeId}
						onSelect={onSelect}
						onWriteNote={onWriteNote}
						onAddLink={onAddLink}
						onOpenLibrary={onOpenLibrary}
					/>
				))}

				<button
					type="button"
					className="mt-2 flex w-full items-center gap-1.5 rounded-md px-2 py-2 text-[12.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
				>
					<PlusIcon className="size-4" />
					New chapter
				</button>
			</nav>
		</aside>
	);
}

function TocChapter({
	chapter,
	activeId,
	onSelect,
	onWriteNote,
	onAddLink,
	onOpenLibrary,
}: {
	chapter: Chapter;
	activeId: string;
	onSelect: (id: string) => void;
	onWriteNote: (chapterId: string) => void;
	onAddLink: (chapterId: string) => void;
	onOpenLibrary: (chapterId: string) => void;
}) {
	const [open, setOpen] = useState(true);
	const [menuOpen, setMenuOpen] = useState(false);

	return (
		<div className="mb-1">
			<div className="flex items-center gap-1 rounded-md pr-1 hover:bg-secondary/60">
				<button
					type="button"
					onClick={() => setOpen((o) => !o)}
					className="flex min-w-0 flex-1 items-center gap-1.5 px-2 py-1.5 text-left"
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

				{/* + Add menu */}
				<div className="relative">
					<button
						type="button"
						title="Add to chapter"
						onClick={() => setMenuOpen((m) => !m)}
						className={cn(
							"flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
							menuOpen && "bg-secondary text-foreground",
						)}
					>
						<PlusIcon className="size-4" />
					</button>

					{menuOpen && (
						<>
							{/* click-away */}
							<button
								type="button"
								aria-label="Close menu"
								className="fixed inset-0 z-10 cursor-default"
								onClick={() => setMenuOpen(false)}
							/>
							<div className="absolute right-0 z-20 mt-1 w-56 overflow-hidden rounded-lg border border-border bg-popover py-1 shadow-lg">
								<AddMenuRow
									icon={SearchIcon}
									title="From the library"
									desc="A case, statute, or rule"
									onClick={() => {
										setMenuOpen(false);
										onOpenLibrary(chapter.id);
									}}
								/>
								<AddMenuRow
									icon={FileTextIcon}
									title="Write a note"
									desc="Your own text page"
									onClick={() => {
										setMenuOpen(false);
										onWriteNote(chapter.id);
									}}
								/>
								<AddMenuRow
									icon={LinkIcon}
									title="Add a web link"
									desc="Link to an outside source"
									onClick={() => {
										setMenuOpen(false);
										onAddLink(chapter.id);
									}}
								/>
							</div>
						</>
					)}
				</div>
			</div>

			{open && (
				<ul className="mt-0.5 mb-2 ml-3 border-border border-l pl-1.5">
					{chapter.items.map((it) => {
						const Icon = KIND_ICON[it.kind];
						const isActive = it.id === activeId;
						return (
							<li key={it.id}>
								<button
									type="button"
									onClick={() => onSelect(it.id)}
									className={cn(
										"group flex w-full items-start gap-1.5 rounded-md px-1.5 py-1.5 text-left transition-colors",
										isActive
											? "bg-primary/10 text-primary"
											: "text-foreground/80 hover:bg-secondary",
									)}
								>
									<GripVerticalIcon className="mt-0.5 size-3.5 shrink-0 text-transparent group-hover:text-muted-foreground/60" />
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
											{it.label}
										</span>
										{it.meta && (
											<span className="block text-[11px] text-muted-foreground leading-tight">
												{it.meta}
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

function AddMenuRow({
	icon: Icon,
	title,
	desc,
	onClick,
}: {
	icon: LucideIcon;
	title: string;
	desc: string;
	onClick: () => void;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className="flex w-full items-start gap-2.5 px-3 py-2 text-left transition-colors hover:bg-secondary"
		>
			<Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
			<span>
				<span className="block font-medium text-[13px]">{title}</span>
				<span className="block text-[11px] text-muted-foreground">{desc}</span>
			</span>
		</button>
	);
}

// ---------------------------------------------------------------------------
// Canvas — switches on the selected item
// ---------------------------------------------------------------------------

function Canvas({
	item,
	onInsertFromLibrary,
}: {
	item: Item;
	onInsertFromLibrary: () => void;
}) {
	if (item.id === "3-2") return <CaseEditor />;
	if (item.id.startsWith("note-"))
		return (
			<NoteEditor key={item.id} onInsertFromLibrary={onInsertFromLibrary} />
		);
	const justAdded = item.id.startsWith("lib-") || item.id.startsWith("link-");
	return <GenericEditor item={item} justAdded={justAdded} />;
}

// --- ADD A COMMENT: the annotated case editor --------------------------------

type Comment = { id: string; quote: string; body: string; author: string };

const SEED_COMMENTS: Comment[] = [
	{
		id: "c-seed",
		quote: "the fifth element — claim of right",
		body: "Four elements are easy here; this is the one Carpenter fails. Make sure you can state why.",
		author: "Prof. Whitfield",
	},
];

const SELECTED_QUOTE = "good-faith claim of right";

function CaseEditor() {
	const [comments, setComments] = useState<Comment[]>(SEED_COMMENTS);
	const [composerOpen, setComposerOpen] = useState(true);
	const [draft, setDraft] = useState("");
	const [toolbar, setToolbar] = useState(true); // selection toolbar visible
	const seq = useRef(0);

	const save = () => {
		const body = draft.trim();
		if (!body) return;
		seq.current += 1;
		setComments((c) => [
			...c,
			{
				id: `c-${seq.current}`,
				quote: SELECTED_QUOTE,
				body,
				author: "Prof. Whitfield",
			},
		]);
		setDraft("");
		setComposerOpen(false);
	};

	const openComposer = () => {
		setComposerOpen(true);
		setToolbar(true);
	};

	return (
		<div>
			{/* Resource header (editable affordances) */}
			<div className="flex items-start justify-between gap-4">
				<div>
					<div className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						Chapter 3 · Adverse Possession
					</div>
					<h1 className="mt-1.5 font-bold text-3xl italic tracking-tight">
						Carpenter v. Ruperto
					</h1>
					<div className="mt-1.5 text-[13px] text-muted-foreground">
						315 N.W.2d 782 (Iowa 1982) · Supreme Court of Iowa
					</div>
				</div>
				<span className="hidden shrink-0 items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1 text-[12px] text-muted-foreground sm:inline-flex">
					<ScaleIcon className="size-3.5" />
					Case · from the library
				</span>
			</div>

			<div className="mt-6 grid gap-x-10 xl:grid-cols-[minmax(0,1fr)_19rem]">
				{/* Opinion text with a live "selection" */}
				<article className="font-serif text-[16px] text-foreground/90 leading-[1.8]">
					<p>
						This is an action to quiet title to a disputed strip of land. The
						plaintiff cleared the adjoining ground, planted a garden, and for
						far longer than the ten-year period treated the strip as her own.
						Her use was open, continuous, and exclusive.
					</p>

					<p className="mt-4">
						The dispositive question is whether her possession was under a{" "}
						<SelectedText
							active={toolbar}
							onComment={openComposer}
							onDismiss={() => setToolbar(false)}
						>
							{SELECTED_QUOTE}
						</SelectedText>
						. The evidence showed she knew the disputed ground was not within
						her deed, and used it anyway, intending to acquire it.
					</p>

					<p className="mt-4">
						One who takes possession knowing the land belongs to another does
						not possess under{" "}
						<Existing>{"the fifth element — claim of right"}</Existing>. To hold
						otherwise would reward the deliberate squatter over the honest but
						mistaken occupant the doctrine was built to protect. The decree
						denying her claim is <strong>affirmed</strong>.
					</p>

					<div className="mt-6 text-[13px] text-muted-foreground italic">
						Tip: select any text in an opinion to highlight it, add a note for
						your students, or hide a passage from the assigned reading.
					</div>
				</article>

				{/* Comments rail — existing notes + the composer */}
				<aside className="mt-8 xl:mt-0">
					<div className="flex items-center justify-between">
						<h2 className="font-semibold text-[13px] text-muted-foreground uppercase tracking-wider">
							Notes &amp; comments
						</h2>
						<button
							type="button"
							onClick={openComposer}
							className="flex items-center gap-1 text-[12px] font-medium text-primary hover:underline"
						>
							<PlusIcon className="size-3.5" />
							Add note
						</button>
					</div>

					<div className="mt-3 space-y-3">
						{comments.map((c) => (
							<CommentCard
								key={c.id}
								comment={c}
								onDelete={() =>
									setComments((cs) => cs.filter((x) => x.id !== c.id))
								}
							/>
						))}

						{composerOpen && (
							<Composer
								quote={SELECTED_QUOTE}
								value={draft}
								onChange={setDraft}
								onSave={save}
								onCancel={() => {
									setComposerOpen(false);
									setDraft("");
								}}
							/>
						)}
					</div>
				</aside>
			</div>
		</div>
	);
}

// A passage shown as if the professor just selected it: highlighted, with a
// small floating toolbar (Highlight · Comment · Hide).
function SelectedText({
	children,
	active,
	onComment,
	onDismiss,
}: {
	children: ReactNode;
	active: boolean;
	onComment: () => void;
	onDismiss: () => void;
}) {
	return (
		<span className="relative">
			<button
				type="button"
				onClick={active ? onDismiss : onComment}
				className="rounded-[3px] bg-primary/20 px-0.5 text-foreground ring-1 ring-primary/30"
			>
				{children}
			</button>

			{active && (
				<span className="-translate-x-1/2 absolute bottom-full left-1/2 z-20 mb-2 flex items-center gap-0.5 rounded-lg border border-border bg-popover p-1 font-sans shadow-lg">
					<ToolbarButton icon={HighlighterIcon} label="Highlight" />
					<ToolbarButton
						icon={MessageSquareIcon}
						label="Comment"
						highlight
						onClick={onComment}
					/>
					<ToolbarButton icon={EyeIcon} label="Hide" />
					{/* little caret */}
					<span className="-bottom-1 -translate-x-1/2 absolute left-1/2 size-2 rotate-45 border-border border-r border-b bg-popover" />
				</span>
			)}
		</span>
	);
}

function ToolbarButton({
	icon: Icon,
	label,
	highlight,
	onClick,
}: {
	icon: LucideIcon;
	label: string;
	highlight?: boolean;
	onClick?: () => void;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"flex items-center gap-1 rounded-md px-2 py-1 text-[12px] font-medium transition-colors",
				highlight
					? "text-primary hover:bg-primary/10"
					: "text-foreground/70 hover:bg-secondary",
			)}
		>
			<Icon className="size-3.5" />
			{label}
		</button>
	);
}

// An already-annotated phrase in the body (amber underline).
function Existing({ children }: { children: ReactNode }) {
	return (
		<mark className="rounded-[3px] bg-amber-100 px-0.5 text-foreground underline decoration-2 decoration-amber-400 underline-offset-2">
			{children}
		</mark>
	);
}

function CommentCard({
	comment,
	onDelete,
}: {
	comment: Comment;
	onDelete: () => void;
}) {
	return (
		<div className="group rounded-lg border border-border bg-card p-3">
			<div className="border-amber-300 border-l-2 pl-2 text-[12px] text-muted-foreground italic">
				“{comment.quote}”
			</div>
			<p className="mt-2 text-[13px] leading-relaxed">{comment.body}</p>
			<div className="mt-2 flex items-center justify-between">
				<div className="flex items-center gap-1 text-[11px] text-muted-foreground">
					<span className="flex size-4 items-center justify-center rounded-full bg-primary/10 font-semibold text-[9px] text-primary">
						DW
					</span>
					{comment.author}
				</div>
				<button
					type="button"
					onClick={onDelete}
					className="text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
					title="Delete note"
				>
					<Trash2Icon className="size-3.5" />
				</button>
			</div>
		</div>
	);
}

function Composer({
	quote,
	value,
	onChange,
	onSave,
	onCancel,
}: {
	quote: string;
	value: string;
	onChange: (v: string) => void;
	onSave: () => void;
	onCancel: () => void;
}) {
	return (
		<div className="rounded-lg border border-primary/40 bg-card p-3 shadow-sm ring-1 ring-primary/10">
			<div className="border-primary/40 border-l-2 pl-2 text-[12px] text-muted-foreground italic">
				“{quote}”
			</div>
			<textarea
				rows={3}
				value={value}
				onChange={(e) => onChange(e.target.value)}
				placeholder="Add a note for your students…"
				className="mt-2 w-full resize-none rounded-md border border-border bg-background px-2.5 py-2 text-[13px] outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
			/>
			<div className="mt-2 flex items-center justify-end gap-2">
				<Button size="sm" variant="ghost" onClick={onCancel}>
					Cancel
				</Button>
				<Button size="sm" onClick={onSave} disabled={!value.trim()}>
					<CheckIcon className="size-4" />
					Add note
				</Button>
			</div>
		</div>
	);
}

// --- ADD A PAGE: a freshly-created note page ---------------------------------

function NoteEditor({
	onInsertFromLibrary,
}: {
	onInsertFromLibrary: () => void;
}) {
	const [title, setTitle] = useState("");
	const [body, setBody] = useState("");

	return (
		<div className="mx-auto max-w-3xl">
			<div className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
				New note page
			</div>

			<input
				value={title}
				onChange={(e) => setTitle(e.target.value)}
				placeholder="Note title — e.g. The Doctrine in Brief"
				className="mt-3 w-full bg-transparent font-bold text-3xl tracking-tight outline-none placeholder:text-muted-foreground/40"
			/>

			{/* faux formatting toolbar — bookish, not techy */}
			<div className="mt-4 flex items-center gap-1 border-border border-y py-1.5">
				<FmtButton label="B" className="font-bold" />
				<FmtButton label="I" className="italic" />
				<span className="mx-1 h-4 w-px bg-border" />
				<FmtIcon icon={QuoteIcon} />
				<FmtIcon icon={LinkIcon} />
				<span className="mx-1 h-4 w-px bg-border" />
				<button
					type="button"
					onClick={onInsertFromLibrary}
					className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[12.5px] font-medium text-primary transition-colors hover:bg-primary/10"
				>
					<PlusIcon className="size-3.5" />
					Insert a case or statute
				</button>
			</div>

			<textarea
				value={body}
				onChange={(e) => setBody(e.target.value)}
				rows={14}
				placeholder="Write your note — frame the doctrine, give practical context, or pose the questions you want your students chewing on before class…"
				className="mt-5 w-full resize-none bg-transparent font-serif text-[16px] leading-[1.8] outline-none placeholder:text-muted-foreground/50"
			/>
		</div>
	);
}

function FmtButton({
	label,
	className,
}: {
	label: string;
	className?: string;
}) {
	return (
		<button
			type="button"
			className={cn(
				"flex size-7 items-center justify-center rounded-md text-[14px] text-foreground/70 transition-colors hover:bg-secondary",
				className,
			)}
		>
			{label}
		</button>
	);
}

function FmtIcon({ icon: Icon }: { icon: LucideIcon }) {
	return (
		<button
			type="button"
			className="flex size-7 items-center justify-center rounded-md text-foreground/70 transition-colors hover:bg-secondary"
		>
			<Icon className="size-4" />
		</button>
	);
}

// --- a just-added library item (case/statute/link) ---------------------------

function GenericEditor({
	item,
	justAdded,
}: {
	item: Item;
	justAdded: boolean;
}) {
	const Icon = KIND_ICON[item.kind];
	return (
		<div className="mx-auto max-w-3xl">
			{justAdded && (
				<div className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
					<CheckIcon className="size-3" strokeWidth={3} />
					Added to the book
				</div>
			)}
			<div className={cn("flex items-start gap-3", justAdded && "mt-4")}>
				<span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
					<Icon className="size-5" />
				</span>
				<div>
					<h1 className="font-bold text-2xl tracking-tight">{item.label}</h1>
					{item.meta && (
						<div className="mt-1 text-[13px] text-muted-foreground">
							{item.meta}
						</div>
					)}
				</div>
			</div>
			<p className="mt-6 font-serif text-[16px] text-foreground/80 leading-[1.8]">
				{justAdded
					? "The full text came straight from the library, already linked and carrying its currency line. From here you'd select passages to highlight, comment on, or trim — exactly as on the Carpenter v. Ruperto page."
					: "This page is part of the book. Select any passage to highlight or add a note, or edit the text directly — the same tools as every other page."}
			</p>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Library panel — search the corpus, insert into the book
// ---------------------------------------------------------------------------

function LibraryPanel({
	existing,
	onAdd,
	onClose,
}: {
	existing: Set<string>;
	onAdd: (entry: LibraryEntry) => void;
	onClose: () => void;
}) {
	const [query, setQuery] = useState("adverse possession");
	const [added, setAdded] = useState<Set<string>>(new Set());

	const q = query.trim().toLowerCase();
	const results = q
		? LIBRARY.filter((e) =>
				`${e.name} ${e.citation} ${e.topic}`.toLowerCase().includes(q),
			)
		: LIBRARY;

	return (
		<>
			<button
				type="button"
				aria-label="Close library"
				onClick={onClose}
				className="fixed inset-0 z-40 cursor-default bg-foreground/20"
			/>
			<div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[440px] flex-col border-border border-l bg-card shadow-2xl">
				<div className="flex items-center justify-between border-border border-b px-5 py-4">
					<div>
						<div className="font-semibold text-[15px] tracking-tight">
							Add from the library
						</div>
						<div className="text-[12px] text-muted-foreground">
							Iowa cases, statutes &amp; rules — already linked and citable
						</div>
					</div>
					<button
						type="button"
						onClick={onClose}
						className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
					>
						<XIcon className="size-4" />
					</button>
				</div>

				<div className="border-border border-b px-5 py-3">
					<div className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
						<SearchIcon className="size-4 shrink-0 text-muted-foreground" />
						<input
							value={query}
							onChange={(e) => setQuery(e.target.value)}
							placeholder="Search the corpus…"
							className="min-w-0 flex-1 bg-transparent text-[13px] outline-none"
						/>
						{query && (
							<button
								type="button"
								onClick={() => setQuery("")}
								className="text-muted-foreground hover:text-foreground"
							>
								<XIcon className="size-3.5" />
							</button>
						)}
					</div>
				</div>

				<div className="flex-1 overflow-y-auto px-3 py-3">
					<div className="px-2 pb-2 text-[11px] text-muted-foreground uppercase tracking-wider">
						{results.length} result{results.length === 1 ? "" : "s"}
					</div>
					<div className="space-y-1.5">
						{results.map((e) => {
							const inBook = existing.has(e.name) || added.has(e.id);
							const Icon =
								e.kind === "statute"
									? ScrollTextIcon
									: e.kind === "secondary"
										? BookOpenIcon
										: ScaleIcon;
							return (
								<div
									key={e.id}
									className="flex items-start gap-3 rounded-lg border border-transparent p-2.5 transition-colors hover:border-border hover:bg-secondary/40"
								>
									<span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
										<Icon className="size-4" />
									</span>
									<div className="min-w-0 flex-1">
										<div className="flex items-center gap-2">
											<span className="truncate font-semibold text-[13.5px] italic">
												{e.name}
											</span>
											<span className="shrink-0 rounded bg-secondary px-1.5 py-px text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
												{KIND_LABEL[e.kind]}
											</span>
										</div>
										<div className="text-[12px] text-muted-foreground">
											{e.citation} · {e.sub}
										</div>
									</div>
									<Button
										size="xs"
										variant={inBook ? "ghost" : "outline"}
										disabled={inBook}
										onClick={() => {
											onAdd(e);
											setAdded((s) => new Set(s).add(e.id));
										}}
										className="mt-0.5 shrink-0"
									>
										{inBook ? (
											<>
												<CheckIcon className="size-3.5" />
												Added
											</>
										) : (
											<>
												<PlusIcon className="size-3.5" />
												Add
											</>
										)}
									</Button>
								</div>
							);
						})}

						{results.length === 0 && (
							<div className="px-2 py-10 text-center text-[13px] text-muted-foreground">
								Nothing matches “{query}”.
							</div>
						)}
					</div>
				</div>

				<div className="border-border border-t px-5 py-3 text-center text-[11px] text-muted-foreground">
					Added items drop into the chapter you chose — edit and annotate them
					just like any other page.
				</div>
			</div>
		</>
	);
}
