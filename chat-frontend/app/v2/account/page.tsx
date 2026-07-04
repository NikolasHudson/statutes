"use client";

// v2 account settings — the Carbon settings page wired to the real account
// APIs (lib/iowa-account.ts): /api/account/settings for profile / address /
// practice / preferences, /api/auth/* for email + password, and
// /api/account/api-keys for integrations. Same section inventory as the
// legacy /account page; each section saves on its own.

import {
	CheckIcon,
	CopyIcon,
	KeyRoundIcon,
	MonitorIcon,
	MoonIcon,
	SunIcon,
	Trash2Icon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth-gate";
import {
	BtnPrimary,
	BtnSecondary,
	Eyebrow,
	Notification,
	SelectField,
	TextField,
	ToggleRow,
	useTheme,
} from "@/components/carbon/primitives";
import {
	type APIKey,
	type CreatedAPIKey,
	changePassword,
	createKey,
	fetchPublicConfig,
	fmtDateTime,
	getSettings,
	listKeys,
	revokeKey,
	type UserSettings,
	type UserSettingsPatch,
	updateProfile,
	updateSettings,
} from "@/lib/iowa-account";
import {
	CITATION_STYLES,
	JURISDICTIONS,
	ROLES,
	SEARCH_SCOPES,
	TIMEZONES,
} from "@/lib/settings-options";
import { cn } from "@/lib/utils";

const SECTIONS = [
	{ id: "profile", label: "Profile" },
	{ id: "address", label: "Address" },
	{ id: "practice", label: "Practice" },
	{ id: "preferences", label: "Preferences" },
	{ id: "password", label: "Password" },
	{ id: "api-keys", label: "API keys" },
	{ id: "mcp", label: "MCP config" },
];

export default function V2AccountPage() {
	const { user } = useAuth();
	const [settings, setSettings] = useState<UserSettings | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		getSettings()
			.then(setSettings)
			.catch((e) => setError((e as Error).message));
	}, []);

	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<Eyebrow>Account — {user.email}</Eyebrow>
			<h1 className="mt-4 font-light text-3xl sm:text-4xl">Settings</h1>
			<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
				Profile, research defaults, and integrations. Each section saves on its
				own.
			</p>

			{error ? (
				<Notification
					kind="error"
					title="Couldn't load settings"
					className="mt-8 max-w-xl"
				>
					{error}
				</Notification>
			) : !settings ? (
				<p className="mt-8 text-[var(--cds-text-2)] text-sm">
					Loading settings…
				</p>
			) : (
				<div className="mt-10 grid gap-12 lg:grid-cols-[11rem_minmax(0,42rem)]">
					<OnThisPage />
					<div className="min-w-0 space-y-14">
						<ProfileSection settings={settings} onSaved={setSettings} />
						<AddressSection settings={settings} onSaved={setSettings} />
						<PracticeSection settings={settings} onSaved={setSettings} />
						<PreferencesSection settings={settings} onSaved={setSettings} />
						<PasswordSection />
						<ApiKeysSection />
						<McpSection />
					</div>
				</div>
			)}
		</div>
	);
}

function OnThisPage() {
	const [active, setActive] = useState("profile");
	return (
		<nav className="sticky top-6 hidden self-start lg:block">
			<p className="pb-2 font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
				On this page
			</p>
			{SECTIONS.map((s) => (
				<a
					key={s.id}
					href={`#${s.id}`}
					onClick={() => setActive(s.id)}
					className={cn(
						"flex border-l-[3px] py-1.5 pl-3 text-[13px] transition-colors",
						active === s.id
							? "border-[#0f62fe] font-semibold"
							: "border-transparent text-[var(--cds-text-2)] hover:text-[var(--cds-text)]",
					)}
				>
					{s.label}
				</a>
			))}
		</nav>
	);
}

// ---------------------------------------------------------------------------
// Section scaffolding — shared save-state machinery
// ---------------------------------------------------------------------------

function Section({
	id,
	title,
	desc,
	children,
}: {
	id: string;
	title: string;
	desc: string;
	children: React.ReactNode;
}) {
	return (
		<section
			id={id}
			className="scroll-mt-6 border-[var(--cds-border)] border-t pt-6"
		>
			<h2 className="font-semibold text-sm uppercase tracking-wide">{title}</h2>
			<p className="mt-1 text-[13px] text-[var(--cds-text-2)]">{desc}</p>
			<div className="mt-6">{children}</div>
		</section>
	);
}

type SaveState = "idle" | "busy" | "saved" | "error";

