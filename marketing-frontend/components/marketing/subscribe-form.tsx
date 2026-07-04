"use client";

// Newsletter signup for the articles index. Mockup-only: validates an email and
// shows a confirmation, but doesn't POST anywhere yet (wire to a list provider
// — e.g. Resend/Buttondown — when the site goes live).
//
// Carbon-styled: square text input with the bottom-only hairline, Blue-60
// square submit. `tone="dark"` adapts the field to sit on a #161616 band.

import { CheckIcon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { cn } from "@/lib/utils";

export function SubscribeForm({ tone = "light" }: { tone?: "light" | "dark" }) {
	const [sent, setSent] = useState(false);
	const dark = tone === "dark";

	function onSubmit(e: FormEvent) {
		e.preventDefault();
		setSent(true);
	}

	if (sent) {
		return (
			<p
				className={cn(
					"flex items-center gap-3 text-[15px]",
					dark ? "text-white" : "text-foreground",
				)}
			>
				<span
					className={cn(
						"flex size-5 shrink-0 items-center justify-center border",
						dark
							? "border-[#6f6f6f] text-[#78a9ff]"
							: "border-[#8d8d8d] text-[#0f62fe]",
					)}
				>
					<CheckIcon className="size-3.5" strokeWidth={2.5} />
				</span>
				You're on the list — thanks for subscribing.
			</p>
		);
	}

	return (
		<form
			onSubmit={onSubmit}
			className="flex w-full max-w-md flex-col gap-2 sm:flex-row"
		>
			<input
				type="email"
				required
				placeholder="you@firm.com"
				aria-label="Email address"
				className={cn(
					"h-12 w-full rounded-none border-0 border-b px-4 text-sm focus:outline-2 focus:-outline-offset-2 focus:outline-[#0f62fe]",
					dark
						? "border-[#6f6f6f] bg-[#262626] text-white placeholder:text-[#6f6f6f]"
						: "border-[#8d8d8d] bg-[#f4f4f4] text-foreground placeholder:text-[#a8a8a8]",
				)}
			/>
			<button
				type="submit"
				className="h-12 shrink-0 bg-[#0f62fe] px-4 text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c]"
			>
				Subscribe
			</button>
		</form>
	);
}
