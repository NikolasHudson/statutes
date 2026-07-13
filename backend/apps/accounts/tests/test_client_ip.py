"""Who the client is — the one answer every IP-keyed control in the app depends on.

``client_ip`` feeds the login lockout (django-axes, via AXES_CLIENT_IP_CALLABLE),
the registration throttle, the marketing lead throttle, and the ``source_ip`` on
every audit row. A wrong answer is not a cosmetic logging bug: it is a forged
audit trail, a lockout keyed on an address the attacker chose, and a throttle that
counts proxies instead of people. So these tests are adversarial first and
functional second (SECURITY_AUDIT_2026-07 finding #5).

The topology they encode was VERIFIED against prod on 2026-07-13, not assumed —
the previous model ("App Platform is a single edge hop") was assumed, and wrong:

    client -> Cloudflare (nick.law is orange-clouded) -> DO App Platform -> Django

Two appending proxies, not one. Hence the order of trust under test: a header
Cloudflare overwrites (unforgeable) beats a chain of hops nobody has counted.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.audit import AuditEvent, client_ip

REAL_CLIENT = "203.0.113.9"
# What the LAST appending proxy hands us: an edge address, never a person.
EDGE = "10.0.0.1"
# A Cloudflare egress address, i.e. what CF-Connecting-IP would collapse to if it
# were read on the marketing lead path (where CF sees the container as the client).
CF_EGRESS = "172.68.1.1"
TOKEN = "s3cret-token"


class ClientIpBaseTests(TestCase):
    """The fallback chain: X-Forwarded-For counted from the right, then REMOTE_ADDR."""

    def setUp(self):
        self.factory = RequestFactory()

    def _ip(self, path="/", **meta):
        return client_ip(self.factory.get(path, **meta))

    def test_falls_back_to_remote_addr_without_a_forwarded_header(self):
        self.assertEqual(self._ip(REMOTE_ADDR=REAL_CLIENT), REAL_CLIENT)

    def test_reads_the_entry_our_own_proxy_appended(self):
        self.assertEqual(
            self._ip(HTTP_X_FORWARDED_FOR=REAL_CLIENT, REMOTE_ADDR=EDGE), REAL_CLIENT
        )

    def test_client_cannot_forge_its_ip_with_a_forwarded_header(self):
        """Anyone can send ``X-Forwarded-For: 1.2.3.4``. Our edge APPENDS the address
        it accepted from rather than replacing it, so the header arrives as
        ``1.2.3.4, <real>`` — and the value we key throttles and audit rows on must
        be the address we observed, never the one the caller wrote. Padding the
        header to any length must not move the answer: the client is counted from
        the right, so an attacker can only ever prepend."""
        for forged in (
            "1.2.3.4",
            "1.2.3.4, 5.6.7.8",
            ", ".join(f"198.51.100.{n}" for n in range(1, 30)),
            "not-an-ip-at-all",
            "",
        ):
            with self.subTest(forged=forged):
                self.assertEqual(
                    self._ip(
                        HTTP_X_FORWARDED_FOR=f"{forged}, {REAL_CLIENT}",
                        REMOTE_ADDR=EDGE,
                    ),
                    REAL_CLIENT,
                )

    def test_junk_in_the_trusted_position_is_dropped_not_stored(self):
        """``source_ip``/``ip`` are inet columns: a non-address is a 500 on INSERT,
        so a header that isn't an IP literal must degrade, not propagate."""
        self.assertEqual(
            self._ip(HTTP_X_FORWARDED_FOR="'; DROP TABLE", REMOTE_ADDR=EDGE), EDGE
        )
        self.assertIsNone(self._ip(HTTP_X_FORWARDED_FOR="junk", REMOTE_ADDR="junk"))

    def test_ipv6_survives(self):
        # Not academic: prod's own edge answered an IPv6 client during recon.
        self.assertEqual(
            self._ip(HTTP_X_FORWARDED_FOR="2001:db8::1", REMOTE_ADDR=EDGE),
            "2001:db8::1",
        )

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_extra_trusted_hop_is_discounted(self):
        self.assertEqual(
            self._ip(
                HTTP_X_FORWARDED_FOR=f"1.2.3.4, {REAL_CLIENT}, {EDGE}",
                REMOTE_ADDR="10.0.0.2",
            ),
            REAL_CLIENT,
        )

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_header_shorter_than_our_chain_is_not_trusted_at_all(self):
        """A header that cannot have come through our proxies is one we cannot
        reason about — fall back to the connecting address, never to an entry the
        caller supplied."""
        self.assertEqual(
            self._ip(HTTP_X_FORWARDED_FOR="1.2.3.4", REMOTE_ADDR=EDGE), EDGE
        )

    def test_a_garbage_hop_count_does_not_take_the_app_down(self):
        with override_settings(TRUSTED_PROXY_COUNT="not-a-number"):
            self.assertEqual(
                self._ip(HTTP_X_FORWARDED_FOR=REAL_CLIENT, REMOTE_ADDR=EDGE),
                REAL_CLIENT,
            )

    def test_request_of_none_is_survivable(self):
        self.assertIsNone(client_ip(None))


