"use client";

// Share controls for the article page's sticky rail. Copy-link writes the
// canonical URL to the clipboard (with a brief check-mark confirmation);
// Share uses the native share sheet where the browser has one and falls
// back to copying.

import { CheckIcon, LinkIcon, type LucideIcon, Share2Icon } from "lucide-react";
import { useState } from "react";

export function ShareButtons({ title }: { title: string }) {
	const [copied, setCopied] = useState(false);

	async function copyLink() {
		try {
			await navigator.clipboard.writeText(window.location.href);
			setCopied(true);
			setTimeout(() => setCopied(false), 2000);
		} catch {
			// Clipboard unavailable (permissions/http) — nothing useful to do.
		}
	}

	async function share() {
		if (navigator.share) {
			try {
				await navigator.share({ title, url: window.location.href });
			} catch {
				// User dismissed the sheet — not an error.
			}
		} else {
			await copyLink();
		}
	}

	const buttons: { icon: LucideIcon; label: string; onClick: () => void }[] = [
		{
			icon: copied ? CheckIcon : LinkIcon,
			label: "Copy link",
			onClick: copyLink,
		},
		{ icon: Share2Icon, label: "Share", onClick: share },
	];

	return (
		<>
			{buttons.map((b) => {
				const Icon = b.icon;
				return (
					<button
						key={b.label}
						type="button"
						onClick={b.onClick}
						className="flex size-9 items-center justify-center border border-border bg-card text-muted-foreground transition-colors hover:bg-[#e8e8e8] hover:text-foreground"
						aria-label={b.label}
					>
						<Icon className="size-4" />
					</button>
				);
			})}
		</>
	);
}
