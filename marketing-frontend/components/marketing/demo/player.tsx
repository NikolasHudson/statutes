"use client";

// DemoPlayer — a "living shot": the product screen rebuilt as markup and
// played through on a scripted timeline, in place of a still PNG. Replaces
// <Frame> wherever a capture used to sit (home §03, the Corpus leadspace, the
// Read / Search feature panels).
//
// How it behaves:
//   • Server render is the poster: the old capture, in the frame, at the
//     stage's 16:10 ratio. First paint, LCP and the OG thumbnail are unchanged.
//   • On mount the stage is built over it and the loop starts when the frame
//     scrolls into view; leaving the viewport or hovering pauses it. The loop
//     holds on its last frame, then restarts.
//   • Reduced motion: the finished frame, no timeline, controls disabled.
//   • `steps` renders the three-column strip under the frame whose top rules
//     fill as the loop moves through its phases (the home page's "How an
//     answer is made" copy lives there now).
//
// The stage is a fixed 1120×700 canvas scaled to its container, so the loop
// looks the same in a 1200px hero and a 600px feature panel.

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { DEMOS, type DemoKey } from "./demos";
import { Loop, STAGE_H, STAGE_W } from "./engine";
import "./demo.css";

export type { DemoKey };

type Props = {
	demo: DemoKey;
	/** The capture this loop replaces; painted until the stage is built. */
	poster: { src: string; alt: string };
	/** Render the synced step strip under the frame. */
	steps?: boolean;
	/** Hide the caption / pause / replay row (tight slots like a leadspace). */
	compact?: boolean;
	/** On the ink band: light strip text and a deeper shadow. */
	tone?: "light" | "dark";
	className?: string;
};

