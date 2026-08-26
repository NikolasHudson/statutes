// Circles-only miniature of a brief figure, for index cards and anywhere a
// figure appears too small for its labels to survive. Pure server-rendered
// SVG from the frozen snapshot geometry — no interactivity, decorative
// (the card's text carries the information).

import type { BriefFigure } from "@/lib/briefs";

export function BubbleThumb({
	figure,
	className,
}: {
	figure: BriefFigure;
	className?: string;
}) {
	const [vw, vh] = figure.viewbox;
	return (
		// biome-ignore lint/a11y/noSvgWithoutTitle: decorative miniature, aria-hidden — the surrounding card text carries the information
		<svg
			viewBox={`0 0 ${vw} ${vh}`}
			aria-hidden
			focusable="false"
			className={className}
		>
			{figure.bubbles.map((b) => {
				const color = figure.categories[b.cat]?.color ?? "#c6c6c6";
				return (
					<circle
						key={b.rank}
						cx={b.x}
						cy={b.y}
						r={b.r}
						fill={color}
						fillOpacity={0.32}
						stroke={color}
						strokeWidth={1.5}
					/>
				);
			})}
		</svg>
	);
}
