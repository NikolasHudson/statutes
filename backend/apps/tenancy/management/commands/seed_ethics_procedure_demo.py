"""Seed the Iowa Ethics & Procedure scoped app + a demo bar-association tenant.

Idempotent (update_or_create), so tweaking branding/scope and re-running is safe:

    python manage.py seed_ethics_procedure_demo
    python manage.py seed_ethics_procedure_demo --hostname clerk.nick.law

Creates:
  * the ``iowa-ethics-procedure`` Product — scope-locked to ``iowa-court-rules``,
    jurisdiction Iowa, with the app's own brand. ``--hostname`` is the locked
    front door (default ``clerk.localhost`` so it resolves in any environment;
    use ``X-Product-Slug: iowa-ethics-procedure`` in DEBUG to exercise it without DNS).
  * an ``iowa-bar`` Organization (the distribution vehicle) with an ACTIVE
    org-held Subscription to the product — every member inherits access.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.corpus.models import Jurisdiction
from apps.tenancy.models import Organization, Product, Subscription


class Command(BaseCommand):
    help = "Seed the Iowa Ethics & Procedure app + a demo bar-association tenant."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hostname",
            default="clerk.localhost",
            help="Locked front-door host for the ethics app (e.g. clerk.nick.law).",
        )

    def handle(self, *args, **options):
        iowa = Jurisdiction.objects.filter(slug="iowa").first()
        if iowa is None:
            self.stderr.write(
                self.style.ERROR(
                    "No 'iowa' Jurisdiction found — run the corpus seed migrations first."
                )
            )
            return

        product, _ = Product.objects.update_or_create(
            slug="iowa-ethics-procedure",
            defaults={
                "name": "Iowa Ethics & Procedure",
                "hostname": options["hostname"],
                "allowed_source_slugs": ["iowa-court-rules"],
                "system_prompt_key": "ethics-procedure",
                "jurisdiction": iowa,
                "brand_name": "Iowa Ethics & Procedure",
                "primary_color": "#0b3d2e",
                "accent_color": "#c8a44d",
                "login_tagline": "Iowa ethics & procedure research — every citation verified.",
                "support_email": "support@nick.law",
                "disclaimer": (
                    "This tool provides research and citations to the Iowa Court "
                    "Rules. It is not legal advice and does not create an "
                    "attorney-client relationship."
                ),
            },
        )

        org, _ = Organization.objects.update_or_create(
            slug="iowa-bar",
            defaults={
                "name": "Iowa State Bar Association",
                "status": Organization.Status.ACTIVE,
                "brand_name": "Iowa State Bar Association",
            },
        )

        Subscription.objects.update_or_create(
            org=org,
            product=product,
            defaults={"status": Subscription.Status.ACTIVE},
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded product '{product.name}' (host={product.hostname}, "
                f"scope={product.allowed_source_slugs}) and org '{org.name}' "
                f"with an active site license. Members of '{org.slug}' are entitled."
            )
        )
