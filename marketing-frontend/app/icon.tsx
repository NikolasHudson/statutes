// Favicon, generated at build time (no binary asset to maintain): the square
// Carbon "H" monogram — ink #161616 tile, Blue-60 base rule.

import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
	return new ImageResponse(
		<div
			style={{
				width: "100%",
				height: "100%",
				display: "flex",
				alignItems: "center",
				justifyContent: "center",
				background: "#161616",
				color: "#ffffff",
				fontSize: 22,
				fontWeight: 600,
				borderBottom: "3px solid #0f62fe",
			}}
		>
			H
		</div>,
		size,
	);
}
