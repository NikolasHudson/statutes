"use client";

// Carbon mockup of the signed-out gate (live: components/auth-gate.tsx
// SignInScreen). Split layout restated in Carbon: g100 brand panel with the
// product promise and feature list, square form column with fluid inputs.
// The login/register toggle works; nothing submits.

import { LayersIcon, ScrollTextIcon, ShieldCheckIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { BtnPrimary, TextField } from "../carbon";

const FEATURES: { icon: React.ElementType; title: string; body: string }[] = [
	{
		icon: ShieldCheckIcon,
		title: "Reviewed & grounded",
		body: "Every answer is traced to the currently effective, human-reviewed text.",
	},
	{
		icon: ScrollTextIcon,
		title: "Full citations",
		body: "Citation, effective date, and enacting session law on every provision.",
	},
	{
		icon: LayersIcon,
		title: "Hybrid search",
		body: "Full-text, trigram, and vector retrieval fused with Reciprocal Rank Fusion.",
	},
];

export default function SignInCarbonMockup() {
	const [mode, setMode] = useState<"login" | "register">("login");
	const login = mode === "login";

	return (
		<div className="flex min-h-0 flex-1">
			{/* Brand panel — g100 in both themes */}
			<section className="hidden w-1/2 flex-col justify-between border-[#393939] border-r bg-[#161616] p-10 text-white lg:flex xl:p-14">
				<div>
					<p className="font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.22em]">
						Hudson Legal Tech
					</p>
					<h1 className="mt-8 max-w-md font-light text-4xl leading-[1.15] xl:text-5xl">
						Iowa statutes, court rules &amp; case law
					</h1>
					<div aria-hidden className="mt-8 h-0.5 w-24 bg-[#0f62fe]" />
					<p className="mt-8 max-w-md text-[#c6c6c6] text-lg leading-relaxed">
						A grounded, citable interface to the Iowa legal corpus — built for
						practitioners who need the effective text, not a guess.
					</p>

					<ul className="mt-12 space-y-7">
						{FEATURES.map((f) => {
							const Icon = f.icon;
							return (
								<li key={f.title} className="flex gap-4">
									<Icon
										className="mt-0.5 size-5 shrink-0 text-[#78a9ff]"
										strokeWidth={1.5}
									/>
									<div>
										<p className="font-semibold text-sm">{f.title}</p>
										<p className="mt-1 max-w-sm text-[#a8a8a8] text-sm leading-relaxed">
											{f.body}
										</p>
									</div>
								</li>
							);
						})}
					</ul>
				</div>

				<p className="font-mono text-[#6f6f6f] text-[11px]">
					Sourced from legis.iowa.gov · Not a substitute for the official
					publication.
				</p>
			</section>

			{/* Form column */}
			<section className="flex min-w-0 flex-1 flex-col overflow-y-auto">
				<div className="flex items-center justify-between px-6 pt-5 sm:px-12">
					<Link
						href="/app-carbon-mockup"
						className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em] hover:text-[var(--cds-link)]"
					>
						← All mockup screens
					</Link>
					<p className="font-mono text-[11px] text-[var(--cds-helper)]">
						corpus.nick.law
					</p>
				</div>

				<div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-12 sm:px-0">
					<h2 className="font-light text-3xl">
						{login ? "Sign in" : "Create your account"}
					</h2>
					<p className="mt-3 text-[15px] text-[var(--cds-text-2)] leading-relaxed">
						{login
							? "Sign in to chat with the Iowa Code, Court Rules, and case law."
							: "Get an API key to use the Iowa Legal Corpus from Claude Desktop or your own integration."}
					</p>

					<form className="mt-8 space-y-5" onSubmit={(e) => e.preventDefault()}>
						{!login && (
							<TextField
								label="Full name (optional)"
								placeholder="Nick Hudson"
							/>
						)}
						<TextField
							label="Email"
							type="email"
							placeholder="you@firm.com"
							required
						/>
						<TextField
							label="Password"
							type="password"
							required
							helper={login ? undefined : "At least 8 characters."}
						/>
						<BtnPrimary className="w-full justify-between" type="submit">
							{login ? "Sign in" : "Create account"}
						</BtnPrimary>
					</form>

					{!login && (
						<p className="mt-4 text-[var(--cds-helper)] text-xs leading-relaxed">
							By creating an account you agree to the{" "}
							<span className="cursor-pointer text-[var(--cds-link)] hover:underline">
								Terms of Service
							</span>
							.
						</p>
					)}

					<div className="mt-8 border-[var(--cds-border)] border-t pt-5">
						<button
							type="button"
							onClick={() => setMode(login ? "register" : "login")}
							className="text-[13px] text-[var(--cds-link)] hover:underline"
						>
							{login
								? "New here? Create an account"
								: "Already have an account? Sign in"}
						</button>
					</div>
				</div>
			</section>
		</div>
	);
}
