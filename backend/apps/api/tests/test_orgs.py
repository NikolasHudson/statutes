"""The org self-service API (apps.api.orgs) — BILLING_PLAN.md §4.

Three concerns, in order of how much they matter:

1. **Authz.** Roles are the security boundary; the SPA's role checks are render
   hints. A plain member must not be able to invite, revoke, rename, change a
   role, or remove anyone else, no matter what they POST. An admin must not be
   able to mint an owner by the back door of an invitation.
2. **The last-owner invariant.** An org can never be left ownerless — not by
   removal, not by demotion, not by the last owner "leaving".
3. **Invitation acceptance.** The token is address-bound and single-use: a
   forwarded link is worthless to whoever holds it, and expiry/revocation are
   enforced on redemption, not just in the UI.
"""

from __future__ import annotations

import datetime as dt
import json

from django.core import mail
from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.audit import AuditEvent
from apps.accounts.models import Tier, User
from apps.tenancy import services
from apps.tenancy.models import (
    OrgInvitation,
    OrgMembership,
    Subscription,
    generate_invitation_token,
    hash_invitation_token,
)

from ._factories import make_user

Role = OrgMembership.Role


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _json(client: Client, method: str, path: str, data: dict | None = None):
    return getattr(client, method)(
        path,
        data=json.dumps(data or {}),
        content_type="application/json",
    )


def _make_invitation(org, email: str, *, role=Role.MEMBER, invited_by=None, **kwargs):
    """(raw_token, invitation). Mirrors what POST /invitations does — the raw
    token is returned to the test the same way it is emailed to the invitee, and
    only its hash is ever stored."""
    raw, token_hash = generate_invitation_token()
    invitation = OrgInvitation.objects.create(
        org=org,
        email=email,
        role=role,
        token_hash=token_hash,
        invited_by=invited_by,
        **kwargs,
    )
    return raw, invitation


class OrgFixture(TestCase):
    """A firm with one of each role, plus an outsider. The firm is a personal org
    that grew — which is exactly how a real one is born: a solo user renames
    their org and starts inviting people."""

    def setUp(self):
        self.owner = make_user("owner@example.com", tier=Tier.FREE)
        self.admin = make_user("admin@example.com", tier=Tier.FREE)
        self.member = make_user("member@example.com", tier=Tier.FREE)
        self.outsider = make_user("outsider@example.com", tier=Tier.FREE)

        self.org = services.ensure_personal_org(self.owner)
        self.org.name = "Acme Law"
        self.org.save(update_fields=["name"])

        # The other two have personal orgs of their own — the console must still
        # show them the firm, not their one-person shell.
        for user in (self.admin, self.member, self.outsider):
            services.ensure_personal_org(user)
        services.add_member(self.org, self.admin, Role.ADMIN)
        services.add_member(self.org, self.member, Role.MEMBER)

        self.owner_client = _client(self.owner)
        self.admin_client = _client(self.admin)
        self.member_client = _client(self.member)


# ---------------------------------------------------------------------------
# GET /api/org — the console
# ---------------------------------------------------------------------------


