"use client";

// Carbon mockup of the edition-compare screen (live: /browse/compare +
// components/edition-diff.tsx). Edition picker, amended/added/repealed
// buckets, change list, and a section diff with working inline / side-by-side
// toggle. Static demo diff on Iowa Code § 714.16; nothing calls the API.

import { ArrowRightIcon, Columns2Icon, RowsIcon } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { AppShell, Eyebrow, LineTabs, SelectField } from "../carbon";

type Bucket = "amended" | "added" | "repealed";

const CHANGES: Record<Bucket, { citation: string; heading: string }[]> = {
	amended: [
		{ citation: "§ 714.16", heading: "Consumer frauds" },
		{ citation: "§ 704.4", heading: "Defense of property" },
		{ citation: "§ 321.278", heading: "Operating while intoxicated — devices" },
		{ citation: "§ 598.41", heading: "Custody of children" },
	],
	added: [
		{ citation: "§ 714.16B", heading: "Online marketplace disclosures" },
		{ citation: "§ 80.47", heading: "Automated traffic enforcement" },
	],
	repealed: [{ citation: "§ 321.279A", heading: "Radar detector prohibition" }],
};

// Word-level diff segments for the selected section.
type Seg = { t: "eq" | "ins" | "del"; text: string };

const DIFF: Seg[] = [
	{
		t: "eq",
		text: "The act, use or employment by a person of an unfair practice, deception, fraud, false pretense, false promise, or misrepresentation ",
	},
	{ t: "del", text: "with the intent that others rely upon it " },
	{
		t: "ins",
		text: "whether or not a person has in fact been misled, deceived, or damaged, ",
	},
	{
		t: "eq",
		text: "in connection with the lease, sale, or advertisement of any merchandise",
	},
	{
		t: "ins",
		text: ", including advertisement or sale through an online marketplace,",
	},
	{ t: "eq", text: " is an unlawful practice. " },
	{
		t: "del",
		text: "A civil penalty shall not exceed forty thousand dollars per violation. ",
	},
	{
		t: "ins",
		text: "A civil penalty shall not exceed fifty thousand dollars per violation, adjusted annually for inflation. ",
	},
];

