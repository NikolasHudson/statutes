"""Organization self-service (``/api/org/*``): members, roles, invitations.

The console the SPA's ``/org`` page renders, and the one place a customer can
grow from a solo seat into a firm without talking to us: rename the org, invite
people by email, hand out roles, remove them again. Seats are the Stripe
quantity, so every membership change here is also a change to the bill — which
is exactly why none of this endpoint's mutations touch the ORM directly. They
all go through :mod:`apps.tenancy.services`, whose ``add_member`` /
``remove_member`` / ``change_role`` are the only functions that know how to
mutate a membership *and* re-derive every member's tier, push the new seat count
to Stripe, and write the audit row. See BILLING_PLAN.md §4 and §6a.

**Roles are the security boundary here.** The SPA's role checks decide what
renders; they are hints, and a plain member who forges the request gets nothing:

    read the console            any member
    rename the org              owner, admin
    invite / revoke an invite   owner, admin  (only an owner may invite an OWNER)
    change a member's role      owner
    remove another member       owner, admin
    leave the org yourself      any member (subject to the last-owner rule)

The one invariant underneath all of it: **an org always keeps at least one
owner.** The service layer raises ``LastOwnerError`` rather than let the last
owner be removed or demoted, which is also what stops a solo user from
"leaving" (and orphaning) their own personal org.

``GET /api/org/invitations/{token}`` is the only unauthenticated route: an
invitee usually has no account yet and must be able to see who invited them, and
to what, *before* signing up. It exposes nothing the emailed link didn't already
contain, and the token alone still cannot join anyone to anything — accepting
additionally requires being logged in as the address the invitation was sent to.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.audit import AuditEvent, record_event
from apps.api.session_auth import session_auth
from apps.tenancy import services
from apps.tenancy.models import (
    Organization,
    OrgInvitation,
    OrgMembership,
    generate_invitation_token,
    hash_invitation_token,
)

logger = logging.getLogger(__name__)

orgs_router = Router(tags=["org"], auth=session_auth)

Role = OrgMembership.Role
MANAGERS = frozenset({Role.OWNER, Role.ADMIN})

# services.accept_invitation tags each refusal with a ``code``; this is the only
# place that turns those into HTTP. 404 for a token that matches nothing (an
# unknown token and a wrong token are the same event), 403 for "not your
# invitation", 409 for a real invitation that is simply no longer spendable.
_ACCEPT_STATUS = {
    "unknown": 404,
    "email_mismatch": 403,
    "already_accepted": 409,
    "revoked": 409,
    "expired": 409,
}


# ---------------------------------------------------------------------------
# Schemas — frozen by BILLING_PLAN.md §6a. The SPA shipped against these exact
# keys; note members[].id is the USER id, not the membership id.
# ---------------------------------------------------------------------------


class MemberOut(Schema):
    id: int  # user id — the {user_id} path param below
    email: str
    full_name: str
    role: str
    joined: dt.datetime


class InvitationOut(Schema):
    id: int
    email: str
    role: str
    invited_by: str | None
    expires_at: dt.datetime
    created_at: dt.datetime


class OrgConsoleOut(Schema):
    id: int
    name: str
    status: str
    is_personal: bool
    my_role: str
    seats_used: int
    seats_purchased: int
    members: list[MemberOut]
    invitations: list[InvitationOut]


class InvitePreviewOut(Schema):
    org_name: str
    email: str
    role: str
    inviter: str | None
    valid: bool  # false once accepted, revoked, or expired
    expires_at: dt.datetime


class OrgPatchIn(Schema):
    name: str


class InviteIn(Schema):
    email: str
    role: str = Role.MEMBER


class RoleIn(Schema):
    role: str


class OkOut(Schema):
    ok: bool = True


# ---------------------------------------------------------------------------
# Resolution + authz
# ---------------------------------------------------------------------------


def _console_org(user) -> Organization:
    """The org this console operates on.

    Usually the user's billing org (``services.billing_org``) — but an invitee
    has *two* orgs: the one-person shell created for them at registration, and
    the firm they were invited into. Showing them the shell would be useless (the
    invite page's "View organization" button lands here right after they join),
    so prefer, in order: a non-personal org, then whichever org actually has
    other people in it, then the personal org. Ties break on id, so the answer is
    stable across requests.

    Every other route in this module resolves the org through here, so the
    console, its mutations, and its authz can never disagree about *which* org
    they are talking about.
    """
    orgs = list(services.orgs_for(user))
    if not orgs:
        # Accounts predating the registration hook have no org at all; the same
        # defensive create /api/auth/me does.
        return services.ensure_personal_org(user)
    # Counted separately, NOT with .annotate() on the queryset above: that
    # queryset already filters on ``memberships__user``, and Django would reuse
    # that join for the aggregate — counting the caller's own membership (always
    # 1) instead of the org's members.
    counts = dict(
        OrgMembership.objects.filter(org__in=orgs)
        .values_list("org_id")
        .annotate(n=Count("id"))
    )
    orgs.sort(key=lambda o: (o.is_personal, -counts.get(o.pk, 0), o.pk))
    return orgs[0]


def _require_role(user, org: Organization, allowed=MANAGERS) -> str:
    """The caller's role in ``org``, or 403. Membership itself is authz: a
    non-member gets the same 403 as an under-privileged member — this surface
    never confirms that someone else's org exists."""
    role = services.role_of(user, org)
    if role is None or role not in allowed:
        raise HttpError(403, "you do not have permission to do that in this organization")
    return role


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _pending_invitations(org: Organization):
    return (
        OrgInvitation.objects.filter(
            org=org,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .select_related("invited_by")
        .order_by("-created_at")
    )


def _seats_purchased(org: Organization) -> int:
    """What Stripe is billing for. 0 until the org buys a plan — deliberately
    NOT the member count, so the console can show "4 of 5 seats" honestly."""
    subscription = services.flagship_subscription(org)
    return subscription.seats if subscription is not None else 0


def _console_out(org: Organization, my_role: str) -> OrgConsoleOut:
    members = [
        MemberOut(
            id=m.user_id,
            email=m.user.email,
            full_name=m.user.full_name,
            role=m.role,
            joined=m.created_at,
        )
        for m in services.members_of(org).order_by("created_at", "id")
    ]
    invitations = [
        InvitationOut(
            id=i.pk,
            email=i.email,
            role=i.role,
            invited_by=(i.invited_by.email if i.invited_by_id else None),
            expires_at=i.expires_at,
            created_at=i.created_at,
        )
        for i in _pending_invitations(org)
    ]
    return OrgConsoleOut(
        id=org.pk,
        name=org.name,
        status=org.status,
        is_personal=org.is_personal,
        my_role=my_role,
        seats_used=len(members),
        seats_purchased=_seats_purchased(org),
        members=members,
        invitations=invitations,
    )


# ---------------------------------------------------------------------------
# The org itself
# ---------------------------------------------------------------------------


@orgs_router.get("", response=OrgConsoleOut)
def get_org(request):
    """The console: who's in the org, who's been invited, and what it costs in
    seats. Any member may read it."""
    org = _console_org(request.user)
    role = _require_role(request.user, org, allowed=set(Role.values))
    return _console_out(org, role)


@orgs_router.patch("", response=OrgConsoleOut)
def update_org(request, payload: OrgPatchIn):
    """Rename the org (owner/admin).

    Not cosmetic: the name is what an invitee reads in the invitation email and
    on the accept page, so a firm must be able to stop being "Nick (Personal)"
    before it invites anyone.
    """
    org = _console_org(request.user)
    role = _require_role(request.user, org)

    name = (payload.name or "").strip()
    if not name:
        raise HttpError(400, "name must not be empty")
    if len(name) > 200:
        raise HttpError(400, "name must be 200 characters or fewer")

    previous, org.name = org.name, name
    org.save(update_fields=["name", "updated_at"])
    record_event(
        event_type=AuditEvent.Event.ORG_UPDATE,
        request=request,
        actor=request.user,
        detail={
            "org_id": org.pk,
            "org_slug": org.slug,
            "field": "name",
            "from": previous,
            "to": name,
        },
    )
    return _console_out(org, role)


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


def _app_base_url() -> str:
    """Where the ``/invite/<token>`` link points — ``APP_URL``, and only ``APP_URL``.

    ``/invite`` is a route on the app and nowhere else, so a base URL derived from
    anything else (this used to walk ``CORS_ALLOWED_ORIGINS``, and to return ``""``
    — a *relative* link in an email — when it ran out of candidates) is a dead link
    for the invitee. Same resolution as ``apps/billing/api._return_base_url``, whose
    Stripe override is the only sanctioned divergence.
    """
    return str(settings.APP_URL).rstrip("/")


def _send_invitation_email(invitation: OrgInvitation, raw_token: str, inviter) -> None:
    """Plain, short, one link — the whole point of the mail is the link.

    Best-effort, matching the posture of every other transactional send in the
    codebase (apps/marketing): the DB row is the durable record, and a Postmark
    hiccup must not fail an otherwise-good invite. The owner can see the pending
    invitation in the console and revoke/re-send it.
    """
    link = f"{_app_base_url()}/invite/{raw_token}"
    who = (inviter.full_name or inviter.email) if inviter is not None else "Someone"
    body = (
        f"{who} invited you to join {invitation.org.name} on Hudson.\n\n"
        f"Accept the invitation:\n{link}\n\n"
        f"The link is for {invitation.email} and expires on "
        f"{invitation.expires_at:%B %-d, %Y}.\n"
    )
    try:
        send_mail(
            subject=f"{who} invited you to {invitation.org.name} on Hudson",
            message=body,
            from_email=settings.CONTACT_FROM_EMAIL,
            recipient_list=[invitation.email],
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 — the invitation row is the durable record
        logger.exception(
            "invitation email failed to send (invitation=%s)", invitation.pk
        )


@orgs_router.post("/invitations", response={200: InvitationOut})
def create_invitation(request, payload: InviteIn):
    """Invite an email address into the org (owner/admin).

    409 when the address is already a member or already has a live invitation —
    re-inviting is not how you re-send. An *expired* invitation is quietly
    replaced, because the pending-invitation unique index still counts it and the
    owner's intent is unambiguous.
    """
    org = _console_org(request.user)
    role = _require_role(request.user, org)

    email = (payload.email or "").strip().lower()
    if not email or "@" not in email:
        raise HttpError(400, "a valid email address is required")
    if payload.role not in set(Role.values):
        raise HttpError(400, f"unknown role: {payload.role}")
    # An admin cannot change roles, so it must not be able to mint an owner by
    # the back door of an invitation. Only an owner may invite an owner.
    if payload.role == Role.OWNER and role != Role.OWNER:
        raise HttpError(403, "only an owner may invite another owner")

    if OrgMembership.objects.filter(org=org, user__email__iexact=email).exists():
        raise HttpError(409, "that person is already a member of this organization")

    live = OrgInvitation.objects.filter(
        org=org, email=email, accepted_at__isnull=True, revoked_at__isnull=True
    ).first()
    if live is not None:
        if live.expires_at > timezone.now():
            raise HttpError(409, "an invitation is already pending for that address")
        # Expired but never revoked: it still occupies the one-pending-per-address
        # index slot. Close it out so a fresh invitation can take its place.
        live.revoked_at = timezone.now()
        live.save(update_fields=["revoked_at"])

    raw_token, token_hash = generate_invitation_token()
    invitation = OrgInvitation.objects.create(
        org=org,
        email=email,
        role=payload.role,
        token_hash=token_hash,
        invited_by=request.user,
    )
    record_event(
        event_type=AuditEvent.Event.ORG_INVITE_CREATE,
        request=request,
        actor=request.user,
        detail={
            "org_id": org.pk,
            "org_slug": org.slug,
            "invitation_id": invitation.pk,
            "target_email": email,
            "role": invitation.role,
        },
    )
    # The raw token exists only here and in the email; it is never persisted.
    _send_invitation_email(invitation, raw_token, request.user)

    return InvitationOut(
        id=invitation.pk,
        email=invitation.email,
        role=invitation.role,
        invited_by=request.user.email,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


@orgs_router.delete("/invitations/{int:invitation_id}", response=OkOut)
def revoke_invitation(request, invitation_id: int):
    """Revoke a pending invitation (owner/admin). The link dies immediately —
    ``accept_invitation`` refuses a revoked row."""
    org = _console_org(request.user)
    _require_role(request.user, org)

    invitation = OrgInvitation.objects.filter(pk=invitation_id, org=org).first()
    if invitation is None:
        raise HttpError(404, "no such invitation")
    if invitation.accepted_at is not None:
        raise HttpError(
            409, "that invitation has already been accepted — remove the member instead"
        )
    if invitation.revoked_at is None:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
        record_event(
            event_type=AuditEvent.Event.ORG_INVITE_REVOKE,
            request=request,
            actor=request.user,
            detail={
                "org_id": org.pk,
                "org_slug": org.slug,
                "invitation_id": invitation.pk,
                "target_email": invitation.email,
            },
        )
    return OkOut()


@orgs_router.get("/invitations/{token}", response=InvitePreviewOut, auth=None)
def preview_invitation(request, token: str):
    """Public preview of an emailed invitation, so ``/invite/<token>`` can render
    before the invitee has an account.

    A spent invitation is **200 with ``valid: false``**, not an error — the page
    distinguishes "already used" (which, for the invited address, is success:
    registering from the link already accepted it) from "this link is nonsense",
    and only the latter is a 404.
    """
    invitation = (
        OrgInvitation.objects.select_related("org", "invited_by")
        .filter(token_hash=hash_invitation_token(token))
        .first()
    )
    if invitation is None:
        raise HttpError(404, "this invitation link is not valid")
    return InvitePreviewOut(
        org_name=invitation.org.name,
        email=invitation.email,
        role=invitation.role,
        inviter=(
            (invitation.invited_by.full_name or invitation.invited_by.email)
            if invitation.invited_by_id
            else None
        ),
        valid=invitation.is_pending,
        expires_at=invitation.expires_at,
    )


@orgs_router.post("/invitations/{token}/accept", response=OrgConsoleOut)
def accept_invitation(request, token: str):
    """Join the inviting org (session auth; must be signed in as the invited
    address). Idempotent — see ``services.accept_invitation``.

    Answers with the joined org's console, so the SPA can render the org the user
    just landed in without a second round-trip.
    """
    try:
        membership = services.accept_invitation(request.user, token)
    except services.TenancyError as exc:
        raise HttpError(_ACCEPT_STATUS.get(getattr(exc, "code", ""), 400), str(exc))
    return _console_out(membership.org, membership.role)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def _member_or_404(org: Organization, user_id: int) -> OrgMembership:
    membership = (
        OrgMembership.objects.select_related("user")
        .filter(org=org, user_id=user_id)
        .first()
    )
    if membership is None:
        raise HttpError(404, "that person is not a member of this organization")
    return membership


@orgs_router.patch("/members/{int:user_id}", response=OrgConsoleOut)
def change_member_role(request, user_id: int, payload: RoleIn):
    """Change a member's role. **Owner only** — an admin may bring people in and
    out, but rewriting who holds the org (and its bill) is the owner's call.
    Demoting the last owner is refused (409)."""
    org = _console_org(request.user)
    my_role = _require_role(request.user, org, allowed={Role.OWNER})

    membership = _member_or_404(org, user_id)
    if payload.role not in set(Role.values):
        raise HttpError(400, f"unknown role: {payload.role}")

    try:
        services.change_role(
            org, membership.user, payload.role, actor=request.user, request=request
        )
    except services.LastOwnerError as exc:
        raise HttpError(409, str(exc))
    except services.TenancyError as exc:
        raise HttpError(400, str(exc))

    # An owner may demote *themselves* (as long as another owner remains), which
    # changes what this very response is allowed to show — so re-read the role.
    return _console_out(org, services.role_of(request.user, org) or my_role)


@orgs_router.delete("/members/{int:user_id}", response=OrgConsoleOut)
def remove_member(request, user_id: int):
    """Remove a member (owner/admin) — or leave the org yourself, whatever your
    role. Frees the seat, which lowers the Stripe quantity.

    Self-leave is the reason this route is not simply owner/admin-gated: a member
    who was invited into a firm must be able to walk out of it without asking
    permission. The last-owner rule (409) is what keeps that from orphaning an
    org — and is also why a solo user cannot "leave" their own personal org: they
    are its only owner.
    """
    org = _console_org(request.user)
    is_self = user_id == request.user.pk
    allowed = set(Role.values) if is_self else MANAGERS
    _require_role(request.user, org, allowed=allowed)

    membership = _member_or_404(org, user_id)
    try:
        services.remove_member(org, membership.user, actor=request.user, request=request)
    except services.LastOwnerError as exc:
        raise HttpError(409, str(exc))

    if is_self:
        # They just walked out — the console they get back is the next org that
        # answers for them (their personal org, in the ordinary case).
        org = _console_org(request.user)
    return _console_out(org, services.role_of(request.user, org) or Role.MEMBER)