class ConsoleTests(OrgFixture):
    def test_anonymous_is_401(self):
        self.assertEqual(Client().get("/api/org").status_code, 401)

    def test_console_shape_matches_the_frozen_contract(self):
        Subscription.objects.create(
            org=self.org, plan=Tier.FIRM, status=Subscription.Status.ACTIVE, seats=5
        )
        body = self.owner_client.get("/api/org").json()

        self.assertEqual(body["id"], self.org.pk)
        self.assertEqual(body["name"], "Acme Law")
        self.assertEqual(body["status"], "active")
        self.assertTrue(body["is_personal"])
        self.assertEqual(body["my_role"], "owner")
        self.assertEqual(body["seats_used"], 3)
        self.assertEqual(body["seats_purchased"], 5)
        self.assertEqual(body["invitations"], [])

        by_email = {m["email"]: m for m in body["members"]}
        self.assertEqual(set(by_email), {
            "owner@example.com", "admin@example.com", "member@example.com"
        })
        # members[].id is the USER id — it is the {user_id} path param, and the
        # shipped SPA passes it straight back.
        self.assertEqual(by_email["member@example.com"]["id"], self.member.pk)
        self.assertEqual(by_email["admin@example.com"]["role"], "admin")
        self.assertIn("joined", by_email["owner@example.com"])
        self.assertIn("full_name", by_email["owner@example.com"])

    def test_seats_purchased_is_zero_without_a_subscription(self):
        self.assertEqual(self.owner_client.get("/api/org").json()["seats_purchased"], 0)

    def test_member_sees_the_firm_not_their_personal_shell(self):
        body = self.member_client.get("/api/org").json()
        self.assertEqual(body["id"], self.org.pk)
        self.assertEqual(body["my_role"], "member")

    def test_console_prefers_the_org_with_people_in_it_over_a_lower_id_shell(self):
        """The joiner's own one-person org exists *before* the firm they are later
        invited into, so id order alone would show them the empty shell."""
        joiner = make_user("joiner@example.com")
        shell = services.ensure_personal_org(joiner)
        late_owner = make_user("late@example.com")
        firm = services.ensure_personal_org(late_owner)
        services.add_member(firm, joiner, Role.MEMBER)
        self.assertGreater(firm.pk, shell.pk)

        body = _client(joiner).get("/api/org").json()
        self.assertEqual(body["id"], firm.pk)
        self.assertEqual(body["my_role"], "member")
        self.assertEqual(body["seats_used"], 2)

    def test_solo_user_sees_their_own_personal_org(self):
        body = _client(self.outsider).get("/api/org").json()
        self.assertEqual(body["id"], services.billing_org(self.outsider).pk)
        self.assertEqual(body["my_role"], "owner")
        self.assertEqual(body["seats_used"], 1)

    def test_pending_invitations_are_listed_but_spent_ones_are_not(self):
        _make_invitation(self.org, "pending@example.com", invited_by=self.owner)
        _make_invitation(self.org, "gone@example.com", revoked_at=timezone.now())
        _make_invitation(self.org, "old@example.com",
                         expires_at=timezone.now() - dt.timedelta(days=1))

        invitations = self.owner_client.get("/api/org").json()["invitations"]
        self.assertEqual(len(invitations), 1)
        self.assertEqual(invitations[0]["email"], "pending@example.com")
        self.assertEqual(invitations[0]["invited_by"], "owner@example.com")
        self.assertEqual(invitations[0]["role"], "member")
        self.assertIn("expires_at", invitations[0])


# ---------------------------------------------------------------------------
# PATCH /api/org — rename
# ---------------------------------------------------------------------------


class RenameTests(OrgFixture):
    def test_owner_can_rename(self):
        r = _json(self.owner_client, "patch", "/api/org", {"name": "Acme Law LLP"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "Acme Law LLP")
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "Acme Law LLP")
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.ORG_UPDATE, actor=self.owner
            ).exists()
        )

    def test_admin_can_rename(self):
        r = _json(self.admin_client, "patch", "/api/org", {"name": "Renamed"})
        self.assertEqual(r.status_code, 200)

    def test_member_cannot_rename(self):
        r = _json(self.member_client, "patch", "/api/org", {"name": "Hostile Takeover"})
        self.assertEqual(r.status_code, 403)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "Acme Law")

    def test_empty_name_is_rejected(self):
        r = _json(self.owner_client, "patch", "/api/org", {"name": "   "})
        self.assertEqual(r.status_code, 400)


# ---------------------------------------------------------------------------
# POST /api/org/invitations
# ---------------------------------------------------------------------------


