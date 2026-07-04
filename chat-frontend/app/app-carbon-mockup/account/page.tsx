"use client";

// Carbon mockup of the account settings page (live: /account). Same section
// inventory as the live page — Profile, Address, Practice, Preferences,
// Password, API keys, MCP config — restated in Carbon form patterns: fluid
// inputs, hairline section rules, an "On this page" anchor rail, per-section
// save rows. Static data; nothing calls the API.

import {
	CheckIcon,
	CopyIcon,
	KeyRoundIcon,
	MonitorIcon,
	MoonIcon,
	SunIcon,
	Trash2Icon,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import {
	AppShell,
	BtnPrimary,
	BtnSecondary,
	Eyebrow,
	Notification,
	SelectField,
	TextField,
	ToggleRow,
	useTheme,
} from "../carbon";

// Shared option lists (mirrors lib/settings-options.ts).
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

const SECTIONS = [
	{ id: "profile", label: "Profile" },
	{ id: "address", label: "Address" },
	{ id: "practice", label: "Practice" },
	{ id: "preferences", label: "Preferences" },
	{ id: "password", label: "Password" },
	{ id: "api-keys", label: "API keys" },
	{ id: "mcp", label: "MCP config" },
];

const API_KEYS = [
	{
		name: "Claude Desktop on laptop",
		prefix: "hud_k1_9f3a…",
		meta: "Created Mar 14, 2026 · Last used today, 9:41 AM",
	},
	{
		name: "Cursor — office workstation",
		prefix: "hud_k1_27c8…",
		meta: "Created May 2, 2026 · Last used Jun 28, 2026",
	},
];

const MCP_SNIPPET = `{
  "mcpServers": {
    "iowa-legal-corpus": {
      "command": "npx",
      "args": ["mcp-remote", "https://corpus.nick.law/mcp",
               "--header", "X-API-Key: YOUR_RAW_KEY"]
    }
  }
}`;

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AccountCarbonMockup() {
	return (
		<AppShell active="/app-carbon-mockup/account">
			<div className="px-5 py-10 sm:px-8 lg:py-14">
				<Eyebrow>Account — nick@nickhudson.me</Eyebrow>
				<h1 className="mt-4 font-light text-3xl sm:text-4xl">Settings</h1>
				<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
					Profile, research defaults, and integrations. Each section saves on
					its own.
				</p>

				<div className="mt-10 grid gap-12 lg:grid-cols-[11rem_minmax(0,42rem)]">
					<OnThisPage />
					<div className="min-w-0 space-y-14">
						<ProfileSection />
						<AddressSection />
						<PracticeSection />
						<PreferencesSection />
						<PasswordSection />
						<ApiKeysSection />
						<McpSection />
					</div>
				</div>
			</div>
		</AppShell>
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
// Section scaffolding
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

function SaveRow({ note }: { note?: string }) {
	return (
		<div className="mt-6 flex items-center gap-4">
			<BtnPrimary size="md" arrow={false}>
				Save changes
			</BtnPrimary>
			{note && (
				<span className="font-mono text-[11px] text-[var(--cds-helper)]">
					{note}
				</span>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------

function ProfileSection() {
	return (
		<Section
			id="profile"
			title="Profile"
			desc="How you appear in the app and where we'll reach you."
		>
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField label="First name" defaultValue="Nick" />
				<TextField label="Last name" defaultValue="Hudson" />
				<TextField
					label="Login email"
					defaultValue="nick@nickhudson.me"
					helper="Used to sign in."
				/>
				<TextField
					label="Phone"
					placeholder="(555) 123-4567"
					helper="Optional — for account security & support."
				/>
			</div>
			<SaveRow note="Tier · beta" />
		</Section>
	);
}

function AddressSection() {
	return (
		<Section
			id="address"
			title="Address"
			desc="Your mailing address. All optional."
		>
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
			<SaveRow />
		</Section>
	);
}

function PracticeSection() {
	return (
		<Section
			id="practice"
			title="Practice"
			desc="Used to tailor results and pre-fill search filters."
		>
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField label="Organization" placeholder="e.g. Hudson Law LLC" />
				<SelectField label="Role" options={ROLES} />
				<TextField label="Bar number" placeholder="e.g. AT0001234" />
				<SelectField label="Primary jurisdiction" options={JURISDICTIONS} />
				<SelectField
					label="Time zone"
					options={TIMEZONES}
					className="sm:col-span-2"
				/>
			</div>
			<SaveRow />
		</Section>
	);
}

function PreferencesSection() {
	const { theme, setTheme } = useTheme();
	const [verify, setVerify] = useState(true);
	const [digest, setDigest] = useState(true);
	const [news, setNews] = useState(false);

	const themeChoices = [
		{
			id: "light",
			label: "Light",
			icon: SunIcon,
			apply: () => setTheme("white"),
		},
		{
			id: "dark",
			label: "Dark",
			icon: MoonIcon,
			apply: () => setTheme("g100"),
		},
		{
			id: "system",
			label: "System",
			icon: MonitorIcon,
			apply: () => setTheme("white"),
		},
	];
	const activeId = theme === "g100" ? "dark" : "light";

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
					const active = t.id === activeId;
					return (
						<button
							key={t.id}
							type="button"
							onClick={t.apply}
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
				<SelectField label="Default search scope" options={SCOPES} />
				<SelectField label="Citation style" options={CITATION_STYLES} />
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
			<SaveRow />
		</Section>
	);
}

function PasswordSection() {
	return (
		<Section
			id="password"
			title="Password"
			desc="Use at least 8 characters. We don't enforce more — pick something memorable."
		>
			<div className="grid gap-5 sm:grid-cols-2">
				<TextField label="Current password" type="password" />
				<TextField label="New password" type="password" />
			</div>
			<div className="mt-6">
				<BtnSecondary size="md">Update password</BtnSecondary>
			</div>
		</Section>
	);
}

function ApiKeysSection() {
	const [copied, setCopied] = useState(false);
	return (
		<Section
			id="api-keys"
			title="API keys"
			desc="One key per integration. We only show the raw key once at creation — store it somewhere safe."
		>
			<Notification kind="info" title="New key — copy it now" className="mb-6">
				<p>This is the only time you&rsquo;ll see the full secret.</p>
				<div className="mt-2 flex items-stretch gap-px">
					<code className="flex-1 truncate border border-[var(--cds-border)] bg-[var(--cds-bg)] px-3 py-2 font-mono text-[12px]">
						hud_k1_9f3ab77e21d84c05a6d21f0c4e8b9d12
					</code>
					<button
						type="button"
						onClick={() => {
							setCopied(true);
							setTimeout(() => setCopied(false), 1500);
						}}
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

			<div className="flex items-end gap-3">
				<TextField
					label="Key label"
					placeholder="e.g. Claude Desktop on laptop"
					className="flex-1"
				/>
				<BtnPrimary size="md" arrow={false}>
					Create key
				</BtnPrimary>
			</div>

			<ul className="mt-6 divide-y divide-[var(--cds-border)] border border-[var(--cds-border)]">
				{API_KEYS.map((k) => (
					<li
						key={k.name}
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
									{k.prefix}
								</span>
							</p>
							<p className="text-[var(--cds-helper)] text-xs">{k.meta}</p>
						</div>
						<button
							type="button"
							aria-label={`Revoke ${k.name}`}
							className="flex size-9 items-center justify-center text-[var(--cds-danger-text)] transition-colors hover:bg-[#da1e28]/10"
						>
							<Trash2Icon className="size-4" />
						</button>
					</li>
				))}
			</ul>
			<p className="mt-2 text-[var(--cds-helper)] text-xs">
				Revoked keys start getting 401s immediately. This cannot be undone.
			</p>
		</Section>
	);
}

function McpSection() {
	return (
		<Section
			id="mcp"
			title="MCP config"
			desc="Drop this into Claude Desktop or Cursor to give your AI tools live access to the Iowa Legal Corpus via your API key."
		>
			<div className="flex items-end gap-3">
				<TextField
					label="MCP host"
					defaultValue="https://corpus.nick.law/mcp"
					helper="Pinned to the production MCP endpoint."
					className="flex-1"
				/>
				<BtnSecondary size="md" className="mb-6">
					<CopyIcon className="size-4" />
					Copy snippet
				</BtnSecondary>
			</div>
			<pre className="mt-2 overflow-x-auto border border-[var(--cds-border)] bg-[var(--cds-layer)] p-4 font-mono text-[12px] leading-relaxed">
				{MCP_SNIPPET}
			</pre>
			<p className="mt-2 text-[var(--cds-helper)] text-xs">
				Replace YOUR_RAW_KEY with a key from the section above, then add this to
				claude_desktop_config.json. mcp-remote bridges stdio clients to the
				hosted endpoint.
			</p>
		</Section>
	);
}
