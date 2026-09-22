// Shared chrome for the demo stages: the app's navy rail (mirroring SideNav
// mode="rail" in chat-frontend/components/carbon/primitives.tsx cell for
// cell), the Lucide paths the shell actually uses, and the animated cursor.
// Everything is plain DOM built from strings because the loops are scripted
// against the DOM directly (see engine.ts); React never re-renders a stage.

export const el = (tag: string, cls?: string, html?: string) => {
	const e = document.createElement(tag);
	if (cls) e.className = cls;
	if (html != null) e.innerHTML = html;
	return e;
};

// Stream-in helper: each word becomes a `.w` span the engine fades in.
export const words = (s: string) =>
	s
		.split(" ")
		.map((w) => `<span class="w">${w}</span>`)
		.join(" ");

// Lucide icon bodies (24x24), copied from lucide-react so the rail matches the
// app glyph for glyph. Keep in step with NAV in chat-frontend/app/(app)/shell.tsx.
const L: Record<string, string> = {
	panel:
		'<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m14 9 3 3-3 3"/>',
	search: '<path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/>',
	chat: '<path d="M22 17a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 21.286V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z"/><path d="M7 11h10"/><path d="M7 15h6"/><path d="M7 7h8"/>',
	sliders:
		'<path d="M10 5H3"/><path d="M12 19H3"/><path d="M14 3v4"/><path d="M16 17v4"/><path d="M21 12h-9"/><path d="M21 19h-5"/><path d="M21 5h-7"/><path d="M8 10v4"/><path d="M8 12H3"/>',
	compare:
		'<circle cx="5" cy="6" r="3"/><path d="M12 6h5a2 2 0 0 1 2 2v7"/><path d="m15 9-3-3 3-3"/><circle cx="19" cy="18" r="3"/><path d="M12 18H7a2 2 0 0 1-2-2V9"/><path d="m9 15 3 3-3 3"/>',
	db: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
	org: '<path d="M10 12h4"/><path d="M10 8h4"/><path d="M14 21v-3a2 2 0 0 0-4 0v3"/><path d="M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16"/>',
	card: '<rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/>',
	cloud: '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
	alert:
		'<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
	send: '<path d="M3 12l18-8-8 18-2-8z"/>',
	copy: '<rect x="8" y="8" width="12" height="12"/><path d="M16 8V4H4v12h4"/>',
	print:
		'<rect x="6" y="14" width="12" height="7"/><path d="M6 10V3h12v7M4 10h16v7h-2"/>',
};

export const svg = (k: string, cls = "") =>
	`<svg class="${cls}" viewBox="0 0 24 24">${L[k]}</svg>`;

// Blue-60 stroked icon for the top bar's search field.
export const searchIcon = () => svg("search", "svgi");
export const inkIcon = (k: string) => svg(k, "svgi ink");

/** Which Workspace entry is lit: 0 Library, 1 Assistant, 2 Advanced, 3 Compare, 4 Resources. */
export function rail(active: number) {
	const r = el("div", "rail");
	const ws = ["search", "chat", "sliders", "compare", "db"];
	const acct = ["org", "card", "cloud"];
	r.innerHTML = `<div class="cell home"><span>H</span></div><div class="cell">${svg("panel")}</div>
		<div class="items">${ws
			.map(
				(k, i) =>
					`<div class="cell ${i === active ? "on" : ""}">${svg(k)}</div>`,
			)
			.join("")}<div class="sep"></div>${acct
			.map((k) => `<div class="cell">${svg(k)}</div>`)
			.join("")}</div>
		<div class="foot"><div class="cell beta">${svg("alert")}</div><div class="cell me"><span>NH</span></div></div>`;
	return r;
}

export function cursor() {
	const c = el("div", "cur");
	c.innerHTML =
		'<svg viewBox="0 0 20 24" width="20" height="24"><path d="M2 2l14 11-6 1 4 8-3 1-4-8-5 5z" fill="#161616" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';
	return c;
}