class InviteTests(OrgFixture):
    def test_owner_invites_and_the_email_carries_the_only_copy_of_the_token(self):
        mail.outbox.clear()
        r = _json(self.owner_client, "post", "/api/org/invitations",
                  {"email": "New.Person@Example.com ", "role": "admin"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["email"], "new.person@example.com")  # normalized
        self.assertEqual(body["role"], "admin")
        self.assertEqual(body["invited_by"], "owner@example.com")

        invitation = OrgInvitation.objects.get(pk=body["id"])
        self.assertEqual(invitation.org, self.org)
        self.assertIsNone(invitation.accepted_at)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["new.person@example.com"])
        self.assertIn("Acme Law", message.subject)
        # The raw token exists only in the link; the row holds its hash.
        link = [word for word in message.body.split() if "/invite/" in word][0]
        raw_token = link.rsplit("/invite/", 1)[1]
        self.assertEqual(hash_invitation_token(raw_token), invitation.token_hash)
        self.assertNotIn(raw_token, json.dumps(body))

        self.assertTrue(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.ORG_INVITE_CREATE, actor=self.owner
            ).exists()
        )

    def test_admin_can_invite_a_member(self):
        r = _json(self.admin_client, "post", "/api/org/invitations",
                  {"email": "x@example.com", "role": "member"})
        self.assertEqual(r.status_code, 200)

    def test_member_cannot_invite(self):
        r = _json(self.member_client, "post", "/api/org/invitations",
                  {"email": "x@example.com", "role": "member"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(OrgInvitation.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_admin_cannot_invite_an_owner(self):
        """An admin cannot change roles, so it must not be able to create an
        owner by inviting one."""
        r = _json(self.admin_client, "post", "/api/org/invitations",
                  {"email": "x@example.com", "role": "owner"})
        self.assertEqual(r.status_code, 403)

    def test_owner_may_invite_an_owner(self):
        r = _json(self.owner_client, "post", "/api/org/invitations",
                  {"email": "co@example.com", "role": "owner"})
        self.assertEqual(r.status_code, 200)

    def test_unknown_role_is_rejected(self):
        r = _json(self.owner_client, "post", "/api/org/invitations",
                  {"email": "x@example.com", "role": "superuser"})
        self.assertEqual(r.status_code, 400)

    def test_invalid_email_is_rejected(self):
        r = _json(self.owner_client, "post", "/api/org/invitations",
                  {"email": "not-an-email", "role": "member"})
        self.assertEqual(r.status_code, 400)

    def test_inviting_an_existing_member_is_409(self):
        r = _json(self.owner_client, "post", "/api/org/invitations",
                  {"email": "MEMBER@example.com", "role": "member"})
        self.assertEqual(r.status_code, 409)

    def test_duplicate_pending_invitation_is_409(self):
        _make_invitation(self.org, "dupe@example.com", invited_by=self.owner)
        r = _json(self.owner_client, "post", "/api/org/invitations",
                  {"email": "dupe@example.com", "role": "member"})
        self.assertEqual(r.status_code, 409)

    def test_expired_invitation_is_replaced_not_409(self):
        """The pending-invite unique index still counts an expired row, so
        re-inviting must close it out rather than blow up on the constraint."""
        _, stale = _make_invitation(
            self.org, "again@example.com",
            expires_at=timezone.now() - dt.timedelta(days=1),
        )
        r = _json(self.owner_client, "post", "/api/org/invitations",
                  {"email": "again@example.com", "role": "member"})
        self.assertEqual(r.status_code, 200)
        stale.refresh_from_db()
        self.assertIsNotNone(stale.revoked_at)
        self.assertNotEqual(r.json()["id"], stale.pk)


# ---------------------------------------------------------------------------
# DELETE /api/org/invitations/{id}
# ---------------------------------------------------------------------------


class RevokeInviteTests(OrgFixture):
    def setUp(self):
        super().setUp()
        _, self.invitation = _make_invitation(
            self.org, "invitee@example.com", invited_by=self.owner
        )

    def test_owner_revokes(self):
        r = self.owner_client.delete(f"/api/org/invitations/{self.invitation.pk}")
        self.assertEqual(r.status_code, 200)
        self.invitation.refresh_from_db()
        self.assertIsNotNone(self.invitation.revoked_at)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.ORG_INVITE_REVOKE
            ).exists()
        )

    def test_admin_revokes(self):
        r = self.admin_client.delete(f"/api/org/invitations/{self.invitation.pk}")
        self.assertEqual(r.status_code, 200)

    def test_member_cannot_revoke(self):
        r = self.member_client.delete(f"/api/org/invitations/{self.invitation.pk}")
        self.assertEqual(r.status_code, 403)
        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.revoked_at)

    def test_another_orgs_invitation_is_404(self):
        other_org = services.ensure_personal_org(self.outsider)
        _, foreign = _make_invitation(other_org, "someone@example.com")
        r = self.owner_client.delete(f"/api/org/invitations/{foreign.pk}")
        self.assertEqual(r.status_code, 404)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.revoked_at)

    def test_accepted_invitation_cannot_be_revoked(self):
        self.invitation.accepted_at = timezone.now()
        self.invitation.save(update_fields=["accepted_at"])
        r = self.owner_client.delete(f"/api/org/invitations/{self.invitation.pk}")
        self.assertEqual(r.status_code, 409)


