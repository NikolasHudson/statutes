// Reader display preferences for the case reader (font size, family, measure).
// Per-browser, not per-user — a reading-comfort setting, not account data.
// Same try/catch discipline as lib/nav-prefs.ts: storage can be absent or
// throw (private mode, quota), and the reader must render either way.

export type ReaderFamily = "serif" | "sans";
export type ReaderMeasure = "narrow" | "wide";

export type ReaderPrefs = {
	fontSize: number;
	family: ReaderFamily;
	measure: ReaderMeasure;
};

export const READER_FONT_MIN = 14;
export const READER_FONT_MAX = 22;

export const DEFAULT_READER_PREFS: ReaderPrefs = {
	fontSize: 17,
	family: "serif",
	measure: "narrow",
};

const KEY = "hudson:reader:display";

export function loadReaderPrefs(): ReaderPrefs {
	try {
		const raw = localStorage.getItem(KEY);
		if (!raw) return DEFAULT_READER_PREFS;
		const p = JSON.parse(raw) as Partial<ReaderPrefs>;
		const size = Number(p.fontSize);
		return {
			fontSize:
				Number.isFinite(size) &&
				size >= READER_FONT_MIN &&
				size <= READER_FONT_MAX
					? size
					: DEFAULT_READER_PREFS.fontSize,
			family: p.family === "sans" ? "sans" : "serif",
			measure: p.measure === "wide" ? "wide" : "narrow",
		};
	} catch {
		return DEFAULT_READER_PREFS;
	}
}

export function saveReaderPrefs(prefs: ReaderPrefs): void {
	try {
		localStorage.setItem(KEY, JSON.stringify(prefs));
	} catch {
		/* storage unavailable — the in-memory state still applies */
	}
}
