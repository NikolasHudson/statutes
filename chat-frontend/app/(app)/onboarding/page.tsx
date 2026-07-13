"use client";

// First-run onboarding — the six-step Carbon setup wizard wired to the
// real settings API. Each Continue PATCHes that step's fields (so quitting
// mid-way loses nothing), and the final step accepts the current ToS via
// completeOnboarding, flips the auth user, and lands in the app. AuthGate
// nudges not-yet-onboarded users here (legacy /classic paths keep the
// legacy wizard).

import { CheckIcon, MonitorIcon, MoonIcon, SunIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth-gate";
import {
	BtnPrimary,
	CheckboxRow,
	Eyebrow,
	Notification,
	SelectField,
	TextField,
	ToggleRow,
	useTheme,
} from "@/components/carbon/primitives";
import {
	completeOnboarding,
	getSettings,
	type UserSettings,
	type UserSettingsPatch,
	updateSettings,
} from "@/lib/iowa-account";
import {
	CITATION_STYLES,
	JURISDICTIONS,
	labelOf,
	ROLES,
	SEARCH_SCOPES,
	TIMEZONES,
} from "@/lib/settings-options";
import { BRAND_NAME } from "@/lib/brand";
import { cn } from "@/lib/utils";

const STEPS: { label: string; blurb: string }[] = [
	{ label: "Welcome", blurb: "What we'll set up" },
	{ label: "Your info", blurb: "Contact & practice" },
	{ label: "Appearance", blurb: "Theme" },
	{ label: "Research", blurb: "Defaults & alerts" },
	{ label: "Terms", blurb: "Review & accept" },
	{ label: "All set", blurb: "Finish up" },
];

// Editable wizard state — a draft over UserSettings' patchable fields.
type Draft = Required<
	Pick<
		UserSettingsPatch,
		| "first_name"
		| "last_name"
		| "phone"
		| "address_line1"
		| "address_line2"
		| "city"
		| "region"
		| "postal_code"
		| "organization"
		| "role"
		| "bar_number"
		| "primary_jurisdiction"
		| "timezone"
		| "theme"
		| "default_search_scope"
		| "citation_style"
		| "verify_citations"
		| "weekly_digest"
		| "product_news"
	>
>;

const draftFrom = (s: UserSettings): Draft => ({
	first_name: s.first_name,
	last_name: s.last_name,
	phone: s.phone,
	address_line1: s.address_line1,
	address_line2: s.address_line2,
	city: s.city,
	region: s.region,
	postal_code: s.postal_code,
	organization: s.organization,
	role: s.role,
	bar_number: s.bar_number,
	primary_jurisdiction: s.primary_jurisdiction,
	timezone: s.timezone,
	theme: s.theme,
	default_search_scope: s.default_search_scope,
	citation_style: s.citation_style,
	verify_citations: s.verify_citations,
	weekly_digest: s.weekly_digest,
	product_news: s.product_news,
});

// Which draft fields each step owns (PATCHed when leaving that step).
const STEP_FIELDS: Partial<Record<number, (keyof Draft)[]>> = {
	1: [
		"first_name",
		"last_name",
		"phone",
		"address_line1",
		"address_line2",
		"city",
		"region",
		"postal_code",
		"organization",
		"role",
		"bar_number",
		"primary_jurisdiction",
		"timezone",
	],
	2: ["theme"],
	3: [
		"default_search_scope",
		"citation_style",
		"verify_citations",
		"weekly_digest",
		"product_news",
	],
};

export default function V2OnboardingPage() {
	const router = useRouter();
	const { user, setUser } = useAuth();
	const [settings, setSettings] = useState<UserSettings | null>(null);
	const [draft, setDraft] = useState<Draft | null>(null);
	const [step, setStep] = useState(0);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [agree, setAgree] = useState(false);
	const [understand, setUnderstand] = useState(false);

	useEffect(() => {
		getSettings()
			.then((s) => {
				setSettings(s);
				setDraft(draftFrom(s));
			})
			.catch((e) => setError((e as Error).message));
	}, []);

	if (!settings || !draft) {
		return (
			<div className="px-5 py-10 sm:px-10">
				{error ? (
					<Notification
						kind="error"
						title="Couldn't load your account"
						className="max-w-xl"
					>
						{error}
					</Notification>
				) : (
					<p className="text-[var(--cds-text-2)] text-sm">Loading…</p>
				)}
			</div>
		);
	}

	const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
		setDraft((d) => (d ? { ...d, [k]: v } : d));

	const last = step === STEPS.length - 1;
	const termsStep = step === 4;
	const continueDisabled = busy || (termsStep && !(agree && understand));

	const advance = async () => {
		setError(null);
		const fields = STEP_FIELDS[step];
		setBusy(true);
		try {
			if (fields) {
				const patch: UserSettingsPatch = {};
				for (const f of fields) {
					// biome-ignore lint/suspicious/noExplicitAny: keyed copy of like-typed fields
					(patch as any)[f] = draft[f];
				}
				setSettings(await updateSettings(patch));
			}
			if (termsStep) {
				setSettings(await completeOnboarding(settings.current_tos_version));
			}
			if (last) {
				setUser({ ...user, onboarding_completed: true });
				router.push("/");
				return;
			}
			setStep(step + 1);
		} catch (e) {
			setError((e as Error).message);
		} finally {
			setBusy(false);
		}
	};

	return (
		<div className="flex min-h-0 flex-1">
			<StepperRail step={step} onJump={(n) => n <= step && setStep(n)} />

			<main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
				<div className="flex items-center justify-between px-5 pt-6 sm:px-10">
					<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
						Step {step + 1} of {STEPS.length}
					</p>
					<button
						type="button"
						onClick={() => router.push("/")}
						className="text-[13px] text-[var(--cds-link)] hover:underline"
					>
						Skip for now
					</button>
				</div>
				<div className="mx-5 mt-3 h-0.5 bg-[var(--cds-border)] sm:mx-10">
					<div
						className="h-full bg-[#0f62fe] transition-[width]"
						style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
					/>
				</div>

				<div className="mx-auto w-full max-w-2xl flex-1 px-5 py-10 sm:px-10">
					{error && (
						<Notification kind="error" title="Couldn't save" className="mb-8">
							{error}
						</Notification>
					)}
					{step === 0 && (
						<StepWelcome name={draft.first_name || user.full_name || "there"} />
					)}
					{step === 1 && (
						<StepInfo draft={draft} email={settings.email} set={set} />
					)}
					{step === 2 && <StepAppearance draft={draft} set={set} />}
					{step === 3 && <StepResearch draft={draft} set={set} />}
					{step === 4 && (
						<StepTerms
							version={settings.current_tos_version}
							agree={agree}
							understand={understand}
							onAgree={setAgree}
							onUnderstand={setUnderstand}
						/>
					)}
					{step === 5 && <StepReview draft={draft} email={settings.email} />}
				</div>

				<footer className="flex shrink-0 items-center justify-between border-[var(--cds-border)] border-t px-5 py-4 sm:px-10">
					{step > 0 ? (
						<button
							type="button"
							onClick={() => setStep(step - 1)}
							className="h-10 px-4 text-[var(--cds-link)] text-sm transition-colors hover:bg-[var(--cds-layer-hover)]"
						>
							Back
						</button>
					) : (
						<span />
					)}
					<BtnPrimary size="md" disabled={continueDisabled} onClick={advance}>
						{busy
							? "Saving…"
							: last
								? "Enter the app"
								: termsStep
									? "Accept & continue"
									: "Continue"}
					</BtnPrimary>
				</footer>
			</main>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Stepper rail — g100-dark in both themes, IBM setup-flow register
// ---------------------------------------------------------------------------

function StepperRail({
	step,
	onJump,
}: {
	step: number;
	onJump: (n: number) => void;
}) {
	return (
		<aside className="hidden w-72 shrink-0 flex-col border-[#393939] border-r bg-[#161616] text-white md:flex">
			<div className="px-6 pt-8">
				<p className="font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.22em]">
					Hudson Legal Tech
				</p>
				<h2 className="mt-3 font-light text-2xl">Account setup</h2>
			</div>

			<ol className="mt-8 flex-1">
				{STEPS.map((s, i) => {
					const done = i < step;
					const active = i === step;
					return (
						<li key={s.label}>
							<button
								type="button"
								onClick={() => onJump(i)}
								className={cn(
									"flex w-full items-start gap-4 border-l-[3px] px-6 py-3 text-left transition-colors",
									active
										? "border-[#0f62fe] bg-[#262626]"
										: "border-transparent hover:bg-[#262626]",
								)}
							>
								<span
									className={cn(
										"mt-0.5 flex size-6 shrink-0 items-center justify-center border font-mono text-[11px]",
										done
											? "border-[#0f62fe] bg-[#0f62fe] text-white"
											: active
												? "border-white text-white"
												: "border-[#6f6f6f] text-[#a8a8a8]",
									)}
								>
									{done ? (
										<CheckIcon className="size-3.5" strokeWidth={3} />
									) : (
										i + 1
									)}
								</span>
								<span className="min-w-0">
									<span
										className={cn(
											"block text-sm",
											active ? "font-semibold" : done ? "" : "text-[#a8a8a8]",
										)}
									>
										{s.label}
									</span>
									<span className="block text-[#8d8d8d] text-xs">
										{s.blurb}
									</span>
								</span>
							</button>
						</li>
					);
				})}
			</ol>

			<p className="border-[#393939] border-t px-6 py-5 text-[#8d8d8d] text-xs leading-relaxed">
				Takes about 2 minutes · you can change everything later in Settings.
			</p>
		</aside>
	);
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

function StepHead({
	eyebrow,
	title,
	lede,
}: {
	eyebrow: string;
	title: string;
	lede?: string;
}) {
	return (
		<header>
			<Eyebrow>{eyebrow}</Eyebrow>
			<h1 className="mt-3 font-light text-3xl">{title}</h1>
			{lede && (
				<p className="mt-3 max-w-lg text-[15px] text-[var(--cds-text-2)] leading-relaxed">
					{lede}
				</p>
			)}
		</header>
	);
}

function StepWelcome({ name }: { name: string }) {
	return (
		<div>
			<StepHead
				eyebrow="Welcome"
				title={`Welcome, ${name}.`}
				lede={`Let's get your account set up so ${BRAND_NAME} works the way you do. Four quick steps — everything can be changed later.`}
			/>
			<ul className="mt-8 divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]">
				{[
					["Tell us who you are", "Name, contact info & practice area"],
					["Make it yours", "Light or dark mode"],
					["Set research defaults", "Jurisdiction, citation style & alerts"],
					["Review the terms", "Terms of Service & how we handle data"],
				].map(([t, d], i) => (
					<li
						key={t}
						className="flex items-center gap-4 bg-[var(--cds-layer)] px-4 py-3.5"
					>
						<span className="font-mono text-[var(--cds-helper)] text-[11px]">
							0{i + 1}
						</span>
						<span className="min-w-0">
							<span className="block font-medium text-sm">{t}</span>
							<span className="block text-[var(--cds-text-2)] text-xs">
								{d}
							</span>
						</span>
					</li>
				))}
			</ul>
		</div>
	);
}

function GroupLabel({ children }: { children: React.ReactNode }) {
	return (
		<p className="mt-8 mb-4 border-[var(--cds-border)] border-t pt-5 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
			{children}
		</p>
	);
}

function StepInfo({
	draft,
	email,
	set,
}: {
	draft: Draft;
	email: string;
	set: <K extends keyof Draft>(k: K, v: Draft[K]) => void;
}) {
	return (
		<div>
			<StepHead eyebrow="About you" title="Tell us who you are" />
			<div className="mt-8 grid gap-5 sm:grid-cols-2">
				<TextField
					label="First name"
					value={draft.first_name}
					onChange={(e) => set("first_name", e.target.value)}
				/>
				<TextField
					label="Last name"
					value={draft.last_name}
					onChange={(e) => set("last_name", e.target.value)}
				/>
				<TextField
					label="Email"
					value={email}
					readOnly
					helper="Your login email — used for sign-in and alerts."
				/>
				<TextField
					label="Phone"
					value={draft.phone}
					onChange={(e) => set("phone", e.target.value)}
					placeholder="(555) 123-4567"
				/>
			</div>
			<GroupLabel>Mailing address</GroupLabel>
			<div className="grid gap-5 sm:grid-cols-6">
				<TextField
					label="Street address"
					value={draft.address_line1}
					onChange={(e) => set("address_line1", e.target.value)}
					placeholder="123 Main St"
					className="sm:col-span-4"
				/>
				<TextField
					label="Apt / Suite"
					value={draft.address_line2}
					onChange={(e) => set("address_line2", e.target.value)}
					placeholder="Suite 200"
					className="sm:col-span-2"
				/>
				<TextField
					label="City"
					value={draft.city}
					onChange={(e) => set("city", e.target.value)}
					placeholder="Des Moines"
					className="sm:col-span-3"
				/>
				<TextField
					label="State"
					value={draft.region}
					onChange={(e) => set("region", e.target.value)}
					placeholder="IA"
					className="sm:col-span-1"
				/>
				<TextField
					label="ZIP"
					value={draft.postal_code}
					onChange={(e) => set("postal_code", e.target.value)}
					placeholder="50309"
					className="sm:col-span-2"
				/>
			</div>
			<GroupLabel>Practice</GroupLabel>
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField
					label="Organization"
					value={draft.organization}
					onChange={(e) => set("organization", e.target.value)}
					placeholder="e.g. Hudson Law LLC"
				/>
				<SelectField
					label="Your role"
					options={ROLES}
					value={draft.role}
					onChange={(e) => set("role", e.target.value)}
				/>
				<TextField
					label="Bar number"
					value={draft.bar_number}
					onChange={(e) => set("bar_number", e.target.value)}
					placeholder="e.g. AT0001234"
				/>
				<SelectField
					label="Primary jurisdiction"
					options={JURISDICTIONS}
					value={draft.primary_jurisdiction}
					onChange={(e) => set("primary_jurisdiction", e.target.value)}
				/>
				<SelectField
					label="Time zone"
					options={TIMEZONES}
					value={draft.timezone}
					onChange={(e) => set("timezone", e.target.value)}
					className="sm:col-span-2"
				/>
			</div>
		</div>
	);
}

function StepAppearance({
	draft,
	set,
}: {
	draft: Draft;
	set: <K extends keyof Draft>(k: K, v: Draft[K]) => void;
}) {
	const { setTheme } = useTheme();
	const cards = [
		{
			id: "light",
			label: "Light",
			icon: SunIcon,
			swatch: ["#ffffff", "#f4f4f4", "#161616"],
		},
		{
			id: "dark",
			label: "Dark",
			icon: MoonIcon,
			swatch: ["#161616", "#262626", "#f4f4f4"],
		},
		{
			id: "system",
			label: "System",
			icon: MonitorIcon,
			swatch: ["#ffffff", "#262626", "#161616"],
		},
	];
	const pick = (id: string) => {
		set("theme", id);
		// Flip the live shell too (system falls back to light).
		setTheme(id === "dark" ? "g100" : "white");
	};
	return (
		<div>
			<StepHead
				eyebrow="Appearance"
				title="Make it yours"
				lede="Pick a theme — the whole app flips live."
			/>
			<div className="mt-8 grid gap-4 sm:grid-cols-3">
				{cards.map((c) => {
					const Icon = c.icon;
					const active = draft.theme === c.id;
					return (
						<button
							key={c.id}
							type="button"
							onClick={() => pick(c.id)}
							className={cn(
								"border p-4 text-left transition-colors",
								active
									? "border-[#0f62fe] outline outline-1 outline-[#0f62fe]"
									: "border-[var(--cds-border)] hover:border-[var(--cds-border-strong)]",
							)}
						>
							<span className="flex h-16 overflow-hidden border border-[var(--cds-border)]">
								{c.swatch.map((hex) => (
									<span
										key={hex}
										className="flex-1"
										style={{ backgroundColor: hex }}
									/>
								))}
							</span>
							<span className="mt-3 flex items-center justify-between">
								<span className="flex items-center gap-2 font-medium text-sm">
									<Icon className="size-4" strokeWidth={1.5} />
									{c.label}
								</span>
								{active && (
									<CheckIcon
										className="size-4 text-[var(--cds-link)]"
										strokeWidth={2.5}
									/>
								)}
							</span>
						</button>
					);
				})}
			</div>
		</div>
	);
}

function StepResearch({
	draft,
	set,
}: {
	draft: Draft;
	set: <K extends keyof Draft>(k: K, v: Draft[K]) => void;
}) {
	return (
		<div>
			<StepHead eyebrow="Research" title="Set your defaults" />
			<div className="mt-8 grid gap-5 sm:grid-cols-2">
				<SelectField
					label="Default search scope"
					options={SEARCH_SCOPES}
					value={draft.default_search_scope}
					onChange={(e) => set("default_search_scope", e.target.value)}
				/>
				<SelectField
					label="Citation style"
					options={CITATION_STYLES}
					value={draft.citation_style}
					onChange={(e) => set("citation_style", e.target.value)}
				/>
			</div>
			<GroupLabel>Answers &amp; notifications</GroupLabel>
			<div className="divide-y divide-[var(--cds-border)]">
				<ToggleRow
					label="Verify citations before showing answers"
					detail="Run the deterministic citation & quote check on every AI response. Recommended."
					on={draft.verify_citations}
					onChange={(v) => set("verify_citations", v)}
				/>
				<ToggleRow
					label="Weekly corpus digest"
					detail="What's new in cases, statutes & rules for your jurisdiction."
					on={draft.weekly_digest}
					onChange={(v) => set("weekly_digest", v)}
				/>
				<ToggleRow
					label="Product announcements"
					detail="Occasional emails about new features. No more than monthly."
					on={draft.product_news}
					onChange={(v) => set("product_news", v)}
				/>
			</div>
		</div>
	);
}

function StepTerms({
	version,
	agree,
	understand,
	onAgree,
	onUnderstand,
}: {
	version: string;
	agree: boolean;
	understand: boolean;
	onAgree: (v: boolean) => void;
	onUnderstand: (v: boolean) => void;
}) {
	return (
		<div>
			<StepHead
				eyebrow="Terms"
				title="Review & accept the terms"
				lede={`Current version ${version}.`}
			/>
			<div className="mt-8 max-h-64 overflow-y-auto border border-[var(--cds-border)] bg-[var(--cds-layer)] p-5 text-[13px] text-[var(--cds-text-2)] leading-relaxed">
				<p className="font-semibold text-[var(--cds-text)]">
					Terms of Service — summary
				</p>
				<p className="mt-3">
					Use the service lawfully; no scraping or bulk redistribution of the
					corpus. Your subscription is personal to you or your organization.
				</p>
				<p className="mt-3">
					<strong className="text-[var(--cds-text)]">Not legal advice.</strong>{" "}
					Research results, AI answers, and citator signals are research aids —
					verify against the official publication before relying on them.
				</p>
				<p className="mt-3">
					<strong className="text-[var(--cds-text)]">Your data.</strong> Chat
					logs are kept briefly for abuse prevention and are not used to train
					models. Full terms at{" "}
					<a
						href="/terms"
						target="_blank"
						rel="noopener"
						className="text-[var(--cds-link)] hover:underline"
					>
						/terms
					</a>
					.
				</p>
			</div>
			<div className="mt-5 space-y-1">
				<CheckboxRow
					label="I agree to the Terms of Service and the privacy terms."
					checked={agree}
					onChange={onAgree}
				/>
				<CheckboxRow
					label="I understand results are research, not legal advice."
					checked={understand}
					onChange={onUnderstand}
				/>
			</div>
		</div>
	);
}

function StepReview({ draft, email }: { draft: Draft; email: string }) {
	const rows: [string, string][] = [
		["Name", `${draft.first_name} ${draft.last_name}`.trim() || "—"],
		["Email", email],
		[
			"Role",
			[labelOf(ROLES, draft.role), draft.organization]
				.filter(Boolean)
				.join(" · ") || "—",
		],
		["Jurisdiction", draft.primary_jurisdiction || "—"],
		[
			"Appearance",
			labelOf(
				[
					{ value: "light", label: "Light" },
					{ value: "dark", label: "Dark" },
					{ value: "system", label: "System" },
				],
				draft.theme,
			),
		],
		["Default scope", labelOf(SEARCH_SCOPES, draft.default_search_scope)],
		["Citation style", labelOf(CITATION_STYLES, draft.citation_style)],
		["Verify citations", draft.verify_citations ? "On" : "Off"],
	];
	return (
		<div>
			<StepHead
				eyebrow="All set"
				title="You're all set"
				lede="Here's what we'll save to your account."
			/>
			<dl className="mt-8 divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]">
				{rows.map(([k, v]) => (
					<div
						key={k}
						className="flex items-center justify-between gap-4 bg-[var(--cds-layer)] px-4 py-3 text-sm"
					>
						<dt className="text-[var(--cds-text-2)]">{k}</dt>
						<dd className="font-medium">{v}</dd>
					</div>
				))}
			</dl>
		</div>
	);
}
