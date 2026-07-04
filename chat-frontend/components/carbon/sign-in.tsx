"use client";

// Functional Carbon sign-in / register screen for the v2 app. Visuals come
// from the /app-carbon-mockup/signin exploration; behavior comes from the
// shared useCredentialsForm hook (same brain as the legacy SignInScreen).
// AuthGate renders this INSTEAD of the /v2 layout while signed out, so it
// carries its own CarbonRoot for theme tokens.

import { LayersIcon, ScrollTextIcon, ShieldCheckIcon } from "lucide-react";
import type { AuthUser } from "@/components/auth-gate";
import {
	BtnPrimary,
	CarbonRoot,
	Notification,
	TextField,
} from "@/components/carbon/primitives";
import { useCredentialsForm } from "@/lib/use-credentials-form";

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

export function CarbonSignIn({
	onSignedIn,
}: {
	onSignedIn: (u: AuthUser) => void;
}) {
	const form = useCredentialsForm(onSignedIn);
	const login = form.mode === "login";

	return (
		<CarbonRoot>
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
					<div className="flex justify-end px-6 pt-5 sm:px-12">
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

						{form.error && (
							<Notification
								kind="error"
								title="Sign-in failed"
								className="mt-6"
							>
								{form.error}
							</Notification>
						)}

						<form className="mt-8 space-y-5" onSubmit={form.onSubmit}>
							{!login && (
								<TextField
									id="signin-name"
									label="Full name (optional)"
									autoComplete="name"
									value={form.fullName}
									onChange={(e) => form.setFullName(e.target.value)}
									disabled={form.busy}
								/>
							)}
							<TextField
								id="signin-email"
								label="Email"
								type="email"
								placeholder="you@firm.com"
								required
								autoComplete={login ? "username" : "email"}
								value={form.email}
								onChange={(e) => form.setEmail(e.target.value)}
								disabled={form.busy}
							/>
							<TextField
								id="signin-password"
								label="Password"
								type="password"
								required
								autoComplete={login ? "current-password" : "new-password"}
								helper={login ? undefined : "At least 8 characters."}
								value={form.password}
								onChange={(e) => form.setPassword(e.target.value)}
								disabled={form.busy}
							/>
							<BtnPrimary
								className="w-full justify-between"
								type="submit"
								disabled={form.busy}
							>
								{form.busy ? "Working…" : login ? "Sign in" : "Create account"}
							</BtnPrimary>
						</form>

						{!login && (
							<p className="mt-4 text-[var(--cds-helper)] text-xs leading-relaxed">
								By creating an account you agree to the{" "}
								<a
									href="/terms"
									target="_blank"
									rel="noopener"
									className="text-[var(--cds-link)] hover:underline"
								>
									Terms of Service
								</a>
								.
							</p>
						)}

						<div className="mt-8 border-[var(--cds-border)] border-t pt-5">
							<button
								type="button"
								onClick={form.toggleMode}
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
		</CarbonRoot>
	);
}
