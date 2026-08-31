"use client";

// The coverage-request band's form ("Where should the map grow next?").
// Rides the same lead plumbing as the contact/consulting forms: POST to the
// same-origin /api/contact relay, which lands in the backend's
// ContactSubmission inbox — the `page` field marks these as coverage
// requests for triage. Band treatment, not the boxed white tile: gray-10
// fields with a bottom hairline directly on the white band.

import { ArrowRightIcon, CheckCircle2Icon, Loader2Icon } from "lucide-react";
import { usePathname } from "next/navigation";
import { type FormEvent, useState } from "react";

const INPUT_CLASS =
	"h-12 w-full rounded-none border-0 border-b border-[#8d8d8d] bg-[#f4f4f4] px-4 text-sm placeholder:text-muted-foreground focus:outline-2 focus:outline-[#0f62fe] focus:-outline-offset-2";

export function RequestCoverageForm() {
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
					message: `Coverage request: ${data.get("request")}`,
					website: data.get("website") ?? "",
					page: pathname,
				}),
			});
			if (!res.ok) {
				setError(
					res.status === 429
						? "Too many submissions from this connection. Please email us instead."
						: "Something went wrong sending your request. Please try again, or email us directly.",
				);
				return;
			}
			setSent(true);
		} catch {
			setError(
				"Something went wrong sending your request. Please try again, or email us directly.",
			);
		} finally {
			setBusy(false);
		}
	}

	if (sent) {
		return (
			<div className="mt-9 flex items-start gap-3">
				<CheckCircle2Icon className="mt-0.5 size-5 shrink-0 text-[#0f62fe]" />
				<div>
					<p className="font-semibold text-[15px]">Request received.</p>
					<p className="mt-1 max-w-md text-[#525252] text-sm leading-relaxed">
						We read every one and reply with where it sits in the queue.
					</p>
				</div>
			</div>
		);
	}

	return (
		<form onSubmit={onSubmit} className="relative mt-9">
			<div className="grid max-w-4xl gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)]">
				<Field label="What should we add" htmlFor="request">
					<input
						id="request"
						name="request"
						required
						placeholder="A jurisdiction, a court, a source"
						className={INPUT_CLASS}
					/>
				</Field>
				<Field label="Name" htmlFor="req-name">
					<input
						id="req-name"
						name="name"
						required
						autoComplete="name"
						className={INPUT_CLASS}
					/>
				</Field>
				<Field label="Work email" htmlFor="req-email">
					<input
						id="req-email"
						name="email"
						type="email"
						required
						autoComplete="email"
						placeholder="you@firm.com"
						className={INPUT_CLASS}
					/>
				</Field>
			</div>

			{/* Honeypot — visually hidden and tab-skipped; anything typed here
			    tells the backend to quietly drop the submission. */}
			<div
				aria-hidden
				className="absolute top-0 -left-[9999px] h-0 overflow-hidden"
			>
				<label htmlFor="req-website">
					Website
					<input
						id="req-website"
						name="website"
						tabIndex={-1}
						autoComplete="off"
					/>
				</label>
			</div>

			<button
				type="submit"
				disabled={busy}
				className="mt-6 inline-flex h-12 items-center justify-between gap-10 bg-[#0f62fe] px-4 text-sm text-white transition-colors hover:bg-[#0353e9] active:bg-[#002d9c] disabled:opacity-70"
			>
				<span className="inline-flex items-center gap-2">
					{busy && <Loader2Icon className="size-4 animate-spin" />}
					{busy ? "Sending…" : "Request coverage"}
				</span>
				<ArrowRightIcon className="size-4" />
			</button>
			{error && (
				<p role="alert" className="mt-3 text-[13px] text-[#da1e28]">
					{error}
				</p>
			)}
			<p className="mt-5 font-mono text-[#8d8d8d] text-[11px]">
				Answered by the team that does the ingesting. A timeline, not a sales
				call.
			</p>
		</form>
	);
}

function Field({
	label,
	htmlFor,
	children,
}: {
	label: string;
	htmlFor: string;
	children: React.ReactNode;
}) {
	return (
		<label htmlFor={htmlFor} className="block">
			<span className="mb-2 block text-[#525252] text-[12px]">{label}</span>
			{children}
		</label>
	);
}