class CloudflareTests(TestCase):
    """CF-Connecting-IP: the production control.

    Cloudflare OVERWRITES this header on ingress, so a browser cannot forge it, and
    unlike a hop count it does not depend on how many proxies append to XFF. It is
    only unforgeable where Cloudflare is actually in front — hence the switch, and
    hence the first test here.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def _ip(self, path="/", **meta):
        return client_ip(self.factory.get(path, **meta))

    def test_cf_header_is_ignored_when_we_do_not_trust_cloudflare(self):
        """Off by default. With no Cloudflare in front, CF-Connecting-IP is just a
        string a client typed — trusting it would hand anyone a free forgery."""
        self.assertEqual(
            self._ip(HTTP_CF_CONNECTING_IP="1.2.3.4", REMOTE_ADDR=REAL_CLIENT),
            REAL_CLIENT,
        )

    @override_settings(TRUST_CF_CONNECTING_IP=True)
    def test_cf_header_is_honoured_when_we_do(self):
        self.assertEqual(
            self._ip(HTTP_CF_CONNECTING_IP=REAL_CLIENT, REMOTE_ADDR=EDGE), REAL_CLIENT
        )

    @override_settings(TRUST_CF_CONNECTING_IP=True)
    def test_cf_header_beats_a_padded_forwarded_chain(self):
        """The real production shape. The attacker prepends junk to XFF; Cloudflare
        stamps the truth in a header they do not control. The hop count — which is
        the thing nobody has measured — never enters into it."""
        self.assertEqual(
            self._ip(
                HTTP_X_FORWARDED_FOR=f"1.2.3.4, 5.6.7.8, {CF_EGRESS}, {EDGE}",
                HTTP_CF_CONNECTING_IP=REAL_CLIENT,
                REMOTE_ADDR=EDGE,
            ),
            REAL_CLIENT,
        )

    @override_settings(TRUST_CF_CONNECTING_IP=True)
    def test_a_junk_cf_header_degrades_rather_than_propagating(self):
        self.assertEqual(
            self._ip(HTTP_CF_CONNECTING_IP="not-an-ip", REMOTE_ADDR=EDGE), EDGE
        )


@override_settings(MARKETING_PROXY_TOKEN=TOKEN)
class MarketingProxyTests(TestCase):
    """The marketing site relays leads SERVER-SIDE, so the visitor's address is not
    a property of the connection the backend sees. It is carried explicitly in
    X-Real-Client-IP and authenticated with a shared secret — and confined to
    /api/marketing/*, because a token that can assert a source IP must not be able
    to assert one against the login lockout or the audit trail."""

    CONTACT = "/api/marketing/contact"
    LOGIN = "/api/auth/login"

    def setUp(self):
        self.factory = RequestFactory()

    def _ip(self, path, **meta):
        return client_ip(self.factory.post(path, **meta))

    def test_forwarded_client_is_honoured_with_the_token_on_a_marketing_path(self):
        self.assertEqual(
            self._ip(
                self.CONTACT,
                HTTP_X_REAL_CLIENT_IP=REAL_CLIENT,
                HTTP_X_MARKETING_PROXY_TOKEN=TOKEN,
                REMOTE_ADDR=EDGE,
            ),
            REAL_CLIENT,
        )

    @override_settings(TRUST_CF_CONNECTING_IP=True)
    def test_the_asserted_client_beats_cloudflare_on_the_lead_path(self):
        """THE ordering that makes lead attribution work. On a proxied lead
        Cloudflare sees the MARKETING CONTAINER as the client, so CF-Connecting-IP
        is the container's egress address — read it first and every lead on earth
        keys to one bucket, which is the bug this replaces."""
        self.assertEqual(
            self._ip(
                self.CONTACT,
                HTTP_X_REAL_CLIENT_IP=REAL_CLIENT,
                HTTP_X_MARKETING_PROXY_TOKEN=TOKEN,
                HTTP_CF_CONNECTING_IP=CF_EGRESS,
                REMOTE_ADDR=EDGE,
            ),
            REAL_CLIENT,
        )

    def test_the_token_cannot_assert_an_ip_against_the_auth_surface(self):
        """Path scoping, as an attacker would exercise a leaked token. Even holding
        the VALID secret, an asserted address is ignored anywhere but the lead
        funnel — otherwise the token becomes a licence to forge audit rows and to
        lock out accounts from an address of the attacker's choosing."""
        for path in (self.LOGIN, "/api/auth/register", "/api/chat", "/"):
            with self.subTest(path=path):
                self.assertEqual(
                    self._ip(
                        path,
                        HTTP_X_REAL_CLIENT_IP="8.8.8.8",
                        HTTP_X_MARKETING_PROXY_TOKEN=TOKEN,
                        REMOTE_ADDR=REAL_CLIENT,
                    ),
                    REAL_CLIENT,
                )

    def test_a_marketing_prefix_lookalike_does_not_qualify(self):
        """Prefix matching is on /api/marketing/ — not on anything that merely
        starts with the letters."""
        self.assertEqual(
            self._ip(
                "/api/marketing-evil/contact",
                HTTP_X_REAL_CLIENT_IP="8.8.8.8",
                HTTP_X_MARKETING_PROXY_TOKEN=TOKEN,
                REMOTE_ADDR=REAL_CLIENT,
            ),
            REAL_CLIENT,
        )

    def test_without_the_token_the_asserted_ip_buys_nothing(self):
        self.assertEqual(
            self._ip(
                self.CONTACT, HTTP_X_REAL_CLIENT_IP="8.8.8.8", REMOTE_ADDR=REAL_CLIENT
            ),
            REAL_CLIENT,
        )

    def test_a_wrong_token_is_not_trusted(self):
        self.assertEqual(
            self._ip(
                self.CONTACT,
                HTTP_X_REAL_CLIENT_IP="8.8.8.8",
                HTTP_X_MARKETING_PROXY_TOKEN="s3cret-token-guess",
                REMOTE_ADDR=REAL_CLIENT,
            ),
            REAL_CLIENT,
        )

    @override_settings(MARKETING_PROXY_TOKEN="")
    def test_unset_token_ignores_the_header_entirely(self):
        """Dev sets no token; a header claiming otherwise must not enable the hop.
        (An empty expected secret must never compare equal to an empty presented
        one — that would make the whole thing opt-out.)"""
        self.assertEqual(
            self._ip(
                self.CONTACT,
                HTTP_X_REAL_CLIENT_IP="8.8.8.8",
                HTTP_X_MARKETING_PROXY_TOKEN="",
                REMOTE_ADDR=REAL_CLIENT,
            ),
            REAL_CLIENT,
        )

    def test_a_non_ascii_token_does_not_raise(self):
        """REGRESSION: hmac.compare_digest on two `str` raises TypeError as soon as
        either holds a character above U+007F, and Django decodes request headers as
        ISO-8859-1 — so one high byte in X-Marketing-Proxy-Token was a TypeError
        inside client_ip. That runs on EVERY login (django-axes) and inside
        record_event OUTSIDE its try/except, so any unauthenticated caller could 500
        login, registration and the lead forms the moment MARKETING_PROXY_TOKEN was
        set in prod. Latent only because the token is unset today, which is exactly
        why the suite was green. Compare bytes; never raise."""
        for hostile in ("t\xffken", "ÿ" * 32, "s3cret-tokén", "\x80"):
            with self.subTest(token=hostile):
                self.assertEqual(
                    self._ip(
                        self.CONTACT,
                        HTTP_X_REAL_CLIENT_IP="8.8.8.8",
                        HTTP_X_MARKETING_PROXY_TOKEN=hostile,
                        REMOTE_ADDR=REAL_CLIENT,
                    ),
                    REAL_CLIENT,
                )


@override_settings(MARKETING_PROXY_TOKEN=TOKEN)
class NonAsciiTokenIsNotA500Test(TestCase):
    """The same regression, end to end and unauthenticated: the crash was reachable
    by anyone who could POST to /api/auth/login with one hostile header."""

    def test_login_survives_a_hostile_proxy_token_header(self):
        resp = self.client.post(
            "/api/auth/login",
            data='{"email": "nobody@example.com", "password": "whatever-12345"}',
            content_type="application/json",
            HTTP_X_MARKETING_PROXY_TOKEN="t\xffken",
            REMOTE_ADDR=REAL_CLIENT,
        )
        # 401 (bad credentials) is fine, 429 (axes) is fine — a 500 is the bug.
        self.assertNotEqual(resp.status_code, 500, resp.content)
        self.assertIn(resp.status_code, (401, 429), resp.content)

    def test_register_survives_a_hostile_proxy_token_header(self):
        resp = self.client.post(
            "/api/auth/register",
            data='{"email": "hostile@example.com", "password": "longenough-12"}',
            content_type="application/json",
            HTTP_X_MARKETING_PROXY_TOKEN="t\xffken",
            REMOTE_ADDR=REAL_CLIENT,
        )
        self.assertNotEqual(resp.status_code, 500, resp.content)
        # And the audit row still records the address we OBSERVED.
        row = AuditEvent.objects.get(
            event_type=AuditEvent.Event.REGISTER, actor_email="hostile@example.com"
        )
        self.assertEqual(row.source_ip, REAL_CLIENT)


class RegistrationThrottleForgeryTests(TestCase):
    """End-to-end proof of the finding's impact: rotating a client-controlled header
    used to mint a fresh throttle bucket per request, defeating the 10/hour
    registration cap outright (mass account creation / enumeration probing)."""

    PASSWORD = "correct-horse-battery-staple"

    def setUp(self):
        cache.clear()  # the throttle counter is a cache key, shared across tests

    def _register(self, email: str, **meta):
        return self.client.post(
            "/api/auth/register",
            data={"email": email, "password": self.PASSWORD},
            content_type="application/json",
            **meta,
        )

    def test_rotating_the_forwarded_header_cannot_buy_a_fresh_bucket(self):
        statuses = [
            self._register(
                f"probe{n}@example.com",
                # The attacker writes the left of the header; the edge appends the
                # address it actually saw.
                HTTP_X_FORWARDED_FOR=f"10.9.9.{n}, {REAL_CLIENT}",
                REMOTE_ADDR=EDGE,
            ).status_code
            for n in range(1, 13)
        ]
        self.assertEqual(statuses.count(200), 10, statuses)  # _REGISTER_MAX_PER_HOUR
        self.assertEqual(statuses[-1], 429, statuses)

    @override_settings(TRUST_CF_CONNECTING_IP=True)
    def test_rotating_the_cf_header_cannot_buy_a_fresh_bucket(self):
        """Cloudflare overwrites CF-Connecting-IP, so in prod the value under test
        here cannot arrive from the client at all — but if it ever could, it must not
        be a throttle bypass. The request is what an attacker sends; the assertion is
        that only the address CLOUDFLARE stamped counts."""
        statuses = [
            self._register(
                f"cfprobe{n}@example.com",
                HTTP_CF_CONNECTING_IP=REAL_CLIENT,  # what CF actually stamped
                HTTP_X_FORWARDED_FOR=f"10.9.9.{n}",  # what the attacker rotates
                REMOTE_ADDR=EDGE,
            ).status_code
            for n in range(1, 13)
        ]
        self.assertEqual(statuses.count(200), 10, statuses)
        self.assertEqual(statuses[-1], 429, statuses)

    @override_settings(MARKETING_PROXY_TOKEN=TOKEN)
    def test_rotating_an_asserted_client_ip_cannot_buy_a_fresh_bucket(self):
        """Even holding the marketing secret, /api/auth/register is not a path where
        an asserted address is honoured — so the cap still binds."""
        statuses = [
            self._register(
                f"assert{n}@example.com",
                HTTP_X_REAL_CLIENT_IP=f"10.9.9.{n}",
                HTTP_X_MARKETING_PROXY_TOKEN=TOKEN,
                REMOTE_ADDR=REAL_CLIENT,
            ).status_code
            for n in range(1, 13)
        ]
        self.assertEqual(statuses.count(200), 10, statuses)
        self.assertEqual(statuses[-1], 429, statuses)

    def test_the_audit_row_records_the_observed_ip_not_the_claimed_one(self):
        self._register(
            "audited@example.com",
            HTTP_X_FORWARDED_FOR=f"8.8.8.8, {REAL_CLIENT}",
            REMOTE_ADDR=EDGE,
        )
        row = AuditEvent.objects.get(
            event_type=AuditEvent.Event.REGISTER, actor_email="audited@example.com"
        )
        self.assertEqual(row.source_ip, REAL_CLIENT)


@override_settings(
    AXES_ENABLED=True, AXES_FAILURE_LIMIT=3, TRUST_CF_CONNECTING_IP=True
)
class LockoutIsKeyedOnTheRealClientTests(TestCase):
    """The blast radius that made this critical. AXES_LOCKOUT_PARAMETERS is
    [["ip_address", "username"]] — if client_ip returns a near-constant proxy
    address, the lockout degenerates to per-username: a handful of failures from
    ANYWHERE lock any named account, and the attacker's real address is never
    recorded. So the lockout must key on the address Cloudflare stamped, and one
    client's failures must not lock out another's."""

    PASSWORD = "correct-horse-battery-staple"

    def setUp(self):
        from axes.handlers.proxy import AxesProxyHandler
        from axes.models import AccessAttempt

        AxesProxyHandler.reset_attempts()
        AccessAttempt.objects.all().delete()
        cache.clear()
        from apps.accounts.models import User

        User.objects.create_user(email="victim@example.com", password=self.PASSWORD)

    def _login(self, password, cf_ip):
        return self.client.post(
            "/api/auth/login",
            data=f'{{"email": "victim@example.com", "password": "{password}"}}',
            content_type="application/json",
            HTTP_CF_CONNECTING_IP=cf_ip,
            # Same padded chain every time: it must not be what keys the lockout.
            HTTP_X_FORWARDED_FOR=f"1.2.3.4, {CF_EGRESS}, {EDGE}",
            REMOTE_ADDR=EDGE,
        )

    def test_one_clients_failures_do_not_lock_out_another_client(self):
        attacker = "198.51.100.77"
        for _ in range(4):
            self._login("wrong-password-xx", cf_ip=attacker)
        # The attacker's own address is now locked...
        self.assertEqual(
            self._login(self.PASSWORD, cf_ip=attacker).status_code, 429
        )
        # ...but an innocent user on a DIFFERENT address, with the SAME account and
        # the SAME (padded, constant) XFF chain, can still sign in. If client_ip
        # collapsed everyone onto a proxy address, this would be a 429 and the
        # lockout would be a denial-of-service primitive against any known email.
        ok = self._login(self.PASSWORD, cf_ip=REAL_CLIENT)
        self.assertEqual(ok.status_code, 200, ok.content)
