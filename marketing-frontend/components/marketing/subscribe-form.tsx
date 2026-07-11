"use client";

// Newsletter signup for the articles index. POSTs to the same-origin
// /api/subscribe route handler, which relays to the backend's
// NewsletterSubscriber table (exportable from the Django admin when a real
// list provider is adopted). Includes a hidden honeypot field for bots.
//
// Carbon-styled: square text input with the bottom-only hairline, Blue-60
// square submit. `tone="dark"` adapts the field to sit on a #161616 band.

import { CheckIcon, Loader2Icon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { cn } from "@/lib/utils";

export function SubscribeForm({ tone = "light" }: { tone?: "light" | "dark" }) {
	const [sent, setSent] = useState(false);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState(false);
	const dark = tone === "dark";

	async function onSubmit(e: FormEvent<HTMLFormElement>) {
		e.preventDefault();
		setBusy(true);
		setError(false);
		const data = new FormData(e.currentTarget);
		try {
			const res = await fetch("/api/subscribe", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					email: data.get("email"),
					website: data.get("website") ?? "",
				}),
			});
			if (!res.ok) {
				setError(true);
				return;
			}
			setSent(true);
		} catch {
			setError(true);
		} finally {
			setBusy(false);
		}
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
			className="relative flex w-full max-w-md flex-col gap-2 sm:flex-row"
		>
			<input
				type="email"
				name="email"
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
			{/* Honeypot — hidden from real users, filled by bots. */}
			<div
				aria-hidden
				className="absolute -left-[9999px] top-0 h-0 overflow-hidden"
			>
				<label htmlFor="subscribe-website">
					Website
					<input
						id="subscribe-website"
						name="website"
						tabIndex={-1}
						autoComplete="off"
					/>
				</label>
			</div>
			<button
				type="submit"
				disabled={busy}
				className="inline-flex h-12 shrink-0 items-center gap-2 bg-[#0f62fe] px-4 text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c] disabled:opacity-70"
			>
				{busy && <Loader2Icon className="size-4 animate-spin" />}
				Subscribe
			</button>
			{error && (
				<p
					role="alert"
					className={cn(
						"text-[13px] sm:absolute sm:top-full sm:mt-2",
						dark ? "text-[#ff8389]" : "text-[#da1e28]",
					)}
				>
					Couldn't subscribe just now — please try again.
				</p>
			)}
		</form>
	);
}
