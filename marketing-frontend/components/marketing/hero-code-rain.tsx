"use client";

// Hero background: real Iowa statute text dissolving into binary — the
// product's whole thesis (law in, grounded computation out) as ambient
// texture. One canvas, low frame rate, very low contrast; a diagonal
// conversion front sweeps the grid, statute text ahead of it, bits behind
// it, a narrow flicker zone at the boundary. Binary picks up a faint
// Carbon blue. prefers-reduced-motion renders a single static frame.
//
// The parent section provides the dark overlay that keeps the hero copy
// readable — this component only paints glyphs on transparent.

import { useEffect, useRef } from "react";

// Verbatim Iowa Code text (§ 123.93 notice-of-action + § 668.3(1)(a)
// comparative fault) — background texture, but real law, on brand.
const SOURCE = (
	"Within six months of the occurrence of an injury, the injured person " +
	"shall give written notice to the licensee or permittee or such " +
	"licensee's or permittee's insurance carrier of the person's intention " +
	"to bring an action under this section, indicating the time, place and " +
	"circumstances causing the injury. Contributory fault shall not bar " +
	"recovery in an action by a claimant to recover damages for fault " +
	"resulting in death or in injury to person or property unless the " +
	"claimant bears a greater percentage of fault than the combined " +
	"percentage of fault attributed to the defendants, third-party " +
	"defendants and persons who have been released, but any damages allowed " +
	"shall be diminished in proportion to the amount of fault attributable " +
	"to the claimant. "
).repeat(8);

const CELL_W = 10;
const CELL_H = 24;
const FONT_PX = 13;
const FPS = 10;
// Fraction of the sweep cycle spent as binary / as the flicker boundary.
const BINARY_SPAN = 0.42;
const FLICKER_SPAN = 0.08;
const SWEEP_SECONDS = 26; // one full text→binary→text pass

// Deterministic per-cell hash → [0, 1). Cheap, stable, no allocation.
function hash(x: number, y: number, seed: number): number {
	let h = (x * 374761393 + y * 668265263) ^ (seed * 1274126177);
	h = (h ^ (h >>> 13)) * 1103515245;
	return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

export function HeroCodeRain() {
	const ref = useRef<HTMLCanvasElement>(null);

	useEffect(() => {
		const canvas = ref.current;
		const ctx = canvas?.getContext("2d");
		if (!canvas || !ctx) return;

		const reduced = window.matchMedia(
			"(prefers-reduced-motion: reduce)",
		).matches;
		const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
		let cols = 0;
		let rows = 0;
		let raf = 0;
		let last = 0;

		// next/font registers Plex Mono under a hashed family name; the canvas
		// element carries `font-mono`, so read the resolved stack off it.
		const family = getComputedStyle(canvas).fontFamily || "monospace";

		const resize = () => {
			const { width, height } = canvas.getBoundingClientRect();
			canvas.width = Math.round(width * dpr);
			canvas.height = Math.round(height * dpr);
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
			ctx.font = `${FONT_PX}px ${family}`;
			ctx.textBaseline = "top";
			cols = Math.ceil(width / CELL_W);
			rows = Math.ceil(height / CELL_H);
		};

		const draw = (tSec: number) => {
			ctx.clearRect(0, 0, canvas.width, canvas.height);
			const sweep = tSec / SWEEP_SECONDS;
			const bitEpoch = Math.floor(tSec * 3); // bits re-roll ~3×/sec
			for (let y = 0; y < rows; y++) {
				for (let x = 0; x < cols; x++) {
					const ch = SOURCE[(y * cols + x) % SOURCE.length];
					if (ch === " ") continue;
					// Diagonal front position for this cell, looping 0→1.
					const phase =
						(x / cols) * 0.55 +
						(y / rows) * 0.25 -
						sweep +
						hash(x, y, 1) * 0.04;
					const p = ((phase % 1) + 1) % 1;

					const inFlicker = p < FLICKER_SPAN;
					const asBinary =
						p < BINARY_SPAN && (!inFlicker || hash(x, y, bitEpoch) > 0.5);

					const jitter = hash(x, y, 2); // stable per-cell brightness
					if (asBinary) {
						const bit = hash(x, y, bitEpoch + 7) > 0.5 ? "1" : "0";
						ctx.fillStyle = `rgba(120, 169, 255, ${0.22 + jitter * 0.22})`;
						ctx.fillText(bit, x * CELL_W, y * CELL_H);
					} else {
						ctx.fillStyle = `rgba(198, 198, 198, ${0.14 + jitter * 0.14})`;
						ctx.fillText(ch, x * CELL_W, y * CELL_H);
					}
				}
			}
		};

		const loop = (now: number) => {
			raf = requestAnimationFrame(loop);
			if (now - last < 1000 / FPS) return;
			last = now;
			draw(now / 1000);
		};

		let started = false;
		const start = () => {
			if (started) return;
			started = true;
			resize();
			if (reduced) {
				draw(SWEEP_SECONDS * 0.35); // one mixed text/binary frame
			} else {
				raf = requestAnimationFrame(loop);
			}
		};

		// Draw with the real font metrics (avoids a fallback-font first paint),
		// but don't wait forever if the font never resolves.
		document.fonts?.ready.then(start);
		const fallback = window.setTimeout(start, 1500);

		const onResize = () => {
			resize();
			if (reduced) draw(SWEEP_SECONDS * 0.35);
		};
		window.addEventListener("resize", onResize);

		// Don't burn frames while the hero is off-screen.
		const io = new IntersectionObserver(([entry]) => {
			if (reduced || !started) return;
			cancelAnimationFrame(raf);
			if (entry.isIntersecting) raf = requestAnimationFrame(loop);
		});
		io.observe(canvas);

		return () => {
			cancelAnimationFrame(raf);
			clearTimeout(fallback);
			window.removeEventListener("resize", onResize);
			io.disconnect();
		};
	}, []);

	return (
		<canvas
			ref={ref}
			aria-hidden
			className="pointer-events-none absolute inset-0 size-full font-mono"
		/>
	);
}