// One PATCH per section: run the save, flash "Saved", surface errors inline.
function useSectionSave(onSaved: (s: UserSettings) => void) {
	const [state, setState] = useState<SaveState>("idle");
	const [error, setError] = useState<string | null>(null);
	const save = async (
		patch: UserSettingsPatch,
		extra?: () => Promise<void>,
	) => {
		setState("busy");
		setError(null);
		try {
			await extra?.();
			const next = await updateSettings(patch);
			onSaved(next);
			setState("saved");
			setTimeout(() => setState("idle"), 2000);
		} catch (e) {
			setError((e as Error).message);
			setState("error");
		}
	};
	return { state, error, save };
}

function SaveRow({
	state,
	error,
	onSave,
	note,
}: {
	state: SaveState;
	error: string | null;
	onSave: () => void;
	note?: string;
}) {
	return (
		<>
			{state === "error" && error && (
				<Notification kind="error" title="Couldn't save" className="mt-6">
					{error}
				</Notification>
			)}
			<div className="mt-6 flex items-center gap-4">
				<BtnPrimary
					size="md"
					arrow={false}
					disabled={state === "busy"}
					onClick={onSave}
				>
					{state === "busy" ? "Saving…" : "Save changes"}
				</BtnPrimary>
				{state === "saved" ? (
					<span className="inline-flex items-center gap-1.5 text-[13px] text-[var(--cds-success-text)]">
						<CheckIcon className="size-4" /> Saved
					</span>
				) : note ? (
					<span className="font-mono text-[11px] text-[var(--cds-helper)]">
						{note}
					</span>
				) : null}
			</div>
		</>
	);
}

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------

function ProfileSection({
	settings,
	onSaved,
}: {
	settings: UserSettings;
	onSaved: (s: UserSettings) => void;
}) {
	const { user, setUser } = useAuth();
	const [first, setFirst] = useState(settings.first_name);
	const [last, setLast] = useState(settings.last_name);
	const [email, setEmail] = useState(settings.email);
	const [phone, setPhone] = useState(settings.phone);
	const { state, error, save } = useSectionSave(onSaved);

	return (
		<Section
			id="profile"
			title="Profile"
			desc="How you appear in the app and where we'll reach you."
		>
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField
					label="First name"
					value={first}
					onChange={(e) => setFirst(e.target.value)}
				/>
				<TextField
					label="Last name"
					value={last}
					onChange={(e) => setLast(e.target.value)}
				/>
				<TextField
					label="Login email"
					type="email"
					value={email}
					onChange={(e) => setEmail(e.target.value)}
					helper="Used to sign in."
				/>
				<TextField
					label="Phone"
					value={phone}
					onChange={(e) => setPhone(e.target.value)}
					placeholder="(555) 123-4567"
					helper="Optional — for account security & support."
				/>
			</div>
			<SaveRow
				state={state}
				error={error}
				note={`Tier · ${user.tier}`}
				onSave={() =>
					save({ first_name: first, last_name: last, phone }, async () => {
						// The login email lives on the auth user, not settings.
						if (email.trim() && email.trim() !== settings.email) {
							const u = await updateProfile({ email: email.trim() });
							setUser(u);
						}
					})
				}
			/>
		</Section>
	);
}

function AddressSection({
	settings,
	onSaved,
}: {
	settings: UserSettings;
	onSaved: (s: UserSettings) => void;
}) {
	const [line1, setLine1] = useState(settings.address_line1);
	const [line2, setLine2] = useState(settings.address_line2);
	const [city, setCity] = useState(settings.city);
	const [region, setRegion] = useState(settings.region);
	const [postal, setPostal] = useState(settings.postal_code);
	const { state, error, save } = useSectionSave(onSaved);

	return (
		<Section
			id="address"
			title="Address"
			desc="Your mailing address. All optional."
		>
			<div className="grid gap-5 sm:grid-cols-6">
				<TextField
					label="Street address"
					value={line1}
					onChange={(e) => setLine1(e.target.value)}
					placeholder="123 Main St"
					className="sm:col-span-4"
				/>
				<TextField
					label="Apt / Suite"
					value={line2}
					onChange={(e) => setLine2(e.target.value)}
					placeholder="Suite 200"
					className="sm:col-span-2"
				/>
				<TextField
					label="City"
					value={city}
					onChange={(e) => setCity(e.target.value)}
					placeholder="Des Moines"
					className="sm:col-span-3"
				/>
				<TextField
					label="State"
					value={region}
					onChange={(e) => setRegion(e.target.value)}
					placeholder="IA"
					className="sm:col-span-1"
				/>
				<TextField
					label="ZIP"
					value={postal}
					onChange={(e) => setPostal(e.target.value)}
					placeholder="50309"
					className="sm:col-span-2"
				/>
			</div>
			<SaveRow
				state={state}
				error={error}
				onSave={() =>
					save({
						address_line1: line1,
						address_line2: line2,
						city,
						region,
						postal_code: postal,
					})
				}
			/>
		</Section>
	);
}

