"use client";

// A framed "product photo" slot for the marketing site. Renders a browser
// window (chrome bar + faux address) around a screenshot. Drop-in friendly:
// give it the intended public path as `src`; until that file exists the <img>
// 404s and we fall back to a labeled placeholder that names the exact file to
// add. The moment the file lands in /public, the real screenshot appears with
// no code change. Recommended capture sizes live in
// public/marketing/corpus/README.md.

import { ImageIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { appHost } from "@/lib/brand";
import { cn } from "@/lib/utils";

export function Screenshot({
	src,
	alt,
	label,
	url,
	aspect = "16 / 10",
	className,
}: {
	/** Intended public path, e.g. "/marketing/corpus/assistant.png". */
	src: string;
	alt: string;
	/** Human label shown in the placeholder before the image is added. */
	label: string;
	/** Faux address-bar text. Defaults to the app's own host. */
	url?: string;
	/** CSS aspect-ratio for the viewport, e.g. "16 / 10". */
	aspect?: string;
	className?: string;
}) {
	const [failed, setFailed] = useState(false);

	// These pages are server-rendered, and the app's host is only knowable from
	// `window` unless NEXT_PUBLIC_APP_URL is set — so resolve it after mount
	// rather than during render, which would hydrate a different address than
	// the server sent.
	const [host, setHost] = useState("");
	useEffect(() => setHost(appHost()), []);
	const address = url ?? host;

	return (
		<div
			className={cn(
				"overflow-hidden rounded-xl border border-border bg-card shadow-2xl",
				className,
			)}
		>
			{/* browser chrome */}
			<div className="flex items-center gap-2 border-border border-b bg-secondary/60 px-3 py-2.5">
				<span className="size-2.5 rounded-full bg-[#ff5f57]" />
				<span className="size-2.5 rounded-full bg-[#febc2e]" />
				<span className="size-2.5 rounded-full bg-[#28c840]" />
				<div className="mx-auto w-full max-w-xs truncate rounded-md bg-background px-3 py-1 text-center font-medium text-[11px] text-muted-foreground">
					{address}
				</div>
				{/* keeps the address bar visually centered against the dots */}
				<span aria-hidden className="w-[42px] shrink-0" />
			</div>

			{/* viewport */}
			<div
				className="relative w-full bg-secondary/30"
				style={{ aspectRatio: aspect }}
			>
				{failed ? (
					<Placeholder label={label} src={src} />
				) : (
					// biome-ignore lint/performance/noImgElement: drop-in screenshot slot needs onError fallback
					<img
						src={src}
						alt={alt}
						className="absolute inset-0 size-full object-cover object-top"
						onError={() => setFailed(true)}
					/>
				)}
			</div>
		</div>
	);
}

function Placeholder({ label, src }: { label: string; src: string }) {
	return (
		<div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
			{/* dashed inner frame so it clearly reads as a slot, not a broken image */}
			<div
				aria-hidden
				className="absolute inset-3 rounded-lg border border-border border-dashed"
			/>
			<div className="relative flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
				<ImageIcon className="size-6" />
			</div>
			<div className="relative">
				<p className="font-semibold text-foreground text-sm">{label}</p>
				<p className="mt-1 font-mono text-[11px] text-muted-foreground">
					Add image: <span className="text-primary">public{src}</span>
				</p>
			</div>
		</div>
	);
}
