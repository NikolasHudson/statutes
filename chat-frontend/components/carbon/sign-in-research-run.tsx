"use client";

// Sign-in brand-panel demo: the assistant's "Research run" step panel as a
// slow, self-playing loop — the verification gate, shown rather than
// described. Data is a real run (Iowa Code § 614.1(9), medical-malpractice
// limitations): the same labels and tallies the live assistant rendered.
// All rows are always mounted (pending ones dimmed) so the panel never
// changes height; the loop is deliberately quiet — a returning user sees
// this screen daily. prefers-reduced-motion renders the completed state,
// static.

import { CheckIcon, Loader2Icon } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const STEPS: { label: string; detail: string; runMs: number }[] = [
	{
		label: "Searching the corpus",
		detail: "“medical malpractice limitations Iowa”",
		runMs: 1600,
	},
	{ label: "Reading section", detail: "614.1(9)(a)", runMs: 1400 },
	{
		label: "Verifying citations",
		detail: "5 of 5 citations · 3 of 3 quotes",
		runMs: 2200,
	},
];

const HOLD_MS = 6000; // completed state lingers — the point of the demo
const FADE_MS = 600;

export function SignInResearchRun() {
	// phase 0..2 = that step running; 3 = all done; -1 = fading before reset.
	const [phase, setPhase] = useState(0);
	const [reduced, setReduced] = useState(false);

	useEffect(() => {
		if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
			setReduced(true);
			setPhase(3);
			return;
		}
		let t: ReturnType<typeof setTimeout>;
		if (phase >= 0 && phase < STEPS.length) {
			t = setTimeout(() => setPhase(phase + 1), STEPS[phase].runMs);
		} else if (phase === STEPS.length) {
			t = setTimeout(() => setPhase(-1), HOLD_MS);
		} else {
			t = setTimeout(() => setPhase(0), FADE_MS);
		}
		return () => clearTimeout(t);
	}, [phase]);

	return (
		<figure className="max-w-lg">
			<div className="border border-[#393939]">
				<div className="flex items-center justify-between border-[#393939] border-b px-4 py-2.5">
					<span className="font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.18em]">
						Research run
					</span>
					<span
						className={cn(
							"font-mono text-[#6f6f6f] text-[11px] transition-opacity duration-500",
							phase === STEPS.length ? "opacity-100" : "opacity-0",
						)}
					>
						5.2 s
					</span>
				</div>
				<ul
					className={cn(
						"transition-opacity",
						phase === -1 ? "opacity-0" : "opacity-100",
					)}
					style={{ transitionDuration: `${FADE_MS}ms` }}
				>
					{STEPS.map((s, i) => {
						const done = phase === -1 || phase > i;
						const running = phase === i && !reduced;
						return (
							<li
								key={s.label}
								className={cn(
									"flex items-baseline gap-3 border-[#262626] border-b px-4 py-3 last:border-b-0 transition-opacity duration-500",
									done || running ? "opacity-100" : "opacity-35",
								)}
							>
								<span className="relative top-0.5 flex size-4 shrink-0 items-center justify-center">
									{done ? (
										<CheckIcon className="size-4 text-[#42be65]" />
									) : running ? (
										<Loader2Icon className="size-3.5 animate-spin text-[#78a9ff]" />
									) : (
										<span className="size-1.5 rounded-full bg-[#525252]" />
									)}
								</span>
								<span className="whitespace-nowrap text-[13.5px] text-white">
									{s.label}
								</span>
								<span
									className={cn(
										"ml-auto truncate text-right font-mono text-[11px] text-[#a8a8a8] transition-opacity duration-500",
										done ? "opacity-100" : "opacity-0",
									)}
								>
									{s.detail}
								</span>
							</li>
						);
					})}
				</ul>
			</div>
			<figcaption className="mt-3 font-mono text-[#6f6f6f] text-[11px] leading-relaxed">
				The verification gate — every answer clears it before you see it.
			</figcaption>
		</figure>
	);
}
