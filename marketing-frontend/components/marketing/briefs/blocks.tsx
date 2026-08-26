// Server-rendered building blocks for data-brief pages: the numbered hero
// with its KPI row, the hairline figure header, the table twin every figure
// ships with (the table is the record; the chart is the enhancement), and
// the two-column methodology close. All of it renders on the Carbon ink
// band / paper rhythm the rest of the marketing site uses.

import type { BriefFigure } from "@/lib/briefs";
import { cn } from "@/lib/utils";
import { tint } from "./palette";

// The prose measure shared by a brief's running text. Figures run the full
// width of the page container, so the text is centered under them in one fixed
// measure so every paragraph, quote and heading shares the same edges.
export const PROSE = "mx-auto w-full max-w-[46rem]";

export function BriefHero({
	no,
	asOf,
	title,
	dek,
	kpis,
	kicker,
}: {
	no: string;
	asOf: string;
	title: string;
	dek: React.ReactNode;
	kpis: { value: string; label: string }[];
	/** Replaces the default "Hudson Corpus · Data brief {no}" line. */
	kicker?: React.ReactNode;
}) {
	// The KPI band centres under the title in its own measure; four cells go
	// 2×2 before they go 1×4 so the labels never wrap to three lines.
	const cols =
		kpis.length >= 4
			? "sm:grid-cols-2 lg:grid-cols-4"
			: kpis.length === 2
				? "sm:grid-cols-2"
				: "sm:grid-cols-3";
	return (
		<header className="bg-[#161616] text-white">
			<div className="mx-auto max-w-7xl px-5 pt-16 sm:px-8 lg:pt-24">
				<div className="mx-auto flex max-w-[52rem] flex-col items-center text-center">
					<p className="font-mono text-[#78a9ff] text-xs uppercase tracking-[0.16em]">
						{kicker ?? <>Hudson Corpus · Data brief {no}</>}
					</p>
					<h1 className="mt-6 text-balance font-light text-[2.6rem] leading-[1.08] tracking-[-0.015em] sm:text-6xl lg:text-[4.4rem]">
						{title}
					</h1>
					<p
						className={`${PROSE} mt-7 text-balance font-light text-[#c6c6c6] text-lg leading-[1.55] sm:text-[21px] [&_em]:text-[#f4f4f4] [&_strong]:font-semibold [&_strong]:text-[#f4f4f4]`}
					>
						{dek}
					</p>
					<p className="mt-8 font-mono text-[#a8a8a8] text-xs uppercase tracking-[0.1em]">
						As of {asOf}
					</p>
				</div>
				<div
					className={cn(
						"mx-auto mt-16 grid max-w-5xl gap-y-8 border-[#393939] border-t pt-8 pb-14 sm:gap-y-10",
						cols,
					)}
				>
					{kpis.map((k, i) => (
						<div
							key={k.label}
							className={cn(
								"px-6 text-center",
								i > 0 && "sm:border-[#393939] sm:border-l",
							)}
						>
							<div className="font-light text-[2.75rem] leading-none tabular-nums sm:text-5xl">
								{k.value}
							</div>
							<div className="mx-auto mt-3 max-w-[18em] text-balance text-[#a8a8a8] text-sm leading-snug">
								{k.label}
							</div>
						</div>
					))}
				</div>
			</div>
		</header>
	);
}

export function FigureBlock({
	label,
	kicker,
	children,
	className,
}: {
	label: string;
	kicker: React.ReactNode;
	children: React.ReactNode;
	className?: string;
}) {
	return (
		<section className={cn("bg-[#161616] pb-20 text-white", className)}>
			<div className="mx-auto max-w-7xl px-5 sm:px-8">
				<div className="flex flex-wrap items-baseline gap-x-8 gap-y-3 border-[#393939] border-t pt-4">
					<span className="font-mono text-[#a8a8a8] text-xs uppercase tracking-[0.12em]">
						{label}
					</span>
					<span className="max-w-[46em] text-[#c6c6c6] text-[15px]">
						{kicker}
					</span>
				</div>
				{children}
			</div>
		</section>
	);
}

