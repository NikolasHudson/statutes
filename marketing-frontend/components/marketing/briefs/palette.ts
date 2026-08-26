// Shared mark treatments for brief figures. The categorical hues themselves
// travel inside each snapshot (a published figure must stay self-contained),
// validated colorblind-safe all-pairs on the #161616 band — which is also
// why no figure may carry more than three categories (DATA_BRIEFS.md).
// This module only fixes the alpha treatments so fills and rims read
// identically across every figure in the series.

export const BUBBLE_FILL_ALPHA = 0.32;
export const BUBBLE_FILL_ALPHA_ACTIVE = 0.52;

// "#8a3ffc" → "rgba(138, 63, 252, 0.32)" for legend swatches and dots.
export function tint(hex: string, alpha: number = BUBBLE_FILL_ALPHA): string {
	const r = Number.parseInt(hex.slice(1, 3), 16);
	const g = Number.parseInt(hex.slice(3, 5), 16);
	const b = Number.parseInt(hex.slice(5, 7), 16);
	return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