# ---------------------------------------------------------------------------
# GET /api/org/invitations/{token} — the public preview
# ---------------------------------------------------------------------------


class InvitePreviewTests(OrgFixture):
    def test_preview_is_public_and_describes_the_invitation(self):
        raw, _ = _make_invitation(self.org, "invitee@example.com",
                                  role=Role.ADMIN, invited_by=self.owner)
        body = Client().get(f"/api/org/invitations/{raw}").json()
        self.assertEqual(body, {
            "org_name": "Acme Law",
            "email": "invitee@example.com",
            "role": "admin",
            "inviter": "owner@example.com",
            "valid": True,
            "expires_at": body["expires_at"],
        })

    def test_unknown_token_is_404(self):
        self.assertEqual(Client().get("/api/org/invitations/nonsense").status_code, 404)

    def test_spent_invitations_preview_as_invalid_rather_than_erroring(self):
        """The /invite page renders "already used" from valid=false — a 404 there
        would read as "this link is nonsense", which is a different message."""
        for kwargs in (
            {"revoked_at": timezone.now()},
            {"accepted_at": timezone.now()},
            {"expires_at": timezone.now() - dt.timedelta(days=1)},
        ):
            raw, _ = _make_invitation(self.org, f"x{len(kwargs)}@example.com", **kwargs)
            r = Client().get(f"/api/org/invitations/{raw}")
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.json()["valid"], kwargs)


# ---------------------------------------------------------------------------
# POST /api/org/invitations/{token}/accept
# ---------------------------------------------------------------------------


