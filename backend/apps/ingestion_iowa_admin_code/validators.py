"""Pre-write validation. Pure functions over ParseResult + Changeset.

Validators raise ValidationError to abort an ingest, or append warnings the
caller can display. Goal: catch parser regressions before they hit the
canonical Node table, not after. Mirrors the Court Rules validators.
"""

from __future__ import annotations

from dataclasses import dataclass

from .differ import Changeset
from .parser import ParseResult


@dataclass
class ValidationIssue:
    severity: str  # "error" or "warning"
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


class ValidationError(Exception):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__(f"{len(issues)} validation error(s)")


REPEAL_RATIO_LIMIT = 0.10


def validate(parsed: ParseResult, changeset: Changeset) -> list[ValidationIssue]:
    """Run all checks. Returns warnings; raises ValidationError on errors."""
    issues: list[ValidationIssue] = []

    issues.extend(_check_every_rule_has_heading(parsed))
    issues.extend(_check_rule_paths_unique(parsed))
    issues.extend(_check_repeal_volume(changeset))
    issues.extend(_check_content_hash_consistency(changeset))
    issues.extend(_flag_empty_content_chapters(parsed))

    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise ValidationError(errors + [i for i in issues if i.severity != "error"])
    return issues


def _check_every_rule_has_heading(parsed: ParseResult):
    for rule in parsed.iter_rules():
        if not rule.heading.strip():
            yield ValidationIssue(
                severity="error", code="missing_heading", path=rule.path,
                message=f"rule {rule.path} has no heading",
            )


def _check_rule_paths_unique(parsed: ParseResult):
    seen: dict[str, int] = {}
    for rule in parsed.iter_rules():
        seen[rule.path] = seen.get(rule.path, 0) + 1
    for path, count in seen.items():
        if count > 1:
            yield ValidationIssue(
                severity="error", code="duplicate_path", path=path,
                message=f"rule {path} appears {count} times in input",
            )


def _check_repeal_volume(changeset: Changeset):
    """A repeal wave > 10% of in-scope rules is almost certainly a parser bug
    or a partial input. Block it."""
    in_scope_total = (
        len(changeset.rules_added)
        + len(changeset.rules_amended)
        + len(changeset.rules_unchanged)
        + len(changeset.rules_repealed)
    )
    if in_scope_total == 0:
        return
    ratio = len(changeset.rules_repealed) / in_scope_total
    if ratio > REPEAL_RATIO_LIMIT:
        yield ValidationIssue(
            severity="error", code="unannounced_repeal_wave", path="(corpus)",
            message=(
                f"{len(changeset.rules_repealed)} repeals out of {in_scope_total} "
                f"in-scope rules ({ratio:.1%}) exceeds {REPEAL_RATIO_LIMIT:.0%}"
            ),
        )


def _check_content_hash_consistency(changeset: Changeset):
    """Defensive: unchanged rules must keep the same content_hash; amended
    rules must differ. Guards against a parser bug producing different hashes
    for identical bytes (or identical hashes across an edit)."""
    for change in changeset.rules_unchanged:
        if change.parsed.content_hash != change.prior_content_hash:
            yield ValidationIssue(
                severity="error", code="hash_drift_unchanged",
                path=change.parsed.path,
                message="unchanged rule but content_hash differs from prior",
            )
    for change in changeset.rules_amended:
        if change.parsed.content_hash == change.prior_content_hash:
            yield ValidationIssue(
                severity="error", code="hash_drift_amended",
                path=change.parsed.path,
                message="amended rule but content_hash matches prior",
            )


def _flag_empty_content_chapters(parsed: ParseResult):
    """Non-reserved chapters that yielded zero rules use a structure the DOCX
    extractor did not handle (or the fetch fell back to a PDF). Surface as a
    warning so the gap is visible; the chapter node is still created."""
    for ch in parsed.iter_chapters():
        if not ch.reserved and not ch.rules:
            yield ValidationIssue(
                severity="warning", code="empty_content_chapter", path=ch.path,
                message=(
                    f"chapter {ch.agency}-{ch.number} ({ch.title!r}) parsed 0 rules"
                    + (f": {'; '.join(ch.parse_notes)}" if ch.parse_notes else "")
                ),
            )
