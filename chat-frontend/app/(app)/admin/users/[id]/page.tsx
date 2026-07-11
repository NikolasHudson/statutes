"use client";

// Admin · User detail — manage one account over /api/admin/users/{id}.
// Left: account controls (tier, monthly budget override, deactivate/staff
// toggles behind an inline confirm) + API keys with admin revoke. Right:
// usage snapshot, profile, and the recent security-event trail. The server
// re-checks every guardrail (staffness, superuser fence, self-lockout) on
// each write; can_edit/can_edit_staff_flag here only decide what to render.

import { ArrowLeftIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
	BtnDanger,
	BtnGhost,
	BtnSecondary,
	Eyebrow,
	KVList,
	Notification,
	Panel,
	SelectField,
	Tag,
	type TagKind,
	TextField,
} from "@/components/carbon/primitives";
import { AccountError } from "@/lib/iowa-account";
import {
	type AdminAuditEvent,
	type AdminUserDetail,
	type AdminUserPatch,
	getAdminUser,
	patchAdminUser,
	revokeAdminUserKey,
	type UsageTier,
} from "@/lib/iowa-admin";
import { cn } from "@/lib/utils";
import { TIER_TAGS } from "../tags";

const fmtMoney = (n: number) => `$${n.toFixed(2)}`;

function fmtTok(n: number): string {
	if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
	if (n >= 1e3) return `${Math.round(n / 1e3)}K`;
	return String(Math.round(n));
}

// ISO datetime → "Jul 10, 2026, 14:03" in the viewer's locale.
function fmtWhen(iso: string | null): string {
	if (!iso) return "—";
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return iso;
	return d.toLocaleString("en-US", {
		month: "short",
		day: "numeric",
		year: "numeric",
		hour: "2-digit",
		minute: "2-digit",
		hour12: false,
	});
}

const TIER_OPTIONS = [
	{ value: "free", label: "Trial" },
	{ value: "solo", label: "Solo" },
	{ value: "firm", label: "Firm" },
	{ value: "custom", label: "Custom" },
];

const EVENT_LABELS: Record<string, string> = {
	login_success: "Login",
	login_failure: "Failed login",
	login_locked_out: "Login blocked (lockout)",
	logout: "Logout",
	register: "Registered",
	register_blocked: "Registration blocked",
	password_change: "Password changed",
	profile_change: "Profile changed",
	settings_change: "Settings changed",
	tos_accepted: "Accepted terms",
	onboarding_completed: "Completed onboarding",
	api_key_create: "API key created",
	api_key_revoke: "API key revoked",
	admin_user_change: "Account changed by admin",
};

const eventLabel = (t: string) =>
	EVENT_LABELS[t] ?? t.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

const OUTCOME_TAGS: Record<
	AdminAuditEvent["outcome"],
	{ label: string; kind: TagKind }
> = {
	success: { label: "OK", kind: "green" },
	failure: { label: "Failed", kind: "red" },
	blocked: { label: "Blocked", kind: "yellow" },
};

