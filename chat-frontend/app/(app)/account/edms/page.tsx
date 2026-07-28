"use client";

// Hudson EDMSpro settings — a sibling page under the account umbrella, not a
// section on /account.
//
// The rule (Nick, 2026-07-28, and it generalizes to every future product):
// /account is already seven stacked sections and must not grow an eighth every
// time a product ships. Products get their own page, the way /account/billing
// already does.
//
// User-scoped, not org-scoped: everything here is one attorney's own preference,
// not a firm-wide setting.
//
// One thing on this page is load-bearing beyond the UI. Turning contribution
// sharing ON is only possible from a session-authenticated request — the server
// refuses it from the extension's OAuth token or from an API key — which makes
// the consent screen below the *only* door into sharing a client's filings.
// Its copy is therefore part of the control, not decoration.

import { CheckIcon, ExternalLinkIcon, ShieldIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
	BtnSecondary,
	Eyebrow,
	Notification,
	Panel,
	Tag,
	TextField,
} from "@/components/carbon/primitives";
import {
	OnThisPage,
	SaveRow,
	Section,
	useSaveState,
} from "@/components/settings/section";
import {
	EDMS_EXTENSION_URL,
	EDMS_PRODUCT_NAME,
	EDMS_PRODUCT_SHORT_NAME,
} from "@/lib/brand";
import { AccountError } from "@/lib/iowa-account";
import {
	type EdmsSettings,
	getEdmsSettings,
	getSafetyList,
	previewTemplate,
	type SafetyList,
	updateEdmsSettings,
} from "@/lib/iowa-edms";

const SECTIONS = [
	{ id: "naming", label: "File naming" },
	{ id: "contribute", label: "Contribution library" },
	{ id: "safety", label: "Safety filter" },
	{ id: "extension", label: "Get the extension" },
] as const;

export default function EdmsSettingsPage() {
	const [settings, setSettings] = useState<EdmsSettings | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [gated, setGated] = useState<402 | 403 | null>(null);

	useEffect(() => {
		getEdmsSettings()
			.then(setSettings)
			.catch((e) => {
				if (
					e instanceof AccountError &&
					(e.status === 402 || e.status === 403)
				) {
					setGated(e.status);
				} else {
					setError((e as Error).message);
				}
			});
	}, []);

	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<Eyebrow>Account — {EDMS_PRODUCT_SHORT_NAME}</Eyebrow>
			<h1 className="mt-4 font-light text-3xl sm:text-4xl">
				{EDMS_PRODUCT_NAME}
			</h1>
			<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
				Save filings from the Iowa Courts docket in one click, named the way you
				want them. Documents go from the court straight to your machine — they
				never pass through Hudson.
			</p>

			{gated ? (
				<NotOnYourPlan status={gated} />
			) : error ? (
				<Notification
					kind="error"
					title="Couldn't load EDMSpro settings"
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
					<OnThisPage sections={SECTIONS} />
					<div className="min-w-0 space-y-14">
						<NamingSection settings={settings} onChange={setSettings} />
						<ContributeSection settings={settings} onChange={setSettings} />
						<SafetySection />
						<ExtensionSection />
					</div>
				</div>
			)}
		</div>
	);
}

