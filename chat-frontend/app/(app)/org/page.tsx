"use client";

// Organization — the member console for the user's billing org
// (/api/org): who's in it, what they can do, who's been invited, and how many
// seats that adds up to. Seats are the Stripe quantity, so the seat counter
// here is also a bill preview: one member = one seat.
//
// Permission split (server-enforced; this only decides what renders):
//   owner  — everything, including changing another member's role
//   admin  — invite, revoke invites, remove members
//   member — read-only, plus leaving the org
// The server re-checks the role on every mutation and refuses to remove or
// demote the last owner.

import { MailIcon, UsersIcon } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/auth-gate";
import {
	BtnDanger,
	BtnGhost,
	BtnPrimary,
	BtnSecondary,
	Eyebrow,
	Notification,
	Panel,
	SelectField,
	Tag,
	TextField,
} from "@/components/carbon/primitives";
import { AccountError, fmtDate } from "@/lib/iowa-account";
import {
	canManageOrg,
	changeMemberRole,
	getOrg,
	inviteMember,
	type OrgConsole,
	type OrgRole,
	ROLE_OPTIONS,
	removeMember,
	renameOrg,
	revokeInvitation,
} from "@/lib/iowa-org";
import { ORG_STATUS_TAGS, ROLE_TAGS } from "@/lib/org-display";
import { cn } from "@/lib/utils";

