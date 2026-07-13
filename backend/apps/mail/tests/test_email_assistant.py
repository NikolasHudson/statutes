"""Email-assistant surface tests: the inbound webhook's parse/dedupe/routing
and the worker pipeline's gate ordering, threading, and reply mechanics.

``run_chat_turn`` is mocked throughout — the LLM loop has its own suite
(apps/api/tests/test_chat.py); these tests pin the email wrapper around it:
who gets an answer, who gets silence, what the reply carries, and what state
is left behind.
"""

from __future__ import annotations

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.corpus.models import Jurisdiction
from apps.mail.models import (
    AddressAllowlist,
    AssistantAddress,
    EmailThread,
    InboundEmail,
    OutboundEmail,
)
from apps.mail.services import claim_pending, process_inbound
from apps.tenancy.models import Product

User = get_user_model()

WEBHOOK = "/api/email/inbound"
TOKEN = "test-webhook-token"

LOCMEM_EMAIL = "django.core.mail.backends.locmem.EmailBackend"


def postmark_payload(**overrides):
    """A realistic Postmark inbound webhook document (abridged)."""
    payload = {
        "MessageID": "pm-message-1",
        "From": "lawyer@example.com",
        "FromFull": {"Email": "lawyer@example.com", "Name": "Ada Lawyer"},
        "To": "assistant@mail.nick.law",
        "ToFull": [{"Email": "assistant@mail.nick.law", "Name": ""}],
        "OriginalRecipient": "assistant@mail.nick.law",
        "MailboxHash": "",
        "Subject": "Mechanics lien priority",
        "TextBody": "Full body\n> quoted stuff",
        "StrippedTextReply": "What is the lien priority rule in Iowa?",
        "Headers": [
            {"Name": "Message-ID", "Value": "<orig-1@example.com>"},
            {"Name": "Received-SPF", "Value": "pass (sender authorized)"},
            {
                "Name": "Authentication-Results",
                "Value": "spf=pass; dkim=pass header.d=example.com",
            },
        ],
        "Attachments": [],
    }
    payload.update(overrides)
    return payload