function PracticeSection({
	settings,
	onSaved,
}: {
	settings: UserSettings;
	onSaved: (s: UserSettings) => void;
}) {
	const [org, setOrg] = useState(settings.organization);
	const [role, setRole] = useState(settings.role);
	const [bar, setBar] = useState(settings.bar_number);
	const [jurisdiction, setJurisdiction] = useState(
		settings.primary_jurisdiction,
	);
	const [timezone, setTimezone] = useState(settings.timezone);
	const { state, error, save } = useSectionSave(onSaved);

	return (
		<Section
			id="practice"
			title="Practice"
			desc="Used to tailor results and pre-fill search filters."
		>
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField
					label="Organization"
					value={org}
					onChange={(e) => setOrg(e.target.value)}
					placeholder="e.g. Hudson Law LLC"
				/>
				<SelectField
					label="Role"
					options={ROLES}
					value={role}
					onChange={(e) => setRole(e.target.value)}
				/>
				<TextField
					label="Bar number"
					value={bar}
					onChange={(e) => setBar(e.target.value)}
					placeholder="e.g. AT0001234"
				/>
				<SelectField
					label="Primary jurisdiction"
					options={JURISDICTIONS}
					value={jurisdiction}
					onChange={(e) => setJurisdiction(e.target.value)}
				/>
				<SelectField
					label="Time zone"
					options={TIMEZONES}
					value={timezone}
					onChange={(e) => setTimezone(e.target.value)}
					className="sm:col-span-2"
				/>
			</div>
			<SaveRow
				state={state}
				error={error}
				onSave={() =>
					save({
						organization: org,
						role,
						bar_number: bar,
						primary_jurisdiction: jurisdiction,
						timezone,
					})
				}
			/>
		</Section>
	);
}

function PreferencesSection({
	settings,
	onSaved,
}: {
	settings: UserSettings;
	onSaved: (s: UserSettings) => void;
}) {
	const { setTheme } = useTheme();
	const [themeChoice, setThemeChoice] = useState(settings.theme);
	const [scope, setScope] = useState(settings.default_search_scope);
	const [style, setStyle] = useState(settings.citation_style);
	const [verify, setVerify] = useState(settings.verify_citations);
	const [digest, setDigest] = useState(settings.weekly_digest);
	const [news, setNews] = useState(settings.product_news);
	const { state, error, save } = useSectionSave(onSaved);

	const themeChoices = [
		{ id: "light", label: "Light", icon: SunIcon },
		{ id: "dark", label: "Dark", icon: MoonIcon },
		{ id: "system", label: "System", icon: MonitorIcon },
	];
	const pickTheme = (id: string) => {
		setThemeChoice(id);
		// Apply immediately inside the v2 shell (system falls back to light).
		setTheme(id === "dark" ? "g100" : "white");
	};

	return (
		<Section
			id="preferences"
			title="Preferences"
			desc="Appearance, research defaults, and what we email you."
		>
			<p className="mb-2 text-[var(--cds-text-2)] text-xs">Theme</p>
			<div className="inline-flex border border-[var(--cds-border)]">
				{themeChoices.map((t) => {
					const Icon = t.icon;
					const active = t.id === themeChoice;
					return (
						<button
							key={t.id}
							type="button"
							onClick={() => pickTheme(t.id)}
							className={cn(
								"flex h-10 items-center gap-2 px-4 text-[13px] transition-colors",
								active
									? "bg-[var(--cds-layer-selected)] font-semibold"
									: "text-[var(--cds-text-2)] hover:bg-[var(--cds-layer-hover)]",
							)}
						>
							<Icon className="size-4" strokeWidth={1.5} />
							{t.label}
						</button>
					);
				})}
			</div>

			<div className="mt-6 grid gap-5 sm:grid-cols-2">
				<SelectField
					label="Default search scope"
					options={SEARCH_SCOPES}
					value={scope}
					onChange={(e) => setScope(e.target.value)}
				/>
				<SelectField
					label="Citation style"
					options={CITATION_STYLES}
					value={style}
					onChange={(e) => setStyle(e.target.value)}
				/>
			</div>

			<div className="mt-4 divide-y divide-[var(--cds-border)]">
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
			<SaveRow
				state={state}
				error={error}
				onSave={() =>
					save({
						theme: themeChoice,
						default_search_scope: scope,
						citation_style: style,
						verify_citations: verify,
						weekly_digest: digest,
						product_news: news,
					})
				}
			/>
		</Section>
	);
}

