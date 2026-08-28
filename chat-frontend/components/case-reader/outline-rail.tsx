"use client";

// Left rail of the case reader: the document outline (scroll-spy, labels
// wrap instead of truncating — a Roman-numeral heading is a sentence), the
// case details, and the display controls (size / family / measure).

import { ExternalLinkIcon } from "lucide-react";
import { memo, type ReactNode } from "react";
import type { Section } from "@/lib/case-format";
import type { CaseDetail } from "@/lib/iowa-browse";
import {
	READER_FONT_MAX,
	READER_FONT_MIN,
	type ReaderPrefs,
} from "@/lib/reader-prefs";
import { cn } from "@/lib/utils";

const HEADING_NUM = /^([IVXLC]{1,5}|[A-D])\.\s+(.+)$/;

export const Outline = memo(function Outline({
	sections,
	active,
	onJump,
}: {
	sections: Section[];
	active: string | null;
	onJump: (id: string) => void;
}) {
	if (sections.length < 2) return null;
	return (
		<nav aria-label="Document outline">
			<p className="px-4 pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				Outline
			</p>
			{sections.map((s) => {
				const m = HEADING_NUM.exec(s.label);
				return (
					<button
						key={s.id}
						type="button"
						onClick={() => onJump(s.id)}
						aria-current={active === s.id ? "true" : undefined}
						style={{ paddingLeft: `${0.875 + s.depth * 0.75}rem` }}
						className={cn(
							"flex w-full gap-2 border-l-[3px] py-1.5 pr-3 text-left text-[13px] leading-[1.4] transition-colors",
							active === s.id
								? "border-[#0f62fe] font-semibold text-[var(--cds-text)]"
								: "border-transparent text-[var(--cds-text-2)] hover:text-[var(--cds-text)]",
						)}
					>
						{m ? (
							<>
								<span className="w-6 shrink-0 font-mono text-[11px] text-[var(--cds-helper)] leading-[1.6]">
									{m[1]}
								</span>
								<span className="min-w-0">{m[2]}</span>
							</>
						) : (
							<span className="min-w-0">{s.label}</span>
						)}
					</button>
				);
			})}
		</nav>
	);
});

export const Details = memo(function Details({ data }: { data: CaseDetail }) {
	const rows: [string, ReactNode][] = [];
	if (data.docket_number)
		rows.push([
			"Docket",
			<span className="font-mono" key="d">
				{data.docket_number}
			</span>,
		]);
	if (data.judges?.trim()) rows.push(["Panel", data.judges.trim()]);
	if (data.precedential_status) rows.push(["Status", data.precedential_status]);
	if (data.disposition?.trim())
		rows.push(["Disposition", data.disposition.trim()]);
	if (data.posture?.trim()) rows.push(["Posture", data.posture.trim()]);
	if (data.nature_of_suit?.trim())
		rows.push(["Nature of suit", data.nature_of_suit.trim()]);
	if (data.official_url)
		rows.push([
			"Source",
			<a
				key="s"
				href={data.official_url}
				target="_blank"
				rel="noopener noreferrer"
				className="inline-flex items-center gap-1 text-[var(--cds-link)] hover:underline"
			>
				CourtListener
				<ExternalLinkIcon className="size-3" />
			</a>,
		]);
	if (rows.length === 0) return null;
	return (
		<div>
			<p className="px-4 pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				Details
			</p>
			<dl className="text-xs">
				{rows.map(([k, v]) => (
					<div key={k} className="px-4 py-1.5">
						<dt className="text-[var(--cds-helper)]">{k}</dt>
						<dd className="mt-0.5 leading-[1.45]">{v}</dd>
					</div>
				))}
			</dl>
		</div>
	);
});

export function DisplayControls({
	prefs,
	onChange,
}: {
	prefs: ReaderPrefs;
	onChange: (p: ReaderPrefs) => void;
}) {
	return (
		<div>
			<p className="px-4 pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				Display
			</p>
			<div className="flex flex-col gap-2 px-4">
				<div className="flex border border-[var(--cds-border)]">
					<button
						type="button"
						aria-label="Smaller text"
						disabled={prefs.fontSize <= READER_FONT_MIN}
						onClick={() =>
							onChange({
								...prefs,
								fontSize: Math.max(READER_FONT_MIN, prefs.fontSize - 1),
							})
						}
						className="w-9 py-1 text-[12px] text-[var(--cds-text-2)] transition-colors hover:bg-[var(--cds-layer-hover)] disabled:opacity-40"
					>
						A−
					</button>
					<span className="flex-1 border-[var(--cds-border)] border-x py-1 text-center font-mono text-[12px] text-[var(--cds-text-2)] tabular-nums">
						{prefs.fontSize} px
					</span>
					<button
						type="button"
						aria-label="Larger text"
						disabled={prefs.fontSize >= READER_FONT_MAX}
						onClick={() =>
							onChange({
								...prefs,
								fontSize: Math.min(READER_FONT_MAX, prefs.fontSize + 1),
							})
						}
						className="w-9 py-1 text-[12px] text-[var(--cds-text-2)] transition-colors hover:bg-[var(--cds-layer-hover)] disabled:opacity-40"
					>
						A+
					</button>
				</div>
				<Segmented
					label="Typeface"
					value={prefs.family}
					options={[
						{ id: "serif", label: "Serif" },
						{ id: "sans", label: "Sans" },
					]}
					onChange={(family) => onChange({ ...prefs, family })}
				/>
				<Segmented
					label="Measure"
					value={prefs.measure}
					options={[
						{ id: "narrow", label: "Narrow" },
						{ id: "wide", label: "Wide" },
					]}
					onChange={(measure) => onChange({ ...prefs, measure })}
				/>
			</div>
		</div>
	);
}

function Segmented<T extends string>({
	label,
	value,
	options,
	onChange,
}: {
	label: string;
	value: T;
	options: { id: T; label: string }[];
	onChange: (v: T) => void;
}) {
	return (
		<div
			role="group"
			aria-label={label}
			className="flex border border-[var(--cds-border)]"
		>
			{options.map((o, i) => {
				const on = o.id === value;
				return (
					<button
						key={o.id}
						type="button"
						aria-pressed={on}
						onClick={() => onChange(o.id)}
						className={cn(
							"flex-1 py-1 text-center text-[12px] transition-colors",
							i > 0 && "border-[var(--cds-border)] border-l",
							on
								? "bg-[var(--cds-layer-selected)] font-semibold text-[var(--cds-text)]"
								: "text-[var(--cds-text-2)] hover:bg-[var(--cds-layer-hover)]",
						)}
					>
						{o.label}
					</button>
				);
			})}
		</div>
	);
}
