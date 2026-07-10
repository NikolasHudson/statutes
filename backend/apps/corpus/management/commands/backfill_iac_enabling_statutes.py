"""Materialize statute↔regulation edges from IAC enabling-statute captures.

    python manage.py backfill_iac_enabling_statutes
    python manage.py backfill_iac_enabling_statutes --dry-run

Every Iowa Admin. Code rule head carries a parenthetical naming the Iowa Code
authority it implements ("441—65.2(234)" → ch. 234); ingestion stashes those
tokens in the rule Node's ``source_metadata["enabling_statutes"]``. This walks
every current approved rule version and writes one CrossReference per distinct
authority: an INTERNAL edge to the ``iowa-code`` Node when the token resolves
(chapters "234"/"17A" and dotted sections "455B.133" are both Node paths), or
an EXTERNAL edge carrying the token verbatim when it doesn't (repealed or
never-codified chapters) — never silently dropped.

This is the first cross-SOURCE pass: from_version lives in iowa-admin-code,
to_node in iowa-code. Idempotent per version via the ``reg_enabling`` source
scope (delete-and-rebuild), same contract as backfill_cross_references.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.corpus.models import (
    CrossReference,
    CrossReferenceKind,
    CrossReferenceSource,
    Node,
    NodeVersion,
    ReviewStatus,
    Source,
)


class Command(BaseCommand):
    help = "Write IAC rule → enabling Iowa Code statute CrossReference edges."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]

        iac = Source.objects.filter(slug="iowa-admin-code").first()
        iowa_code = Source.objects.filter(slug="iowa-code").first()
        if iac is None or iowa_code is None:
            self.stderr.write(self.style.ERROR("need both iowa-admin-code and iowa-code sources"))
            return

        versions = (
            NodeVersion.objects.filter(
                node__source=iac,
                node__node_type__key="rule",
                effective_to__isnull=True,
                review_status=ReviewStatus.APPROVED,
            )
            .select_related("node")
            .order_by("node__path")
        )

        # Every distinct token across the corpus resolves in ONE query; the
        # per-version loop then only touches the map. Tokens are Iowa Code
        # Node paths already: bare chapters ("234", "17A") and dotted
        # sections ("455B.133") both match Node.path verbatim.
        tokens: set[str] = set()
        per_version: list[tuple[NodeVersion, list[str]]] = []
        for version in versions.iterator():
            raw = version.node.source_metadata.get("enabling_statutes") or []
            # Dedup preserving order; rule heads repeat tokens ("234,234").
            seen: list[str] = []
            for t in raw:
                t = t.strip()
                if t and t not in seen:
                    seen.append(t)
            per_version.append((version, seen))
            tokens.update(seen)

        target_by_path = {
            n.path: n.id
            for n in Node.objects.filter(source=iowa_code, path__in=tokens)
        }

        stats = {"versions": 0, "internal": 0, "external": 0}
        for version, toks in per_version:
            if not toks:
                if not dry_run:
                    CrossReference.objects.filter(
                        from_version=version,
                        source=CrossReferenceSource.REG_ENABLING,
                    ).delete()
                continue

            stats["versions"] += 1
            resolved = [(t, target_by_path.get(t)) for t in toks]
            stats["internal"] += sum(1 for _, nid in resolved if nid)
            stats["external"] += sum(1 for _, nid in resolved if not nid)

            if dry_run:
                misses = [t for t, nid in resolved if not nid]
                if misses:
                    self.stdout.write(
                        f"{version.node.path}: unresolved {', '.join(misses)}"
                    )
                continue

            with transaction.atomic():
                CrossReference.objects.filter(
                    from_version=version,
                    source=CrossReferenceSource.REG_ENABLING,
                ).delete()
                CrossReference.objects.bulk_create(
                    [
                        CrossReference(
                            from_version=version,
                            to_node_id=node_id,
                            external_text="" if node_id else f"Iowa Code {token}",
                            kind=CrossReferenceKind.INTERNAL
                            if node_id
                            else CrossReferenceKind.EXTERNAL,
                            source=CrossReferenceSource.REG_ENABLING,
                        )
                        for token, node_id in resolved
                    ]
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"{'would write' if dry_run else 'wrote'} edges for "
                f"{stats['versions']} rules: {stats['internal']} internal, "
                f"{stats['external']} external (unresolved)"
            )
        )