function PasswordSection() {
	const [current, setCurrent] = useState("");
	const [next, setNext] = useState("");
	const [state, setState] = useState<SaveState>("idle");
	const [error, setError] = useState<string | null>(null);

	const submit = async () => {
		setState("busy");
		setError(null);
		try {
			await changePassword({ current_password: current, new_password: next });
			setCurrent("");
			setNext("");
			setState("saved");
			setTimeout(() => setState("idle"), 2000);
		} catch (e) {
			setError((e as Error).message);
			setState("error");
		}
	};

	return (
		<Section
			id="password"
			title="Password"
			desc="Use at least 8 characters. We don't enforce more — pick something memorable."
		>
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField
					label="Current password"
					type="password"
					autoComplete="current-password"
					value={current}
					onChange={(e) => setCurrent(e.target.value)}
				/>
				<TextField
					label="New password"
					type="password"
					autoComplete="new-password"
					value={next}
					onChange={(e) => setNext(e.target.value)}
				/>
			</div>
			{state === "error" && error && (
				<Notification
					kind="error"
					title="Couldn't update password"
					className="mt-6"
				>
					{error}
				</Notification>
			)}
			<div className="mt-6 flex items-center gap-4">
				<BtnSecondary
					size="md"
					disabled={state === "busy" || !current || next.length < 8}
					onClick={submit}
				>
					{state === "busy" ? "Updating…" : "Update password"}
				</BtnSecondary>
				{state === "saved" && (
					<span className="inline-flex items-center gap-1.5 text-[13px] text-[var(--cds-success-text)]">
						<CheckIcon className="size-4" /> Password updated
					</span>
				)}
			</div>
		</Section>
	);
}