export default function AdminUserDetailPage() {
	const params = useParams<{ id: string }>();
	const userId = Number(params.id);

	const [detail, setDetail] = useState<AdminUserDetail | null>(null);
	const [error, setError] = useState<Error | null>(null);
	// Save errors surface in a banner without dropping the loaded page.
	const [saveError, setSaveError] = useState<string | null>(null);
	const [saving, setSaving] = useState(false);

	const load = useCallback(() => {
		getAdminUser(userId)
			.then((d) => {
				setDetail(d);
				setError(null);
			})
			.catch((e) => setError(e as Error));
	}, [userId]);

	useEffect(() => {
		if (Number.isFinite(userId)) load();
	}, [userId, load]);

	const save = useCallback(
		async (patch: AdminUserPatch) => {
			setSaving(true);
			setSaveError(null);
			try {
				setDetail(await patchAdminUser(userId, patch));
			} catch (e) {
				setSaveError(
					e instanceof AccountError ? e.detail : "Could not save changes.",
				);
			} finally {
				setSaving(false);
			}
		},
		[userId],
	);

	const httpStatus = error instanceof AccountError ? error.status : null;

	if (httpStatus === 401) {
		return (
			<Wrap>
				<Notification kind="error" title="Staff only" className="max-w-xl">
					You need an active staff session to view this page.
				</Notification>
			</Wrap>
		);
	}
	if (httpStatus === 404) {
		return (
			<Wrap>
				<Notification kind="error" title="No such user" className="max-w-xl">
					That account doesn&rsquo;t exist.{" "}
					<Link href="/admin/users" className="underline">
						Back to users
					</Link>
					.
				</Notification>
			</Wrap>
		);
	}
	if (error && !detail) {
		return (
			<Wrap>
				<Notification
					kind="error"
					title="Couldn't load user"
					className="max-w-xl"
				>
					{error.message}
				</Notification>
			</Wrap>
		);
	}
	if (!detail) {
		return (
			<Wrap>
				<p className="text-[var(--cds-text-2)] text-sm">Loading user…</p>
			</Wrap>
		);
	}

	const u = detail.user;
	const tierTag = TIER_TAGS[u.tier] ?? {
		label: u.tier,
		kind: "gray" as TagKind,
	};

	return (
		<Wrap>
			<Link
				href="/admin/users"
				className="mb-6 inline-flex items-center gap-2 text-[var(--cds-link)] text-sm hover:underline"
			>
				<ArrowLeftIcon className="size-4" strokeWidth={1.5} />
				All users
			</Link>
			<header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
				<div>
					<Eyebrow>Admin · User management</Eyebrow>
					<h1 className="mt-4 break-all font-light text-3xl">{u.email}</h1>
					<div className="mt-3 flex flex-wrap items-center gap-2">
						{u.name && (
							<span className="mr-2 text-[15px] text-[var(--cds-text-2)]">
								{u.name}
							</span>
						)}
						<Tag kind={tierTag.kind}>{tierTag.label}</Tag>
						{u.is_superuser ? (
							<Tag kind="outline">Superuser</Tag>
						) : u.is_staff ? (
							<Tag kind="outline">Staff</Tag>
						) : null}
						{u.is_active ? (
							<Tag kind="green">Active</Tag>
						) : (
							<Tag kind="red">Deactivated</Tag>
						)}
					</div>
				</div>
			</header>

			{saveError && (
				<Notification kind="error" title="Couldn't save" className="mt-6">
					{saveError}
				</Notification>
			)}
			{!detail.can_edit && (
				<Notification kind="info" title="Read only" className="mt-6 max-w-xl">
					Only a superuser can modify a staff account.
				</Notification>
			)}

			<div
				className={cn(
					"mt-8 grid gap-6 xl:grid-cols-[3fr_2fr]",
					saving && "pointer-events-none opacity-60",
				)}
			>
				<div className="flex flex-col gap-6">
					<AccountControls detail={detail} onSave={save} />
					<ApiKeysPanel detail={detail} userId={userId} onChanged={load} />
					<EventsPanel events={detail.events} />
				</div>
				<div className="flex flex-col gap-6">
					<Panel title="Usage">
						<KVList
							rows={[
								["Spend this month", fmtMoney(detail.usage.month_cost_usd)],
								[
									"Spend — last 30 days",
									fmtMoney(detail.usage.days30_cost_usd),
								],
								["Tokens — last 30 days", fmtTok(detail.usage.days30_tokens)],
								["Last LLM activity", fmtWhen(detail.usage.last_llm_activity)],
								[
									"Budget used",
									u.budget_used_pct === null
										? "exempt"
										: `${Math.round(u.budget_used_pct)}% of ${fmtMoney(u.budget_usd ?? 0)}`,
								],
							]}
						/>
						<div className="border-[var(--cds-border)] border-t px-4 py-2.5">
							<Link
								href="/admin/usage"
								className="text-[var(--cds-link)] text-xs hover:underline"
							>
								Open the usage dashboard →
							</Link>
						</div>
					</Panel>
					<Panel title="Account">
						<KVList
							rows={[
								["Joined", fmtWhen(u.date_joined)],
								["Last login", fmtWhen(u.last_login)],
								[
									"Onboarding",
									u.onboarding_completed ? "completed" : "not completed",
								],
								[
									"Terms accepted",
									detail.profile.tos_version
										? `v${detail.profile.tos_version} · ${fmtWhen(detail.profile.tos_accepted_at)}`
										: "—",
								],
							]}
						/>
					</Panel>
					<Panel title="Profile">
						<KVList
							rows={[
								["Organization", detail.profile.organization || "—"],
								["Role", detail.profile.role || "—"],
								["Bar number", detail.profile.bar_number || "—"],
								["Jurisdiction", detail.profile.primary_jurisdiction || "—"],
								["Phone", detail.profile.phone || "—"],
								[
									"Location",
									[detail.profile.city, detail.profile.region]
										.filter(Boolean)
										.join(", ") || "—",
								],
								["Timezone", detail.profile.timezone || "—"],
							]}
						/>
					</Panel>
				</div>
			</div>
		</Wrap>
	);
}

