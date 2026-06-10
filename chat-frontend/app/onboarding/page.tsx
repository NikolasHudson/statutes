"use client";

// First-run onboarding wizard — the wired, persisted version of what started as
// the /onboarding-mockup prototype. On mount it loads the user's current
// settings (GET /api/account/settings) and pre-fills the form; on finish it
// PATCHes the collected fields and POSTs onboarding/complete to record ToS
// acceptance, then refreshes the auth user and drops into the app.
//
// The AuthGate (components/auth-gate.tsx) routes not-yet-onboarded users here on
// first login; "Skip for now" leaves without completing (they'll be nudged again
// next session). The theme step flips the real useTheme() hook so the choice is
// visible live before it's saved.
//
// Flow: Welcome → Your info → Appearance → Research preferences → Terms → Done.

import {
	ArrowLeftIcon,
	ArrowRightIcon,
	BellIcon,
	BriefcaseIcon,
	CheckIcon,
	CircleCheckBigIcon,
	ClockIcon,
	FileTextIcon,
	Loader2Icon,
	type LucideIcon,
	MapPinIcon,
	MonitorIcon,
	MoonIcon,
	ScaleIcon,
	ShieldCheckIcon,
	SparklesIcon,
	SunIcon,
	UserIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/auth-gate";
import { useTheme } from "@/components/theme-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
	AccountError,
	completeOnboarding,
	getSettings,
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
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Step model
// ---------------------------------------------------------------------------

type StepId =
	| "welcome"
	| "info"
	| "appearance"
	| "preferences"
	| "terms"
	| "done";

type Step = {
	id: StepId;
	label: string;
	blurb: string;
	icon: LucideIcon;
};

const STEPS: Step[] = [
	{
		id: "welcome",
		label: "Welcome",
		blurb: "What we'll set up",
		icon: SparklesIcon,
	},
	{
		id: "info",
		label: "Your info",
		blurb: "Contact & practice",
		icon: UserIcon,
	},
	{ id: "appearance", label: "Appearance", blurb: "Theme", icon: SunIcon },
	{
		id: "preferences",
		label: "Research",
		blurb: "Defaults & alerts",
		icon: ScaleIcon,
	},
	{
		id: "terms",
		label: "Terms",
		blurb: "Review & accept",
		icon: ShieldCheckIcon,
	},
	{
		id: "done",
		label: "All set",
		blurb: "Finish up",
		icon: CircleCheckBigIcon,
	},
];

// Option lists + labelOf are shared with the account settings page — see
// lib/settings-options.ts (the single source of truth that mirrors the backend
// TextChoices). The native <NativeSelect> control is components/ui/native-select.tsx.
type ThemeChoice = "light" | "dark" | "system";

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function OnboardingPage() {
	const { theme, toggle } = useTheme();
	const { user, setUser } = useAuth();
	const router = useRouter();

	const [loading, setLoading] = useState(true);
	const [loadError, setLoadError] = useState<string | null>(null);

	const [stepIdx, setStepIdx] = useState(0);
	const [maxSeen, setMaxSeen] = useState(0);
	const [finishing, setFinishing] = useState(false);
	const [finishError, setFinishError] = useState<string | null>(null);

	// ---- Form state (filled from GET /settings on mount) ---------------------
	const [firstName, setFirstName] = useState("");
	const [lastName, setLastName] = useState("");
	const [email, setEmail] = useState("");
	const [phone, setPhone] = useState("");

	const [street, setStreet] = useState("");
	const [unit, setUnit] = useState("");
	const [city, setCity] = useState("");
	const [addrState, setAddrState] = useState("");
	const [zip, setZip] = useState("");

	const [org, setOrg] = useState("");
	const [role, setRole] = useState(ROLES[0].value);
	const [barNumber, setBarNumber] = useState("");
	const [homeJurisdiction, setHomeJurisdiction] = useState(
		JURISDICTIONS[0].value,
	);
	const [timezone, setTimezone] = useState(TIMEZONES[0].value);

	const [themeChoice, setThemeChoice] = useState<ThemeChoice>("system");

	const [defaultScope, setDefaultScope] = useState(SEARCH_SCOPES[0].value);
	const [citationStyle, setCitationStyle] = useState(CITATION_STYLES[0].value);
	const [verifyCitations, setVerifyCitations] = useState(true);
	const [weeklyDigest, setWeeklyDigest] = useState(true);
	const [productNews, setProductNews] = useState(false);

	const [agreeTos, setAgreeTos] = useState(false);
	const [agreeNotAdvice, setAgreeNotAdvice] = useState(false);
	const [tosVersion, setTosVersion] = useState("");

	// Load current settings once. Falls back to the auth user's name if the
	// settings call somehow lags, so the greeting isn't blank.
	// biome-ignore lint/correctness/useExhaustiveDependencies: run once on mount; user.* is only a blank-state fallback, intentionally not a trigger.
	useEffect(() => {
		let cancelled = false;
		getSettings()
			.then((s) => {
				if (cancelled) return;
				setFirstName(s.first_name || user.first_name || "");
				setLastName(s.last_name || user.last_name || "");
				setEmail(s.email || user.email || "");
				setPhone(s.phone);
				setStreet(s.address_line1);
				setUnit(s.address_line2);
				setCity(s.city);
				setAddrState(s.region);
				setZip(s.postal_code);
				setOrg(s.organization);
				setRole(s.role || ROLES[0].value);
				setBarNumber(s.bar_number);
				setHomeJurisdiction(s.primary_jurisdiction || JURISDICTIONS[0].value);
				setTimezone(s.timezone || TIMEZONES[0].value);
				setThemeChoice((s.theme as ThemeChoice) || "system");
				setDefaultScope(s.default_search_scope || SEARCH_SCOPES[0].value);
				setCitationStyle(s.citation_style || CITATION_STYLES[0].value);
				setVerifyCitations(s.verify_citations);
				setWeeklyDigest(s.weekly_digest);
				setProductNews(s.product_news);
				setTosVersion(s.current_tos_version);
				setLoading(false);
			})
			.catch((e: unknown) => {
				if (cancelled) return;
				setLoadError(
					e instanceof AccountError
						? e.detail
						: "Could not load your settings.",
				);
				setLoading(false);
			});
		return () => {
			cancelled = true;
		};
	}, []);

	const step = STEPS[stepIdx];
	const isFirst = stepIdx === 0;
	const isLast = stepIdx === STEPS.length - 1;
	const progress = Math.round((stepIdx / (STEPS.length - 1)) * 100);

	// Selecting a concrete theme flips the *real* app theme so the preview is live.
	const selectTheme = (choice: ThemeChoice) => {
		setThemeChoice(choice);
		const target =
			choice === "system"
				? window.matchMedia("(prefers-color-scheme: dark)").matches
					? "dark"
					: "light"
				: choice;
		if (target !== theme) toggle();
	};

	const canContinue = useMemo(() => {
		if (step.id === "info")
			return firstName.trim().length > 0 && lastName.trim().length > 0;
		if (step.id === "terms") return agreeTos && agreeNotAdvice;
		return true;
	}, [step.id, firstName, lastName, agreeTos, agreeNotAdvice]);

	const goTo = (idx: number) => {
		const clamped = Math.max(0, Math.min(STEPS.length - 1, idx));
		setStepIdx(clamped);
		setMaxSeen((m) => Math.max(m, clamped));
	};
	const next = () => goTo(stepIdx + 1);
	const back = () => goTo(stepIdx - 1);

	const finish = async () => {
		setFinishing(true);
		setFinishError(null);
		try {
			await updateSettings({
				first_name: firstName.trim(),
				last_name: lastName.trim(),
				phone: phone.trim(),
				address_line1: street.trim(),
				address_line2: unit.trim(),
				city: city.trim(),
				region: addrState.trim(),
				postal_code: zip.trim(),
				organization: org.trim(),
				role,
				bar_number: barNumber.trim(),
				primary_jurisdiction: homeJurisdiction,
				timezone,
				theme: themeChoice,
				default_search_scope: defaultScope,
				citation_style: citationStyle,
				verify_citations: verifyCitations,
				weekly_digest: weeklyDigest,
				product_news: productNews,
			});
			await completeOnboarding(tosVersion || undefined);
			// Refresh the auth user so onboarding_completed flips (stops the
			// AuthGate nudge) and the sidebar name updates without a reload.
			const me = await fetch("/api/auth/me", { credentials: "include" }).then(
				(r) => (r.ok ? r.json() : null),
			);
			if (me) setUser(me);
			router.push("/");
		} catch (e: unknown) {
			setFinishError(
				e instanceof AccountError
					? e.detail
					: "Something went wrong saving your settings. Please try again.",
			);
			setFinishing(false);
		}
	};

	if (loading) {
		return (
			<div className="flex h-dvh w-full items-center justify-center gap-2 text-muted-foreground text-sm">
				<Loader2Icon className="size-4 animate-spin" />
				Loading your account…
			</div>
		);
	}

	if (loadError) {
		return (
			<div className="flex h-dvh w-full flex-col items-center justify-center gap-4 px-6 text-center">
				<p className="max-w-sm text-muted-foreground text-sm">{loadError}</p>
				<Button onClick={() => router.push("/")} variant="outline">
					Continue to the app
				</Button>
			</div>
		);
	}

	return (
		<div className="flex h-dvh w-full">
			<div className="grid h-full w-full md:grid-cols-[18rem_1fr]">
				{/* ---- Left rail: brand + vertical stepper ----------------------- */}
				<aside className="hidden flex-col border-r bg-muted/30 md:flex">
					<div className="flex items-center gap-2.5 border-b px-5 py-4">
						<div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
							<ScaleIcon className="size-4" />
						</div>
						<div className="flex flex-col leading-none">
							<span className="font-semibold text-sm">Hudson Legal Tech</span>
							<span className="mt-0.5 text-muted-foreground text-xs">
								Account setup
							</span>
						</div>
					</div>

					<nav className="flex-1 px-3 py-4">
						<ol className="space-y-0.5">
							{STEPS.map((s, i) => {
								const Icon = s.icon;
								const active = i === stepIdx;
								const done = i < stepIdx;
								const reachable = i <= maxSeen;
								return (
									<li key={s.id}>
										<button
											type="button"
											disabled={!reachable}
											onClick={() => reachable && goTo(i)}
											className={cn(
												"flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors",
												active
													? "bg-card shadow-xs"
													: reachable
														? "hover:bg-accent/60"
														: "cursor-default opacity-50",
											)}
										>
											<span
												className={cn(
													"flex size-7 shrink-0 items-center justify-center rounded-full border text-xs transition-colors",
													done
														? "border-primary bg-primary text-primary-foreground"
														: active
															? "border-primary text-primary"
															: "border-border text-muted-foreground",
												)}
											>
												{done ? (
													<CheckIcon className="size-3.5" />
												) : (
													<Icon className="size-3.5" />
												)}
											</span>
											<span className="flex min-w-0 flex-col">
												<span
													className={cn(
														"truncate font-medium text-[13px] leading-tight",
														active ? "text-foreground" : "text-foreground/80",
													)}
												>
													{s.label}
												</span>
												<span className="truncate text-[11px] text-muted-foreground leading-tight">
													{s.blurb}
												</span>
											</span>
										</button>
									</li>
								);
							})}
						</ol>
					</nav>

					<div className="border-t px-5 py-3 text-[11px] text-muted-foreground">
						Takes about 2 minutes · you can change everything later in{" "}
						<span className="font-medium text-foreground/70">Settings</span>.
					</div>
				</aside>

				{/* ---- Right column: progress + step body + footer --------------- */}
				<div className="flex min-w-0 flex-col">
					<div className="flex items-center gap-3 border-b px-5 py-3 sm:px-8">
						<span className="font-medium text-muted-foreground text-xs tabular-nums">
							Step {stepIdx + 1} of {STEPS.length}
						</span>
						<div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
							<div
								className="h-full rounded-full bg-primary transition-all duration-300"
								style={{ width: `${Math.max(progress, 6)}%` }}
							/>
						</div>
						<Link
							href="/"
							className="text-muted-foreground text-xs hover:text-foreground"
						>
							Skip for now
						</Link>
					</div>

					<div className="flex-1 overflow-y-auto px-5 py-8 sm:px-10 sm:py-12">
						<div className="mx-auto flex min-h-full max-w-2xl flex-col justify-center">
							{step.id === "welcome" && <WelcomeStep firstName={firstName} />}
							{step.id === "info" && (
								<InfoStep
									firstName={firstName}
									setFirstName={setFirstName}
									lastName={lastName}
									setLastName={setLastName}
									email={email}
									phone={phone}
									setPhone={setPhone}
									street={street}
									setStreet={setStreet}
									unit={unit}
									setUnit={setUnit}
									city={city}
									setCity={setCity}
									addrState={addrState}
									setAddrState={setAddrState}
									zip={zip}
									setZip={setZip}
									org={org}
									setOrg={setOrg}
									role={role}
									setRole={setRole}
									barNumber={barNumber}
									setBarNumber={setBarNumber}
									homeJurisdiction={homeJurisdiction}
									setHomeJurisdiction={setHomeJurisdiction}
									timezone={timezone}
									setTimezone={setTimezone}
								/>
							)}
							{step.id === "appearance" && (
								<AppearanceStep
									themeChoice={themeChoice}
									selectTheme={selectTheme}
								/>
							)}
							{step.id === "preferences" && (
								<PreferencesStep
									defaultScope={defaultScope}
									setDefaultScope={setDefaultScope}
									citationStyle={citationStyle}
									setCitationStyle={setCitationStyle}
									verifyCitations={verifyCitations}
									setVerifyCitations={setVerifyCitations}
									weeklyDigest={weeklyDigest}
									setWeeklyDigest={setWeeklyDigest}
									productNews={productNews}
									setProductNews={setProductNews}
								/>
							)}
							{step.id === "terms" && (
								<TermsStep
									tosVersion={tosVersion}
									agreeTos={agreeTos}
									setAgreeTos={setAgreeTos}
									agreeNotAdvice={agreeNotAdvice}
									setAgreeNotAdvice={setAgreeNotAdvice}
								/>
							)}
							{step.id === "done" && (
								<DoneStep
									firstName={firstName}
									lastName={lastName}
									email={email}
									phone={phone}
									street={street}
									unit={unit}
									city={city}
									addrState={addrState}
									zip={zip}
									org={org}
									role={role}
									barNumber={barNumber}
									homeJurisdiction={homeJurisdiction}
									themeChoice={themeChoice}
									defaultScope={defaultScope}
									citationStyle={citationStyle}
									verifyCitations={verifyCitations}
								/>
							)}
						</div>
					</div>

					<div className="border-t px-5 py-4 sm:px-10">
						<div className="mx-auto flex max-w-2xl flex-col gap-3">
							{finishError && (
								<p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-destructive text-sm">
									{finishError}
								</p>
							)}
							<div className="flex items-center justify-between gap-3">
								<Button
									variant="ghost"
									onClick={back}
									disabled={isFirst || finishing}
									className={cn(isFirst && "invisible")}
								>
									<ArrowLeftIcon className="size-4" />
									Back
								</Button>

								{isLast ? (
									<Button
										onClick={finish}
										disabled={finishing}
										className="min-w-44"
									>
										{finishing ? (
											<>
												<Loader2Icon className="size-4 animate-spin" />
												Setting up…
											</>
										) : (
											<>
												Enter the app
												<ArrowRightIcon className="size-4" />
											</>
										)}
									</Button>
								) : (
									<Button
										onClick={next}
										disabled={!canContinue}
										className="min-w-32"
									>
										{step.id === "terms" ? "Accept & continue" : "Continue"}
										<ArrowRightIcon className="size-4" />
									</Button>
								)}
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Shared step primitives
// ---------------------------------------------------------------------------

function StepHeading({
	eyebrow,
	title,
	description,
}: {
	eyebrow: string;
	title: string;
	description: string;
}) {
	return (
		<div className="mb-6">
			<p className="font-semibold text-[11px] text-primary uppercase tracking-[0.18em]">
				{eyebrow}
			</p>
			<h1 className="mt-1.5 font-semibold text-2xl tracking-tight">{title}</h1>
			<p className="mt-1.5 text-muted-foreground text-sm">{description}</p>
		</div>
	);
}

function Field({
	label,
	hint,
	children,
}: {
	label: string;
	hint?: string;
	children: React.ReactNode;
}) {
	return (
		<label className="block">
			<span className="font-medium text-foreground text-sm">{label}</span>
			<div className="mt-1.5">{children}</div>
			{hint && <p className="mt-1 text-muted-foreground text-xs">{hint}</p>}
		</label>
	);
}

// Switch-style toggle in a labelled row (no Switch primitive exists).
function ToggleRow({
	icon: Icon,
	label,
	description,
	checked,
	onChange,
}: {
	icon: LucideIcon;
	label: string;
	description: string;
	checked: boolean;
	onChange: (v: boolean) => void;
}) {
	return (
		<button
			type="button"
			onClick={() => onChange(!checked)}
			className="flex w-full items-center gap-3 rounded-lg border bg-card p-3 text-left transition-colors hover:bg-accent/40"
		>
			<span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
				<Icon className="size-4" />
			</span>
			<span className="flex min-w-0 flex-1 flex-col">
				<span className="font-medium text-[13px] leading-tight">{label}</span>
				<span className="text-[11px] text-muted-foreground leading-tight">
					{description}
				</span>
			</span>
			<span
				className={cn(
					"relative h-5 w-9 shrink-0 rounded-full transition-colors",
					checked ? "bg-primary" : "bg-muted-foreground/30",
				)}
			>
				<span
					className={cn(
						"absolute top-0.5 size-4 rounded-full bg-white shadow-sm transition-all",
						checked ? "left-[1.125rem]" : "left-0.5",
					)}
				/>
			</span>
		</button>
	);
}

// Checkbox-style row used on the Terms step.
function CheckRow({
	checked,
	onChange,
	children,
}: {
	checked: boolean;
	onChange: (v: boolean) => void;
	children: React.ReactNode;
}) {
	return (
		<button
			type="button"
			onClick={() => onChange(!checked)}
			className="flex w-full items-start gap-3 rounded-lg border bg-card p-3.5 text-left transition-colors hover:bg-accent/40"
		>
			<span
				className={cn(
					"mt-0.5 flex size-5 shrink-0 items-center justify-center rounded border transition-colors",
					checked
						? "border-primary bg-primary text-primary-foreground"
						: "border-border bg-background",
				)}
			>
				{checked && <CheckIcon className="size-3.5" />}
			</span>
			<span className="text-[13px] leading-relaxed text-foreground/90">
				{children}
			</span>
		</button>
	);
}

// Small section divider used to group fields within a step.
function GroupLabel({ children }: { children: React.ReactNode }) {
	return (
		<p className="mt-7 mb-3 border-t pt-5 font-medium text-foreground text-sm">
			{children}
		</p>
	);
}

// ---------------------------------------------------------------------------
// Step: Welcome
// ---------------------------------------------------------------------------

function WelcomeStep({ firstName }: { firstName: string }) {
	const greeting = firstName.trim() || "there";
	const items = [
		{
			icon: UserIcon,
			label: "Tell us who you are",
			sub: "Name, contact info & practice area",
		},
		{ icon: SunIcon, label: "Make it yours", sub: "Light or dark mode" },
		{
			icon: ScaleIcon,
			label: "Set research defaults",
			sub: "Jurisdiction, citation style & alerts",
		},
		{
			icon: ShieldCheckIcon,
			label: "Review the terms",
			sub: "Terms of Service & how we handle data",
		},
	];
	return (
		<div>
			<div className="mb-6 flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
				<SparklesIcon className="size-6" />
			</div>
			<h1 className="font-semibold text-2xl tracking-tight">
				Welcome, {greeting}.
			</h1>
			<p className="mt-2 max-w-md text-muted-foreground text-sm">
				Let&apos;s get your account set up so the Iowa Legal Corpus works the
				way you do. Four quick steps — everything is adjustable later in
				Settings.
			</p>
			<ul className="mt-6 space-y-2.5">
				{items.map((it) => {
					const Icon = it.icon;
					return (
						<li key={it.label} className="flex items-center gap-3">
							<span className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-card text-primary">
								<Icon className="size-4" />
							</span>
							<span className="flex flex-col">
								<span className="font-medium text-sm leading-tight">
									{it.label}
								</span>
								<span className="text-muted-foreground text-xs leading-tight">
									{it.sub}
								</span>
							</span>
						</li>
					);
				})}
			</ul>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Step: Your info
// ---------------------------------------------------------------------------

function InfoStep(props: {
	firstName: string;
	setFirstName: (v: string) => void;
	lastName: string;
	setLastName: (v: string) => void;
	email: string;
	phone: string;
	setPhone: (v: string) => void;
	street: string;
	setStreet: (v: string) => void;
	unit: string;
	setUnit: (v: string) => void;
	city: string;
	setCity: (v: string) => void;
	addrState: string;
	setAddrState: (v: string) => void;
	zip: string;
	setZip: (v: string) => void;
	org: string;
	setOrg: (v: string) => void;
	role: string;
	setRole: (v: string) => void;
	barNumber: string;
	setBarNumber: (v: string) => void;
	homeJurisdiction: string;
	setHomeJurisdiction: (v: string) => void;
	timezone: string;
	setTimezone: (v: string) => void;
}) {
	return (
		<div>
			<StepHeading
				eyebrow="About you"
				title="Tell us who you are"
				description="We use this to personalize results, address you in the app, and reach you about your account."
			/>

			{/* Identity & contact */}
			<div className="grid gap-5 sm:grid-cols-2">
				<Field label="First name">
					<Input
						value={props.firstName}
						onChange={(e) => props.setFirstName(e.target.value)}
						placeholder="First name"
					/>
				</Field>
				<Field label="Last name">
					<Input
						value={props.lastName}
						onChange={(e) => props.setLastName(e.target.value)}
						placeholder="Last name"
					/>
				</Field>
				<Field
					label="Email"
					hint="Your login email — used for sign-in and alerts."
				>
					<Input
						value={props.email}
						readOnly
						className="cursor-not-allowed bg-muted/40 text-muted-foreground"
					/>
				</Field>
				<Field label="Phone" hint="Optional — for account security & support.">
					<Input
						type="tel"
						value={props.phone}
						onChange={(e) => props.setPhone(e.target.value)}
						placeholder="(555) 123-4567"
					/>
				</Field>
			</div>

			{/* Mailing address */}
			<GroupLabel>Mailing address</GroupLabel>
			<div className="grid gap-5 sm:grid-cols-6">
				<div className="sm:col-span-6">
					<Field label="Street address" hint="Optional.">
						<Input
							value={props.street}
							onChange={(e) => props.setStreet(e.target.value)}
							placeholder="123 Main St"
						/>
					</Field>
				</div>
				<div className="sm:col-span-2">
					<Field label="Apt / Suite">
						<Input
							value={props.unit}
							onChange={(e) => props.setUnit(e.target.value)}
							placeholder="Suite 200"
						/>
					</Field>
				</div>
				<div className="sm:col-span-2">
					<Field label="City">
						<Input
							value={props.city}
							onChange={(e) => props.setCity(e.target.value)}
							placeholder="Des Moines"
						/>
					</Field>
				</div>
				<div className="sm:col-span-1">
					<Field label="State">
						<Input
							value={props.addrState}
							onChange={(e) => props.setAddrState(e.target.value)}
							placeholder="IA"
							maxLength={2}
						/>
					</Field>
				</div>
				<div className="sm:col-span-1">
					<Field label="ZIP">
						<Input
							value={props.zip}
							onChange={(e) => props.setZip(e.target.value)}
							placeholder="50309"
							inputMode="numeric"
						/>
					</Field>
				</div>
			</div>

			{/* Practice */}
			<GroupLabel>Practice</GroupLabel>
			<div className="grid gap-5 sm:grid-cols-2">
				<Field label="Organization" hint="Firm, agency, or school — optional.">
					<Input
						value={props.org}
						onChange={(e) => props.setOrg(e.target.value)}
						placeholder="e.g. Hudson Law LLC"
					/>
				</Field>
				<Field label="Your role">
					<NativeSelect
						value={props.role}
						onChange={props.setRole}
						options={ROLES}
						icon={BriefcaseIcon}
					/>
				</Field>
				<Field
					label="Bar number"
					hint="Optional — your attorney registration number."
				>
					<Input
						value={props.barNumber}
						onChange={(e) => props.setBarNumber(e.target.value)}
						placeholder="e.g. AT0001234"
					/>
				</Field>
				<Field
					label="Primary jurisdiction"
					hint="Pre-selected in search filters."
				>
					<NativeSelect
						value={props.homeJurisdiction}
						onChange={props.setHomeJurisdiction}
						options={JURISDICTIONS}
						icon={MapPinIcon}
					/>
				</Field>
				<Field label="Time zone" hint="Used for timestamps & alert delivery.">
					<NativeSelect
						value={props.timezone}
						onChange={props.setTimezone}
						options={TIMEZONES}
						icon={ClockIcon}
					/>
				</Field>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Step: Appearance
// ---------------------------------------------------------------------------

const THEME_OPTIONS: { id: ThemeChoice; label: string; icon: LucideIcon }[] = [
	{ id: "light", label: "Light", icon: SunIcon },
	{ id: "dark", label: "Dark", icon: MoonIcon },
	{ id: "system", label: "System", icon: MonitorIcon },
];

function AppearanceStep(props: {
	themeChoice: ThemeChoice;
	selectTheme: (c: ThemeChoice) => void;
}) {
	return (
		<div>
			<StepHeading
				eyebrow="Appearance"
				title="Make it yours"
				description="Pick a theme — the page updates live so you can see it. Saved to your account, so it follows you to any device."
			/>

			<Field label="Theme">
				<div className="grid grid-cols-3 gap-3">
					{THEME_OPTIONS.map((opt) => {
						const Icon = opt.icon;
						const active = props.themeChoice === opt.id;
						return (
							<button
								key={opt.id}
								type="button"
								onClick={() => props.selectTheme(opt.id)}
								className={cn(
									"flex flex-col items-center gap-3 rounded-xl border p-3 transition-all",
									active
										? "border-primary ring-[3px] ring-ring/40"
										: "hover:border-foreground/30",
								)}
							>
								<ThemeSwatch variant={opt.id} />
								<span className="flex items-center gap-1.5 font-medium text-[13px]">
									<Icon className="size-3.5" />
									{opt.label}
									{active && <CheckIcon className="size-3.5 text-primary" />}
								</span>
							</button>
						);
					})}
				</div>
			</Field>
		</div>
	);
}

// Tiny preview card representing each theme.
function ThemeSwatch({ variant }: { variant: ThemeChoice }) {
	if (variant === "system") {
		return (
			<div className="flex h-16 w-full overflow-hidden rounded-lg border">
				<div className="flex-1 bg-white p-1.5">
					<div className="h-1.5 w-8 rounded-full bg-zinc-300" />
					<div className="mt-1 h-1.5 w-10 rounded-full bg-zinc-200" />
				</div>
				<div className="flex-1 bg-zinc-900 p-1.5">
					<div className="h-1.5 w-8 rounded-full bg-zinc-600" />
					<div className="mt-1 h-1.5 w-10 rounded-full bg-zinc-700" />
				</div>
			</div>
		);
	}
	const dark = variant === "dark";
	return (
		<div
			className={cn(
				"h-16 w-full overflow-hidden rounded-lg border p-2",
				dark ? "bg-zinc-900" : "bg-white",
			)}
		>
			<div
				className={cn(
					"h-1.5 w-9 rounded-full",
					dark ? "bg-zinc-600" : "bg-zinc-300",
				)}
			/>
			<div
				className={cn(
					"mt-1.5 h-1.5 w-12 rounded-full",
					dark ? "bg-zinc-700" : "bg-zinc-200",
				)}
			/>
			<div className="mt-2 h-3 w-10 rounded bg-primary" />
		</div>
	);
}

// ---------------------------------------------------------------------------
// Step: Research preferences
// ---------------------------------------------------------------------------

function PreferencesStep(props: {
	defaultScope: string;
	setDefaultScope: (v: string) => void;
	citationStyle: string;
	setCitationStyle: (v: string) => void;
	verifyCitations: boolean;
	setVerifyCitations: (v: boolean) => void;
	weeklyDigest: boolean;
	setWeeklyDigest: (v: boolean) => void;
	productNews: boolean;
	setProductNews: (v: boolean) => void;
}) {
	return (
		<div>
			<StepHeading
				eyebrow="Research"
				title="Set your defaults"
				description="Smart starting points for every search and answer. Tune them now or leave the defaults — Settings has the same controls."
			/>

			<div className="grid gap-5 sm:grid-cols-2">
				<Field label="Default search scope">
					<NativeSelect
						value={props.defaultScope}
						onChange={props.setDefaultScope}
						options={SEARCH_SCOPES}
						icon={FileTextIcon}
					/>
				</Field>
				<Field label="Citation style">
					<NativeSelect
						value={props.citationStyle}
						onChange={props.setCitationStyle}
						options={CITATION_STYLES}
						icon={ScaleIcon}
					/>
				</Field>
			</div>

			<p className="mt-6 mb-2 font-medium text-foreground text-sm">
				Answers & notifications
			</p>
			<div className="space-y-2.5">
				<ToggleRow
					icon={ShieldCheckIcon}
					label="Verify citations before showing answers"
					description="Run the deterministic citation & quote check on every AI response. Recommended."
					checked={props.verifyCitations}
					onChange={props.setVerifyCitations}
				/>
				<ToggleRow
					icon={BellIcon}
					label="Weekly corpus digest"
					description="What's new in cases, statutes & rules for your jurisdiction."
					checked={props.weeklyDigest}
					onChange={props.setWeeklyDigest}
				/>
				<ToggleRow
					icon={SparklesIcon}
					label="Product announcements"
					description="Occasional emails about new features. No more than monthly."
					checked={props.productNews}
					onChange={props.setProductNews}
				/>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Step: Terms
// ---------------------------------------------------------------------------

function TermsStep(props: {
	tosVersion: string;
	agreeTos: boolean;
	setAgreeTos: (v: boolean) => void;
	agreeNotAdvice: boolean;
	setAgreeNotAdvice: (v: boolean) => void;
}) {
	return (
		<div>
			<StepHeading
				eyebrow="Almost done"
				title="Review & accept the terms"
				description={`Please read and accept before continuing.${
					props.tosVersion ? ` Current version ${props.tosVersion}.` : ""
				}`}
			/>

			<div className="mb-5 max-h-44 overflow-y-auto rounded-lg border bg-muted/20 p-4 text-[13px] text-muted-foreground leading-relaxed">
				<p className="font-medium text-foreground">
					Terms of Service — summary
				</p>
				<p className="mt-2">
					Hudson Legal Tech provides legal research tools over a corpus of
					statutes, regulations, court rules, and case law. You agree to use the
					service for lawful research purposes and not to scrape, resell, or
					redistribute the corpus.
				</p>
				<p className="mt-2">
					<span className="font-medium text-foreground">Not legal advice.</span>{" "}
					Outputs are research assistance, may contain errors, and do not create
					an attorney–client relationship. You are responsible for independently
					verifying any authority before relying on it.
				</p>
				<p className="mt-2">
					<span className="font-medium text-foreground">Your data.</span> We
					store your account details and preferences to operate the service;
					chat logs are kept only briefly before automatic deletion. We do not
					sell personal data and do not use your queries to train AI models. See
					the Privacy &amp; Your Data section of the Terms for retention and
					deletion.
				</p>
				<p className="mt-2">
					Full text:{" "}
					<Link
						href="/terms"
						target="_blank"
						className="text-primary underline underline-offset-2"
					>
						Terms of Service
					</Link>{" "}
					·{" "}
					<Link
						href="/terms#privacy"
						target="_blank"
						className="text-primary underline underline-offset-2"
					>
						Privacy & Your Data
					</Link>
				</p>
			</div>

			<div className="space-y-2.5">
				<CheckRow checked={props.agreeTos} onChange={props.setAgreeTos}>
					I have read and agree to the{" "}
					<Link
						href="/terms"
						target="_blank"
						className="font-medium text-primary underline underline-offset-2"
					>
						Terms of Service
					</Link>
					, including its{" "}
					<Link
						href="/terms#privacy"
						target="_blank"
						className="font-medium text-primary underline underline-offset-2"
					>
						privacy and data practices
					</Link>
					.
				</CheckRow>
				<CheckRow
					checked={props.agreeNotAdvice}
					onChange={props.setAgreeNotAdvice}
				>
					I understand the service provides research assistance, not legal
					advice, and that I&apos;m responsible for verifying authorities.
				</CheckRow>
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Step: Done
// ---------------------------------------------------------------------------

function DoneStep(props: {
	firstName: string;
	lastName: string;
	email: string;
	phone: string;
	street: string;
	unit: string;
	city: string;
	addrState: string;
	zip: string;
	org: string;
	role: string;
	barNumber: string;
	homeJurisdiction: string;
	themeChoice: ThemeChoice;
	defaultScope: string;
	citationStyle: string;
	verifyCitations: boolean;
}) {
	const cityLine = [props.city, props.addrState].filter(Boolean).join(", ");
	const address =
		[props.street, props.unit, cityLine, props.zip]
			.filter(Boolean)
			.join(", ") || "—";
	const roleLabel = labelOf(ROLES, props.role);
	const rows: { label: string; value: string }[] = [
		{
			label: "Name",
			value: `${props.firstName} ${props.lastName}`.trim() || "—",
		},
		{ label: "Email", value: props.email },
		{ label: "Phone", value: props.phone || "—" },
		{
			label: "Role",
			value: props.org ? `${roleLabel} · ${props.org}` : roleLabel,
		},
		{ label: "Bar number", value: props.barNumber || "—" },
		{ label: "Address", value: address },
		{
			label: "Jurisdiction",
			value: labelOf(JURISDICTIONS, props.homeJurisdiction),
		},
		{ label: "Appearance", value: cap(props.themeChoice) },
		{
			label: "Default scope",
			value: labelOf(SEARCH_SCOPES, props.defaultScope),
		},
		{
			label: "Citation style",
			value: labelOf(CITATION_STYLES, props.citationStyle),
		},
		{ label: "Verify citations", value: props.verifyCitations ? "On" : "Off" },
	];
	return (
		<div>
			<div className="mb-6 flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
				<CircleCheckBigIcon className="size-6" />
			</div>
			<h1 className="font-semibold text-2xl tracking-tight">
				You&apos;re all set
			</h1>
			<p className="mt-2 max-w-md text-muted-foreground text-sm">
				Here&apos;s what we&apos;ll save to your account. You can change any of
				it from Settings whenever you like.
			</p>

			<dl className="mt-6 overflow-hidden rounded-lg border">
				{rows.map((r, i) => (
					<div
						key={r.label}
						className={cn(
							"flex items-center justify-between gap-4 px-4 py-2.5 text-sm",
							i % 2 === 1 && "bg-muted/30",
						)}
					>
						<dt className="text-muted-foreground">{r.label}</dt>
						<dd className="truncate text-right font-medium">{r.value}</dd>
					</div>
				))}
			</dl>
		</div>
	);
}

function cap(s: string) {
	return s.charAt(0).toUpperCase() + s.slice(1);
}