class AcceptInviteTests(OrgFixture):
    def setUp(self):
        super().setUp()
        # A paid firm plan, so acceptance is observable in the invitee's tier.
        Subscription.objects.create(
            org=self.org, plan=Tier.FIRM, status=Subscription.Status.ACTIVE, seats=5
        )
        self.invitee = make_user("invitee@example.com", tier=Tier.FREE)
        services.ensure_personal_org(self.invitee)
        self.raw, self.invitation = _make_invitation(
            self.org, "invitee@example.com", invited_by=self.owner
        )

    def test_accept_joins_the_org_syncs_the_tier_and_stamps_the_row(self):
        r = _json(_client(self.invitee), "post",
                  f"/api/org/invitations/{self.raw}/accept")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], self.org.pk)
        self.assertEqual(body["my_role"], "member")
        self.assertEqual(body["seats_used"], 4)

        self.assertTrue(
            OrgMembership.objects.filter(org=self.org, user=self.invitee).exists()
        )
        self.invitation.refresh_from_db()
        self.assertIsNotNone(self.invitation.accepted_at)
        # The org's plan flows to the new member through the derived tier cache.
        self.invitee.refresh_from_db()
        self.assertEqual(self.invitee.tier, Tier.FIRM)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.ORG_INVITE_ACCEPT, actor=self.invitee
            ).exists()
        )

    def test_accept_is_idempotent(self):
        client = _client(self.invitee)
        first = _json(client, "post", f"/api/org/invitations/{self.raw}/accept")
        second = _json(client, "post", f"/api/org/invitations/{self.raw}/accept")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            OrgMembership.objects.filter(org=self.org, user=self.invitee).count(), 1
        )

    def test_a_forwarded_link_cannot_be_redeemed_by_the_wrong_account(self):
        """The token alone is not enough: acceptance is bound to the invited
        address. This is the security boundary of the whole invite flow."""
        r = _json(_client(self.outsider), "post",
                  f"/api/org/invitations/{self.raw}/accept")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(
            OrgMembership.objects.filter(org=self.org, user=self.outsider).exists()
        )

    def test_anonymous_cannot_accept(self):
        r = Client().post(f"/api/org/invitations/{self.raw}/accept")
        self.assertEqual(r.status_code, 401)

    def test_unknown_token_is_404(self):
        r = _json(_client(self.invitee), "post", "/api/org/invitations/nope/accept")
        self.assertEqual(r.status_code, 404)

    def test_revoked_invitation_is_409(self):
        self.invitation.revoked_at = timezone.now()
        self.invitation.save(update_fields=["revoked_at"])
        r = _json(_client(self.invitee), "post",
                  f"/api/org/invitations/{self.raw}/accept")
        self.assertEqual(r.status_code, 409)
        self.assertFalse(
            OrgMembership.objects.filter(org=self.org, user=self.invitee).exists()
        )

    def test_expired_invitation_is_409(self):
        self.invitation.expires_at = timezone.now() - dt.timedelta(seconds=1)
        self.invitation.save(update_fields=["expires_at"])
        r = _json(_client(self.invitee), "post",
                  f"/api/org/invitations/{self.raw}/accept")
        self.assertEqual(r.status_code, 409)

    def test_registering_from_an_invite_link_joins_the_org(self):
        """The register payload's ``invite`` field is the same raw token — this is
        the flow the emailed link takes for someone with no account yet."""
        raw, _ = _make_invitation(self.org, "fresh@example.com", invited_by=self.owner)
        r = _json(Client(), "post", "/api/auth/register", {
            "email": "fresh@example.com",
            "password": "hunter2hunter2",
            "full_name": "Fresh Invitee",
            "invite": raw,
        })
        self.assertEqual(r.status_code, 200)
        fresh = User.objects.get(email="fresh@example.com")
        self.assertTrue(
            OrgMembership.objects.filter(org=self.org, user=fresh).exists()
        )
        self.assertEqual(r.json()["tier"], Tier.FIRM)

    def test_a_bad_invite_token_does_not_sink_registration(self):
        r = _json(Client(), "post", "/api/auth/register", {
            "email": "nobody@example.com",
            "password": "hunter2hunter2",
            "invite": "garbage",
        })
        self.assertEqual(r.status_code, 200)
        nobody = User.objects.get(email="nobody@example.com")
        self.assertEqual(services.orgs_for(nobody).count(), 1)  # just their own


# ---------------------------------------------------------------------------
# PATCH /api/org/members/{user_id}
# ---------------------------------------------------------------------------


