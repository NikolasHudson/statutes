// Favicon, generated at build time (no binary asset to maintain): the square
// Carbon "H" monogram — solid Blue-90 navy tile, matching the app's nav rail.

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
				background: "#001d6c",
				color: "#ffffff",
				fontSize: 22,
				fontWeight: 600,
			}}
		>
			H
		</div>,
		size,
	);
}
