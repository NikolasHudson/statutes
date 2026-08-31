// Default Open Graph / Twitter card for every marketing page — the Carbon
// ink band with the wordmark and thesis line. Generated at build time;
// individual routes can override with their own opengraph-image later.

import { ImageResponse } from "next/og";
import { SITE_URL } from "@/lib/site";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt =
	"Hudson Legal Technologies: serious legal research, within reach of every practicing attorney";

export default function OpenGraphImage() {
	return new ImageResponse(
		<div
			style={{
				width: "100%",
				height: "100%",
				display: "flex",
				flexDirection: "column",
				justifyContent: "space-between",
				background: "#161616",
				color: "#ffffff",
				padding: 72,
				fontFamily: "sans-serif",
			}}
		>
			<div
				style={{
					fontSize: 26,
					letterSpacing: 6,
					textTransform: "uppercase",
					color: "#a8a8a8",
				}}
			>
				Hudson Legal Technologies
			</div>
			<div style={{ display: "flex", flexDirection: "column" }}>
				<div style={{ width: 120, height: 6, background: "#0f62fe" }} />
				<div
					style={{
						marginTop: 40,
						fontSize: 64,
						fontWeight: 300,
						lineHeight: 1.15,
						maxWidth: 980,
					}}
				>
					Serious legal research, within reach of every practicing attorney.
				</div>
				<div style={{ marginTop: 32, fontSize: 28, color: "#c6c6c6" }}>
					Every answer traced to the text, every citation verified.
				</div>
			</div>
			{/* The card is the one place the domain is printed as an image — a
			    literal here survives any rename, and would still read
			    "hudsonlegal.tech" on a site served from somewhere else. */}
			<div style={{ fontSize: 24, color: "#78a9ff" }}>
				{new URL(SITE_URL).host}
			</div>
		</div>,
		size,
	);
}
