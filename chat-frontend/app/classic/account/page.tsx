"use client";

// Account settings page. Mirrors the legacy MUI AccountPage:
//   - Profile (name + email)
//   - Password change
//   - API keys (list, create with one-time raw-key reveal, revoke)
//   - MCP config snippet for Claude Desktop / Cursor / etc.
// Sidebar shows the same Hudson Legal Tech brand + a section anchor list,
// with the shared theme/user footer used across /chat and /browse.

import {
	AlertCircleIcon,
	BellIcon,
	BriefcaseIcon,
	CheckIcon,
	ClockIcon,
	CopyIcon,
	FileTextIcon,
	KeyIcon,
	Loader2Icon,
	type LucideIcon,
	MapPinIcon,
	MonitorIcon,
	MoonIcon,
	PlusIcon,
	ScaleIcon,
	SettingsIcon,
	ShieldCheckIcon,
	SlidersHorizontalIcon,
	SparklesIcon,
	SunIcon,
	TrashIcon,
	UserIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppSidebarBrand } from "@/components/app-sidebar-brand";
import { AppSidebarFooter } from "@/components/app-sidebar-footer";
import { AppSidebarNav } from "@/components/app-sidebar-nav";
import { type AuthUser, useAuth } from "@/components/auth-gate";
import { useTheme } from "@/components/theme-provider";
import {
	Breadcrumb,
	BreadcrumbItem,
	BreadcrumbList,
	BreadcrumbPage,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Separator } from "@/components/ui/separator";
import {
	Sidebar,
	SidebarContent,
	SidebarFooter,
	SidebarGroup,
	SidebarGroupLabel,
	SidebarInset,
	SidebarMenu,
	SidebarMenuButton,
	SidebarMenuItem,
	SidebarProvider,
	SidebarRail,
	SidebarTrigger,
} from "@/components/ui/sidebar";
import { BRAND_NAME, MCP_SERVER_ID, mcpUrl } from "@/lib/brand";
import {
	AccountError,
	type APIKey,
	type CreatedAPIKey,
	changePassword,
	createKey,
	fetchPublicConfig,
	fmtDate,
	fmtDateTime,
	getSettings,
	listKeys,
	revokeKey,
	type UserSettings,
	updateProfile,
	updateSettings,
} from "@/lib/iowa-account";
import {
	CITATION_STYLES,
	JURISDICTIONS,
	ROLES,
	SEARCH_SCOPES,
	THEMES,
	TIMEZONES,
} from "@/lib/settings-options";
import { cn } from "@/lib/utils";

const SECTIONS = [
	{ id: "profile", label: "Profile", icon: UserIcon },
	{ id: "address", label: "Address", icon: MapPinIcon },
	{ id: "practice", label: "Practice", icon: BriefcaseIcon },
	{ id: "preferences", label: "Preferences", icon: SlidersHorizontalIcon },
	{ id: "password", label: "Password", icon: KeyIcon },
	{ id: "api-keys", label: "API keys", icon: SettingsIcon },
	{ id: "mcp", label: "MCP config", icon: SettingsIcon },
] as const;