export default function CompareCarbonMockup() {
	const [bucket, setBucket] = useState<Bucket>("amended");
	const [selected, setSelected] = useState("§ 714.16");
	const [view, setView] = useState<"inline" | "split">("inline");

	return (
		<AppShell active="/app-carbon-mockup/compare">
			<div className="flex h-full min-h-0 flex-col">
				{/* Edition picker bar */}
				<div className="flex flex-wrap items-end gap-4 border-[var(--cds-border)] border-b px-5 py-4 sm:px-8">
					<div>
						<Eyebrow>Iowa Code — edition changes</Eyebrow>
						<div className="mt-3 flex items-end gap-3">
							<SelectField
								label="From"
								options={["2024 edition", "2023 edition"]}
								className="w-40"
							/>
							<ArrowRightIcon className="mb-2.5 size-4 text-[var(--cds-helper)]" />
							<SelectField
								label="To"
								options={["2025 edition"]}
								className="w-40"
							/>
						</div>
					</div>
					<p className="mb-1 ml-auto font-mono text-[11px] text-[var(--cds-helper)]">
						312 chapters with prior-edition data
					</p>
				</div>

				<div className="flex min-h-0 flex-1">
					{/* Change list */}
					<aside className="flex w-80 shrink-0 flex-col border-[var(--cds-border)] border-r">
						<div className="px-4 pt-4">
							<LineTabs
								tabs={[
									{
										id: "amended" as const,
										label: "Amended",
										count: CHANGES.amended.length,
									},
									{
										id: "added" as const,
										label: "Added",
										count: CHANGES.added.length,
									},
									{
										id: "repealed" as const,
										label: "Repealed",
										count: CHANGES.repealed.length,
									},
								]}
								value={bucket}
								onChange={setBucket}
							/>
						</div>
						<div className="min-h-0 flex-1 overflow-y-auto py-2">
							{CHANGES[bucket].map((c) => (
								<button
									key={c.citation}
									type="button"
									onClick={() => setSelected(c.citation)}
									className={cn(
										"flex w-full flex-col border-l-[3px] px-4 py-2.5 text-left transition-colors",
										selected === c.citation
											? "border-[#0f62fe] bg-[var(--cds-layer-selected)]"
											: "border-transparent hover:bg-[var(--cds-layer-hover)]",
									)}
								>
									<span className="font-mono text-[13px]">{c.citation}</span>
									<span className="truncate text-[var(--cds-text-2)] text-xs">
										{c.heading}
									</span>
								</button>
							))}
						</div>
					</aside>

					{/* Diff pane */}
					<section className="min-w-0 flex-1 overflow-y-auto">
						<div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
							<div className="flex flex-wrap items-end justify-between gap-4">
								<div>
									<p className="font-mono text-[13px]">Iowa Code {selected}</p>
									<h1 className="mt-1 font-light text-2xl">Consumer frauds</h1>
								</div>
								<div className="flex border border-[var(--cds-border)]">
									{(
										[
											{ id: "inline", label: "Inline", icon: RowsIcon },
											{
												id: "split",
												label: "Side by side",
												icon: Columns2Icon,
											},
										] as const
									).map((v) => (
										<button
											key={v.id}
											type="button"
											onClick={() => setView(v.id)}
											className={cn(
												"flex h-9 items-center gap-2 px-3 text-[13px] transition-colors",
												view === v.id
													? "bg-[var(--cds-layer-selected)] font-semibold"
													: "text-[var(--cds-text-2)] hover:bg-[var(--cds-layer-hover)]",
											)}
										>
											<v.icon className="size-3.5" strokeWidth={1.5} />
											{v.label}
										</button>
									))}
								</div>
							</div>

							<div className="mt-4 flex gap-4 font-mono text-[11px] text-[var(--cds-helper)]">
								<span>
									<span className="mr-1.5 inline-block size-2.5 bg-[#24a148]/25 align-middle outline outline-1 outline-[#24a148]" />
									added in 2025
								</span>
								<span>
									<span className="mr-1.5 inline-block size-2.5 bg-[#da1e28]/20 align-middle outline outline-1 outline-[#da1e28]" />
									removed from 2024
								</span>
							</div>

							{view === "inline" ? <InlineDiff /> : <SplitDiff />}
						</div>
					</section>
				</div>
			</div>
		</AppShell>
	);
}

// ---------------------------------------------------------------------------
// Diff renderings
// ---------------------------------------------------------------------------

function seg(s: Seg, side?: "from" | "to") {
	if (s.t === "eq") return <span key={s.text}>{s.text}</span>;
	if (s.t === "ins") {
		if (side === "from") return null;
		return (
			<ins key={s.text} className="bg-[#24a148]/20 no-underline">
				{s.text}
			</ins>
		);
	}
	if (side === "to") return null;
	return (
		<del
			key={s.text}
			className={cn("bg-[#da1e28]/15", side === "from" && "no-underline")}
		>
			{s.text}
		</del>
	);
}

function InlineDiff() {
	return (
		<p className="mt-6 border border-[var(--cds-border)] bg-[var(--cds-layer)] p-6 text-[15px] leading-[1.9]">
			{DIFF.map((s) => seg(s))}
		</p>
	);
}

function SplitDiff() {
	return (
		<div className="mt-6 grid gap-px border border-[var(--cds-border)] bg-[var(--cds-border)] md:grid-cols-2">
			{(
				[
					{ side: "from" as const, label: "2024 · as of Jul 1, 2024" },
					{ side: "to" as const, label: "2025 · as of Jul 1, 2025" },
				] as const
			).map((col) => (
				<div key={col.side} className="bg-[var(--cds-layer)]">
					<p className="border-[var(--cds-border)] border-b px-5 py-2 font-mono text-[11px] text-[var(--cds-helper)]">
						{col.label}
					</p>
					<p className="p-5 text-[14px] leading-[1.85]">
						{DIFF.map((s) => seg(s, col.side))}
					</p>
				</div>
			))}
		</div>
	);
}
