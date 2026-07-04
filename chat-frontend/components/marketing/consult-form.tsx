"use client";

// Contact / booking form for the consulting page. Mockup-only: it validates
// required fields and shows a success state on submit, but doesn't POST
// anywhere yet (wire to a real endpoint / inbox when the page goes live).
// Styled to match the app's <Input> so it drops cleanly into the design system.

import { CheckCircle2Icon, Loader2Icon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const TEXTAREA_CLASS =
	"min-h-28 w-full rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 md:text-sm";

export function ConsultForm() {
	const [sent, setSent] = useState(false);
	const [busy, setBusy] = useState(false);

	function onSubmit(e: FormEvent) {
		e.preventDefault();
		setBusy(true);
		// Mockup: no backend yet — fake a brief submit, then show confirmation.
		setSent(true);
		setBusy(false);
	}

	if (sent) {
		return (
			<div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-card p-10 text-center">
				<div className="flex size-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
					<CheckCircle2Icon className="size-6" />
				</div>
				<h3 className="mt-4 font-semibold text-lg tracking-tight">
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
			className="rounded-2xl border border-border bg-card p-6 sm:p-8"
		>
			<div className="grid gap-4 sm:grid-cols-2">
				<Field label="Name" htmlFor="name">
					<Input id="name" name="name" required autoComplete="name" />
				</Field>
				<Field label="Work email" htmlFor="email">
					<Input
						id="email"
						name="email"
						type="email"
						required
						autoComplete="email"
					/>
				</Field>
			</div>
			<div className="mt-4 grid gap-4 sm:grid-cols-2">
				<Field label="Organization" htmlFor="org" optional>
					<Input id="org" name="org" autoComplete="organization" />
				</Field>
				<Field label="Your role" htmlFor="role" optional>
					<Input id="role" name="role" placeholder="e.g. Partner, GC, CTO" />
				</Field>
			</div>
			<div className="mt-4">
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

			<Button type="submit" size="lg" className="mt-6 w-full" disabled={busy}>
				{busy && <Loader2Icon className="size-4 animate-spin" />}
				{busy ? "Sending…" : "Request a consultation"}
			</Button>
			<p className="mt-3 text-center text-[12px] text-muted-foreground">
				No sales pressure — just a conversation about whether we can help.
			</p>
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
			<span className="mb-1.5 flex items-center gap-1.5 font-medium text-sm">
				{label}
				{optional && (
					<span className="font-normal text-muted-foreground text-xs">
						(optional)
					</span>
				)}
			</span>
			{children}
		</label>
	);
}
