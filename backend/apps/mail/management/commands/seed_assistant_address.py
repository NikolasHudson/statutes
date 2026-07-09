"""Create/update an assistant inbox and its pilot allowlist.

    python manage.py seed_assistant_address --address assistant@mail.nick.law \\
        --name "Hudson Research Assistant" --allow nick@nickhudson.me

    python manage.py seed_assistant_address --address ethics@mail.nick.law \\
        --product iowa-ethics-procedure --mode entitled

Idempotent (update_or_create), mirroring seed_ethics_procedure_demo.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.mail.models import AddressAllowlist, AssistantAddress
from apps.tenancy.models import Product


class Command(BaseCommand):
    help = "Create or update an AssistantAddress (and optional allowlist entries)."

    def add_arguments(self, parser):
        parser.add_argument("--address", required=True)
        parser.add_argument("--name", default="Hudson Research Assistant")
        parser.add_argument(
            "--product", default="", help="Product slug to scope to (omit = flagship)."
        )
        parser.add_argument(
            "--mode",
            choices=[m.value for m in AssistantAddress.Mode],
            default=AssistantAddress.Mode.ALLOWLIST.value,
        )
        parser.add_argument(
            "--allow",
            action="append",
            default=[],
            help="Sender email to allowlist (repeatable).",
        )

    def handle(self, *args, **options):
        product = None
        if options["product"]:
            product = Product.objects.filter(slug=options["product"]).first()
            if product is None:
                raise CommandError(f"no Product with slug {options['product']!r}")

        address, created = AssistantAddress.objects.update_or_create(
            address=options["address"].strip().lower(),
            defaults={
                "display_name": options["name"],
                "product": product,
                "mode": options["mode"],
                "active": True,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Updated'} {address.address} "
                f"(mode={address.mode}, product={product.slug if product else 'flagship'})"
            )
        )
        for email in options["allow"]:
            _, added = AddressAllowlist.objects.get_or_create(
                address=address, email=email.strip().lower()
            )
            self.stdout.write(
                f"  allowlist: {email} {'added' if added else 'already present'}"
            )