class ChangeRoleTests(OrgFixture):
    def _patch(self, client, user, role):
        return _json(client, "patch", f"/api/org/members/{user.pk}", {"role": role})

    def test_owner_promotes_a_member(self):
        r = self._patch(self.owner_client, self.member, "admin")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            services.role_of(self.member, self.org), Role.ADMIN
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.ORG_ROLE_CHANGE, actor=self.owner
            ).exists()
        )

    def test_admin_cannot_change_roles(self):
        r = self._patch(self.admin_client, self.member, "admin")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(services.role_of(self.member, self.org), Role.MEMBER)

    def test_member_cannot_promote_themselves(self):
        r = self._patch(self.member_client, self.member, "owner")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(services.role_of(self.member, self.org), Role.MEMBER)

    def test_last_owner_cannot_be_demoted(self):
        r = self._patch(self.owner_client, self.owner, "member")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(services.role_of(self.owner, self.org), Role.OWNER)

    def test_owner_may_step_down_once_another_owner_exists(self):
        self._patch(self.owner_client, self.admin, "owner")
        r = self._patch(self.owner_client, self.owner, "member")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["my_role"], "member")

    def test_unknown_role_is_400(self):
        r = self._patch(self.owner_client, self.member, "root")
        self.assertEqual(r.status_code, 400)

    def test_non_member_is_404(self):
        r = self._patch(self.owner_client, self.outsider, "admin")
        self.assertEqual(r.status_code, 404)


# ---------------------------------------------------------------------------
# DELETE /api/org/members/{user_id}
# ---------------------------------------------------------------------------


class RemoveMemberTests(OrgFixture):
    def test_owner_removes_a_member_and_the_seat_goes_with_them(self):
        Subscription.objects.create(
            org=self.org, plan=Tier.FIRM, status=Subscription.Status.ACTIVE, seats=5
        )
        services.sync_org_tiers(self.org)
        self.member.refresh_from_db()
        self.assertEqual(self.member.tier, Tier.FIRM)

        r = self.owner_client.delete(f"/api/org/members/{self.member.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["seats_used"], 2)
        self.assertFalse(
            OrgMembership.objects.filter(org=self.org, user=self.member).exists()
        )
        # Losing the org loses the plan it granted.
        self.member.refresh_from_db()
        self.assertEqual(self.member.tier, Tier.FREE)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type=AuditEvent.Event.ORG_MEMBER_REMOVE, actor=self.owner
            ).exists()
        )

    def test_admin_removes_a_member(self):
        r = self.admin_client.delete(f"/api/org/members/{self.member.pk}")
        self.assertEqual(r.status_code, 200)

    def test_member_cannot_remove_anyone_else(self):
        r = self.member_client.delete(f"/api/org/members/{self.admin.pk}")
        self.assertEqual(r.status_code, 403)
        self.assertTrue(
            OrgMembership.objects.filter(org=self.org, user=self.admin).exists()
        )

    def test_member_can_leave_on_their_own(self):
        r = self.member_client.delete(f"/api/org/members/{self.member.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(
            OrgMembership.objects.filter(org=self.org, user=self.member).exists()
        )
        # …and the console they get back is their own org again.
        self.assertEqual(r.json()["id"], services.billing_org(self.member).pk)

    def test_last_owner_cannot_be_removed(self):
        r = self.owner_client.delete(f"/api/org/members/{self.owner.pk}")
        self.assertEqual(r.status_code, 409)
        self.assertTrue(
            OrgMembership.objects.filter(org=self.org, user=self.owner).exists()
        )

    def test_admin_cannot_remove_the_last_owner(self):
        r = self.admin_client.delete(f"/api/org/members/{self.owner.pk}")
        self.assertEqual(r.status_code, 409)

    def test_solo_user_cannot_orphan_their_personal_org(self):
        client = _client(self.outsider)
        org = services.billing_org(self.outsider)
        r = client.delete(f"/api/org/members/{self.outsider.pk}")
        self.assertEqual(r.status_code, 409)
        self.assertTrue(
            OrgMembership.objects.filter(org=org, user=self.outsider).exists()
        )

    def test_non_member_is_404(self):
        r = self.owner_client.delete(f"/api/org/members/{self.outsider.pk}")
        self.assertEqual(r.status_code, 404)