@override_settings(EMAIL_INBOUND_WEBHOOK_TOKEN=TOKEN)
class InboundWebhookTests(TestCase):
    def setUp(self):
        self.address = AssistantAddress.objects.create(
            address="assistant@mail.nick.law"
        )

    def post(self, payload, token=TOKEN):
        return self.client.post(
            f"{WEBHOOK}?token={token}",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_requires_token(self):
        response = self.post(postmark_payload(), token="wrong")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(InboundEmail.objects.count(), 0)

    @override_settings(EMAIL_INBOUND_WEBHOOK_TOKEN="")
    def test_unconfigured_returns_503(self):
        response = self.post(postmark_payload())
        self.assertEqual(response.status_code, 503)

    def test_stores_pending_row_with_parsed_fields(self):
        response = self.post(postmark_payload())
        self.assertEqual(response.status_code, 200)
        row = InboundEmail.objects.get()
        self.assertEqual(row.status, InboundEmail.Status.PENDING)
        self.assertEqual(row.address, self.address)
        self.assertEqual(row.from_email, "lawyer@example.com")
        self.assertEqual(row.rfc_message_id, "<orig-1@example.com>")
        self.assertTrue(row.spf_pass)
        self.assertTrue(row.dkim_pass)
        self.assertFalse(row.is_auto_generated)
        # StrippedTextReply preferred over the quoted full body.
        self.assertEqual(row.body_text, "What is the lien priority rule in Iowa?")

    def test_duplicate_delivery_is_idempotent(self):
        self.post(postmark_payload())
        response = self.post(postmark_payload())
        self.assertTrue(response.json()["duplicate"])
        self.assertEqual(InboundEmail.objects.count(), 1)

    def test_plus_tag_routes_to_base_address_with_hash(self):
        payload = postmark_payload(
            OriginalRecipient="assistant+t12ab34cd9@mail.nick.law",
            MailboxHash="t12ab34cd9",
        )
        self.post(payload)
        row = InboundEmail.objects.get()
        self.assertEqual(row.address, self.address)
        self.assertEqual(row.mailbox_hash, "t12ab34cd9")

    def test_unknown_recipient_dead_letters(self):
        payload = postmark_payload(OriginalRecipient="nobody@mail.nick.law")
        self.post(payload)
        row = InboundEmail.objects.get()
        self.assertEqual(row.status, InboundEmail.Status.IGNORED)
        self.assertIsNone(row.address)

    def test_attachment_content_never_stored(self):
        payload = postmark_payload(
            Attachments=[
                {
                    "Name": "smith-v-jones.pdf",
                    "Content": "QkFTRTY0",
                    "ContentType": "application/pdf",
                    "ContentLength": 8,
                }
            ]
        )
        self.post(payload)
        row = InboundEmail.objects.get()
        stored = row.raw_payload["Attachments"][0]
        self.assertNotIn("Content", stored)
        self.assertEqual(stored["Name"], "smith-v-jones.pdf")

    def test_auto_submitted_flagged(self):
        payload = postmark_payload(
            Headers=[{"Name": "Auto-Submitted", "Value": "auto-replied"}]
        )
        self.post(payload)
        self.assertTrue(InboundEmail.objects.get().is_auto_generated)


ANSWER = ("Iowa Code § 572.18 governs priority. [advisory omitted]", "gpt-5-mini")


@override_settings(
    EMAIL_BACKEND=LOCMEM_EMAIL,
    EMAIL_INBOUND_WEBHOOK_TOKEN=TOKEN,
    OPENAI_API_KEY="sk-test",
)
class ProcessingTests(TestCase):
    def setUp(self):
        cache.clear()  # quota + notice counters are cache-backed
        self.user = User.objects.create_user(
            email="lawyer@example.com", password="pw"
        )
        self.address = AssistantAddress.objects.create(
            address="assistant@mail.nick.law",
            mode=AssistantAddress.Mode.ALLOWLIST,
        )
        AddressAllowlist.objects.create(
            address=self.address, email="lawyer@example.com"
        )

    def make_inbound(self, **overrides):
        fields = {
            "provider_id": f"pm-{InboundEmail.objects.count() + 1}",
            "rfc_message_id": "<orig-1@example.com>",
            "address": self.address,
            "from_email": "lawyer@example.com",
            "to_email": "assistant@mail.nick.law",
            "subject": "Lien priority",
            "body_text": "What is the lien priority rule?",
            "spf_pass": True,
            "dkim_pass": True,
        }
        fields.update(overrides)
        return InboundEmail.objects.create(**fields)

    def process(self, inbound):
        """Claim-then-process, as the worker does."""
        claimed = claim_pending()
        self.assertIn(inbound.pk, [r.pk for r in claimed])
        row = next(r for r in claimed if r.pk == inbound.pk)
        process_inbound(row)
        inbound.refresh_from_db()
        return inbound

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_happy_path_sends_threaded_reply(self, turn):
        inbound = self.process(self.make_inbound())

        self.assertEqual(inbound.status, InboundEmail.Status.ANSWERED)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["lawyer@example.com"])
        self.assertEqual(sent.subject, "Re: Lien priority")
        self.assertIn("572.18", sent.body)
        self.assertIn("not legal advice", sent.body.lower())
        self.assertEqual(sent.extra_headers["In-Reply-To"], "<orig-1@example.com>")

        thread = EmailThread.objects.get()
        self.assertEqual(thread.user, self.user)
        self.assertEqual(thread.turn_count, 1)
        self.assertEqual(
            [m["role"] for m in thread.messages], ["user", "assistant"]
        )
        # Reply-To carries the plus-token so any client's reply finds the thread.
        self.assertEqual(
            sent.reply_to, [f"assistant+{thread.token}@mail.nick.law"]
        )
        self.assertIn(thread.token, sent.body)

        outbound = OutboundEmail.objects.get()
        self.assertEqual(outbound.thread, thread)
        self.assertTrue(outbound.message_id)

        turn.assert_called_once()
        kwargs = turn.call_args.kwargs
        self.assertIsNone(kwargs["source_slug"])  # flagship = unscoped
        self.assertEqual(
            kwargs["messages"],
            [{"role": "user", "content": "What is the lien priority rule?"}],
        )

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_reply_continues_thread_via_mailbox_hash(self, turn):
        thread = EmailThread.objects.create(
            address=self.address,
            user=self.user,
            messages=[
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": "a1"},
            ],
            turn_count=1,
        )
        inbound = self.process(
            self.make_inbound(
                mailbox_hash=thread.token, body_text="What about an LLC?"
            )
        )
        self.assertEqual(inbound.status, InboundEmail.Status.ANSWERED)
        self.assertEqual(EmailThread.objects.count(), 1)
        # History replayed: prior exchange + the new question.
        self.assertEqual(
            [m["content"] for m in turn.call_args.kwargs["messages"]],
            ["q1", "a1", "What about an LLC?"],
        )
        thread.refresh_from_db()
        self.assertEqual(thread.turn_count, 2)
        self.assertEqual(len(thread.messages), 4)

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_reply_continues_thread_via_references_header(self, turn):
        thread = EmailThread.objects.create(address=self.address, user=self.user)
        OutboundEmail.objects.create(
            thread=thread, message_id="<out-1@mail.nick.law>", subject="Re: x"
        )
        inbound = self.process(
            self.make_inbound(in_reply_to="<out-1@mail.nick.law>")
        )
        inbound.refresh_from_db()
        self.assertEqual(inbound.thread, thread)

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_anothers_thread_token_is_not_joinable(self, turn):
        other = User.objects.create_user(email="other@example.com", password="pw")
        others_thread = EmailThread.objects.create(
            address=self.address,
            user=other,
            messages=[{"role": "user", "content": "confidential"}],
        )
        inbound = self.process(self.make_inbound(mailbox_hash=others_thread.token))
        self.assertEqual(inbound.status, InboundEmail.Status.ANSWERED)
        # A fresh thread was created; the other user's history never replayed.
        self.assertNotEqual(inbound.thread, others_thread)
        self.assertEqual(
            turn.call_args.kwargs["messages"],
            [{"role": "user", "content": "What is the lien priority rule?"}],
        )

    # -- Silent-drop gates ---------------------------------------------------

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_failed_sender_auth_is_silently_ignored(self, turn):
        inbound = self.process(self.make_inbound(spf_pass=False, dkim_pass=None))
        self.assertEqual(inbound.status, InboundEmail.Status.IGNORED)
        self.assertEqual(inbound.reject_reason, "sender failed SPF/DKIM")
        self.assertEqual(len(mail.outbox), 0)
        turn.assert_not_called()

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_auto_generated_never_answered(self, turn):
        inbound = self.process(self.make_inbound(is_auto_generated=True))
        self.assertEqual(inbound.status, InboundEmail.Status.IGNORED)
        self.assertEqual(len(mail.outbox), 0)

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_unregistered_sender_ignored(self, turn):
        inbound = self.process(self.make_inbound(from_email="stranger@example.com"))
        self.assertEqual(inbound.status, InboundEmail.Status.IGNORED)
        self.assertEqual(len(mail.outbox), 0)

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_not_on_allowlist_ignored(self, turn):
        AddressAllowlist.objects.all().delete()
        inbound = self.process(self.make_inbound())
        self.assertEqual(inbound.status, InboundEmail.Status.IGNORED)
        self.assertEqual(inbound.reject_reason, "not on allowlist")
        self.assertEqual(len(mail.outbox), 0)

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_per_sender_daily_cap(self, turn):
        self.address.max_daily_per_sender = 1
        self.address.save()
        self.process(self.make_inbound())
        second = self.process(self.make_inbound())
        self.assertEqual(second.status, InboundEmail.Status.IGNORED)
        self.assertEqual(second.reject_reason, "per-sender daily cap")
        self.assertEqual(len(mail.outbox), 1)  # only the first got an answer

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_stop_suppresses_thread(self, turn):
        thread = EmailThread.objects.create(address=self.address, user=self.user)
        inbound = self.process(
            self.make_inbound(mailbox_hash=thread.token, body_text="STOP")
        )
        self.assertEqual(inbound.status, InboundEmail.Status.IGNORED)
        thread.refresh_from_db()
        self.assertEqual(thread.status, EmailThread.Status.SUPPRESSED)
        self.assertEqual(len(mail.outbox), 0)
        # And a later reply on the suppressed thread stays silent.
        later = self.process(self.make_inbound(mailbox_hash=thread.token))
        self.assertEqual(later.status, InboundEmail.Status.IGNORED)
        self.assertEqual(len(mail.outbox), 0)

    # -- Notice gates ----------------------------------------------------------

    @override_settings(CHAT_DAILY_USER_LIMIT=0)
    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_quota_exceeded_notifies_once_per_day(self, turn):
        first = self.process(self.make_inbound())
        self.assertEqual(first.status, InboundEmail.Status.REJECTED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("limit", mail.outbox[0].body.lower())
        turn.assert_not_called()

        second = self.process(self.make_inbound())
        self.assertEqual(second.status, InboundEmail.Status.REJECTED)
        self.assertEqual(len(mail.outbox), 1)  # no second notice

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_scoped_product_entitlement_and_clamp(self, turn):
        jurisdiction, _ = Jurisdiction.objects.get_or_create(
            slug="iowa", defaults={"name": "Iowa", "abbreviation": "IA"}
        )
        product = Product.objects.create(
            slug="iowa-ethics-procedure",
            name="Iowa Ethics & Procedure",
            jurisdiction=jurisdiction,
            allowed_source_slugs=["iowa-court-rules"],
        )
        ethics = AssistantAddress.objects.create(
            address="ethics@mail.nick.law",
            product=product,
            mode=AssistantAddress.Mode.ENTITLED,
        )

        # FREE tier, no subscription: rejected with a notice.
        inbound = self.process(
            self.make_inbound(address=ethics, to_email="ethics@mail.nick.law")
        )
        self.assertEqual(inbound.status, InboundEmail.Status.REJECTED)
        self.assertEqual(inbound.reject_reason, "not entitled")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("access", mail.outbox[0].body.lower())
        turn.assert_not_called()

        # Full-corpus PLAN: answered, and the search scope is clamped to the
        # product's sources — the email surface honors the same lock as chat.
        # Entitlement reads billing state (apps.tenancy.services.effective_plan),
        # not the derived ``user.tier`` column, so give the user a real solo
        # subscription on their personal org rather than just flipping the cache.
        from apps.accounts.models import Tier
        from apps.tenancy.models import Subscription
        from apps.tenancy.services import ensure_personal_org, sync_user_tier

        Subscription.objects.create(
            org=ensure_personal_org(self.user),
            product=None,  # NULL = the flagship full-corpus plan
            plan=Tier.SOLO,
            status=Subscription.Status.ACTIVE,
        )
        sync_user_tier(self.user)
        self.user.refresh_from_db()
        answered = self.process(
            self.make_inbound(address=ethics, to_email="ethics@mail.nick.law")
        )
        self.assertEqual(answered.status, InboundEmail.Status.ANSWERED)
        self.assertEqual(
            turn.call_args.kwargs["source_slug"], "iowa-court-rules"
        )

    # -- Failure handling -------------------------------------------------------

    @mock.patch("apps.mail.services.run_chat_turn")
    def test_turn_failure_retries_then_notifies(self, turn):
        from apps.api.chat import ChatTurnError

        turn.side_effect = ChatTurnError("OpenAI call failed: APIError", trace=[])
        inbound = self.make_inbound()

        for attempt in (1, 2):
            inbound = self.process(inbound)
            self.assertEqual(inbound.status, InboundEmail.Status.PENDING)
            self.assertEqual(inbound.attempts, attempt)
            self.assertGreater(inbound.next_attempt_at, timezone.now())
            self.assertEqual(len(mail.outbox), 0)
            # Backoff means it is not claimable yet; fast-forward for the test.
            inbound.next_attempt_at = timezone.now()
            inbound.save(update_fields=["next_attempt_at"])

        final = self.process(inbound)
        self.assertEqual(final.status, InboundEmail.Status.FAILED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("wasn't able to complete", mail.outbox[0].body)

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_empty_body_ignored(self, turn):
        inbound = self.process(self.make_inbound(body_text="   "))
        self.assertEqual(inbound.status, InboundEmail.Status.IGNORED)
        turn.assert_not_called()

    # -- Body selection (forwards vs replies) -----------------------------------

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_forwarded_email_uses_full_body_not_stripped(self, turn):
        """An attorney forwarding a client email types a one-line cover note;
        Postmark's StrippedTextReply strips the forwarded material as if it
        were a quoted chain. The model must see the whole thing."""
        full = (
            "Can we help? What claims do they have if anything?\n\n"
            "---------- Forwarded message ---------\n"
            "From: Sarah Jenkins\n\n"
            "A pipe burst and black mold has grown all over the drywall..."
        )
        inbound = self.process(
            self.make_inbound(
                subject="Fwd: need legal help",
                body_text="Can we help? What claims do they have if anything?",
                raw_payload={
                    "StrippedTextReply": "Can we help? What claims do they have if anything?",
                    "TextBody": full,
                },
            )
        )
        self.assertEqual(inbound.status, InboundEmail.Status.ANSWERED)
        sent_body = turn.call_args.kwargs["messages"][-1]["content"]
        self.assertIn("black mold", sent_body)

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_forward_with_no_cover_note_still_answered(self, turn):
        """Forward without typing anything: StrippedTextReply is empty, but
        the message must not be dropped as 'empty body'."""
        inbound = self.process(
            self.make_inbound(
                body_text="",
                raw_payload={
                    "StrippedTextReply": "",
                    "TextBody": "Begin forwarded message\nclient facts here",
                },
            )
        )
        self.assertEqual(inbound.status, InboundEmail.Status.ANSWERED)
        self.assertIn(
            "client facts",
            turn.call_args.kwargs["messages"][-1]["content"],
        )

    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_in_thread_reply_still_uses_stripped_text(self, turn):
        """Replies inside a thread keep the stripped form so our own quoted
        answer isn't re-fed (it's already in the thread history)."""
        thread = EmailThread.objects.create(
            address=self.address, user=self.user,
            messages=[{"role": "user", "content": "q1"},
                      {"role": "assistant", "content": "a1"}],
        )
        self.process(
            self.make_inbound(
                mailbox_hash=thread.token,
                body_text="What about an LLC?",
                raw_payload={
                    "StrippedTextReply": "What about an LLC?",
                    "TextBody": "What about an LLC?\n\n> On Jul 9 the assistant wrote:\n> a1",
                },
            )
        )
        self.assertEqual(
            turn.call_args.kwargs["messages"][-1]["content"], "What about an LLC?"
        )

    # -- Rich rendering ---------------------------------------------------------

    @mock.patch("apps.mail.services.run_chat_turn")
    def test_reply_carries_linked_html_alternative(self, turn):
        from apps.api.tests._factories import make_iowa_corpus_minimal

        _, section, _ = make_iowa_corpus_minimal()
        turn.return_value = ("See Iowa Code § 714.16 for the rule.", "gpt-5-mini")
        self.process(self.make_inbound())

        sent = mail.outbox[0]
        # Plaintext part: untouched prose + a Sources list with raw URLs.
        self.assertIn("See Iowa Code § 714.16 for the rule.", sent.body)
        self.assertIn(f"https://app.hudsonlegal.tech/section/{section.id}", sent.body)
        self.assertIn("official PDF: https://www.legis.iowa.gov", sent.body)
        # HTML part: inline anchor on the citation.
        ((html_body, mimetype),) = sent.alternatives
        self.assertEqual(mimetype, "text/html")
        self.assertIn(f'href="https://app.hudsonlegal.tech/section/{section.id}"', html_body)

    @mock.patch("apps.mail.services.render.requests.get")
    @mock.patch("apps.mail.services.run_chat_turn", return_value=ANSWER)
    def test_pdf_attached_only_on_express_request(self, turn, get):
        from apps.api.tests._factories import make_iowa_corpus_minimal

        make_iowa_corpus_minimal()
        get.return_value = mock.Mock(status_code=200, content=b"%PDF-1.7 fake")

        # No "pdf" in the question: no attachment, no fetch.
        self.process(self.make_inbound(body_text="What does Iowa Code § 714.16 say?"))
        self.assertEqual(mail.outbox[0].attachments, [])
        get.assert_not_called()

        # Express request: the official PDF rides along.
        self.process(
            self.make_inbound(
                body_text="Please send the PDF of Iowa Code § 714.16."
            )
        )
        (attachment,) = mail.outbox[1].attachments
        self.assertEqual(attachment[0], "Iowa Code 714.16.pdf")
        self.assertEqual(attachment[2], "application/pdf")