function CategoryCell({ figure, cat }: { figure: BriefFigure; cat: string }) {
	const c = figure.categories[cat];
	if (!c) return null;
	return (
		<span className="whitespace-nowrap">
			<span
				aria-hidden
				className="mr-1.5 inline-block size-[9px] rounded-full border-[1.5px] align-baseline"
				style={{ borderColor: c.color, background: tint(c.color) }}
			/>
			{c.label}
		</span>
	);
}

// The full-data table behind a figure. `citationColumn` switches between the
// Iowa layout (Year / Court) and the federal layout (Citation / Year), and
// the caption line under a short name renders only when the corpus caption
// actually differs from it.
export function BriefTable({
	figure,
	citationColumn = false,
	countHeader,
	areaHeader,
}: {
	figure: BriefFigure;
	citationColumn?: boolean;
	countHeader: string;
	areaHeader: string;
}) {
	const th =
		"sticky top-0 bg-white py-3 pr-4 text-left font-semibold text-[#525252] text-xs uppercase tracking-[0.04em]";
	const td = "border-[#e0e0e0] border-b py-2.5 pr-4 align-top";
	return (
		<div className="mt-9 overflow-x-auto border-[#161616] border-t">
			<div className="max-h-[520px] overflow-y-auto">
				<table className="w-full min-w-[640px] border-collapse text-[#161616] text-sm">
					<thead>
						<tr className="border-[#e0e0e0] border-b">
							<th className={th}>#</th>
							<th className={th}>Case</th>
							{citationColumn && <th className={th}>Citation</th>}
							<th className={th}>Year</th>
							{!citationColumn && <th className={th}>Court</th>}
							<th className={cn(th, "text-right")}>{countHeader}</th>
							<th className={cn(th, "whitespace-nowrap")}>{areaHeader}</th>
						</tr>
					</thead>
					<tbody>
						{figure.bubbles.map((b) => (
							<tr key={b.rank} className="hover:bg-[#f4f4f4]">
								<td className={cn(td, "font-mono text-[#525252]")}>{b.rank}</td>
								<td className={td}>
									<span className="font-semibold">{b.name}</span>
									{!citationColumn &&
										b.full.toLowerCase() !== b.name.toLowerCase() && (
											<div className="mt-px max-w-[34em] text-[#525252] text-[12.5px]">
												{b.full}
											</div>
										)}
								</td>
								{citationColumn && (
									<td className={cn(td, "font-mono tabular-nums")}>{b.full}</td>
								)}
								<td className={td}>{b.year}</td>
								{!citationColumn && <td className={td}>{b.court}</td>}
								<td className={cn(td, "text-right font-mono tabular-nums")}>
									{b.cites.toLocaleString("en-US")}
								</td>
								<td className={td}>
									<CategoryCell figure={figure} cat={b.cat} />
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
}

export function Methodology({
	measured,
	finePrint,
}: {
	measured: React.ReactNode[];
	finePrint: React.ReactNode[];
}) {
	const item =
		"relative mb-2.5 pl-[18px] text-[#525252] text-sm leading-relaxed before:absolute before:top-[0.62em] before:left-0 before:w-2 before:border-[#0f62fe] before:border-t before:content-['']";
	return (
		<section data-print="ink" className="bg-[#f4f4f4] py-16 text-[#161616]">
			<div className="mx-auto max-w-7xl px-5 sm:px-8">
				<p className="font-mono text-[#0f62fe] text-xs uppercase tracking-[0.16em]">
					Methodology
				</p>
				<div className="mt-7 grid gap-12 md:grid-cols-2">
					<div>
						<h3 className="mb-3 font-semibold text-[15px]">
							How this was measured
						</h3>
						<ul>
							{measured.map((m, i) => (
								// biome-ignore lint/suspicious/noArrayIndexKey: static editorial list, never reordered
								<li key={i} className={item}>
									{m}
								</li>
							))}
						</ul>
					</div>
					<div>
						<h3 className="mb-3 font-semibold text-[15px]">
							Read the fine print
						</h3>
						<ul>
							{finePrint.map((m, i) => (
								// biome-ignore lint/suspicious/noArrayIndexKey: static editorial list, never reordered
								<li key={i} className={item}>
									{m}
								</li>
							))}
						</ul>
					</div>
				</div>
			</div>
		</section>
	);
}
