"use client";

// Hero visual for the products index: the citation graph itself, abstracted.
// A jittered lattice of documents whose citation edges draw in, hold, and fade
// — the graph behind the corpus as ambient texture rather than a chart. Nodes
// are squares (Carbon has no radii), a minority of edges carry Blue 40, and
// nothing is labelled: it reads as texture from across the room and as a
// citation network up close.
//
// The canvas covers the whole hero band and the falloff is painted into the
// pixels — a horizontal ramp that leaves the copy side empty and a feather on
// the top and bottom edges. Two reasons it is done here rather than in CSS: a
// `mask-image` promotes the canvas to its own compositing layer, which reads
// as a faintly different black against the band, and a radial mask only ever
// feathered the corners, leaving the left and right edges of the box visible.
// Nothing bounds the graph now except its own fade.
//
// Same discipline as HeroCodeRain: capped DPR, low frame rate, paused
// off-screen, and a single static frame under prefers-reduced-motion.

import { useEffect, useRef } from "react";

const CELL = 44; // lattice pitch, CSS px
const JITTER = 0.3; // node wander off its lattice point, as a fraction of a cell
const NODE = 3; // node square side, CSS px
const REACH = 1.5; // longest edge, in cells — drops the stretched diagonals
const KEEP = 0.5; // share of candidate edges kept (the rest never exist)
const HOT = 0.26; // share of edges drawn in Blue 40 rather than gray
const PERIOD = 12; // seconds for one draw → hold → fade cycle
const DRAW = 0.12; // share of the period spent drawing in…
const HOLD = 0.2; // …held at full strength…
const FADE = 0.14; // …fading out (the remainder the edge is simply absent)
const FPS = 24;

// Falloff, as fractions of the canvas — which is itself the right 64% of the
// band (see the element below), so the ramp scales with the viewport instead
// of drifting under the copy on narrower screens. The graph is absent where
// the copy is, reaches full strength two-thirds across, and bleeds off the
// right edge the way the home hero's code rain does. Net of the two: it first
// shows around 62% of the band and is at full density by 80%, whatever the
// window is doing.
const RAMP_IN = 0.32; // …starts to appear here
const RAMP_FULL = 0.68; // …full strength here
const FEATHER_Y = 0.22; // top/bottom feather, as a fraction of the height
const CUTOFF = 0.02; // below this the cell is skipped entirely

