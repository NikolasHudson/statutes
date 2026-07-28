"use client";

// Shared scaffolding for settings pages: a titled section, the one-save-per-
// section state machine, and the save row that reports it.
//
// Lifted out of app/(app)/account/page.tsx when /account/edms became the second
// consumer. The settings-architecture rule is that product settings get their
// own sibling page rather than another section on /account (which is already
// seven stacked sections), so there will be a third and a fourth — copying this
// each time is how two pages end up flashing "Saved" for different durations.

import { CheckIcon } from "lucide-react";
import { useState } from "react";
import { BtnPrimary, Notification } from "@/components/carbon/primitives";

export function Section({
	id,
	title,
	desc,
	children,
}: {
	id: string;
	title: string;
	desc: string;
	children: React.ReactNode;
}) {
	return (
		<section
			id={id}
			className="scroll-mt-6 border-[var(--cds-border)] border-t pt-6"
		>
			<h2 className="font-semibold text-sm uppercase tracking-wide">{title}</h2>
			<p className="mt-1 text-[13px] text-[var(--cds-text-2)]">{desc}</p>
			<div className="mt-6">{children}</div>
		</section>
	);
}

export type SaveState = "idle" | "busy" | "saved" | "error";

/**
 * Run one section's save: flash "Saved" for two seconds, surface the error
 * inline otherwise. `run` takes the whole async operation so a section can do
 * more than a single PATCH (connect, disconnect, create a folder) and still
 * report through the same states.
 */
export function useSaveState() {
	const [state, setState] = useState<SaveState>("idle");
	const [error, setError] = useState<string | null>(null);

	const run = async (op: () => Promise<void>) => {
		setState("busy");
		setError(null);
		try {
			await op();
			setState("saved");
			setTimeout(() => setState("idle"), 2000);
		} catch (e) {
			setError((e as Error).message);
			setState("error");
		}
	};

	return { state, error, run };
}

export function SaveRow({
	state,
	error,
	onSave,
	note,
	label = "Save changes",
	disabled,
}: {
	state: SaveState;
	error: string | null;
	onSave: () => void;
	note?: string;
	label?: string;
	disabled?: boolean;
}) {
	return (
		<>
			{state === "error" && error && (
				<Notification kind="error" title="Couldn't save" className="mt-6">
					{error}
				</Notification>
			)}
			<div className="mt-6 flex items-center gap-4">
				<BtnPrimary
					size="md"
					arrow={false}
					disabled={disabled || state === "busy"}
					onClick={onSave}
				>
					{state === "busy" ? "Saving…" : label}
				</BtnPrimary>
				{state === "saved" ? (
					<span className="inline-flex items-center gap-1.5 text-[13px] text-[var(--cds-success-text)]">
						<CheckIcon className="size-4" /> Saved
					</span>
				) : note ? (
					<span className="font-mono text-[11px] text-[var(--cds-helper)]">
						{note}
					</span>
				) : null}
			</div>
		</>
	);
}

/** Sticky "On this page" rail shared by the settings pages. */
export function OnThisPage({
	sections,
}: {
	sections: readonly { id: string; label: string }[];
}) {
	const [active, setActive] = useState(sections[0]?.id ?? "");
	return (
		<nav className="sticky top-6 hidden self-start lg:block">
			<p className="pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				On this page
			</p>
			{sections.map((s) => (
				<a
					key={s.id}
					href={`#${s.id}`}
					onClick={() => setActive(s.id)}
					className={
						active === s.id
							? "flex border-[#0f62fe] border-l-[3px] py-1.5 pl-3 font-semibold text-[13px]"
							: "flex border-transparent border-l-[3px] py-1.5 pl-3 text-[13px] text-[var(--cds-text-2)] transition-colors hover:text-[var(--cds-text)]"
					}
				>
					{s.label}
				</a>
			))}
		</nav>
	);
}