export default function AccountPage() {
	return (
		<SidebarProvider>
			<div className="flex h-dvh w-full pr-0.5">
				<AccountSidebar />
				<SidebarInset>
					<header className="flex h-16 shrink-0 items-center gap-3 border-b px-4">
						<SidebarTrigger />
						<Separator orientation="vertical" className="mr-2 h-4" />
						<Breadcrumb>
							<BreadcrumbList>
								<BreadcrumbItem>
									<BreadcrumbPage>Account</BreadcrumbPage>
								</BreadcrumbItem>
							</BreadcrumbList>
						</Breadcrumb>
					</header>

					<main className="flex-1 overflow-y-auto px-6 py-8 md:px-10 lg:px-16">
						<div className="mx-auto flex max-w-3xl flex-col gap-12">
							<SettingsSections />
							<PasswordSection />
							<ApiKeysSection />
							<McpConfigSection />
						</div>
					</main>
				</SidebarInset>
			</div>
		</SidebarProvider>
	);
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

function AccountSidebar() {
	return (
		<Sidebar>
			<AppSidebarBrand />

			<SidebarContent className="px-2">
				<AppSidebarNav />
				<SidebarGroup>
					<SidebarGroupLabel>On this page</SidebarGroupLabel>
					<SidebarMenu>
						{SECTIONS.map((s) => {
							const Icon = s.icon;
							return (
								<SidebarMenuItem key={s.id}>
									<SidebarMenuButton asChild>
										<a href={`#${s.id}`}>
											<Icon className="size-4" />
											<span>{s.label}</span>
										</a>
									</SidebarMenuButton>
								</SidebarMenuItem>
							);
						})}
					</SidebarMenu>
				</SidebarGroup>
			</SidebarContent>

			<SidebarRail />

			<SidebarFooter className="border-t">
				<AppSidebarFooter />
			</SidebarFooter>
		</Sidebar>
	);
}

// ---------------------------------------------------------------------------
// Section primitives
// ---------------------------------------------------------------------------

function SectionHeader({
	id,
	title,
	description,
}: {
	id: string;
	title: string;
	description?: string;
}) {
	return (
		<div id={id} className="scroll-mt-20">
			<h2 className="font-semibold text-foreground text-xs uppercase tracking-[0.18em]">
				{title}
			</h2>
			{description && (
				<p className="mt-1 text-muted-foreground text-sm">{description}</p>
			)}
		</div>
	);
}

function Field({
	label,
	children,
	hint,
}: {
	label: string;
	children: React.ReactNode;
	hint?: string;
}) {
	return (
		<label className="block">
			<span className="font-medium text-foreground text-sm">{label}</span>
			<div className="mt-1.5">{children}</div>
			{hint && <p className="mt-1 text-muted-foreground text-xs">{hint}</p>}
		</label>
	);
}

function Banner({
	kind,
	children,
}: {
	kind: "ok" | "error";
	children: React.ReactNode;
}) {
	const ok = kind === "ok";
	return (
		<div
			className={
				ok
					? "flex items-start gap-2 rounded-md border border-green-500/30 bg-green-500/10 p-3 text-green-700 text-sm dark:text-green-300"
					: "flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm"
			}
		>
			{ok ? (
				<CheckIcon className="mt-0.5 size-4 shrink-0" />
			) : (
				<AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
			)}
			<span>{children}</span>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Settings (profile + address + practice + preferences)
//
// One GET /api/account/settings loads the shared bundle; each section below
// edits a slice of it and PATCHes just that slice. Saving returns the full
// updated settings, which we lift back to the parent so every section stays in
// sync. (Login email is the exception — it lives on the auth record and saves
// through updateProfile / /api/auth/me.)
// ---------------------------------------------------------------------------

type SectionProps = {
	settings: UserSettings;
	onChange: (s: UserSettings) => void;
};

function SettingsSections() {
	const [settings, setSettings] = useState<UserSettings | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let cancelled = false;
		getSettings()
			.then((s) => !cancelled && setSettings(s))
			.catch(
				(e) =>
					!cancelled &&
					setError(
						e instanceof AccountError ? e.detail : "Failed to load settings.",
					),
			);
		return () => {
			cancelled = true;
		};
	}, []);

	if (error) {
		return (
			<section className="flex flex-col gap-4">
				<SectionHeader id="profile" title="Profile" />
				<Banner kind="error">{error}</Banner>
			</section>
		);
	}
	if (!settings) {
		return (
			<div
				id="profile"
				className="flex scroll-mt-20 items-center gap-2 text-muted-foreground text-sm"
			>
				<Loader2Icon className="size-3.5 animate-spin" /> Loading settings…
			</div>
		);
	}

	return (
		<>
			<ProfileSection settings={settings} onChange={setSettings} />
			<AddressSection settings={settings} onChange={setSettings} />
			<PracticeSection settings={settings} onChange={setSettings} />
			<PreferencesSection settings={settings} onChange={setSettings} />
		</>
	);
}

// A labelled save button + status banners — the same footer every settings
// section uses. `dirty` gates the button; `state` drives the spinner/banners.
function SaveRow({
	dirty,
	saving,
	msg,
	err,
	onSave,
	children,
}: {
	dirty: boolean;
	saving: boolean;
	msg: string | null;
	err: string | null;
	onSave: () => void;
	children?: React.ReactNode;
}) {
	return (
		<>
			{msg && <Banner kind="ok">{msg}</Banner>}
			{err && <Banner kind="error">{err}</Banner>}
			<div className="flex items-center gap-3">
				<Button onClick={onSave} disabled={!dirty || saving}>
					{saving && <Loader2Icon className="size-3.5 animate-spin" />}
					Save changes
				</Button>
				{children}
			</div>
		</>
	);
}

// Switch-style toggle in a labelled row — used by the preferences section.
function PrefToggle({
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

function ProfileSection({ settings, onChange }: SectionProps) {
	const { user, setUser } = useAuth();
	const [firstName, setFirstName] = useState(settings.first_name);
	const [lastName, setLastName] = useState(settings.last_name);
	const [email, setEmail] = useState(settings.email);
	const [phone, setPhone] = useState(settings.phone);
	const [saving, setSaving] = useState(false);
	const [msg, setMsg] = useState<string | null>(null);
	const [err, setErr] = useState<string | null>(null);

	const nextEmail = email.trim().toLowerCase();
	const dirty =
		firstName !== settings.first_name ||
		lastName !== settings.last_name ||
		phone !== settings.phone ||
		nextEmail !== settings.email;

	const onSave = async () => {
		setSaving(true);
		setMsg(null);
		setErr(null);
		try {
			let next = settings;
			if (
				firstName !== settings.first_name ||
				lastName !== settings.last_name ||
				phone !== settings.phone
			) {
				next = await updateSettings({
					first_name: firstName.trim(),
					last_name: lastName.trim(),
					phone: phone.trim(),
				});
			}
			// Login email lives on the auth record, not the settings bundle.
			if (nextEmail !== settings.email) {
				const u = await updateProfile({ email: nextEmail });
				next = { ...next, email: u.email };
			}
			// Refresh the auth context so the sidebar name/email update live.
			const me = await fetch("/api/auth/me", { credentials: "include" }).then(
				(r) => (r.ok ? r.json() : null),
			);
			if (me) setUser(me as AuthUser);
			onChange(next);
			setFirstName(next.first_name);
			setLastName(next.last_name);
			setEmail(next.email);
			setPhone(next.phone);
			setMsg("Profile updated.");
		} catch (e) {
			setErr(
				e instanceof AccountError ? e.detail : "Failed to update profile.",
			);
		} finally {
			setSaving(false);
		}
	};

	return (
		<section className="flex flex-col gap-4">
			<SectionHeader
				id="profile"
				title="Profile"
				description="How you appear in the app and where we'll reach you."
			/>
			<div className="grid gap-4 sm:grid-cols-2">
				<Field label="First name">
					<Input
						value={firstName}
						onChange={(e) => setFirstName(e.target.value)}
						placeholder="First name"
					/>
				</Field>
				<Field label="Last name">
					<Input
						value={lastName}
						onChange={(e) => setLastName(e.target.value)}
						placeholder="Last name"
					/>
				</Field>
				<Field label="Login email" hint="Used to sign in.">
					<Input
						type="email"
						value={email}
						onChange={(e) => setEmail(e.target.value)}
						autoComplete="email"
					/>
				</Field>
				<Field label="Phone" hint="Optional — for account security & support.">
					<Input
						type="tel"
						value={phone}
						onChange={(e) => setPhone(e.target.value)}
						placeholder="(555) 123-4567"
					/>
				</Field>
			</div>
			<SaveRow
				dirty={dirty}
				saving={saving}
				msg={msg}
				err={err}
				onSave={onSave}
			>
				<span className="text-muted-foreground text-xs">
					Tier · <span className="font-semibold">{user.tier}</span>
				</span>
			</SaveRow>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Address
// ---------------------------------------------------------------------------

function AddressSection({ settings, onChange }: SectionProps) {
	const [street, setStreet] = useState(settings.address_line1);
	const [unit, setUnit] = useState(settings.address_line2);
	const [city, setCity] = useState(settings.city);
	const [region, setRegion] = useState(settings.region);
	const [postal, setPostal] = useState(settings.postal_code);
	const [saving, setSaving] = useState(false);
	const [msg, setMsg] = useState<string | null>(null);
	const [err, setErr] = useState<string | null>(null);

	const dirty =
		street !== settings.address_line1 ||
		unit !== settings.address_line2 ||
		city !== settings.city ||
		region !== settings.region ||
		postal !== settings.postal_code;

	const onSave = async () => {
		setSaving(true);
		setMsg(null);
		setErr(null);
		try {
			const next = await updateSettings({
				address_line1: street.trim(),
				address_line2: unit.trim(),
				city: city.trim(),
				region: region.trim(),
				postal_code: postal.trim(),
			});
			onChange(next);
			setStreet(next.address_line1);
			setUnit(next.address_line2);
			setCity(next.city);
			setRegion(next.region);
			setPostal(next.postal_code);
			setMsg("Address updated.");
		} catch (e) {
			setErr(
				e instanceof AccountError ? e.detail : "Failed to update address.",
			);
		} finally {
			setSaving(false);
		}
	};

	return (
		<section className="flex flex-col gap-4">
			<SectionHeader
				id="address"
				title="Address"
				description="Your mailing address. All optional."
			/>
			<div className="grid gap-4 sm:grid-cols-6">
				<div className="sm:col-span-6">
					<Field label="Street address">
						<Input
							value={street}
							onChange={(e) => setStreet(e.target.value)}
							placeholder="123 Main St"
						/>
					</Field>
				</div>
				<div className="sm:col-span-2">
					<Field label="Apt / Suite">
						<Input value={unit} onChange={(e) => setUnit(e.target.value)} />
					</Field>
				</div>
				<div className="sm:col-span-2">
					<Field label="City">
						<Input value={city} onChange={(e) => setCity(e.target.value)} />
					</Field>
				</div>
				<div className="sm:col-span-1">
					<Field label="State">
						<Input
							value={region}
							onChange={(e) => setRegion(e.target.value)}
							maxLength={2}
							placeholder="IA"
						/>
					</Field>
				</div>
				<div className="sm:col-span-1">
					<Field label="ZIP">
						<Input
							value={postal}
							onChange={(e) => setPostal(e.target.value)}
							inputMode="numeric"
							placeholder="50309"
						/>
					</Field>
				</div>
			</div>
			<SaveRow
				dirty={dirty}
				saving={saving}
				msg={msg}
				err={err}
				onSave={onSave}
			/>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Practice
// ---------------------------------------------------------------------------

function PracticeSection({ settings, onChange }: SectionProps) {
	const [org, setOrg] = useState(settings.organization);
	const [role, setRole] = useState(settings.role || ROLES[0].value);
	const [barNumber, setBarNumber] = useState(settings.bar_number);
	const [jurisdiction, setJurisdiction] = useState(
		settings.primary_jurisdiction || JURISDICTIONS[0].value,
	);
	const [timezone, setTimezone] = useState(
		settings.timezone || TIMEZONES[0].value,
	);
	const [saving, setSaving] = useState(false);
	const [msg, setMsg] = useState<string | null>(null);
	const [err, setErr] = useState<string | null>(null);

	const dirty =
		org !== settings.organization ||
		role !== (settings.role || ROLES[0].value) ||
		barNumber !== settings.bar_number ||
		jurisdiction !==
			(settings.primary_jurisdiction || JURISDICTIONS[0].value) ||
		timezone !== (settings.timezone || TIMEZONES[0].value);

	const onSave = async () => {
		setSaving(true);
		setMsg(null);
		setErr(null);
		try {
			const next = await updateSettings({
				organization: org.trim(),
				role,
				bar_number: barNumber.trim(),
				primary_jurisdiction: jurisdiction,
				timezone,
			});
			onChange(next);
			setMsg("Practice details updated.");
		} catch (e) {
			setErr(
				e instanceof AccountError ? e.detail : "Failed to update details.",
			);
		} finally {
			setSaving(false);
		}
	};

	return (
		<section className="flex flex-col gap-4">
			<SectionHeader
				id="practice"
				title="Practice"
				description="Used to tailor results and pre-fill search filters."
			/>
			<div className="grid gap-4 sm:grid-cols-2">
				<Field label="Organization" hint="Firm, agency, or school — optional.">
					<Input
						value={org}
						onChange={(e) => setOrg(e.target.value)}
						placeholder="e.g. Hudson Law LLC"
					/>
				</Field>
				<Field label="Role">
					<NativeSelect
						value={role}
						onChange={setRole}
						options={ROLES}
						icon={BriefcaseIcon}
					/>
				</Field>
				<Field
					label="Bar number"
					hint="Optional — your attorney registration number."
				>
					<Input
						value={barNumber}
						onChange={(e) => setBarNumber(e.target.value)}
						placeholder="e.g. AT0001234"
					/>
				</Field>
				<Field label="Primary jurisdiction">
					<NativeSelect
						value={jurisdiction}
						onChange={setJurisdiction}
						options={JURISDICTIONS}
						icon={MapPinIcon}
					/>
				</Field>
				<Field label="Time zone">
					<NativeSelect
						value={timezone}
						onChange={setTimezone}
						options={TIMEZONES}
						icon={ClockIcon}
					/>
				</Field>
			</div>
			<SaveRow
				dirty={dirty}
				saving={saving}
				msg={msg}
				err={err}
				onSave={onSave}
			/>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Preferences (appearance + research defaults + notifications)
// ---------------------------------------------------------------------------

function PreferencesSection({ settings, onChange }: SectionProps) {
	const { theme, toggle } = useTheme();
	const [themeChoice, setThemeChoice] = useState(settings.theme || "system");
	const [scope, setScope] = useState(
		settings.default_search_scope || SEARCH_SCOPES[0].value,
	);
	const [citation, setCitation] = useState(
		settings.citation_style || CITATION_STYLES[0].value,
	);
	const [verify, setVerify] = useState(settings.verify_citations);
	const [digest, setDigest] = useState(settings.weekly_digest);
	const [news, setNews] = useState(settings.product_news);
	const [saving, setSaving] = useState(false);
	const [msg, setMsg] = useState<string | null>(null);
	const [err, setErr] = useState<string | null>(null);

	// Flip the live app theme so the choice is visible immediately, the same way
	// the onboarding wizard does. The saved value persists on Save.
	const selectTheme = (choice: string) => {
		setThemeChoice(choice);
		const target =
			choice === "system"
				? window.matchMedia("(prefers-color-scheme: dark)").matches
					? "dark"
					: "light"
				: choice;
		if (target !== theme) toggle();
	};

	const dirty =
		themeChoice !== (settings.theme || "system") ||
		scope !== (settings.default_search_scope || SEARCH_SCOPES[0].value) ||
		citation !== (settings.citation_style || CITATION_STYLES[0].value) ||
		verify !== settings.verify_citations ||
		digest !== settings.weekly_digest ||
		news !== settings.product_news;

	const onSave = async () => {
		setSaving(true);
		setMsg(null);
		setErr(null);
		try {
			const next = await updateSettings({
				theme: themeChoice,
				default_search_scope: scope,
				citation_style: citation,
				verify_citations: verify,
				weekly_digest: digest,
				product_news: news,
			});
			onChange(next);
			setMsg("Preferences updated.");
		} catch (e) {
			setErr(
				e instanceof AccountError ? e.detail : "Failed to update preferences.",
			);
		} finally {
			setSaving(false);
		}
	};

	return (
		<section className="flex flex-col gap-4">
			<SectionHeader
				id="preferences"
				title="Preferences"
				description="Appearance, research defaults, and what we email you."
			/>

			<Field label="Theme">
				<div className="inline-flex rounded-lg border bg-muted/40 p-1">
					{THEMES.map((t) => {
						const Icon =
							t.value === "light"
								? SunIcon
								: t.value === "dark"
									? MoonIcon
									: MonitorIcon;
						const active = themeChoice === t.value;
						return (
							<button
								key={t.value}
								type="button"
								onClick={() => selectTheme(t.value)}
								className={cn(
									"flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium text-[13px] transition-colors",
									active
										? "bg-card text-foreground shadow-xs"
										: "text-muted-foreground hover:text-foreground",
								)}
							>
								<Icon className="size-3.5" />
								{t.label}
							</button>
						);
					})}
				</div>
			</Field>

			<div className="grid gap-4 sm:grid-cols-2">
				<Field label="Default search scope">
					<NativeSelect
						value={scope}
						onChange={setScope}
						options={SEARCH_SCOPES}
						icon={FileTextIcon}
					/>
				</Field>
				<Field label="Citation style">
					<NativeSelect
						value={citation}
						onChange={setCitation}
						options={CITATION_STYLES}
						icon={ScaleIcon}
					/>
				</Field>
			</div>

			<div className="space-y-2.5">
				<PrefToggle
					icon={ShieldCheckIcon}
					label="Verify citations before showing answers"
					description="Run the deterministic citation & quote check on every AI response. Recommended."
					checked={verify}
					onChange={setVerify}
				/>
				<PrefToggle
					icon={BellIcon}
					label="Weekly corpus digest"
					description="What's new in cases, statutes & rules for your jurisdiction."
					checked={digest}
					onChange={setDigest}
				/>
				<PrefToggle
					icon={SparklesIcon}
					label="Product announcements"
					description="Occasional emails about new features. No more than monthly."
					checked={news}
					onChange={setNews}
				/>
			</div>

			<SaveRow
				dirty={dirty}
				saving={saving}
				msg={msg}
				err={err}
				onSave={onSave}
			/>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Password
// ---------------------------------------------------------------------------

function PasswordSection() {
	const [curPw, setCurPw] = useState("");
	const [newPw, setNewPw] = useState("");
	const [saving, setSaving] = useState(false);
	const [msg, setMsg] = useState<string | null>(null);
	const [err, setErr] = useState<string | null>(null);

	const onSave = async () => {
		setSaving(true);
		setMsg(null);
		setErr(null);
		try {
			await changePassword({
				current_password: curPw,
				new_password: newPw,
			});
			setCurPw("");
			setNewPw("");
			setMsg("Password updated.");
		} catch (e) {
			setErr(
				e instanceof AccountError ? e.detail : "Failed to change password.",
			);
		} finally {
			setSaving(false);
		}
	};

	return (
		<section className="flex flex-col gap-4">
			<SectionHeader
				id="password"
				title="Password"
				description="Use at least 8 characters. We don't enforce more — pick something memorable."
			/>
			<div className="grid gap-4 sm:grid-cols-2">
				<Field label="Current password">
					<Input
						type="password"
						value={curPw}
						onChange={(e) => setCurPw(e.target.value)}
						autoComplete="current-password"
					/>
				</Field>
				<Field label="New password">
					<Input
						type="password"
						value={newPw}
						onChange={(e) => setNewPw(e.target.value)}
						autoComplete="new-password"
					/>
				</Field>
			</div>
			{msg && <Banner kind="ok">{msg}</Banner>}
			{err && <Banner kind="error">{err}</Banner>}
			<div>
				<Button
					onClick={onSave}
					disabled={saving || !curPw || newPw.length < 8}
				>
					{saving && <Loader2Icon className="size-3.5 animate-spin" />}
					Update password
				</Button>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// API Keys
// ---------------------------------------------------------------------------

function ApiKeysSection() {
	const [keys, setKeys] = useState<APIKey[] | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [name, setName] = useState("");
	const [creating, setCreating] = useState(false);
	const [justCreated, setJustCreated] = useState<CreatedAPIKey | null>(null);
	const [confirmRevoke, setConfirmRevoke] = useState<APIKey | null>(null);
	const [copied, setCopied] = useState(false);

	const refresh = useCallback(async () => {
		try {
			const data = await listKeys();
			setKeys(data);
		} catch (e) {
			setError(e instanceof AccountError ? e.detail : "Failed to load keys.");
		}
	}, []);

	useEffect(() => {
		void refresh();
	}, [refresh]);

	const onCreate = async () => {
		if (!name.trim()) return;
		setCreating(true);
		setError(null);
		try {
			const created = await createKey(name.trim());
			setJustCreated(created);
			setName("");
			await refresh();
		} catch (e) {
			setError(e instanceof AccountError ? e.detail : "Failed to create key.");
		} finally {
			setCreating(false);
		}
	};

	const onRevoke = async () => {
		if (!confirmRevoke) return;
		try {
			await revokeKey(confirmRevoke.id);
			setConfirmRevoke(null);
			await refresh();
		} catch (e) {
			setError(e instanceof AccountError ? e.detail : "Failed to revoke key.");
		}
	};

	const onCopyRaw = async () => {
		if (!justCreated) return;
		await navigator.clipboard.writeText(justCreated.raw_key);
		setCopied(true);
		window.setTimeout(() => setCopied(false), 1500);
	};

	return (
		<section className="flex flex-col gap-4">
			<SectionHeader
				id="api-keys"
				title="API keys"
				description="One key per integration. We only show the raw key once at creation — store it somewhere safe."
			/>

			{justCreated && (
				<div className="rounded-lg border border-primary/40 bg-primary/5 p-4">
					<div className="flex items-baseline justify-between gap-3">
						<div>
							<h3 className="font-semibold text-foreground text-sm">
								New key — copy it now
							</h3>
							<p className="mt-1 text-muted-foreground text-xs">
								This is the only time you'll see the full secret. We store only
								the prefix on our side.
							</p>
						</div>
						<button
							type="button"
							onClick={() => setJustCreated(null)}
							className="text-muted-foreground text-xs hover:text-foreground"
						>
							Dismiss
						</button>
					</div>
					<div className="mt-3 flex items-center gap-2 rounded-md border bg-background px-3 py-2 font-mono text-xs">
						<span className="min-w-0 flex-1 truncate">
							{justCreated.raw_key}
						</span>
						<Button
							size="sm"
							variant="outline"
							onClick={onCopyRaw}
							className="shrink-0"
						>
							{copied ? (
								<CheckIcon className="size-3.5" />
							) : (
								<CopyIcon className="size-3.5" />
							)}
							{copied ? "Copied" : "Copy"}
						</Button>
					</div>
				</div>
			)}

			<div className="flex flex-col gap-3 sm:flex-row sm:items-end">
				<Field label="Key label">
					<Input
						value={name}
						onChange={(e) => setName(e.target.value)}
						placeholder="e.g. Claude Desktop on laptop"
					/>
				</Field>
				<Button onClick={onCreate} disabled={creating || !name.trim()}>
					{creating ? (
						<Loader2Icon className="size-3.5 animate-spin" />
					) : (
						<PlusIcon className="size-3.5" />
					)}
					Create key
				</Button>
			</div>

			{error && <Banner kind="error">{error}</Banner>}

			{keys === null ? (
				<div className="flex items-center gap-2 text-muted-foreground text-sm">
					<Loader2Icon className="size-3.5 animate-spin" /> Loading keys…
				</div>
			) : keys.length === 0 ? (
				<div className="rounded-md border border-dashed bg-muted/30 px-4 py-8 text-center text-muted-foreground text-sm">
					No keys yet. Create one above to integrate with the MCP server.
				</div>
			) : (
				<ul className="divide-y border-y">
					{keys.map((k) => (
						<li key={k.id} className="flex items-baseline gap-4 py-3 text-sm">
							<span className="w-44 shrink-0 truncate font-medium">
								{k.name}
							</span>
							<span className="w-32 shrink-0 font-mono text-muted-foreground text-xs">
								{k.prefix}…
							</span>
							<span className="hidden flex-1 text-muted-foreground text-xs md:block">
								Created {fmtDate(k.created_at)} · Last used{" "}
								{fmtDateTime(k.last_used_at)}
							</span>
							<button
								type="button"
								onClick={() => setConfirmRevoke(k)}
								className="ml-auto shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
								aria-label={`Revoke ${k.name}`}
							>
								<TrashIcon className="size-4" />
							</button>
						</li>
					))}
				</ul>
			)}

			<Dialog
				open={confirmRevoke !== null}
				onOpenChange={(open) => !open && setConfirmRevoke(null)}
			>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Revoke this key?</DialogTitle>
						<DialogDescription>
							Anything currently using{" "}
							<span className="font-mono">{confirmRevoke?.prefix}…</span> (
							{confirmRevoke?.name}) will start getting 401s immediately. This
							cannot be undone.
						</DialogDescription>
					</DialogHeader>
					<DialogFooter>
						<Button variant="outline" onClick={() => setConfirmRevoke(null)}>
							Cancel
						</Button>
						<Button
							onClick={onRevoke}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Revoke key
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</section>
	);
}

// ---------------------------------------------------------------------------
// MCP config
// ---------------------------------------------------------------------------

const PATH_FALLBACK = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin";

// The env var the client substitutes into the header, derived from the connector
// key so the two can never drift apart: "hudson-corpus" → HUDSON_CORPUS_KEY.
const MCP_ENV_KEY = `${MCP_SERVER_ID.toUpperCase().replaceAll("-", "_")}_KEY`;

function claudeDesktopSnippet(rawKey: string, mcpHost: string) {
	return JSON.stringify(
		{
			mcpServers: {
				[MCP_SERVER_ID]: {
					command: "npx",
					args: [
						"-y",
						"mcp-remote",
						mcpHost,
						"--header",
						// Escaped: the ${...} is literal text the MCP client expands, not
						// a template substitution of ours.
						`X-API-Key:\${${MCP_ENV_KEY}}`,
					],
					env: {
						[MCP_ENV_KEY]: rawKey,
						PATH: PATH_FALLBACK,
					},
				},
			},
		},
		null,
		2,
	);
}

function McpConfigSection() {
	const [mcpHost, setMcpHost] = useState<string>("");
	const [mcpSource, setMcpSource] = useState<
		"explicit" | "codespaces" | "unset"
	>("unset");
	const [copied, setCopied] = useState(false);

	useEffect(() => {
		let cancelled = false;
		// Seed from this app's own origin before asking the server: the MCP endpoint
		// is served from the same origin as this page, so window.location is the one
		// source that cannot be stale. The old seed was a literal
		// "https://your-host.example.com/mcp" — if the server pinned no MCP_HOST and
		// wasn't a Codespace (i.e. production), users copied a snippet pointing at a
		// host that does not exist.
		//
		// Resolved here rather than during render because mcpUrl() reads
		// window.location whenever NEXT_PUBLIC_APP_URL is unset (dev): seeding state
		// with it would hydrate the server's window-less "/mcp" against the browser's
		// absolute URL and tear the snippet's text node.
		setMcpHost(mcpUrl());
		fetchPublicConfig()
			.then((cfg) => {
				if (cancelled) return;
				if (cfg.mcp_host) setMcpHost(cfg.mcp_host);
				setMcpSource(cfg.source);
			})
			.catch(() => {
				/* keep the same-origin fallback */
			});
		return () => {
			cancelled = true;
		};
	}, []);

	const snippet = useMemo(
		() => claudeDesktopSnippet("YOUR_RAW_KEY", mcpHost),
		[mcpHost],
	);

	const onCopy = async () => {
		await navigator.clipboard.writeText(snippet);
		setCopied(true);
		window.setTimeout(() => setCopied(false), 1500);
	};

	return (
		<section className="flex flex-col gap-4">
			<SectionHeader
				id="mcp"
				title="MCP config"
				description={`Drop this into Claude Desktop or Cursor to give your AI tools live access to ${BRAND_NAME} via your API key.`}
			/>

			<div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
				<Field
					label="MCP host"
					hint={
						mcpSource === "explicit"
							? "Pinned by the server's public config."
							: mcpSource === "codespaces"
								? "Auto-detected from the running Codespace."
								: "Defaulted to the origin serving this page. Pin MCP_HOST on the server to override."
					}
				>
					<Input value={mcpHost} onChange={(e) => setMcpHost(e.target.value)} />
				</Field>
				<Button variant="outline" onClick={onCopy}>
					{copied ? (
						<CheckIcon className="size-3.5" />
					) : (
						<CopyIcon className="size-3.5" />
					)}
					{copied ? "Copied" : "Copy snippet"}
				</Button>
			</div>

			<pre className="max-h-96 overflow-auto rounded-lg border bg-muted/40 p-4 text-xs leading-relaxed">
				<code>{snippet}</code>
			</pre>

			<div className="rounded-md border bg-muted/20 p-4 text-muted-foreground text-sm">
				<p>
					Replace{" "}
					<code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
						YOUR_RAW_KEY
					</code>{" "}
					with a key you create above. Then drop the snippet into Claude
					Desktop&apos;s{" "}
					<code className="font-mono text-xs">claude_desktop_config.json</code>{" "}
					(or your MCP client&apos;s equivalent) and restart the app.
				</p>
				<p className="mt-2">
					Why <code className="font-mono text-xs">mcp-remote</code>? Claude
					Desktop only knows how to spawn local stdio subprocesses;{" "}
					<code className="font-mono text-xs">mcp-remote</code> is a tiny shim
					that bridges to our streamable HTTP transport, attaching the{" "}
					<code className="font-mono text-xs">X-API-Key</code> header on every
					request.
				</p>
			</div>
		</section>
	);
}