// Deterministic per-pair hash → [0, 1). Cheap, stable, no allocation.
function hash(a: number, b: number, seed: number): number {
	let h = (a * 374761393 + b * 668265263) ^ (seed * 1274126177);
	h = (h ^ (h >>> 13)) * 1103515245;
	return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

// Hermite ease, clamped — smooth at both ends so the fade has no visible start.
function smooth(t: number): number {
	const c = t < 0 ? 0 : t > 1 ? 1 : t;
	return c * c * (3 - 2 * c);
}

type Node = { x: number; y: number; f: number };
type Edge = { a: number; b: number; off: number; hot: boolean };

// Right, down, and both diagonals — enough to read as a network without the
// lattice showing through as a grid.
const NEIGHBORS = [
	[1, 0],
	[0, 1],
	[1, 1],
	[-1, 1],
];

export function HeroCitationLattice() {
	const ref = useRef<HTMLCanvasElement>(null);

	useEffect(() => {
		const canvas = ref.current;
		const ctx = canvas?.getContext("2d");
		if (!canvas || !ctx) return;

		const reduced = window.matchMedia(
			"(prefers-reduced-motion: reduce)",
		).matches;
		const dpr = Math.min(window.devicePixelRatio || 1, 2);
		let nodes: Node[] = [];
		let edges: Edge[] = [];
		let act = new Float32Array(0); // per-node activity this frame
		let hotAct = new Float32Array(0); // …the share of it arriving on blue edges
		let raf = 0;
		let last = 0;

		const build = () => {
			const { width, height } = canvas.getBoundingClientRect();
			if (!width || !height) return;
			canvas.width = Math.round(width * dpr);
			canvas.height = Math.round(height * dpr);
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
			ctx.lineWidth = 1;

			// One extra row/column, shifted half a cell out, so the lattice runs
			// past the band instead of stopping inside it.
			const cols = Math.max(2, Math.ceil(width / CELL) + 2);
			const rows = Math.max(2, Math.ceil(height / CELL) + 2);
			const feather = Math.max(1, height * FEATHER_Y);
			nodes = [];
			for (let y = 0; y < rows; y++) {
				for (let x = 0; x < cols; x++) {
					const px = (x - 0.5 + (hash(x, y, 1) - 0.5) * 2 * JITTER) * CELL;
					const py = (y - 0.5 + (hash(x, y, 2) - 0.5) * 2 * JITTER) * CELL;
					const fx = smooth((px / width - RAMP_IN) / (RAMP_FULL - RAMP_IN));
					const fy = smooth(py / feather) * smooth((height - py) / feather);
					nodes.push({ x: px, y: py, f: fx * fy });
				}
			}

			edges = [];
			for (let y = 0; y < rows; y++) {
				for (let x = 0; x < cols; x++) {
					const ai = y * cols + x;
					for (const [dx, dy] of NEIGHBORS) {
						const nx = x + dx;
						const ny = y + dy;
						if (nx < 0 || nx >= cols || ny >= rows) continue;
						const bi = ny * cols + nx;
						if (hash(ai, bi, 3) > KEEP) continue;
						const a = nodes[ai];
						const b = nodes[bi];
						if (a.f < CUTOFF && b.f < CUTOFF) continue;
						if (Math.hypot(b.x - a.x, b.y - a.y) > REACH * CELL) continue;
						edges.push({
							a: ai,
							b: bi,
							off: hash(ai, bi, 4),
							hot: hash(ai, bi, 5) < HOT,
						});
					}
				}
			}
			act = new Float32Array(nodes.length);
			hotAct = new Float32Array(nodes.length);
		};

		const draw = (tSec: number) => {
			ctx.clearRect(0, 0, canvas.width, canvas.height);
			act.fill(0);
			hotAct.fill(0);

			for (const e of edges) {
				const p = (((tSec / PERIOD + e.off) % 1) + 1) % 1;
				let alpha: number;
				let frac = 1; // how much of the edge has been drawn
				if (p < DRAW) {
					frac = p / DRAW;
					alpha = frac * frac; // ease in, so the head leads the brightness
				} else if (p < DRAW + HOLD) {
					alpha = 1;
				} else if (p < DRAW + HOLD + FADE) {
					alpha = 1 - (p - DRAW - HOLD) / FADE;
				} else {
					continue; // dark for the rest of the cycle
				}

				const a = nodes[e.a];
				const b = nodes[e.b];
				// An edge is only ever as present as the dimmer of its two ends, so
				// no line survives into the empty side of the band.
				const fade = Math.min(a.f, b.f);
				if (fade < CUTOFF) continue;
				ctx.strokeStyle = e.hot
					? `rgba(120, 169, 255, ${alpha * fade * 0.62})`
					: `rgba(168, 168, 168, ${alpha * fade * 0.34})`;
				ctx.beginPath();
				ctx.moveTo(a.x, a.y);
				ctx.lineTo(a.x + (b.x - a.x) * frac, a.y + (b.y - a.y) * frac);
				ctx.stroke();

				// The citing end lights immediately; the cited end lights as the
				// edge lands on it.
				act[e.a] = Math.max(act[e.a], alpha);
				act[e.b] = Math.max(act[e.b], alpha * frac);
				if (e.hot) {
					hotAct[e.a] = Math.max(hotAct[e.a], alpha);
					hotAct[e.b] = Math.max(hotAct[e.b], alpha * frac);
				}
			}

			for (let i = 0; i < nodes.length; i++) {
				const n = nodes[i];
				if (n.f < CUTOFF) continue;
				const base = 0.13 + hash(i, 0, 6) * 0.08; // stable per-node floor
				const size = act[i] > 0.7 ? NODE + 1 : NODE;
				ctx.fillStyle =
					hotAct[i] > 0.4
						? `rgba(120, 169, 255, ${(base + hotAct[i] * 0.6) * n.f})`
						: `rgba(198, 198, 198, ${(base + act[i] * 0.34) * n.f})`;
				ctx.fillRect(n.x - size / 2, n.y - size / 2, size, size);
			}
		};

		const loop = (now: number) => {
			raf = requestAnimationFrame(loop);
			if (now - last < 1000 / FPS) return;
			last = now;
			draw(now / 1000);
		};

		build();
		if (reduced) {
			draw(PERIOD * 0.4); // one representative frame
		} else {
			raf = requestAnimationFrame(loop);
		}

		const onResize = () => {
			build();
			if (reduced) draw(PERIOD * 0.4);
		};
		window.addEventListener("resize", onResize);

		// Don't burn frames while the hero is scrolled past.
		const io = new IntersectionObserver(([entry]) => {
			if (reduced) return;
			cancelAnimationFrame(raf);
			if (entry.isIntersecting) raf = requestAnimationFrame(loop);
		});
		io.observe(canvas);

		return () => {
			cancelAnimationFrame(raf);
			window.removeEventListener("resize", onResize);
			io.disconnect();
		};
	}, []);

	// The right 64% of the band. The left edge is invisible — RAMP_IN keeps the
	// first third of the canvas empty — and the right edge runs off the page,
	// so the graph has no boundary of its own anywhere. `h-full` is load-
	// bearing: canvas is a replaced element, so inset-y-0 alone leaves it at
	// its intrinsic 2:1 ratio instead of stretching to the band.
	return (
		<canvas
			ref={ref}
			aria-hidden
			className="pointer-events-none absolute inset-y-0 right-0 h-full w-[64%]"
		/>
	);
}