// The nav entry is gated on the plan's feature list, but that list can be stale
// (a downgrade mid-session), so the page states its own case rather than
// rendering an empty shell.
function NotOnYourPlan({ status }: { status: 402 | 403 }) {
	return (
		<div className="mt-10 max-w-xl">
			<Notification
				kind="info"
				title={
					status === 402
						? "An active plan is required"
						: `${EDMS_PRODUCT_NAME} isn't on your plan`
				}
			>
				<p>
					{status === 402
						? "Start your trial to use EDMSpro and the rest of Hudson."
						: "EDMSpro is included with the Solo and Firm plans."}
				</p>
				<Link
					href="/account/billing"
					className="mt-3 inline-flex items-center gap-2 text-[var(--cds-link)] text-sm hover:underline"
				>
					Go to billing <ExternalLinkIcon className="size-3.5" />
				</Link>
			</Notification>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Template field with clickable token chips + a live preview
// ---------------------------------------------------------------------------

function TemplateField({
	label,
	helper,
	value,
	tokens,
	kind,
	prefix,
	disabled,
	onChange,
}: {
	label: string;
	helper?: string;
	value: string;
	tokens: string[];
	kind: "folder" | "file";
	prefix?: string;
	disabled?: boolean;
	onChange: (v: string) => void;
}) {
	const ref = useRef<HTMLInputElement>(null);

	// Insert at the caret rather than appending: people build these templates by
	// clicking into the middle of one they already have.
	const insert = (token: string) => {
		const el = ref.current;
		if (!el) {
			onChange(value + token);
			return;
		}
		const start = el.selectionStart ?? value.length;
		const end = el.selectionEnd ?? value.length;
		const next = value.slice(0, start) + token + value.slice(end);
		onChange(next);
		requestAnimationFrame(() => {
			el.focus();
			el.setSelectionRange(start + token.length, start + token.length);
		});
	};

	const preview = previewTemplate(value, kind);

	return (
		<div>
			<TextField
				label={label}
				helper={helper}
				value={value}
				disabled={disabled}
				ref={ref}
				onChange={(e) => onChange(e.target.value)}
			/>
			<div className="mt-3 flex flex-wrap gap-1.5">
				{tokens.map((token) => (
					<button
						key={token}
						type="button"
						disabled={disabled}
						onClick={() => insert(token)}
						className="border border-[var(--cds-border-strong)] px-2 py-1 font-mono text-[11px] text-[var(--cds-text-2)] transition-colors hover:border-[#0f62fe] hover:text-[var(--cds-link)] disabled:cursor-not-allowed disabled:opacity-50"
					>
						{token}
					</button>
				))}
			</div>
			<p className="mt-3 break-all font-mono text-[11px] text-[var(--cds-helper)]">
				Example: {prefix ? `${prefix}/` : ""}
				{preview}
			</p>
		</div>
	);
}

// ---------------------------------------------------------------------------
// 1. File naming
// ---------------------------------------------------------------------------

function NamingSection({
	settings,
	onChange,
}: {
	settings: EdmsSettings;
	onChange: (s: EdmsSettings) => void;
}) {
	const [template, setTemplate] = useState(settings.naming_template);
	const { state, error, run } = useSaveState();

	return (
		<Section
			id="naming"
			title="File naming"
			desc="How each saved filing is named."
		>
			<TemplateField
				label="Filename pattern"
				helper="Missing values are dropped and the separators tidied up."
				value={template}
				tokens={settings.filename_tokens}
				kind="file"
				onChange={setTemplate}
			/>
			<SaveRow
				state={state}
				error={error}
				onSave={() =>
					run(async () => {
						onChange(await updateEdmsSettings({ naming_template: template }));
					})
				}
			/>
		</Section>
	);
}

// ---------------------------------------------------------------------------
// 2. Contribution library — the consent screen
// ---------------------------------------------------------------------------

function ContributeSection({
	settings,
	onChange,
}: {
	settings: EdmsSettings;
	onChange: (s: EdmsSettings) => void;
}) {
	const [acknowledged, setAcknowledged] = useState(false);
	const { state, error, run } = useSaveState();
	const on = settings.crowdsource_opt_in;

	const set = (value: boolean) =>
		run(async () => {
			onChange(await updateEdmsSettings({ crowdsource_opt_in: value }));
			setAcknowledged(false);
		});

	return (
		<Section
			id="contribute"
			title="Contribution library"
			desc="Optionally share the filings you save, to help build a library of Iowa motions and orders."
		>
			<div className="border border-[var(--cds-border)] border-l-[3px] border-l-[#0f62fe] bg-[var(--cds-layer)] px-4 py-4 text-sm">
				<p className="font-semibold">If you turn this on</p>
				<ul className="mt-2 list-disc space-y-1.5 pl-5 text-[var(--cds-text-2)] text-[13px] leading-relaxed">
					<li>
						A copy of each filing you save is also sent to Hudson and stored in
						a private bucket. Nothing else about your account changes.
					</li>
					<li>
						Nothing is published, shown to anyone, or used to answer research
						questions. The collection sits untouched until a redaction process
						and a contribution policy exist — both of which are still being
						built.
					</li>
					<li>
						Confidential case types are never shared, whatever this setting
						says: juvenile, CINA and adoption matters are refused by the server.
					</li>
					<li>
						<strong className="text-[var(--cds-text)]">
							Contributions are lasting.
						</strong>{" "}
						Turning this off later stops future filings from being shared, but
						filings you have already shared stay in the collection. To have
						those removed, delete your account or write to us and ask.
					</li>
				</ul>
				<p className="mt-3 text-[13px] text-[var(--cds-text-2)]">
					See the{" "}
					<Link
						href="/privacy"
						className="text-[var(--cds-link)] hover:underline"
					>
						privacy policy
					</Link>{" "}
					for how we handle what you send us.
				</p>
			</div>

			{state === "error" && error && (
				<Notification kind="error" title="Couldn't save" className="mt-6">
					{error}
				</Notification>
			)}

			{on ? (
				<div className="mt-6">
					<Tag kind="green">
						<CheckIcon className="size-3.5" /> Sharing is on
					</Tag>
					<p className="mt-4 max-w-lg text-[13px] text-[var(--cds-text-2)] leading-relaxed">
						Turning this off stops future filings from being shared. Filings you
						have already shared stay in the collection — removal is by account
						deletion or a written request.
					</p>
					<div className="mt-4">
						<BtnSecondary
							size="md"
							disabled={state === "busy"}
							onClick={() => set(false)}
						>
							{state === "busy" ? "Saving…" : "Stop sharing new filings"}
						</BtnSecondary>
					</div>
				</div>
			) : (
				<div className="mt-6">
					<label className="flex cursor-pointer items-start gap-3 text-sm">
						<input
							type="checkbox"
							checked={acknowledged}
							onChange={(e) => setAcknowledged(e.target.checked)}
							className="mt-0.5 size-4 shrink-0 accent-[#0f62fe]"
						/>
						<span className="text-[var(--cds-text-2)]">
							I have read the above, I have authority to share these documents,
							and I understand that what I share cannot be un-shared by turning
							this setting off.
						</span>
					</label>
					<SaveRow
						state={state}
						error={null}
						disabled={!acknowledged}
						label="Turn on sharing"
						onSave={() => set(true)}
						note="Off by default"
					/>
				</div>
			)}
		</Section>
	);
}

// ---------------------------------------------------------------------------
// 3. Safety filter
// ---------------------------------------------------------------------------

function SafetySection() {
	const [list, setList] = useState<SafetyList | null>(null);

	useEffect(() => {
		getSafetyList()
			.then(setList)
			.catch(() => setList(null));
	}, []);

	return (
		<Section
			id="safety"
			title="Safety filter"
			desc="Case types that are never shared, enforced on our side."
		>
			<div className="flex items-start gap-3">
				<ShieldIcon
					className="mt-0.5 size-5 shrink-0 text-[var(--cds-helper)]"
					strokeWidth={1.5}
				/>
				<div className="min-w-0">
					<div className="flex flex-wrap gap-2">
						{(list?.blocked ?? []).map((row) => (
							<Tag key={row.prefix} kind="outline">
								<span className="font-mono">{row.prefix}</span> · {row.label}
							</Tag>
						))}
					</div>
					<p className="mt-3 max-w-lg text-[13px] text-[var(--cds-text-2)] leading-relaxed">
						{list?.note ??
							"Filings in confidential case types are never shared, regardless of your contribution setting."}{" "}
						This is checked by the server on every contribution, so it holds
						even if the extension is out of date.
					</p>
				</div>
			</div>
		</Section>
	);
}

// ---------------------------------------------------------------------------
// 4. Get the extension
// ---------------------------------------------------------------------------

function ExtensionSection() {
	return (
		<Section
			id="extension"
			title="Get the extension"
			desc="EDMSpro works inside the Iowa Courts docket, in Chrome."
		>
			<Panel title="Browser extension">
				<div className="space-y-3 px-4 py-4 text-sm">
					<p className="text-[var(--cds-text-2)]">
						Install the extension, then sign in from its side panel — the same
						Hudson account you're using now. Save buttons appear on each docket
						row.
					</p>
					{EDMS_EXTENSION_URL ? (
						<a
							href={EDMS_EXTENSION_URL}
							target="_blank"
							rel="noreferrer"
							className="inline-flex items-center gap-2 text-[var(--cds-link)] hover:underline"
						>
							Open the Chrome Web Store listing{" "}
							<ExternalLinkIcon className="size-3.5" />
						</a>
					) : (
						<p className="text-[var(--cds-helper)] text-[13px]">
							The Chrome Web Store listing isn't published yet.
						</p>
					)}
				</div>
			</Panel>
		</Section>
	);
}
