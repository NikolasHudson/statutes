// Statute/rule body-text structure, shared by the legacy reading pane
// (components/browse/reader.tsx) and the Carbon v2 section reader
// (app/v2/section/[id]) so outline parsing can't drift between skins.
//
// Iowa Code sections are an enumerated hierarchy encoded in the body text:
// each item is on its own line, prefixed with nbsp padding and a marker —
// "1." subsection, "a." paragraph, "(1)" subparagraph, "(a)" sub-subparagraph.
// We infer the depth from the marker style (the Code's fixed nesting order)
// and render an indented outline with hanging markers instead of one blob.

export type StatuteBlock = {
	level: number;
	marker: string | null;
	text: string;
};

const MARKER_RULES: { re: RegExp; level: number }[] = [
	{ re: /^(\d+)\.(?=[\s ])/, level: 1 }, // 1. 2. — subsection
	{ re: /^([a-z]{1,2})\.(?=[\s ])/, level: 2 }, // a. b. — paragraph
	{ re: /^\((\d+)\)(?=[\s ]|$)/, level: 3 }, // (1) — subparagraph
	{ re: /^\(([a-z]{1,3})\)(?=[\s ]|$)/, level: 4 }, // (a) (iv) — sub-sub
];

export function parseStatuteBlocks(text: string): StatuteBlock[] {
	const blocks: StatuteBlock[] = [];
	for (const raw of text.split("\n")) {
		const line = raw.replace(/^[\s ]+/, "").replace(/[\s ]+$/, "");
		if (!line) continue;
		let matched: StatuteBlock | null = null;
		for (const { re, level } of MARKER_RULES) {
			const m = re.exec(line);
			if (m) {
				matched = {
					level,
					marker: m[0],
					text: line.slice(m[0].length).replace(/^[\s ]+/, ""),
				};
				break;
			}
		}
		blocks.push(matched ?? { level: 0, marker: null, text: line });
	}
	return blocks;
}

// Indentation per nesting level. Level 0 (chapeau / plain prose) is flush; each
// deeper enumerated level steps in. Capped so deep nesting can't run off-pane.
export function statuteIndentRem(level: number): number {
	return Math.min(level, 4) * 1.4;
}