function Wrap({ children }: { children: React.ReactNode }) {
	return (
		<div className="mx-auto w-full max-w-[1100px] px-5 py-10 sm:px-8">
			{children}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Account controls — tier + budget save together; the dangerous flags
// (deactivate, staff) each sit behind an inline confirm.
// ---------------------------------------------------------------------------

function AccountControls({
	detail,
	onSave,
}: {
	detail: AdminUserDetail;
	onSave: (patch: AdminUserPatch) => Promise<void>;
}) {
	const u = detail.user;
	const [tier, setTier] = useState<UsageTier>(u.tier);
	const [budget, setBudget] = useState(
		detail.monthly_budget_override_usd === null
			? ""
			: String(detail.monthly_budget_override_usd),
	);
	const [budgetInvalid, setBudgetInvalid] = useState(false);

	// Re-sync the form when a save (or admin toggle) returns fresh state.
	useEffect(() => {
		setTier(u.tier);
		setBudget(
			detail.monthly_budget_override_usd === null
				? ""
				: String(detail.monthly_budget_override_usd),
		);
		setBudgetInvalid(false);
	}, [u.tier, detail.monthly_budget_override_usd]);

	const parsedBudget = budget.trim() === "" ? null : Number(budget);
	const dirty =
		tier !== u.tier || parsedBudget !== detail.monthly_budget_override_usd;

	const submit = () => {
		if (
			parsedBudget !== null &&
			(!Number.isFinite(parsedBudget) || parsedBudget < 0)
		) {
			setBudgetInvalid(true);
			return;
		}
		setBudgetInvalid(false);
		void onSave({ tier, monthly_budget_usd: parsedBudget });
	};

	return (
		<Panel title="Account controls">
			<div className="flex flex-col gap-5 p-4">
				<div className="flex flex-wrap items-end gap-4">
					<SelectField
						label="Tier"
						value={tier}
						disabled={!detail.can_edit}
						onChange={(e) => setTier(e.target.value as UsageTier)}
						options={TIER_OPTIONS}
						className="w-40"
					/>
					<TextField
						label="Monthly budget override (USD)"
						type="number"
						min={0}
						step="0.01"
						placeholder="tier default"
						value={budget}
						disabled={!detail.can_edit}
						onChange={(e) => setBudget(e.target.value)}
						className="w-56"
					/>
					<BtnSecondary
						size="md"
						disabled={!detail.can_edit || !dirty}
						onClick={submit}
					>
						Save changes
					</BtnSecondary>
				</div>
				{budgetInvalid && (
					<p className="text-[var(--cds-danger-text,#da1e28)] text-xs">
						Budget must be a non-negative number (leave blank for the tier
						default).
					</p>
				)}
				<p className="text-[var(--cds-helper)] text-xs">
					The budget override replaces the tier&rsquo;s monthly LLM spend cap
					for this user only. Blank = tier default. Staff accounts are exempt
					from budgets.
				</p>

				<div className="flex flex-col divide-y divide-[var(--cds-border)] border-[var(--cds-border)] border-t pt-1">
					<DangerRow
						label={u.is_active ? "Deactivate account" : "Reactivate account"}
						detail={
							u.is_active
								? "Ends their session and disables all API keys and MCP tokens immediately."
								: "Restores sign-in and re-enables their unrevoked API keys."
						}
						confirmLabel={u.is_active ? "Deactivate" : "Reactivate"}
						danger={u.is_active}
						disabled={!detail.can_edit}
						onConfirm={() => onSave({ is_active: !u.is_active })}
					/>
					{detail.can_edit_staff_flag && (
						<DangerRow
							label={u.is_staff ? "Remove staff access" : "Grant staff access"}
							detail={
								u.is_staff
									? "Removes access to the admin dashboards and user management."
									: "Grants access to the admin dashboards, user management, and budget exemption."
							}
							confirmLabel={u.is_staff ? "Remove staff" : "Grant staff"}
							danger={!u.is_staff}
							disabled={!detail.can_edit}
							onConfirm={() => onSave({ is_staff: !u.is_staff })}
						/>
					)}
				</div>
			</div>
		</Panel>
	);
}

// A labeled action that swaps into an inline "Confirm / Cancel" pair instead
// of firing immediately — Carbon-ish, and no window.confirm.
function DangerRow({
	label,
	detail,
	confirmLabel,
	danger,
	disabled,
	onConfirm,
}: {
	label: string;
	detail: string;
	confirmLabel: string;
	danger: boolean;
	disabled?: boolean;
	onConfirm: () => void | Promise<void>;
}) {
	const [arming, setArming] = useState(false);
	return (
		<div className="flex flex-wrap items-center justify-between gap-3 py-3">
			<div className="min-w-0 max-w-md">
				<p className="text-sm">{label}</p>
				<p className="mt-0.5 text-[var(--cds-helper)] text-xs">{detail}</p>
			</div>
			{arming ? (
				<span className="flex items-center gap-2">
					<span className="text-[var(--cds-text-2)] text-xs">
						Are you sure?
					</span>
					{danger ? (
						<BtnDanger
							size="md"
							onClick={() => {
								setArming(false);
								void onConfirm();
							}}
						>
							{confirmLabel}
						</BtnDanger>
					) : (
						<BtnSecondary
							size="md"
							onClick={() => {
								setArming(false);
								void onConfirm();
							}}
						>
							{confirmLabel}
						</BtnSecondary>
					)}
					<BtnGhost size="md" onClick={() => setArming(false)}>
						Cancel
					</BtnGhost>
				</span>
			) : (
				<BtnGhost size="md" disabled={disabled} onClick={() => setArming(true)}>
					{label}
				</BtnGhost>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// API keys — active keys with an admin revoke (incident-response lever)
// ---------------------------------------------------------------------------

function ApiKeysPanel({
	detail,
	userId,
	onChanged,
}: {
	detail: AdminUserDetail;
	userId: number;
	onChanged: () => void;
}) {
	const [error, setError] = useState<string | null>(null);
	const [busyId, setBusyId] = useState<number | null>(null);

	const revoke = async (keyId: number) => {
		setBusyId(keyId);
		setError(null);
		try {
			await revokeAdminUserKey(userId, keyId);
			onChanged();
		} catch (e) {
			setError(e instanceof AccountError ? e.detail : "Could not revoke key.");
		} finally {
			setBusyId(null);
		}
	};

	return (
		<Panel title={`API keys — ${detail.api_keys.length} active`}>
			{error && (
				<div className="p-4 pb-0">
					<Notification kind="error" title="Couldn't revoke">
						{error}
					</Notification>
				</div>
			)}
			{detail.api_keys.length === 0 ? (
				<p className="p-4 text-[var(--cds-text-2)] text-sm">
					No active API keys.
				</p>
			) : (
				<div className="divide-y divide-[var(--cds-border)]">
					{detail.api_keys.map((k) => (
						<div
							key={k.id}
							className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
						>
							<div className="min-w-0">
								<p className="text-sm">
									{k.name}{" "}
									<code className="ml-1 font-mono text-[var(--cds-helper)] text-xs">
										{k.prefix}…
									</code>
								</p>
								<p className="mt-0.5 text-[var(--cds-helper)] text-xs">
									created {fmtWhen(k.created_at)} · last used{" "}
									{k.last_used_at ? fmtWhen(k.last_used_at) : "never"}
								</p>
							</div>
							<KeyRevoke
								disabled={!detail.can_edit || busyId !== null}
								busy={busyId === k.id}
								onConfirm={() => revoke(k.id)}
							/>
						</div>
					))}
				</div>
			)}
		</Panel>
	);
}

function KeyRevoke({
	disabled,
	busy,
	onConfirm,
}: {
	disabled: boolean;
	busy: boolean;
	onConfirm: () => void;
}) {
	const [arming, setArming] = useState(false);
	if (busy)
		return <span className="text-[var(--cds-helper)] text-xs">Revoking…</span>;
	if (arming)
		return (
			<span className="flex items-center gap-2">
				<BtnDanger
					size="md"
					onClick={() => {
						setArming(false);
						onConfirm();
					}}
				>
					Revoke key
				</BtnDanger>
				<BtnGhost size="md" onClick={() => setArming(false)}>
					Cancel
				</BtnGhost>
			</span>
		);
	return (
		<BtnGhost size="md" disabled={disabled} onClick={() => setArming(true)}>
			Revoke
		</BtnGhost>
	);
}

// ---------------------------------------------------------------------------
// Security events — recent audit trail for this account
// ---------------------------------------------------------------------------

function EventsPanel({ events }: { events: AdminAuditEvent[] }) {
	return (
		<Panel title={`Security events — last ${events.length}`}>
			{events.length === 0 ? (
				<p className="p-4 text-[var(--cds-text-2)] text-sm">
					No recorded events for this account.
				</p>
			) : (
				<div className="divide-y divide-[var(--cds-border)]">
					{events.map((e) => {
						const outcome = OUTCOME_TAGS[e.outcome] ?? OUTCOME_TAGS.success;
						return (
							<div
								key={e.id}
								className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-2.5"
							>
								<span className="flex min-w-0 items-center gap-2">
									<Tag kind={outcome.kind}>{outcome.label}</Tag>
									<span className="text-sm">{eventLabel(e.event_type)}</span>
								</span>
								<span className="font-mono text-[var(--cds-helper)] text-xs tabular-nums">
									{e.source_ip ?? ""} · {fmtWhen(e.created_at)}
								</span>
							</div>
						);
					})}
				</div>
			)}
		</Panel>
	);
}
