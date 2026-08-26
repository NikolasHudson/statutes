// Share card for data brief 001 — the share preview IS the figure: the real
// fifty-bubble layout from the frozen snapshot, drawn as positioned circles
// beside the title. Generated at build time from the same JSON the page
// renders, so the card can never disagree with the chart.

import { ImageResponse } from "next/og";
import { tint } from "@/components/marketing/briefs/palette";
import { briefNo, formatAsOf, MOST_CITED_CASES } from "@/lib/briefs";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt =
	"The fifty most-cited Iowa cases, drawn as a packed bubble chart — Hudson Corpus data brief 001";

const snap = MOST_CITED_CASES;
const fig = snap.figures[0];
const [vw, vh] = fig.viewbox;

// Scale the 1000×660 viewBox into the card's right half.
const CHART_W = 620;
const CHART_H = 560;
const S = Math.min(CHART_W / vw, CHART_H / vh);

export default function OpenGraphImage() {
	return new ImageResponse(
		<div
			style={{
				width: "100%",
				height: "100%",
				display: "flex",
				alignItems: "center",
				background: "#161616",
				color: "#ffffff",
				fontFamily: "sans-serif",
			}}
		>
			<div
				style={{
					display: "flex",
					flexDirection: "column",
					justifyContent: "center",
					width: 560,
					height: "100%",
					padding: "0 24px 0 64px",
				}}
			>
				<div
					style={{
						fontSize: 20,
						letterSpacing: 3,
						textTransform: "uppercase",
						color: "#78a9ff",
					}}
				>
					{`Hudson Corpus · Data brief ${briefNo(snap)}`}
				</div>
				<div
					style={{ marginTop: 28, width: 96, height: 5, background: "#0f62fe" }}
				/>
				<div
					style={{
						marginTop: 32,
						fontSize: 50,
						fontWeight: 300,
						lineHeight: 1.15,
					}}
				>
					The Most-Cited Cases in Iowa
				</div>
				<div style={{ marginTop: 28, fontSize: 24, color: "#c6c6c6" }}>
					{`${snap.totals.edges.toLocaleString("en-US")} citations · as of ${formatAsOf(snap.as_of)}`}
				</div>
			</div>
			<div
				style={{
					position: "relative",
					display: "flex",
					width: CHART_W,
					height: CHART_H,
				}}
			>
				{fig.bubbles.map((b) => {
					const color = fig.categories[b.cat]?.color ?? "#c6c6c6";
					return (
						<div
							key={b.rank}
							style={{
								position: "absolute",
								left: (b.x - b.r) * S + (CHART_W - vw * S) / 2,
								top: (b.y - b.r) * S + (CHART_H - vh * S) / 2,
								width: 2 * b.r * S,
								height: 2 * b.r * S,
								borderRadius: 9999,
								border: `2px solid ${color}`,
								background: tint(color),
							}}
						/>
					);
				})}
			</div>
		</div>,
		size,
	);
}
