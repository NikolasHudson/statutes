// The timeline engine behind every living shot. A Demo is a screenplay: a
// build() that paints the resting UI into the stage, and a list of
// [ms, action] steps the engine fires as the clock passes them. The engine
// owns the clock (rAF, pausable), the phase/caption bookkeeping the player
// shows, and the small vocabulary of DOM verbs the scripts are written in
// (type, moveTo, click, show, stream, count …). It never touches React state
// directly; the player subscribes through `Hooks`.

import { cursor } from "./chrome";

export const STAGE_W = 1120;
export const STAGE_H = 700;

export type Step = [number, (this: Loop) => void];

export type Demo = {
	key: string;
	/** Step-strip copy, one entry per phase. */
	stepCopy: [title: string, body: string][];
	/** Phase start times (ms), one per stepCopy entry; first is 0. */
	phases: number[];
	/** Loop length (ms) before the hold + restart. */
	total: number;
	/** Caption per moment: [ms, text]. */
	captions: [number, string][];
	build(stage: HTMLElement): void;
	steps: Step[];
};

export type Hooks = {
	onPhase?(index: number, fraction: number, all: boolean): void;
	onCaption?(text: string): void;
	onState?(playing: boolean): void;
};

export const prefersReducedMotion = () =>
	typeof window !== "undefined" &&
	window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export class Loop {
	stage: HTMLElement;
	demo: Demo;
	hooks: Hooks;
	reduced: boolean;
	steps: Step[];
	total: number;
	hold = 2400;
	t = 0;
	i = 0;
	last = 0;
	playing = false;
	raf = 0;
	cur!: HTMLElement;
	private typer = 0;
	private timers: number[] = [];

	constructor(stage: HTMLElement, demo: Demo, hooks: Hooks = {}) {
		this.stage = stage;
		this.demo = demo;
		this.hooks = hooks;
		this.reduced = prefersReducedMotion();
		this.steps = demo.steps.slice().sort((a, b) => a[0] - b[0]);
		this.total = demo.total;
		this.reset();
	}

	destroy() {
		this.pause();
		this.clearTimers();
		this.stage.innerHTML = "";
	}

	private clearTimers() {
		if (this.typer) clearInterval(this.typer);
		for (const id of this.timers) clearTimeout(id);
		this.timers = [];
	}

	reset() {
		this.clearTimers();
		this.t = 0;
		this.i = 0;
		this.stage.innerHTML = "";
		this.cur = cursor();
		this.demo.build(this.stage);
		this.stage.appendChild(this.cur);
		this.moveCursor(1000, 600, false);
		this.hooks.onPhase?.(0, 0, false);
		this.hooks.onCaption?.(this.demo.captions[0][1]);
		if (this.reduced) {
			// No timeline: land on the finished frame.
			for (const s of this.steps) this.fire(s);
			this.hooks.onPhase?.(this.demo.phases.length, 1, true);
			this.hooks.onCaption?.(
				this.demo.captions[this.demo.captions.length - 1][1],
			);
		}
	}

	private fire(s: Step) {
		try {
			s[1].call(this);
		} catch (e) {
			console.error(e);
		}
	}

	play() {
		if (this.reduced || this.playing) return;
		this.playing = true;
		this.last = performance.now();
		this.raf = requestAnimationFrame(this.tick);
		this.hooks.onState?.(true);
	}

	pause() {
		if (!this.playing) return;
		this.playing = false;
		cancelAnimationFrame(this.raf);
		this.hooks.onState?.(false);
	}

	private tick = (now: number) => {
		if (!this.playing) return;
		this.t += now - this.last;
		this.last = now;
		while (this.i < this.steps.length && this.steps[this.i][0] <= this.t) {
			this.fire(this.steps[this.i]);
			this.i++;
		}
		const ph = this.demo.phases;
		let p = 0;
		for (let k = 0; k < ph.length; k++) if (this.t >= ph[k]) p = k;
		const end = ph[p + 1] ?? this.total;
		this.hooks.onPhase?.(p, (this.t - ph[p]) / (end - ph[p]), false);
		let c = this.demo.captions[0][1];
		for (const [at, txt] of this.demo.captions) if (this.t >= at) c = txt;
		this.hooks.onCaption?.(c);
		if (this.t >= this.total + this.hold) this.reset();
		this.raf = requestAnimationFrame(this.tick);
	};

	// ---- script vocabulary -------------------------------------------------

	private q<T extends Element = HTMLElement>(sel: string) {
		return this.stage.querySelector<T>(sel);
	}
	private qa(sel: string) {
		return this.stage.querySelectorAll<HTMLElement>(sel);
	}
	/** Scale factor between stage pixels and screen pixels right now. */
	private scale() {
		return this.stage.getBoundingClientRect().width / STAGE_W;
	}

	moveCursor(x: number, y: number, show = true) {
		this.cur.style.transform = `translate(${x}px,${y}px)`;
		this.cur.classList.toggle("vis", show);
	}

	moveTo(sel: string, dx = 12, dy = 10) {
		const t = this.q(sel);
		if (!t) return;
		const a = t.getBoundingClientRect();
		const b = this.stage.getBoundingClientRect();
		const sc = this.scale();
		this.moveCursor((a.left - b.left) / sc + dx, (a.top - b.top) / sc + dy);
	}

	click() {
		const c = this.cur;
		c.classList.remove("click");
		void c.offsetWidth;
		c.classList.add("click");
		this.timers.push(window.setTimeout(() => c.classList.remove("click"), 300));
	}

	type(sel: string, text: string, ms: number) {
		const q = this.q(sel);
		if (!q) return;
		if (this.typer) clearInterval(this.typer);
		if (this.reduced) {
			q.textContent = text;
			return;
		}
		let n = 0;
		this.typer = window.setInterval(() => {
			if (!this.playing) return;
			n++;
			q.textContent = text.slice(0, n);
			if (n >= text.length) clearInterval(this.typer);
		}, ms / text.length);
	}

	show(sel: string) {
		for (const e of this.qa(sel)) e.classList.add("show");
	}
	hide(sel: string) {
		for (const e of this.qa(sel)) e.classList.remove("show");
	}
	text(sel: string, val: string) {
		for (const e of this.qa(sel)) e.textContent = val;
	}
	html(sel: string, val: string) {
		for (const e of this.qa(sel)) e.innerHTML = val;
	}
	addClass(sel: string, cls: string) {
		for (const e of this.qa(sel)) e.classList.add(cls);
	}
	removeClass(sel: string, cls: string) {
		for (const e of this.qa(sel)) e.classList.remove(cls);
	}
	style(sel: string, prop: string, val: string) {
		for (const e of this.qa(sel)) e.style.setProperty(prop, val);
	}

	/** Count a number up over `ms`, formatted by `fmt`. */
	count(sel: string, to: number, ms: number, fmt: (v: number) => string) {
		const t = this.q(sel);
		if (!t) return;
		if (this.reduced) {
			t.textContent = fmt(to);
			return;
		}
		const start = performance.now();
		const step = () => {
			const k = Math.min(1, (performance.now() - start) / ms);
			t.textContent = fmt(Math.round(to * k));
			if (k < 1) requestAnimationFrame(step);
		};
		step();
	}

	/** Fade in each `.w` word under `sel`, spread across `ms`. */
	stream(sel: string, ms: number) {
		const ws = this.qa(`${sel} .w`);
		const per = ms / Math.max(1, ws.length);
		ws.forEach((w, i) => {
			this.timers.push(
				window.setTimeout(
					() => w.classList.add("show"),
					this.reduced ? 0 : i * per,
				),
			);
		});
	}

	/** Drop a hover card under an anchor, kept inside `within`'s width. */
	hoverCard(card: string, anchor: string, within: string, dx = -20) {
		const h = this.q(card);
		const a = this.q(anchor);
		const w = this.q(within);
		if (!h || !a || !w) return;
		const ar = a.getBoundingClientRect();
		const wr = w.getBoundingClientRect();
		const sc = this.scale();
		const width = h.offsetWidth || 340;
		const left = Math.min(
			wr.width / sc - width - 10,
			Math.max(0, (ar.left - wr.left) / sc + dx),
		);
		h.style.left = `${left}px`;
		h.style.top = `${(ar.bottom - wr.top) / sc + 8}px`;
		h.classList.add("show");
	}
}
