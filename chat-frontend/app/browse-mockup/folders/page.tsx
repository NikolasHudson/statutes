"use client";

// Design mockup for "Folders" — a Westlaw/Lexis-grade saved-research workspace
// where a user files cases, statutes, court rules, saved searches, and notes
// into named (and nestable) folders. Self-contained on its own route
// (/browse-mockup/folders) so it can be shown and iterated on without touching
// the live app. Two panes: a folder tree on the left (with counts, nesting, and
// a "New folder" affordance) and the selected folder's contents on the right
// (header + meta + per-item rows). A header dropdown demonstrates the
// "Save to folder" control as it would appear from a case/statute page — the
// entry point that puts items here. All data is illustrative mock content; the
// royal accent + higher-contrast light palette are the app-wide light theme.

import {
	ArrowUpDownIcon,
	CheckIcon,
	ChevronDownIcon,
	ChevronRightIcon,
	ClockIcon,
	FilePlus2Icon,
	FolderIcon,
	FolderOpenIcon,
	FolderPlusIcon,
	GavelIcon,
	LandmarkIcon,
	type LucideIcon,
	MoreHorizontalIcon,
	PencilIcon,
	PlusIcon,
	ScaleIcon,
	SearchIcon,
	Share2Icon,
	StarIcon,
	StickyNoteIcon,
	Trash2Icon,
	UsersIcon,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { MockupSidebar } from "@/components/browse/mockup-sidebar";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuCheckboxItem,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import {
	SidebarInset,
	SidebarProvider,
	SidebarTrigger,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Mock data model — a saved item is anything you can file: a case, a statute,
// a court rule, a saved search, or a free-text note.
// ---------------------------------------------------------------------------

type ItemKind = "case" | "statute" | "rule" | "search" | "note";

type SavedItem = {
	id: string;
	kind: ItemKind;
	title: string;
	subtitle: string; // citation / court / scope line
	note?: string; // user annotation
	savedAt: string;
};

type Folder = {
	id: string;
	name: string;
	description?: string;
	shared?: { with: string; people: number };
	starred?: boolean;
	updatedAt: string;
	items: SavedItem[];
	children?: Folder[];
};

const KIND_VIEW: Record<
	ItemKind,
	{ icon: LucideIcon; label: string; tint: string }
> = {
	case: { icon: ScaleIcon, label: "Case", tint: "text-primary bg-primary/10" },
	statute: {
		icon: LandmarkIcon,
		label: "Statute",
		tint: "text-emerald-700 bg-emerald-600/10",
	},
	rule: {
		icon: GavelIcon,
		label: "Court rule",
		tint: "text-amber-700 bg-amber-600/10",
	},
	search: {
		icon: SearchIcon,
		label: "Saved search",
		tint: "text-violet-700 bg-violet-600/10",
	},
	note: {
		icon: StickyNoteIcon,
		label: "Note",
		tint: "text-rose-700 bg-rose-600/10",
	},
};

// Illustrative folders tuned to the live Iowa corpus (cases w/ N.W.2d cites,
// Iowa Code sections, court rules). "Untitled folder" is intentionally empty so
// the empty state is visible.
const FOLDERS: Folder[] = [
	{
		id: "cpa",
		name: "Consumer Fraud — Hy-Vee Matter",
		description:
			"Working file for the Iowa Consumer Fraud Act claim. Private right of action, damages, and AG-enforcement authorities.",
		shared: { with: "Litigation team", people: 3 },
		starred: true,
		updatedAt: "2 hours ago",
		items: [
			{
				id: "i1",
				kind: "case",
				title: "State ex rel. Miller v. Pace",
				subtitle: "677 N.W.2d 761 · Iowa Supreme Court · 2004",
				note: "AG enforcement scope under 714.16 — quote ¶ 18.",
				savedAt: "2 hours ago",
			},
			{
				id: "i2",
				kind: "case",
				title: "State v. Vanover",
				subtitle: "559 N.W.2d 618 · Iowa Supreme Court · 1997",
				note: "Pattern/practice element. Good on intent.",
				savedAt: "Today, 9:14 AM",
			},
			{
				id: "i3",
				kind: "statute",
				title: "Iowa Code § 714.16 — Consumer frauds",
				subtitle: "Statutes & Codes · 2025 edition",
				note: "Core CPA provision. Compare 2023 vs 2025 text.",
				savedAt: "Yesterday",
			},
			{
				id: "i4",
				kind: "statute",
				title: "Iowa Code ch. 714H — Private Right of Action",
				subtitle: "Statutes & Codes · 2025 edition",
				savedAt: "Yesterday",
			},
			{
				id: "i5",
				kind: "search",
				title: '"private right of action" AND consumer fraud',
				subtitle: "Case law · All Iowa courts · 24 results",
				savedAt: "2 days ago",
			},
			{
				id: "i6",
				kind: "note",
				title: "Elements memo — §714.16 claim",
				subtitle: "Note · 3 paragraphs",
				note: "Draft elements list + damages theory for MSJ brief.",
				savedAt: "3 days ago",
			},
		],
		children: [
			{
				id: "cpa-damages",
				name: "Damages & Remedies",
				updatedAt: "Yesterday",
				items: [
					{
						id: "d1",
						kind: "case",
						title: "Wright v. Brooke Group Ltd.",
						subtitle: "652 N.W.2d 159 · Iowa Supreme Court · 2002",
						savedAt: "Yesterday",
					},
					{
						id: "d2",
						kind: "rule",
						title: "Iowa R. Civ. P. 1.961 — Computation of damages",
						subtitle: "Court Rules · Civil Procedure",
						savedAt: "4 days ago",
					},
				],
			},
			{
				id: "cpa-class",
				name: "Class Certification",
				updatedAt: "1 week ago",
				items: [
					{
						id: "c1",
						kind: "rule",
						title: "Iowa R. Civ. P. 1.261 — Class actions",
						subtitle: "Court Rules · Civil Procedure",
						savedAt: "1 week ago",
					},
				],
			},
		],
	},
	{
		id: "premises",
		name: "Premises Liability Research",
		description:
			"General negligence / duty-of-care authorities for retail slip-and-fall.",
		starred: false,
		updatedAt: "Yesterday",
		items: [
			{
				id: "p1",
				kind: "case",
				title: "Koenig v. Koenig",
				subtitle: "766 N.W.2d 635 · Iowa Supreme Court · 2009",
				note: "Abolished invitee/licensee distinction.",
				savedAt: "Yesterday",
			},
			{
				id: "p2",
				kind: "case",
				title: "Benham v. King",
				subtitle: "700 N.W.2d 314 · Iowa Supreme Court · 2005",
				savedAt: "5 days ago",
			},
			{
				id: "p3",
				kind: "note",
				title: "Open & obvious doctrine — status in Iowa",
				subtitle: "Note · 1 paragraph",
				savedAt: "5 days ago",
			},
		],
	},
	{
		id: "statint",
		name: "Statutory Interpretation",
		description: "Canons, legislative history, and edition-diff exhibits.",
		updatedAt: "3 days ago",
		items: [
			{
				id: "s1",
				kind: "case",
				title: "State v. Iowa Dist. Court",
				subtitle: "889 N.W.2d 467 · Iowa Supreme Court · 2017",
				savedAt: "3 days ago",
			},
			{
				id: "s2",
				kind: "search",
				title: "plain meaning OR legislative intent",
				subtitle: "Case law · Iowa Supreme Court · 61 results",
				savedAt: "3 days ago",
			},
		],
	},
	{
		id: "untitled",
		name: "Untitled folder",
		updatedAt: "Just now",
		items: [],
	},
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function FoldersMockupPage() {
	const [selectedId, setSelectedId] = useState<string>("cpa");
	const [expanded, setExpanded] = useState<Set<string>>(new Set(["cpa"]));
	const [filterText, setFilterText] = useState("");
	const [kindFilter, setKindFilter] = useState<ItemKind | "all">("all");
	const [checked, setChecked] = useState<Set<string>>(new Set());

	// Flatten the tree so a subfolder id resolves to its folder object.
	const flat = useMemo(() => {
		const out: Folder[] = [];
		const walk = (fs: Folder[]) => {
			for (const f of fs) {
				out.push(f);
				if (f.children) walk(f.children);
			}
		};
		walk(FOLDERS);
		return out;
	}, []);

	const selected = flat.find((f) => f.id === selectedId) ?? FOLDERS[0];

	const totalFolders = flat.length;
	const totalItems = flat.reduce((n, f) => n + f.items.length, 0);

	const visibleItems = selected.items.filter(
		(it) => kindFilter === "all" || it.kind === kindFilter,
	);

	const toggleExpand = (id: string) =>
		setExpanded((prev) => {
			const next = new Set(prev);
			next.has(id) ? next.delete(id) : next.add(id);
			return next;
		});

	const select = (id: string) => {
		setSelectedId(id);
		setChecked(new Set());
		setKindFilter("all");
	};

	const toggleCheck = (id: string) =>
		setChecked((prev) => {
			const next = new Set(prev);
			next.has(id) ? next.delete(id) : next.add(id);
			return next;
		});

	const allChecked =
		visibleItems.length > 0 && visibleItems.every((it) => checked.has(it.id));

	return (
		<SidebarProvider>
			<div className="flex h-dvh w-full pr-0.5">
				<MockupSidebar />
				<SidebarInset>
					<header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
						<SidebarTrigger />
						<Separator orientation="vertical" className="mr-1 h-4" />
						<span className="font-medium text-sm">Folders</span>
						<span className="ml-auto hidden text-muted-foreground text-xs sm:inline">
							{totalFolders} folders · {totalItems} saved items
						</span>
					</header>

					<main className="min-w-0 flex-1 overflow-y-auto">
						<div className="mx-auto max-w-6xl px-5 py-5">
							{/* ---- Utility bar: title + actions ---------------------- */}
							<div className="flex items-end justify-between gap-4">
								<div className="min-w-0">
									<h1 className="font-semibold text-xl tracking-tight">
										Folders
									</h1>
									<p className="mt-0.5 truncate text-muted-foreground text-xs">
										Organize saved cases, statutes, rules, searches, and notes.
									</p>
								</div>
								<div className="flex shrink-0 items-center gap-1">
									<SaveToFolderDemo />
									<Button size="sm" className="h-8 gap-1.5">
										<FolderPlusIcon className="size-3.5" />
										New folder
									</Button>
								</div>
							</div>

							{/* ---- Two-pane: folder tree + folder contents ---------- */}
							<div className="mt-4 grid gap-5 lg:grid-cols-[16rem_1fr]">
								{/* Folder tree */}
								<aside className="space-y-3">
									<div className="overflow-hidden rounded-lg border bg-card">
										<div className="relative border-b">
											<SearchIcon className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-3 size-3.5 text-muted-foreground" />
											<input
												value={filterText}
												onChange={(e) => setFilterText(e.target.value)}
												placeholder="Filter folders…"
												aria-label="Filter folders"
												className="h-9 w-full bg-transparent pr-3 pl-8 text-[13px] outline-none placeholder:text-muted-foreground"
											/>
										</div>
										<nav className="p-1.5">
											{FOLDERS.filter((f) =>
												f.name.toLowerCase().includes(filterText.toLowerCase()),
											).map((f) => (
												<FolderRow
													key={f.id}
													folder={f}
													depth={0}
													selectedId={selectedId}
													expanded={expanded}
													onSelect={select}
													onToggle={toggleExpand}
												/>
											))}
										</nav>
										<div className="border-t p-1.5">
											<button
												type="button"
												className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[13px] text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
											>
												<PlusIcon className="size-3.5" />
												New folder
											</button>
										</div>
									</div>

									{/* Secondary collections */}
									<div className="overflow-hidden rounded-lg border bg-card p-1.5">
										<SideLink
											icon={UsersIcon}
											label="Shared with me"
											count={2}
										/>
										<SideLink icon={StarIcon} label="Starred" count={1} />
										<SideLink icon={ClockIcon} label="Recently saved" />
										<SideLink icon={Trash2Icon} label="Trash" />
									</div>
								</aside>

								{/* Folder contents */}
								<section className="min-w-0">
									{/* Folder header */}
									<div className="rounded-lg border bg-card">
										<div className="flex items-start gap-3 p-4">
											<span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
												<FolderOpenIcon className="size-5" />
											</span>
											<div className="min-w-0 flex-1">
												<div className="flex items-center gap-2">
													<Link
														href="#"
														className="text-muted-foreground text-xs hover:text-foreground"
													>
														Folders
													</Link>
													<ChevronRightIcon className="size-3 text-muted-foreground/50" />
													<span className="truncate text-muted-foreground text-xs">
														{selected.name}
													</span>
												</div>
												<div className="mt-0.5 flex items-center gap-2">
													<h2 className="truncate font-semibold text-lg tracking-tight">
														{selected.name}
													</h2>
													{selected.starred && (
														<StarIcon className="size-4 shrink-0 fill-amber-400 text-amber-400" />
													)}
												</div>
												{selected.description && (
													<p className="mt-1 text-muted-foreground text-[13px] leading-snug">
														{selected.description}
													</p>
												)}
												<div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
													<span className="tabular-nums">
														{selected.items.length}{" "}
														{selected.items.length === 1 ? "item" : "items"}
													</span>
													<span aria-hidden>·</span>
													<span>Updated {selected.updatedAt}</span>
													{selected.shared && (
														<>
															<span aria-hidden>·</span>
															<span className="inline-flex items-center gap-1">
																<UsersIcon className="size-3" />
																Shared with {selected.shared.with}
															</span>
														</>
													)}
												</div>
											</div>
											<div className="flex shrink-0 items-center gap-1">
												<Button
													variant="outline"
													size="sm"
													className="h-8 gap-1.5"
												>
													<Share2Icon className="size-3.5" />
													Share
												</Button>
												<FolderActionsMenu />
											</div>
										</div>

										{/* Toolbar: select-all + type filter + sort */}
										<div className="flex items-center gap-2 border-t px-3 py-2">
											<label className="flex items-center gap-2 text-muted-foreground text-xs">
												<input
													type="checkbox"
													checked={allChecked}
													onChange={() =>
														setChecked(
															allChecked
																? new Set()
																: new Set(visibleItems.map((it) => it.id)),
														)
													}
													className="size-3.5 accent-primary"
												/>
												{checked.size > 0
													? `${checked.size} selected`
													: "Select"}
											</label>

											{checked.size > 0 ? (
												<div className="flex items-center gap-1">
													<Button
														variant="ghost"
														size="sm"
														className="h-7 gap-1.5 text-xs"
													>
														<FolderIcon className="size-3.5" />
														Move
													</Button>
													<Button
														variant="ghost"
														size="sm"
														className="h-7 gap-1.5 text-xs"
													>
														<Trash2Icon className="size-3.5" />
														Remove
													</Button>
												</div>
											) : (
												<div className="flex flex-1 items-center gap-1 overflow-x-auto">
													<KindChip
														label="All"
														active={kindFilter === "all"}
														onClick={() => setKindFilter("all")}
													/>
													{(Object.keys(KIND_VIEW) as ItemKind[]).map((k) => {
														const count = selected.items.filter(
															(it) => it.kind === k,
														).length;
														if (count === 0) return null;
														return (
															<KindChip
																key={k}
																label={`${KIND_VIEW[k].label} ${count}`}
																active={kindFilter === k}
																onClick={() => setKindFilter(k)}
															/>
														);
													})}
												</div>
											)}

											<button
												type="button"
												className="ml-auto inline-flex shrink-0 items-center gap-1 rounded px-2 py-1 text-muted-foreground text-xs hover:bg-accent/50 hover:text-foreground"
											>
												<ArrowUpDownIcon className="size-3.5" />
												Date saved
											</button>
										</div>
									</div>

									{/* Item list */}
									<div className="mt-3 overflow-hidden rounded-lg border bg-card">
										{visibleItems.length === 0 ? (
											<EmptyFolder hasItems={selected.items.length > 0} />
										) : (
											<ul>
												{visibleItems.map((it, i) => (
													<ItemRow
														key={it.id}
														item={it}
														first={i === 0}
														checked={checked.has(it.id)}
														onCheck={() => toggleCheck(it.id)}
													/>
												))}
											</ul>
										)}
									</div>

									{/* Subfolders, when present */}
									{selected.children && selected.children.length > 0 && (
										<div className="mt-4">
											<h3 className="mb-2 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">
												Subfolders
											</h3>
											<div className="grid gap-2 sm:grid-cols-2">
												{selected.children.map((c) => (
													<button
														key={c.id}
														type="button"
														onClick={() => select(c.id)}
														className="group flex items-center gap-3 rounded-lg border bg-card p-3 text-left transition-colors hover:bg-accent/40"
													>
														<span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
															<FolderIcon className="size-4" />
														</span>
														<span className="min-w-0 flex-1">
															<span className="block truncate font-medium text-[13px]">
																{c.name}
															</span>
															<span className="block text-[11px] text-muted-foreground">
																{c.items.length} items · {c.updatedAt}
															</span>
														</span>
														<ChevronRightIcon className="size-4 shrink-0 text-muted-foreground/40 transition-all group-hover:translate-x-0.5 group-hover:text-foreground" />
													</button>
												))}
											</div>
										</div>
									)}
								</section>
							</div>
						</div>
					</main>
				</SidebarInset>
			</div>
		</SidebarProvider>
	);
}

// ---------------------------------------------------------------------------
// Folder tree row — supports one level of nesting via the `children` array
// ---------------------------------------------------------------------------

function FolderRow({
	folder,
	depth,
	selectedId,
	expanded,
	onSelect,
	onToggle,
}: {
	folder: Folder;
	depth: number;
	selectedId: string;
	expanded: Set<string>;
	onSelect: (id: string) => void;
	onToggle: (id: string) => void;
}) {
	const hasChildren = !!folder.children?.length;
	const isOpen = expanded.has(folder.id);
	const active = selectedId === folder.id;

	return (
		<>
			<div
				className={cn(
					"group flex items-center gap-1 rounded px-1.5 py-1.5 transition-colors",
					active ? "bg-primary/10" : "hover:bg-accent/50",
				)}
				style={{ paddingLeft: depth * 14 + 6 }}
			>
				{hasChildren ? (
					<button
						type="button"
						onClick={() => onToggle(folder.id)}
						aria-label={isOpen ? "Collapse" : "Expand"}
						className="flex size-4 shrink-0 items-center justify-center text-muted-foreground hover:text-foreground"
					>
						<ChevronRightIcon
							className={cn(
								"size-3.5 transition-transform",
								isOpen && "rotate-90",
							)}
						/>
					</button>
				) : (
					<span className="size-4 shrink-0" />
				)}
				<button
					type="button"
					onClick={() => onSelect(folder.id)}
					className="flex min-w-0 flex-1 items-center gap-2 text-left"
				>
					{active ? (
						<FolderOpenIcon className="size-4 shrink-0 text-primary" />
					) : (
						<FolderIcon className="size-4 shrink-0 text-muted-foreground" />
					)}
					<span
						className={cn(
							"truncate text-[13px]",
							active ? "font-medium text-foreground" : "text-foreground/90",
						)}
					>
						{folder.name}
					</span>
					{folder.starred && (
						<StarIcon className="size-3 shrink-0 fill-amber-400 text-amber-400" />
					)}
				</button>
				<span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
					{folder.items.length}
				</span>
			</div>
			{hasChildren &&
				isOpen &&
				folder.children?.map((c) => (
					<FolderRow
						key={c.id}
						folder={c}
						depth={depth + 1}
						selectedId={selectedId}
						expanded={expanded}
						onSelect={onSelect}
						onToggle={onToggle}
					/>
				))}
		</>
	);
}

// ---------------------------------------------------------------------------
// Saved-item row
// ---------------------------------------------------------------------------

function ItemRow({
	item,
	first,
	checked,
	onCheck,
}: {
	item: SavedItem;
	first: boolean;
	checked: boolean;
	onCheck: () => void;
}) {
	const { icon: Icon, label, tint } = KIND_VIEW[item.kind];
	return (
		<li
			className={cn(
				"group flex items-start gap-3 px-3 py-3 transition-colors hover:bg-accent/30",
				!first && "border-t",
				checked && "bg-primary/[0.04]",
			)}
		>
			<input
				type="checkbox"
				checked={checked}
				onChange={onCheck}
				aria-label={`Select ${item.title}`}
				className="mt-1 size-3.5 shrink-0 accent-primary"
			/>
			<span
				className={cn(
					"mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md",
					tint,
				)}
			>
				<Icon className="size-4" />
			</span>
			<div className="min-w-0 flex-1">
				<div className="flex items-center gap-2">
					<Link
						href="#"
						className="truncate font-medium text-[13px] text-foreground hover:text-primary hover:underline"
					>
						{item.title}
					</Link>
					<span className="hidden shrink-0 rounded bg-muted px-1.5 py-px text-[10px] text-muted-foreground sm:inline">
						{label}
					</span>
				</div>
				<p className="mt-0.5 truncate text-[12px] text-muted-foreground">
					{item.subtitle}
				</p>
				{item.note && (
					<p className="mt-1.5 flex items-start gap-1.5 rounded border border-dashed bg-muted/40 px-2 py-1 text-[12px] text-foreground/80">
						<StickyNoteIcon className="mt-px size-3 shrink-0 text-muted-foreground" />
						<span className="min-w-0">{item.note}</span>
					</p>
				)}
			</div>
			<div className="flex shrink-0 flex-col items-end gap-1">
				<span className="whitespace-nowrap text-[11px] text-muted-foreground tabular-nums">
					{item.savedAt}
				</span>
				<div className="flex items-center opacity-0 transition-opacity group-hover:opacity-100">
					<button
						type="button"
						aria-label="Add note"
						className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
					>
						<PencilIcon className="size-3.5" />
					</button>
					<button
						type="button"
						aria-label="More"
						className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
					>
						<MoreHorizontalIcon className="size-3.5" />
					</button>
				</div>
			</div>
		</li>
	);
}

// ---------------------------------------------------------------------------
// Bits
// ---------------------------------------------------------------------------

function KindChip({
	label,
	active,
	onClick,
}: {
	label: string;
	active: boolean;
	onClick: () => void;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"shrink-0 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] transition-colors",
				active
					? "border-primary/30 bg-primary/10 font-medium text-foreground"
					: "border-transparent text-muted-foreground hover:bg-accent/50 hover:text-foreground",
			)}
		>
			{label}
		</button>
	);
}

function SideLink({
	icon: Icon,
	label,
	count,
}: {
	icon: LucideIcon;
	label: string;
	count?: number;
}) {
	return (
		<button
			type="button"
			className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[13px] text-foreground/90 transition-colors hover:bg-accent/50"
		>
			<Icon className="size-3.5 shrink-0 text-muted-foreground" />
			<span className="min-w-0 flex-1 truncate">{label}</span>
			{count !== undefined && (
				<span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
					{count}
				</span>
			)}
		</button>
	);
}

function EmptyFolder({ hasItems }: { hasItems: boolean }) {
	return (
		<div className="flex flex-col items-center justify-center px-6 py-14 text-center">
			<span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
				<FolderOpenIcon className="size-6" />
			</span>
			<p className="mt-3 font-medium text-sm">
				{hasItems ? "No items of this type" : "This folder is empty"}
			</p>
			<p className="mt-1 max-w-xs text-muted-foreground text-xs">
				{hasItems
					? "Try a different type filter, or clear it to see everything."
					: "Save a case, statute, rule, or search to this folder using the “Save to folder” button anywhere in the app."}
			</p>
			{!hasItems && (
				<Button size="sm" variant="outline" className="mt-4 gap-1.5">
					<FilePlus2Icon className="size-3.5" />
					Browse the library
				</Button>
			)}
		</div>
	);
}

function FolderActionsMenu() {
	return (
		<DropdownMenu>
			<DropdownMenuTrigger asChild>
				<Button variant="ghost" size="icon" className="size-8">
					<MoreHorizontalIcon className="size-4" />
					<span className="sr-only">Folder actions</span>
				</Button>
			</DropdownMenuTrigger>
			<DropdownMenuContent align="end" className="w-44">
				<DropdownMenuItem>
					<PencilIcon className="size-3.5" /> Rename
				</DropdownMenuItem>
				<DropdownMenuItem>
					<StarIcon className="size-3.5" /> Star folder
				</DropdownMenuItem>
				<DropdownMenuItem>
					<FolderPlusIcon className="size-3.5" /> New subfolder
				</DropdownMenuItem>
				<DropdownMenuItem>
					<Share2Icon className="size-3.5" /> Share…
				</DropdownMenuItem>
				<DropdownMenuSeparator />
				<DropdownMenuItem className="text-destructive focus:text-destructive">
					<Trash2Icon className="size-3.5" /> Delete folder
				</DropdownMenuItem>
			</DropdownMenuContent>
		</DropdownMenu>
	);
}

// ---------------------------------------------------------------------------
// "Save to folder" control — the entry point shown on case/statute pages.
// Reproduced here (with a sample case) so the save flow is part of the mockup.
// ---------------------------------------------------------------------------

function SaveToFolderDemo() {
	// Which folders the sample case is filed in (pre-checked: the CPA matter).
	const [inFolders, setInFolders] = useState<Set<string>>(new Set(["cpa"]));
	const toggle = (id: string) =>
		setInFolders((prev) => {
			const next = new Set(prev);
			next.has(id) ? next.delete(id) : next.add(id);
			return next;
		});

	return (
		<DropdownMenu>
			<DropdownMenuTrigger asChild>
				<Button variant="outline" size="sm" className="h-8 gap-1.5">
					<FolderPlusIcon className="size-3.5" />
					Save to folder
					<ChevronDownIcon className="size-3.5 text-muted-foreground" />
				</Button>
			</DropdownMenuTrigger>
			<DropdownMenuContent align="end" className="w-72">
				<DropdownMenuLabel className="flex flex-col gap-0.5">
					<span className="text-[11px] text-muted-foreground uppercase tracking-wide">
						Save to folder
					</span>
					<span className="truncate font-normal text-[12px] text-muted-foreground normal-case">
						State ex rel. Miller v. Pace · 677 N.W.2d 761
					</span>
				</DropdownMenuLabel>
				<DropdownMenuSeparator />
				{FOLDERS.filter((f) => f.id !== "untitled").map((f) => (
					<DropdownMenuCheckboxItem
						key={f.id}
						checked={inFolders.has(f.id)}
						onCheckedChange={() => toggle(f.id)}
						onSelect={(e) => e.preventDefault()}
					>
						<FolderIcon className="size-3.5 text-muted-foreground" />
						<span className="min-w-0 flex-1 truncate">{f.name}</span>
						<span className="text-[11px] text-muted-foreground tabular-nums">
							{f.items.length}
						</span>
					</DropdownMenuCheckboxItem>
				))}
				<DropdownMenuSeparator />
				<DropdownMenuItem>
					<FolderPlusIcon className="size-3.5" /> Create new folder…
				</DropdownMenuItem>
				<div className="px-2 py-1.5">
					<Button size="sm" className="h-7 w-full gap-1.5">
						<CheckIcon className="size-3.5" />
						Done · saved to {inFolders.size}{" "}
						{inFolders.size === 1 ? "folder" : "folders"}
					</Button>
				</div>
			</DropdownMenuContent>
		</DropdownMenu>
	);
}
