"""Cookie scoping — the settings invariant that keeps tenants apart.

This lives in ``apps.tenancy`` rather than next to some settings test because it
is a *tenancy* rule, not a config preference: the app now answers on a
multi-tenant apex, so which hosts a session cookie is sent to decides which
tenants can read a session. The rule is enforced in ``core/settings.py``, and
until now it held only BY OMISSION — nothing named it, so nothing protected it.

Two things are pinned:

  1. SESSION_COOKIE_DOMAIN / CSRF_COOKIE_DOMAIN stay None.
  2. The cookie NAMES carry the ``__Host-`` prefix in prod and not in dev.

(2) needs care. ``core/settings.py`` sets the ``__Host-`` names inside
``if not DEBUG:``, so the branch is chosen ONCE, at module import, from the
environment. Django's test runner then forces ``settings.DEBUG = False`` at
runtime without re-executing the module — so under dev's ``DEBUG=True`` .env a
test that read ``django.conf.settings`` would see ``DEBUG`` False alongside the
*dev* cookie names and conclude, wrongly, that prod is broken. The only honest
way to test a DEBUG-conditional is to re-execute the module under each value,
which is what ``_load_settings`` does.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

SETTINGS_PATH = Path(settings.BASE_DIR) / "core" / "settings.py"

# What a browser hands back when we never set a name (django.conf.global_settings).
DJANGO_DEFAULT_SESSION_COOKIE = "sessionid"
DJANGO_DEFAULT_CSRF_COOKIE = "csrftoken"

_UNSET = object()


def _load_settings(*, debug: bool) -> ModuleType:
    """Execute core/settings.py in a throwaway module with DEBUG forced.

    Loaded under a private module name so the real ``core.settings`` — which
    ``django.conf.settings`` is already bound to — is left untouched. Forcing
    the value through os.environ works because ``read_env`` defaults to
    ``overwrite=False``: a var already in the environment beats the .env file.
    """
    spec = importlib.util.spec_from_file_location(
        f"_cookie_probe_settings_debug_{debug}", SETTINGS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, {"DEBUG": str(debug)}):
        spec.loader.exec_module(module)
    return module


class CookieDomainInvariantTests(SimpleTestCase):
    """Neither cookie may ever carry a Domain attribute."""

    # Written as one message because whoever trips this test is one line away
    # from shipping the break, and needs to be told what the line does.
    WHY = (
        "\n\n"
        "SESSION_COOKIE_DOMAIN / CSRF_COOKIE_DOMAIN must stay None.\n\n"
        "Setting a dot-domain (Domain=.hudsonlegal.tech) is a one-line, silent, "
        "catastrophic tenant-isolation break: the browser would then send the "
        "flagship session cookie to EVERY sibling subdomain of the apex — every "
        "current tenant host, every future white-label host, and anything else "
        "that ever resolves under it, including a host we do not operate. One "
        "such host reading that cookie is full account takeover across the "
        "whole apex. It also makes any sibling able to overwrite our cookies "
        "(cookie tossing).\n\n"
        "There is no valid reason to set this. Cross-subdomain SSO is not one — "
        "solve that with a token exchange, not by widening the cookie. Note the "
        "prod cookie names use the __Host- prefix, which FORBIDS Domain outright: "
        "a browser silently rejects a __Host- cookie that carries one, so in prod "
        "this change does not merely leak the session, it breaks login too."
    )

    def test_session_cookie_domain_is_none(self):
        self.assertIsNone(settings.SESSION_COOKIE_DOMAIN, self.WHY)

    def test_csrf_cookie_domain_is_none(self):
        self.assertIsNone(settings.CSRF_COOKIE_DOMAIN, self.WHY)

    def test_neither_debug_branch_sets_a_cookie_domain(self):
        # The live settings above are only ever the branch this box booted. Both
        # branches have to hold, or the invariant is merely dormant in dev and
        # broken in prod (or the reverse).
        for debug in (True, False):
            module = _load_settings(debug=debug)
            for name in ("SESSION_COOKIE_DOMAIN", "CSRF_COOKIE_DOMAIN"):
                value = getattr(module, name, _UNSET)
                self.assertIn(
                    value, (_UNSET, None), f"{name} with DEBUG={debug}{self.WHY}"
                )


class HostCookiePrefixTests(SimpleTestCase):
    """The __Host- prefix is prod-only, and getting that backwards fails silently.

    Both directions are load-bearing, and neither raises:
      * prefix leaking into dev — the browser drops a __Host- cookie that isn't
        Secure, and dev is plain HTTP, so login just stops working, no error.
      * prefix missing in prod — we lose the anti-cookie-tossing guarantee and
        nothing anywhere says so.
    """

    def test_prod_cookies_carry_host_prefix(self):
        prod = _load_settings(debug=False)
        self.assertEqual(prod.SESSION_COOKIE_NAME, "__Host-sessionid")
        self.assertEqual(prod.CSRF_COOKIE_NAME, "__Host-csrftoken")

    def test_prod_host_prefix_is_backed_by_its_preconditions(self):
        # The prefix is a contract, not a naming convention: the browser accepts
        # a __Host- cookie only if it is Secure, Path=/, and Domain-less. Assert
        # the two we set explicitly (Domain is covered above; Path=/ is Django's
        # default and not overridden).
        prod = _load_settings(debug=False)
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.CSRF_COOKIE_SECURE)

    def test_dev_cookies_have_no_host_prefix(self):
        # settings.py doesn't set these names under DEBUG at all — it leaves
        # Django's defaults standing. Assert the effective outcome rather than
        # the omission, since that is what the browser sees.
        dev = _load_settings(debug=True)
        self.assertEqual(
            getattr(dev, "SESSION_COOKIE_NAME", DJANGO_DEFAULT_SESSION_COOKIE),
            DJANGO_DEFAULT_SESSION_COOKIE,
        )
        self.assertEqual(
            getattr(dev, "CSRF_COOKIE_NAME", DJANGO_DEFAULT_CSRF_COOKIE),
            DJANGO_DEFAULT_CSRF_COOKIE,
        )
        self.assertFalse(getattr(dev, "SESSION_COOKIE_SECURE", False))