export default function OrgPage() {
	const { user } = useAuth();
	const [org, setOrg] = useState<OrgConsole | null>(null);
	const [error, setError] = useState<Error | null>(null);
	// Mutation failures (403 wrong role, 409 duplicate invite, last-owner
	// refusals) surface in a banner without dropping the loaded console.
	const [actionError, setActionError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);

	const load = useCallback(() => {
		getOrg()
			.then((o) => {
				setOrg(o);
				setError(null);
			})
			.catch((e) => setError(e as Error));
	}, []);

	useEffect(load, [load]);

	// Every mutation is fire-and-refetch: the server owns seats, roles, and the
	// invariant that an org keeps at least one owner, so we re-read rather than
	// patch state locally.
	const run = useCallback(
		async (action: () => Promise<unknown>) => {
			setBusy(true);
			setActionError(null);
			try {
				await action();
				load();
				return true;
			} catch (e) {
				setActionError(
					e instanceof AccountError ? e.detail : "Something went wrong.",
				);
				return false;
			} finally {
				setBusy(false);
			}
		},
		[load],
	);

	const httpStatus = error instanceof AccountError ? error.status : null;

	if (httpStatus === 401) {
		return (
			<Wrap>
				<Notification kind="error" title="Signed out" className="max-w-xl">
					Sign in again to manage your organization.
				</Notification>
			</Wrap>
		);
	}
	if (error && !org) {
		return (
			<Wrap>
				<Notification
					kind="error"
					title="Couldn't load your organization"
					className="max-w-xl"
				>
					{error.message}
				</Notification>
			</Wrap>
		);
	}
	if (!org) {
		return (
			<Wrap>
				<p className="text-[var(--cds-text-2)] text-sm">
					Loading organization…
				</p>
			</Wrap>
		);
	}

	const canManage = canManageOrg(org.my_role);
	const isOwner = org.my_role === "owner";
	const statusTag = ORG_STATUS_TAGS[org.status] ?? ORG_STATUS_TAGS.active;
	const seatsPurchased = org.seats_purchased || org.seats_used;
	const overSeats =
		org.seats_purchased > 0 && org.seats_used > org.seats_purchased;

	return (
		<Wrap>
			<header>
				<Eyebrow>Account — Organization</Eyebrow>
				<h1 className="mt-4 font-light text-3xl sm:text-4xl">{org.name}</h1>
				<div className="mt-3 flex flex-wrap items-center gap-2">
					<Tag kind={statusTag.kind}>{statusTag.label}</Tag>
					{org.is_personal && <Tag kind="outline">Personal</Tag>}
					<Tag kind={ROLE_TAGS[org.my_role].kind}>
						You are {org.my_role === "admin" ? "an" : "a"}{" "}
						{ROLE_TAGS[org.my_role].label.toLowerCase()}
					</Tag>
				</div>
				<p className="mt-4 max-w-2xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
					Everyone here shares one plan and one bill. Members get the
					organization&rsquo;s plan for as long as they belong to it.
				</p>
			</header>

			{actionError && (
				<Notification kind="error" title="Couldn't do that" className="mt-8">
					{actionError}
				</Notification>
			)}

			{!canManage && (
				<Notification kind="info" title="Read only" className="mt-8 max-w-2xl">
					Only an owner or admin of {org.name} can invite or remove members.
				</Notification>
			)}

			{org.status === "past_due" && (
				<Notification
					kind="warning"
					title="This organization is past due"
					className="mt-8"
					action={
						canManage ? (
							<Link href="/account/billing">
								<BtnSecondary size="md">Fix billing</BtnSecondary>
							</Link>
						) : undefined
					}
				>
					A payment failed. Access drops to the free tier when the grace period
					ends.
				</Notification>
			)}

			<div
				className={cn(
					"mt-8 grid gap-6 lg:grid-cols-[3fr_2fr]",
					busy && "pointer-events-none opacity-60",
				)}
			>
				<div className="flex min-w-0 flex-col gap-6">
					<MembersPanel
						org={org}
						meId={user.id}
						canManage={canManage}
						isOwner={isOwner}
						onRoleChange={(id, role) => run(() => changeMemberRole(id, role))}
						onRemove={(id) => run(() => removeMember(id))}
					/>
					{canManage && (
						<InvitePanel
							org={org}
							onInvite={(email, role) => run(() => inviteMember(email, role))}
						/>
					)}
					<InvitationsPanel
						org={org}
						canManage={canManage}
						onRevoke={(id) => run(() => revokeInvitation(id))}
					/>
				</div>

				<div className="flex flex-col gap-6">
					<Panel title="Seats">
						<div className="px-4 py-4">
							<p className="flex items-baseline gap-2 font-light text-3xl tabular-nums">
								<UsersIcon
									className="size-5 self-center text-[var(--cds-helper)]"
									strokeWidth={1.5}
								/>
								{org.seats_used}
								<span className="text-[var(--cds-helper)] text-base">
									/ {seatsPurchased} seats
								</span>
							</p>
							<p className="mt-3 text-[13px] text-[var(--cds-text-2)] leading-relaxed">
								Every member takes one seat.{" "}
								<span className="text-[var(--cds-text)]">
									Adding a member adds a seat and changes your bill
								</span>{" "}
								— removing one frees the seat. Seat changes are prorated by
								Stripe on your next invoice.
							</p>
							{overSeats && (
								<p className="mt-3 text-[13px] text-[var(--cds-danger-text)]">
									You have more members than purchased seats. The next sync will
									bill for {org.seats_used}.
								</p>
							)}
							<Link
								href="/account/billing"
								className="mt-4 inline-flex text-[13px] text-[var(--cds-link)] hover:underline"
							>
								Plan &amp; billing →
							</Link>
						</div>
					</Panel>

					{canManage && (
						<RenamePanel org={org} onRename={(n) => run(() => renameOrg(n))} />
					)}
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
// Members — role dropdown is owner-only; remove is owner/admin, and anyone can
// leave an org that isn't their personal one.
// ---------------------------------------------------------------------------

function MembersPanel({
	org,
	meId,
	canManage,
	isOwner,
	onRoleChange,
	onRemove,
}: {
	org: OrgConsole;
	meId: number;
	canManage: boolean;
	isOwner: boolean;
	onRoleChange: (userId: number, role: OrgRole) => Promise<boolean>;
	onRemove: (userId: number) => Promise<boolean>;
}) {
	const owners = org.members.filter((m) => m.role === "owner").length;

	return (
		<Panel
			title={`Members — ${org.members.length}`}
			action={
				<span className="font-mono text-[11px] text-[var(--cds-helper)]">
					{org.members.length === 1 ? "1 seat" : `${org.members.length} seats`}
				</span>
			}
		>
			<div className="overflow-x-auto">
				<table className="w-full min-w-[640px] border-collapse text-left">
					<thead>
						<tr>
							{["Member", "Role", "Joined", ""].map((h) => (
								<th
									key={h || "actions"}
									className="whitespace-nowrap border-[var(--cds-border-strong)] border-b bg-[var(--cds-layer)] px-3 py-2.5 font-mono font-normal text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.1em]"
								>
									{h}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{org.members.map((m) => {
							const me = m.id === meId;
							// The server refuses to demote or remove the last owner —
							// don't offer the control that is guaranteed to fail.
							const lastOwner = m.role === "owner" && owners === 1;
							const roleTag = ROLE_TAGS[m.role] ?? ROLE_TAGS.member;
							return (
								<tr
									key={m.id}
									className="border-[var(--cds-border)] border-b transition-colors hover:bg-[var(--cds-layer)]"
								>
									<td className="px-3 py-2.5">
										<p className="text-[13px]">
											{m.email}
											{me && (
												<span className="ml-2 text-[var(--cds-helper)] text-xs">
													you
												</span>
											)}
										</p>
										{m.full_name && (
											<p className="text-[var(--cds-helper)] text-xs">
												{m.full_name}
											</p>
										)}
									</td>
									<td className="whitespace-nowrap px-3 py-2.5">
										{isOwner && !lastOwner ? (
											<SelectField
												aria-label={`Role for ${m.email}`}
												value={m.role}
												options={ROLE_OPTIONS}
												onChange={(e) =>
													void onRoleChange(m.id, e.target.value as OrgRole)
												}
												className="w-32"
											/>
										) : (
											<Tag kind={roleTag.kind}>{roleTag.label}</Tag>
										)}
									</td>
									<td className="whitespace-nowrap px-3 py-2.5 font-mono text-[13px] text-[var(--cds-text-2)] tabular-nums">
										{fmtDate(m.joined)}
									</td>
									<td className="whitespace-nowrap px-3 py-2.5 text-right">
										{lastOwner ? (
											<span className="text-[var(--cds-helper)] text-xs">
												Last owner
											</span>
										) : me && !org.is_personal ? (
											<ConfirmAction
												label="Leave"
												confirmLabel="Leave organization"
												onConfirm={() => void onRemove(m.id)}
											/>
										) : canManage && !me ? (
											<ConfirmAction
												label="Remove"
												confirmLabel="Remove member"
												onConfirm={() => void onRemove(m.id)}
											/>
										) : null}
									</td>
								</tr>
							);
						})}
					</tbody>
				</table>
			</div>
			{canManage && (
				<p className="border-[var(--cds-border)] border-t px-4 py-2.5 text-[var(--cds-helper)] text-xs">
					Removing a member frees their seat and drops them back to the free
					tier unless another organization covers them.
				</p>
			)}
		</Panel>
	);
}

// A destructive action that arms into an inline Confirm / Cancel pair rather
// than firing on first click (same pattern as /admin/users).
function ConfirmAction({
	label,
	confirmLabel,
	onConfirm,
}: {
	label: string;
	confirmLabel: string;
	onConfirm: () => void;
}) {
	const [arming, setArming] = useState(false);
	if (!arming) {
		return (
			<BtnGhost size="md" onClick={() => setArming(true)}>
				{label}
			</BtnGhost>
		);
	}
	return (
		<span className="flex items-center justify-end gap-2">
			<BtnDanger
				size="md"
				onClick={() => {
					setArming(false);
					onConfirm();
				}}
			>
				{confirmLabel}
			</BtnDanger>
			<BtnGhost size="md" onClick={() => setArming(false)}>
				Cancel
			</BtnGhost>
		</span>
	);
}

// ---------------------------------------------------------------------------
// Invite — owner/admin only. Says the quiet part out loud: this changes the bill.
// ---------------------------------------------------------------------------

function InvitePanel({
	org,
	onInvite,
}: {
	org: OrgConsole;
	onInvite: (email: string, role: OrgRole) => Promise<boolean>;
}) {
	const [email, setEmail] = useState("");
	const [role, setRole] = useState<OrgRole>("member");
	const [sent, setSent] = useState<string | null>(null);

	const submit = async () => {
		const addr = email.trim().toLowerCase();
		if (!addr) return;
		if (await onInvite(addr, role)) {
			setSent(addr);
			setEmail("");
			setRole("member");
		}
	};

	return (
		<Panel title="Invite a teammate">
			<div className="p-4">
				{sent && (
					<Notification kind="success" title="Invitation sent" className="mb-4">
						{sent} has been emailed a link to join {org.name}. It expires in 14
						days.
					</Notification>
				)}
				<div className="flex flex-wrap items-end gap-3">
					<TextField
						label="Email"
						type="email"
						placeholder="colleague@firm.com"
						value={email}
						onChange={(e) => {
							setEmail(e.target.value);
							setSent(null);
						}}
						onKeyDown={(e) => {
							if (e.key === "Enter") void submit();
						}}
						className="min-w-[16rem] flex-1"
					/>
					<SelectField
						label="Role"
						value={role}
						options={ROLE_OPTIONS}
						onChange={(e) => setRole(e.target.value as OrgRole)}
						className="w-36"
					/>
					<BtnPrimary
						size="md"
						arrow={false}
						disabled={!email.trim()}
						onClick={() => void submit()}
					>
						<MailIcon className="size-4" strokeWidth={1.5} />
						Send invitation
					</BtnPrimary>
				</div>
				<p className="mt-3 text-[var(--cds-helper)] text-xs leading-relaxed">
					They get an email with a join link. Accepting it adds them to{" "}
					{org.name} —{" "}
					<strong className="font-semibold">that adds a seat</strong> and
					changes your bill from the next invoice.
				</p>
			</div>
		</Panel>
	);
}

// ---------------------------------------------------------------------------
// Pending invitations — visible to everyone, revocable by owner/admin
// ---------------------------------------------------------------------------

function InvitationsPanel({
	org,
	canManage,
	onRevoke,
}: {
	org: OrgConsole;
	canManage: boolean;
	onRevoke: (id: number) => Promise<boolean>;
}) {
	return (
		<Panel title={`Pending invitations — ${org.invitations.length}`}>
			{org.invitations.length === 0 ? (
				<p className="p-4 text-[var(--cds-text-2)] text-sm">
					No invitations are waiting to be accepted.
				</p>
			) : (
				<div className="divide-y divide-[var(--cds-border)]">
					{org.invitations.map((inv) => {
						const roleTag = ROLE_TAGS[inv.role] ?? ROLE_TAGS.member;
						return (
							<div
								key={inv.id}
								className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
							>
								<div className="min-w-0">
									<p className="flex flex-wrap items-center gap-2 text-sm">
										{inv.email}
										<Tag kind={roleTag.kind}>{roleTag.label}</Tag>
									</p>
									<p className="mt-0.5 text-[var(--cds-helper)] text-xs">
										{inv.invited_by ? `Invited by ${inv.invited_by} · ` : ""}
										{inv.expires_at
											? `Expires ${fmtDate(inv.expires_at)}`
											: "Pending"}
									</p>
								</div>
								{canManage && (
									<ConfirmAction
										label="Revoke"
										confirmLabel="Revoke invitation"
										onConfirm={() => void onRevoke(inv.id)}
									/>
								)}
							</div>
						);
					})}
				</div>
			)}
		</Panel>
	);
}

// ---------------------------------------------------------------------------
// Rename — the org name is what invitees see in the invitation email, so a
// firm shouldn't be stuck with the auto-generated personal-org name.
// ---------------------------------------------------------------------------

function RenamePanel({
	org,
	onRename,
}: {
	org: OrgConsole;
	onRename: (name: string) => Promise<boolean>;
}) {
	const [name, setName] = useState(org.name);
	useEffect(() => setName(org.name), [org.name]);

	const dirty = name.trim() !== "" && name.trim() !== org.name;

	return (
		<Panel title="Organization name">
			<div className="p-4">
				<TextField
					label="Name"
					value={name}
					onChange={(e) => setName(e.target.value)}
					helper="Shown to teammates you invite."
				/>
				<BtnSecondary
					size="md"
					className="mt-4"
					disabled={!dirty}
					onClick={() => void onRename(name.trim())}
				>
					Save name
				</BtnSecondary>
			</div>
		</Panel>
	);
}