export function DemoPlayer({
	demo,
	poster,
	steps = false,
	compact = false,
	tone = "light",
	className,
}: Props) {
	const def = DEMOS[demo];
	const root = useRef<HTMLDivElement>(null);
	const wrap = useRef<HTMLDivElement>(null);
	const stage = useRef<HTMLDivElement>(null);
	const loop = useRef<Loop | null>(null);
	const [mounted, setMounted] = useState(false);
	const [phase, setPhase] = useState<{ i: number; k: number; all: boolean }>({
		i: 0,
		k: 0,
		all: false,
	});
	const [caption, setCaption] = useState(def.captions[0][1]);
	const [playing, setPlaying] = useState(false);
	const [manual, setManual] = useState(false);
	const [reduced, setReduced] = useState(false);

	useEffect(() => {
		const r = root.current;
		const w = wrap.current;
		const s = stage.current;
		if (!r || !w || !s) return;

		const lp = new Loop(s, def, {
			onPhase: (i, k, all) => setPhase({ i, k, all }),
			onCaption: setCaption,
			onState: setPlaying,
		});
		loop.current = lp;
		setMounted(true);
		setReduced(lp.reduced);

		const fit = () => {
			const sc = w.clientWidth / STAGE_W;
			s.style.transform = `scale(${sc})`;
			w.style.height = `${STAGE_H * sc}px`;
		};
		const ro = new ResizeObserver(fit);
		ro.observe(w);
		fit();

		let inView = false;
		let hovered = false;
		let paused = false;
		const maybePlay = () => {
			if (inView && !hovered && !paused) lp.play();
		};
		const io = new IntersectionObserver(
			([e]) => {
				inView = e.isIntersecting;
				if (inView) maybePlay();
				else lp.pause();
			},
			{ threshold: 0.3 },
		);
		io.observe(r);
		const enter = () => {
			hovered = true;
			lp.pause();
		};
		const leave = () => {
			hovered = false;
			maybePlay();
		};
		r.addEventListener("mouseenter", enter);
		r.addEventListener("mouseleave", leave);
		// Controls talk to the loop through this element so they see the
		// same closure state as the observers.
		const onCtl = (e: Event) => {
			const d = (e as CustomEvent<"pause" | "replay">).detail;
			if (d === "pause") {
				paused = !paused;
				setManual(paused);
				if (paused) lp.pause();
				else {
					hovered = false;
					lp.play();
				}
			} else {
				lp.pause();
				lp.reset();
				paused = false;
				hovered = false;
				setManual(false);
				lp.play();
			}
		};
		r.addEventListener("hd-ctl", onCtl);

		return () => {
			io.disconnect();
			ro.disconnect();
			r.removeEventListener("mouseenter", enter);
			r.removeEventListener("mouseleave", leave);
			r.removeEventListener("hd-ctl", onCtl);
			lp.destroy();
			loop.current = null;
		};
	}, [def]);

	const ctl = (detail: "pause" | "replay") =>
		root.current?.dispatchEvent(new CustomEvent("hd-ctl", { detail }));

	const dark = tone === "dark";
	const muted = dark ? "text-[#a8a8a8]" : "text-muted-foreground";
	const body = dark ? "text-[#c6c6c6]" : "text-muted-foreground";
	const fg = dark ? "text-white" : "text-foreground";

	return (
		<div ref={root} className={cn("hd-demo", className)}>
			<div
				className={cn(
					"relative border bg-white",
					dark
						? "border-[#393939] shadow-[0_60px_120px_-40px_rgba(0,0,0,.8)]"
						: "border-[#c6c6c6] shadow-[0_40px_90px_-30px_rgba(22,22,22,.28)]",
				)}
			>
				<div
					ref={wrap}
					className="relative w-full overflow-hidden bg-white"
					style={{ aspectRatio: `${STAGE_W} / ${STAGE_H}` }}
				>
					{/* biome-ignore lint/performance/noImgElement: poster for the pre-hydration frame */}
					<img
						src={poster.src}
						alt={poster.alt}
						className={cn(
							"absolute inset-0 size-full object-cover object-top",
							mounted && "invisible",
						)}
					/>
					<div ref={stage} className="hd-stage" aria-hidden />
				</div>
			</div>

			{!compact && (
				<div
					className={cn(
						"mt-3.5 flex items-center gap-4 font-mono text-[11px] uppercase tracking-[0.08em]",
						muted,
					)}
				>
					<span className={cn("min-w-0 flex-1 truncate", body)}>{caption}</span>
					<span
						className={cn(
							!playing && !reduced && "text-[#f1c21b]",
							reduced && "normal-case tracking-normal",
						)}
					>
						{reduced
							? "Final frame · reduced motion"
							: playing
								? "Playing"
								: "Paused"}
					</span>
					<button
						type="button"
						disabled={reduced}
						onClick={() => ctl("pause")}
						className={cn(
							"border-b border-transparent uppercase tracking-[0.08em] disabled:opacity-40",
							dark
								? "text-[#c6c6c6] hover:border-white hover:text-white"
								: "hover:border-foreground hover:text-foreground",
						)}
					>
						{manual ? "Play" : "Pause"}
					</button>
					<button
						type="button"
						disabled={reduced}
						onClick={() => ctl("replay")}
						className={cn(
							"border-b border-transparent uppercase tracking-[0.08em] disabled:opacity-40",
							dark
								? "text-[#c6c6c6] hover:border-white hover:text-white"
								: "hover:border-foreground hover:text-foreground",
						)}
					>
						Replay
					</button>
				</div>
			)}

			{steps && (
				<ol
					className={cn(
						"mt-10 grid gap-0 border-t md:grid-cols-3 md:gap-8",
						dark ? "border-[#393939]" : "border-border",
					)}
				>
					{def.stepCopy.map(([title, text], i) => {
						const on = i === phase.i && !phase.all;
						const done = i < phase.i || phase.all;
						return (
							<li
								key={title}
								className={cn(
									"relative border-b py-5 pb-6 transition-opacity duration-300 md:border-b-0",
									dark ? "border-[#393939]" : "border-border",
									mounted && !on && !done && "opacity-40",
								)}
							>
								{/* The phase rule: fills Blue-60 while active, holds ink when done. */}
								<span
									aria-hidden
									className={cn(
										"absolute top-[-1px] left-0 h-0.5 w-full origin-left",
										on && "bg-[#0f62fe]",
										done && (dark ? "bg-white" : "bg-foreground"),
									)}
									style={{
										transform: `scaleX(${done ? 1 : on ? Math.min(1, phase.k) : 0})`,
										transition: on ? "transform 200ms linear" : undefined,
									}}
								/>
								<span
									className={cn(
										"font-mono text-[13px]",
										done ? muted : dark ? "text-[#78a9ff]" : "text-[#0f62fe]",
									)}
								>
									0{i + 1}
								</span>
								<h3
									className={cn(
										"mt-3.5 max-w-[30ch] text-[17px] leading-[1.35]",
										fg,
									)}
								>
									{title}
								</h3>
								<p
									className={cn(
										"mt-2 max-w-[38ch] text-[14px] leading-relaxed",
										body,
									)}
								>
									{text}
								</p>
							</li>
						);
					})}
				</ol>
			)}
		</div>
	);
}