function ApiKeysSection() {
	const [keys, setKeys] = useState<APIKey[] | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [label, setLabel] = useState("");
	const [busy, setBusy] = useState(false);
	const [created, setCreated] = useState<CreatedAPIKey | null>(null);
	const [copied, setCopied] = useState(false);

	useEffect(() => {
		listKeys()
			.then(setKeys)
			.catch((e) => setError((e as Error).message));
	}, []);

	const create = async () => {
		if (!label.trim()) return;
		setBusy(true);
		setError(null);
		try {
			const key = await createKey(label.trim());
			setCreated(key);
			setLabel("");
			setKeys((prev) => [key, ...(prev ?? [])]);
		} catch (e) {
			setError((e as Error).message);
		} finally {
			setBusy(false);
		}
	};

	const revoke = async (k: APIKey) => {
		if (
			!window.confirm(
				`Revoke "${k.name}"? Integrations using it start getting 401s immediately.`,
			)
		)
			return;
		try {
			await revokeKey(k.id);
			setKeys((prev) => (prev ?? []).filter((x) => x.id !== k.id));
			if (created?.id === k.id) setCreated(null);
		} catch (e) {
			setError((e as Error).message);
		}
	};

	const copyRaw = async () => {
		if (!created) return;
		try {
			await navigator.clipboard.writeText(created.raw_key);
			setCopied(true);
			setTimeout(() => setCopied(false), 1500);
		} catch {
			/* clipboard unavailable */
		}
	};

	return (
		<Section
			id="api-keys"
			title="API keys"
			desc="One key per integration. We only show the raw key once at creation — store it somewhere safe."
		>
			{created && (
				<Notification
					kind="info"
					title="New key — copy it now"
					className="mb-6"
				>
					<p>This is the only time you&rsquo;ll see the full secret.</p>
					<div className="mt-2 flex items-stretch gap-px">
						<code className="flex-1 truncate border border-[var(--cds-border)] bg-[var(--cds-bg)] px-3 py-2 font-mono text-[12px]">
							{created.raw_key}
						</code>
						<button
							type="button"
							onClick={copyRaw}
							className="flex items-center gap-2 bg-[#0f62fe] px-3 text-white text-xs transition-colors hover:bg-[#0353e9]"
						>
							{copied ? (
								<CheckIcon className="size-3.5" />
							) : (
								<CopyIcon className="size-3.5" />
							)}
							{copied ? "Copied" : "Copy"}
						</button>
					</div>
				</Notification>
			)}

			{error && (
				<Notification kind="error" title="API keys" className="mb-6">
					{error}
				</Notification>
			)}

			<div className="flex items-end gap-3">
				<TextField
					label="Key label"
					placeholder="e.g. Claude Desktop on laptop"
					value={label}
					onChange={(e) => setLabel(e.target.value)}
					onKeyDown={(e) => {
						if (e.key === "Enter") create();
					}}
					className="flex-1"
				/>
				<BtnPrimary
					size="md"
					arrow={false}
					disabled={busy || !label.trim()}
					onClick={create}
				>
					{busy ? "Creating…" : "Create key"}
				</BtnPrimary>
			</div>

			{keys === null ? (
				<p className="mt-6 text-[var(--cds-text-2)] text-sm">Loading keys…</p>
			) : keys.length === 0 ? (
				<p className="mt-6 text-[var(--cds-text-2)] text-sm">
					No API keys yet — create one above to use the corpus from Claude
					Desktop or your own integration.
				</p>
			) : (
				<ul className="mt-6 divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]">
					{keys.map((k) => (
						<li
							key={k.id}
							className="flex items-center gap-4 bg-[var(--cds-layer)] px-4 py-3"
						>
							<KeyRoundIcon
								className="size-4 shrink-0 text-[var(--cds-text-2)]"
								strokeWidth={1.5}
							/>
							<div className="min-w-0 flex-1">
								<p className="flex flex-wrap items-baseline gap-x-3 text-sm">
									<span className="font-medium">{k.name}</span>
									<span className="font-mono text-[var(--cds-helper)] text-[11px]">
										{k.prefix}…
									</span>
								</p>
								<p className="text-[var(--cds-helper)] text-xs">
									Created {fmtDateTime(k.created_at)} · Last used{" "}
									{k.last_used_at ? fmtDateTime(k.last_used_at) : "never"}
								</p>
							</div>
							<button
								type="button"
								aria-label={`Revoke ${k.name}`}
								onClick={() => revoke(k)}
								className="flex size-9 items-center justify-center text-[var(--cds-danger-text)] transition-colors hover:bg-[#da1e28]/10"
							>
								<Trash2Icon className="size-4" />
							</button>
						</li>
					))}
				</ul>
			)}
			<p className="mt-2 text-[var(--cds-helper)] text-xs">
				Revoked keys start getting 401s immediately. This cannot be undone.
			</p>
		</Section>
	);
}

function McpSection() {
	const [host, setHost] = useState<string | null>(null);
	const [copied, setCopied] = useState(false);

	useEffect(() => {
		fetchPublicConfig()
			.then((c) => setHost(c.mcp_host))
			.catch(() => setHost(null));
	}, []);

	const mcpHost = host || "https://corpus.nick.law/mcp";
	const snippet = `{
  "mcpServers": {
    "iowa-legal-corpus": {
      "command": "npx",
      "args": ["mcp-remote", "${mcpHost}",
               "--header", "X-API-Key: YOUR_RAW_KEY"]
    }
  }
}`;

	const copy = async () => {
		try {
			await navigator.clipboard.writeText(snippet);
			setCopied(true);
			setTimeout(() => setCopied(false), 1500);
		} catch {
			/* clipboard unavailable */
		}
	};

	return (
		<Section
			id="mcp"
			title="MCP config"
			desc="Drop this into Claude Desktop or Cursor to give your AI tools live access to the Iowa Legal Corpus via your API key."
		>
			<div className="flex items-end gap-3">
				<TextField
					label="MCP host"
					value={mcpHost}
					readOnly
					helper="Pinned to the production MCP endpoint."
					className="flex-1"
				/>
				<BtnSecondary size="md" className="mb-6" onClick={copy}>
					{copied ? (
						<CheckIcon className="size-4" />
					) : (
						<CopyIcon className="size-4" />
					)}
					{copied ? "Copied" : "Copy snippet"}
				</BtnSecondary>
			</div>
			<pre className="mt-2 overflow-x-auto border border-[var(--cds-border)] bg-[var(--cds-layer)] p-4 font-mono text-[12px] leading-relaxed">
				{snippet}
			</pre>
			<p className="mt-2 text-[var(--cds-helper)] text-xs">
				Replace YOUR_RAW_KEY with a key from the section above, then add this to
				claude_desktop_config.json. mcp-remote bridges stdio clients to the
				hosted endpoint.
			</p>
		</Section>
	);
}
