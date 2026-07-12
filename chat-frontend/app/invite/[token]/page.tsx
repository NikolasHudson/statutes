"use client";

// Invitation landing page — the link in an org invitation email.
//
// Public by design (auth-gate.tsx exempts /invite): the invitee usually has no
// account yet, and must be able to see who invited them and to what before
// signing up. It therefore renders OUTSIDE the AuthGate provider and does its
// own /api/auth/me check instead of useAuth().
//
// Three doors:
//   signed out            → sign in / create an account, carrying ?invite=<token>
//                           (register accepts the invitation server-side)
//   signed in, right email → Accept, which calls the accept endpoint
//   signed in, wrong email → switch accounts (the invitation is address-bound)

import { BuildingIcon, CheckCircle2Icon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import type { AuthUser } from "@/components/auth-gate";
import {
	BtnGhost,
	BtnPrimary,
	BtnSecondary,
	CarbonRoot,
	Eyebrow,
	Notification,
	ShellHeader,
	Tag,
} from "@/components/carbon/primitives";
import { csrfHeaders } from "@/lib/csrf";
import { AccountError, fmtDate } from "@/lib/iowa-account";
import {
	acceptInvitation,
	getInvitePreview,
	type OrgInvitePreview,
} from "@/lib/iowa-org";
import { ROLE_TAGS } from "@/lib/org-display";
import { clearThreadStores } from "@/lib/thread-store";

type Phase = "loading" | "ready" | "accepting" | "accepted" | "error";

export default function InvitePage() {
	const token = String(useParams<{ token: string }>().token ?? "");

	const [invite, setInvite] = useState<OrgInvitePreview | null>(null);
	const [user, setUser] = useState<AuthUser | null>(null);
	const [phase, setPhase] = useState<Phase>("loading");
	const [error, setError] = useState<string | null>(null);

	// The preview endpoint is unauthenticated; the session check runs beside it
	// so the page can pick its door in one pass.
	useEffect(() => {
		let cancelled = false;
		Promise.all([
			getInvitePreview(token),
			fetch("/api/auth/me", { credentials: "include" })
				.then((r) => (r.ok ? (r.json() as Promise<AuthUser>) : null))
				.catch(() => null),
		])
			.then(([preview, me]) => {
				if (cancelled) return;
				setInvite(preview);
				setUser(me);
				setPhase("ready");
			})
			.catch((e) => {
				if (cancelled) return;
				setError(
					e instanceof AccountError && e.status === 404
						? "This invitation link isn't valid."
						: ((e as Error).message ?? "Couldn't load this invitation."),
				);
				setPhase("error");
			});
		return () => {
			cancelled = true;
		};
	}, [token]);

	const accept = async () => {
		setPhase("accepting");
		setError(null);
		try {
			await acceptInvitation(token);
			setPhase("accepted");
		} catch (e) {
			setError(
				e instanceof AccountError
					? e.detail
					: "Could not accept the invitation.",
			);
			setPhase("ready");
		}
	};

	// Signing out from a page that lives outside AuthGate's provider: same two
	// steps AuthGate takes (server logout + wipe locally-stored threads), then a
	// reload so the page re-runs its session check.
	const switchAccount = async () => {
		await fetch("/api/auth/logout", {
			method: "POST",
			headers: await csrfHeaders(),
			credentials: "include",
		}).catch(() => {});
		clearThreadStores();
		window.location.assign(`/?invite=${encodeURIComponent(token)}`);
	};

	return (
		<CarbonRoot>
			<ShellHeader homeHref="/" note="Invitation" />
			<main className="flex min-h-0 flex-1 justify-center overflow-y-auto px-5 py-16 sm:px-8">
				<div className="w-full max-w-lg">
					{phase === "loading" ? (
						<p className="text-[var(--cds-text-2)] text-sm">
							Loading invitation…
						</p>
					) : phase === "error" || !invite ? (
						<>
							<Notification kind="error" title="Invitation unavailable">
								{error ?? "This invitation link isn't valid."}
							</Notification>
							<Link href="/" className="mt-6 inline-flex">
								<BtnSecondary size="md">Go to Hudson Corpus</BtnSecondary>
							</Link>
						</>
					) : phase === "accepted" ? (
						<>
							<CheckCircle2Icon
								className="size-8 text-[var(--cds-success-text)]"
								strokeWidth={1.5}
							/>
							<h1 className="mt-5 font-light text-3xl">
								You&rsquo;ve joined {invite.org_name}
							</h1>
							<p className="mt-3 text-[15px] text-[var(--cds-text-2)] leading-relaxed">
								You now share the organization&rsquo;s plan. Your seat is
								counted on its bill.
							</p>
							<div className="mt-8 flex flex-wrap gap-3">
								<Link href="/">
									<BtnPrimary size="md">Start researching</BtnPrimary>
								</Link>
								<Link href="/org">
									<BtnSecondary size="md">View organization</BtnSecondary>
								</Link>
							</div>
						</>
					) : (
						<InviteCard
							invite={invite}
							user={user}
							token={token}
							busy={phase === "accepting"}
							error={error}
							onAccept={accept}
							onSwitchAccount={switchAccount}
						/>
					)}
				</div>
			</main>
		</CarbonRoot>
	);
}

function InviteCard({
	invite,
	user,
	token,
	busy,
	error,
	onAccept,
	onSwitchAccount,
}: {
	invite: OrgInvitePreview;
	user: AuthUser | null;
	token: string;
	busy: boolean;
	error: string | null;
	onAccept: () => void;
	onSwitchAccount: () => void;
}) {
	const roleTag = ROLE_TAGS[invite.role] ?? ROLE_TAGS.member;
	// The invitation is bound to the address it was sent to — the server checks
	// the same thing on accept.
	const rightAccount =
		user !== null && user.email.toLowerCase() === invite.email.toLowerCase();

	return (
		<>
			<Eyebrow>Invitation</Eyebrow>
			<h1 className="mt-4 font-light text-3xl leading-tight">
				{invite.inviter
					? `${invite.inviter} invited you`
					: "You've been invited"}{" "}
				to join {invite.org_name}
			</h1>

			<div className="mt-8 border border-[var(--cds-border)] bg-[var(--cds-layer)] p-5">
				<div className="flex items-start gap-3">
					<BuildingIcon
						className="mt-0.5 size-5 shrink-0 text-[var(--cds-helper)]"
						strokeWidth={1.5}
					/>
					<div className="min-w-0">
						<p className="font-semibold text-sm">{invite.org_name}</p>
						<p className="mt-1 flex flex-wrap items-center gap-2 text-[13px] text-[var(--cds-text-2)]">
							Invited as <Tag kind={roleTag.kind}>{roleTag.label}</Tag>
						</p>
						{invite.email && (
							<p className="mt-2 text-[13px] text-[var(--cds-text-2)]">
								For{" "}
								<span className="text-[var(--cds-text)]">{invite.email}</span>
							</p>
						)}
						{invite.expires_at && (
							<p className="mt-1 text-[var(--cds-helper)] text-xs">
								Expires {fmtDate(invite.expires_at)}
							</p>
						)}
					</div>
				</div>
			</div>

			{!invite.valid ? (
				<>
					{/* Registering from an invite link accepts the invitation on the
					    server, so the invitee lands back here to find it already spent.
					    Signed in as the invited address, that reads as success, not an
					    error. */}
					<Notification
						kind={rightAccount ? "success" : "warning"}
						title={
							rightAccount
								? `You're already in ${invite.org_name}`
								: "This invitation is no longer open"
						}
						className="mt-6"
					>
						{rightAccount
							? "This invitation has already been used — nothing left to do here."
							: `It has already been accepted, revoked, or expired. If you think it should still work, ask ${invite.inviter ?? "an owner"} to send a new one.`}
					</Notification>
					<div className="mt-6 flex flex-wrap gap-3">
						<Link href={user ? "/org" : "/"}>
							<BtnPrimary size="md">
								{user ? "View your organization" : "Go to Hudson Corpus"}
							</BtnPrimary>
						</Link>
						{user && (
							<Link href="/">
								<BtnSecondary size="md">Start researching</BtnSecondary>
							</Link>
						)}
					</div>
				</>
			) : (
				<>
					{error && (
						<Notification
							kind="error"
							title="Couldn't accept the invitation"
							className="mt-6"
						>
							{error}
						</Notification>
					)}

					<p className="mt-6 text-[15px] text-[var(--cds-text-2)] leading-relaxed">
						Joining {invite.org_name} gives you its plan, and takes one of its
						seats.
					</p>

					{!user ? (
						<div className="mt-8">
							<Link href={`/?invite=${encodeURIComponent(token)}`}>
								<BtnPrimary size="lg">Sign in to accept</BtnPrimary>
							</Link>
							<p className="mt-3 text-[var(--cds-helper)] text-xs leading-relaxed">
								No account yet? Create one with{" "}
								{invite.email || "the invited address"} on the next screen and
								you&rsquo;ll join {invite.org_name} automatically.
							</p>
						</div>
					) : rightAccount ? (
						<div className="mt-8">
							<BtnPrimary size="lg" disabled={busy} onClick={onAccept}>
								{busy ? "Joining…" : `Join ${invite.org_name}`}
							</BtnPrimary>
							<p className="mt-3 text-[var(--cds-helper)] text-xs">
								Signed in as {user.email}.
							</p>
						</div>
					) : (
						<div className="mt-8">
							<Notification kind="warning" title="Wrong account">
								This invitation was sent to{" "}
								<span className="text-[var(--cds-text)]">{invite.email}</span>,
								but you&rsquo;re signed in as {user.email}. Sign in with the
								invited address to accept it.
							</Notification>
							<div className="mt-5 flex flex-wrap gap-3">
								<BtnPrimary size="md" onClick={onSwitchAccount}>
									Sign in as {invite.email || "another user"}
								</BtnPrimary>
								<Link href="/">
									<BtnGhost size="md">Stay signed in</BtnGhost>
								</Link>
							</div>
						</div>
					)}
				</>
			)}
		</>
	);
}
