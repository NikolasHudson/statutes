"use client";

// Carbon mockup of the first-run onboarding wizard (live: /onboarding).
// Same six steps as the live wizard, restated as an IBM-style product setup
// flow: dark vertical stepper rail on the left, one step per screen on the
// right, Back/Continue footer. Fully clickable — walk all six steps.
// Static data; nothing saves.

import { CheckIcon, MonitorIcon, MoonIcon, SunIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { cn } from "@/lib/utils";
import {
	BtnPrimary,
	CheckboxRow,
	Eyebrow,
	SelectField,
	ShellHeader,
	TextField,
	ToggleRow,
	useTheme,
} from "../carbon";

const ROLES = [
	"Attorney",
	"Paralegal",
	"Law clerk",
	"Law student",
	"Legal researcher",
	"Other",
];
const JURISDICTIONS = [
	"Iowa",
	"Federal",
	"All states",
	"California",
	"Illinois",
	"New York",
	"Texas",
];
const TIMEZONES = [
	"America/Chicago (Central)",
	"America/New_York (Eastern)",
	"America/Denver (Mountain)",
	"America/Los_Angeles (Pacific)",
];
const CITATION_STYLES = [
	"Bluebook (21st ed.)",
	"ALWD Guide",
	"Iowa local rules",
];
const SCOPES = [
	"Everything",
	"Case law only",
	"Statutes & codes only",
	"Secondary sources only",
];

const STEPS: { label: string; blurb: string }[] = [
	{ label: "Welcome", blurb: "What we'll set up" },
	{ label: "Your info", blurb: "Contact & practice" },
	{ label: "Appearance", blurb: "Theme" },
	{ label: "Research", blurb: "Defaults & alerts" },
	{ label: "Terms", blurb: "Review & accept" },
	{ label: "All set", blurb: "Finish up" },
];

export default function OnboardingCarbonMockup() {
	const [step, setStep] = useState(0);
	const last = step === STEPS.length - 1;

	return (
		<>
			<ShellHeader note="Account setup — Carbon mockup" />
			<div className="flex min-h-0 flex-1">
				<StepperRail step={step} onJump={setStep} />

				<main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
					<div className="flex items-center justify-between px-5 pt-6 sm:px-10">
						<p className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
							Step {step + 1} of {STEPS.length}
						</p>
						<Link
							href="/app-carbon-mockup/assistant"
							className="text-[13px] text-[var(--cds-link)] hover:underline"
						>
							Skip for now
						</Link>
					</div>
					{/* Progress bar — filled span tracks the step. */}
					<div className="mx-5 mt-3 h-0.5 bg-[var(--cds-border)] sm:mx-10">
						<div
							className="h-full bg-[#0f62fe] transition-[width]"
							style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
						/>
					</div>

					<div className="mx-auto w-full max-w-2xl flex-1 px-5 py-10 sm:px-10">
						{step === 0 && <StepWelcome />}
						{step === 1 && <StepInfo />}
						{step === 2 && <StepAppearance />}
						{step === 3 && <StepResearch />}
						{step === 4 && <StepTerms />}
						{step === 5 && <StepReview />}
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
						<BtnPrimary
							size="md"
							onClick={() => setStep(Math.min(step + 1, STEPS.length - 1))}
						>
							{last
								? "Enter the app"
								: step === 4
									? "Accept & continue"
									: "Continue"}
						</BtnPrimary>
					</footer>
				</main>
			</div>
		</>
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

function StepWelcome() {
	return (
		<div>
			<StepHead
				eyebrow="Welcome"
				title="Welcome, Nick."
				lede="Let's get your account set up so the Iowa Legal Corpus works the way you do. Four quick steps — everything can be changed later."
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

function StepInfo() {
	return (
		<div>
			<StepHead eyebrow="About you" title="Tell us who you are" />
			<div className="mt-8 grid gap-5 sm:grid-cols-2">
				<TextField label="First name" defaultValue="Nick" />
				<TextField label="Last name" defaultValue="Hudson" />
				<TextField
					label="Email"
					defaultValue="nick@nickhudson.me"
					readOnly
					helper="Your login email — used for sign-in and alerts."
				/>
				<TextField label="Phone" placeholder="(555) 123-4567" />
			</div>
			<GroupLabel>Mailing address</GroupLabel>
			<div className="grid gap-5 sm:grid-cols-6">
				<TextField
					label="Street address"
					placeholder="123 Main St"
					className="sm:col-span-4"
				/>
				<TextField
					label="Apt / Suite"
					placeholder="Suite 200"
					className="sm:col-span-2"
				/>
				<TextField
					label="City"
					placeholder="Des Moines"
					className="sm:col-span-3"
				/>
				<TextField
					label="State"
					placeholder="IA"
					maxLength={2}
					className="sm:col-span-1"
				/>
				<TextField label="ZIP" placeholder="50309" className="sm:col-span-2" />
			</div>
			<GroupLabel>Practice</GroupLabel>
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField label="Organization" placeholder="e.g. Hudson Law LLC" />
				<SelectField label="Your role" options={ROLES} />
				<TextField label="Bar number" placeholder="e.g. AT0001234" />
				<SelectField label="Primary jurisdiction" options={JURISDICTIONS} />
				<SelectField
					label="Time zone"
					options={TIMEZONES}
					className="sm:col-span-2"
				/>
			</div>
		</div>
	);
}

function StepAppearance() {
	const { theme, setTheme } = useTheme();
	const cards = [
		{
			id: "white" as const,
			label: "Light",
			icon: SunIcon,
			swatch: ["#ffffff", "#f4f4f4", "#161616"],
		},
		{
			id: "g100" as const,
			label: "Dark",
			icon: MoonIcon,
			swatch: ["#161616", "#262626", "#f4f4f4"],
		},
		{
			id: "white" as const,
			label: "System",
			icon: MonitorIcon,
			swatch: ["#ffffff", "#262626", "#161616"],
		},
	];
	return (
		<div>
			<StepHead
				eyebrow="Appearance"
				title="Make it yours"
				lede="Pick a theme — the whole mockup flips live."
			/>
			<div className="mt-8 grid gap-4 sm:grid-cols-3">
				{cards.map((c, i) => {
					const Icon = c.icon;
					const active = i < 2 && theme === c.id;
					return (
						<button
							key={c.label}
							type="button"
							onClick={() => setTheme(c.id)}
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

function StepResearch() {
	const [verify, setVerify] = useState(true);
	const [digest, setDigest] = useState(true);
	const [news, setNews] = useState(false);
	return (
		<div>
			<StepHead eyebrow="Research" title="Set your defaults" />
			<div className="mt-8 grid gap-5 sm:grid-cols-2">
				<SelectField label="Default search scope" options={SCOPES} />
				<SelectField label="Citation style" options={CITATION_STYLES} />
			</div>
			<GroupLabel>Answers &amp; notifications</GroupLabel>
			<div className="divide-y divide-[var(--cds-border)]">
				<ToggleRow
					label="Verify citations before showing answers"
					detail="Run the deterministic citation & quote check on every AI response. Recommended."
					on={verify}
					onChange={setVerify}
				/>
				<ToggleRow
					label="Weekly corpus digest"
					detail="What's new in cases, statutes & rules for your jurisdiction."
					on={digest}
					onChange={setDigest}
				/>
				<ToggleRow
					label="Product announcements"
					detail="Occasional emails about new features. No more than monthly."
					on={news}
					onChange={setNews}
				/>
			</div>
		</div>
	);
}

function StepTerms() {
	const [agree, setAgree] = useState(false);
	const [understand, setUnderstand] = useState(false);
	return (
		<div>
			<StepHead
				eyebrow="Terms"
				title="Review & accept the terms"
				lede="Current version 2026-06-10."
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
					models. Full terms at /terms; privacy at /terms#privacy.
				</p>
			</div>
			<div className="mt-5 space-y-1">
				<CheckboxRow
					label="I agree to the Terms of Service and the privacy terms."
					checked={agree}
					onChange={setAgree}
				/>
				<CheckboxRow
					label="I understand results are research, not legal advice."
					checked={understand}
					onChange={setUnderstand}
				/>
			</div>
		</div>
	);
}

function StepReview() {
	const rows = [
		["Name", "Nick Hudson"],
		["Email", "nick@nickhudson.me"],
		["Role", "Attorney · Hudson Law LLC"],
		["Jurisdiction", "Iowa"],
		["Appearance", "Light"],
		["Default scope", "Everything"],
		["Citation style", "Bluebook (21st ed.)"],
		["Verify citations", "On"],
	] as const;
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
