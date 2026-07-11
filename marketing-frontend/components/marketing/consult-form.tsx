"use client";

// Contact / booking form for the consulting and contact pages. POSTs to the
// same-origin /api/contact route handler, which relays to the backend's
// ContactSubmission table (triaged in the Django admin) and fires an email
// notification. A visually-hidden "website" honeypot field catches bots.
// Carbon (IBM design system) treatment: a square white tile carrying
// gray-10 fields with a bottom hairline and Blue-60 focus outline, mono
// spec labels, and a square Blue-60 submit with a trailing arrow.

import { ArrowRightIcon, CheckCircle2Icon, Loader2Icon } from "lucide-react";
import { usePathname } from "next/navigation";
import { type FormEvent, useState } from "react";

const INPUT_CLASS =
	"h-12 w-full rounded-none border-0 border-b border-[#8d8d8d] bg-[#f4f4f4] px-4 text-sm placeholder:text-muted-foreground focus:outline-2 focus:outline-[#0f62fe] focus:-outline-offset-2";

const TEXTAREA_CLASS =
	"min-h-28 w-full rounded-none border-0 border-b border-[#8d8d8d] bg-[#f4f4f4] px-4 py-3 text-sm placeholder:text-muted-foreground focus:outline-2 focus:outline-[#0f62fe] focus:-outline-offset-2";

export function ConsultForm({
	submitLabel = "Request a consultation",
	caption = "No sales pressure — just a conversation about whether we can help.",
}: {
	submitLabel?: string;
	caption?: string;
} = {}) {
	const pathname = usePathname();
	const [sent, setSent] = useState(false);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);

	async function onSubmit(e: FormEvent<HTMLFormElement>) {
		e.preventDefault();
		setBusy(true);
		setError(null);
		const data = new FormData(e.currentTarget);
		try {
			const res = await fetch("/api/contact", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					name: data.get("name"),
					email: data.get("email"),
					organization: data.get("org") ?? "",
					role: data.get("role") ?? "",
					message: data.get("message"),
					website: data.get("website") ?? "",
					page: pathname,
				}),
			});
			if (!res.ok) {
				setError(
					res.status === 429
						? "Too many submissions from this connection — please email us instead."
						: "Something went wrong sending your message. Please try again, or email us directly.",
				);
				return;
			}
			setSent(true);
		} catch {
			setError(
				"Something went wrong sending your message. Please try again, or email us directly.",
			);
		} finally {
			setBusy(false);
		}
	}

	if (sent) {
		return (
			<div className="flex flex-col items-start justify-center border border-border bg-white p-10 text-foreground">
				<CheckCircle2Icon className="size-6 text-[#0f62fe]" />
				<h3 className="mt-4 font-semibold text-lg">
					Thanks — we'll be in touch
				</h3>
				<p className="mt-2 max-w-sm text-[14px] text-muted-foreground leading-relaxed">
					We read every message and typically reply within a couple of business
					days. Talk soon.
				</p>
			</div>
		);
	}

	return (
		<form
			onSubmit={onSubmit}
			className="relative border border-border bg-white p-6 text-foreground sm:p-8"
		>
			<div className="grid gap-5 sm:grid-cols-2">
				<Field label="Name" htmlFor="name">
					<input
						id="name"
						name="name"
						required
						autoComplete="name"
						className={INPUT_CLASS}
					/>
				</Field>
				<Field label="Work email" htmlFor="email">
					<input
						id="email"
						name="email"
						type="email"
						required
						autoComplete="email"
						className={INPUT_CLASS}
					/>
				</Field>
			</div>
			<div className="mt-5 grid gap-5 sm:grid-cols-2">
				<Field label="Organization" htmlFor="org" optional>
					<input
						id="org"
						name="org"
						autoComplete="organization"
						className={INPUT_CLASS}
					/>
				</Field>
				<Field label="Your role" htmlFor="role" optional>
					<input
						id="role"
						name="role"
						placeholder="e.g. Partner, GC, CTO"
						className={INPUT_CLASS}
					/>
				</Field>
			</div>
			<div className="mt-5">
				<Field label="How can we help?" htmlFor="message">
					<textarea
						id="message"
						name="message"
						required
						className={TEXTAREA_CLASS}
						placeholder="A sentence or two on what you're trying to do."
					/>
				</Field>
			</div>

			{/* Honeypot — visually hidden and tab-skipped; anything typed here
			    tells the backend to quietly drop the submission. */}
			<div
				aria-hidden
				className="absolute -left-[9999px] top-0 h-0 overflow-hidden"
			>
				<label htmlFor="website">
					Website
					<input id="website" name="website" tabIndex={-1} autoComplete="off" />
				</label>
			</div>

			<button
				type="submit"
				disabled={busy}
				className="mt-8 inline-flex h-12 w-full items-center justify-between gap-10 bg-[#0f62fe] px-4 text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c] disabled:opacity-70"
			>
				<span className="inline-flex items-center gap-2">
					{busy && <Loader2Icon className="size-4 animate-spin" />}
					{busy ? "Sending…" : submitLabel}
				</span>
				<ArrowRightIcon className="size-4" />
			</button>
			{error && (
				<p role="alert" className="mt-3 text-[13px] text-[#da1e28]">
					{error}
				</p>
			)}
			<p className="mt-3 text-[12px] text-muted-foreground">{caption}</p>
		</form>
	);
}

function Field({
	label,
	htmlFor,
	optional,
	children,
}: {
	label: string;
	htmlFor: string;
	optional?: boolean;
	children: React.ReactNode;
}) {
	return (
		<label htmlFor={htmlFor} className="block">
			<span className="mb-2 flex items-baseline gap-1.5 font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
				{label}
				{optional && <span className="normal-case">(optional)</span>}
			</span>
			{children}
		</label>
	);
}
