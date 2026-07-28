"""Register (or re-point) the first-party OAuth client for the EDMSpro extension.

The extension is a **public** OAuth client — it ships to users' machines, so it
can hold no secret and authenticates with PKCE alone. It is deliberately NOT
created through the open Dynamic Client Registration endpoint that Claude
Desktop uses: a first-party client with a fixed ``client_id`` and a pinned
redirect URI is one we can reason about, whereas a self-registered row would
mean the extension's identity depended on whichever registration happened to
run last.

The redirect URI is Chrome's ``https://<extension-id>.chromiumapp.org/``, which
``chrome.identity.launchWebAuthFlow`` intercepts. It is a plain HTTPS URL, so it
passes the OAuth 2.1 redirect validation unchanged (only ``chrome-extension://``
scheme URIs are rejected, and this flow never uses one).

Pin ``key`` in the extension's ``manifest.json`` before running this: without it
Chrome derives a different extension id on every machine, and the redirect URI
below would only work on the box it was seeded from.

    ./manage.py seed_edms_oauth_client --extension-id abcdefghijklmnopabcdefghijklmnop

Idempotent: re-running updates the registered redirect URIs in place.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from apps.oauth_server.models import OAuthClient
from core.brand import EDMS_OAUTH_CLIENT_ID, EDMS_PRODUCT_NAME

_EXTENSION_ID_RE = re.compile(r"^[a-p]{32}$")


class Command(BaseCommand):
    help = "Register the first-party OAuth client used by the EDMSpro extension."

    def add_arguments(self, parser):
        parser.add_argument(
            "--extension-id",
            action="append",
            default=[],
            dest="extension_ids",
            help=(
                "Chrome extension id (32 chars, a-p). Repeatable — pass the "
                "unpacked-dev id as well as the Web Store id."
            ),
        )
        parser.add_argument(
            "--redirect-uri",
            action="append",
            default=[],
            dest="redirect_uris",
            help="Extra redirect URI to allow verbatim (advanced/testing).",
        )

    def handle(self, *args, **options):
        uris: list[str] = []
        for ext_id in options["extension_ids"]:
            ext_id = ext_id.strip().lower()
            if not _EXTENSION_ID_RE.match(ext_id):
                raise CommandError(
                    f"'{ext_id}' is not a Chrome extension id (32 characters, a-p)."
                )
            uris.append(f"https://{ext_id}.chromiumapp.org/")
        uris.extend(u.strip() for u in options["redirect_uris"] if u.strip())
        if not uris:
            raise CommandError("Pass at least one --extension-id or --redirect-uri.")

        client, created = OAuthClient.objects.update_or_create(
            client_id=EDMS_OAUTH_CLIENT_ID,
            defaults={
                "client_name": EDMS_PRODUCT_NAME,
                "client_secret_hash": "",
                "token_endpoint_auth_method": OAuthClient.AuthMethod.NONE,
                "redirect_uris": uris,
                "grant_types": ["authorization_code", "refresh_token"],
                "scope": "edms",
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} OAuth client {client.client_id}")
        )
        for uri in uris:
            self.stdout.write(f"  redirect_uri: {uri}")
