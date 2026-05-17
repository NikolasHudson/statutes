"""Pre-write validation. Pure functions over ParseResult + Changeset.

Validators raise ValidationError to abort an ingest, or append to a list of
warnings the caller can display. Goal: catch parser regressions before they
hit the canonical Node table, not after.
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


def validate(parsed: ParseResult, changeset: Changeset) -> list[ValidationIssue]:
    """Run all checks. Returns warnings; raises ValidationError on errors."""
    issues: list[ValidationIssue] = []

    issues.extend(_check_every_rule_has_heading(parsed))
    issues.extend(_check_rule_paths_unique(parsed))
    issues.extend(_check_repeal_volume(changeset))
    issues.extend(_check_content_hash_changed_only_when_text_changed(changeset))
    issues.extend(_flag_unparsed_content_chapters(parsed))

    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise ValidationError(errors + [i for i in issues if i.severity != "error"])
    return issues


def _check_every_rule_has_heading(parsed: ParseResult):
    for rule in parsed.iter_rules():
        if not rule.heading.strip():
            yield ValidationIssue(
                severity="error",
                code="missing_heading",
                path=rule.path,
                message=f"rule {rule.number} has no heading",
            )


def _check_rule_paths_unique(parsed: ParseResult):
    seen: dict[str, int] = {}
    for rule in parsed.iter_rules():
        seen[rule.path] = seen.get(rule.path, 0) + 1
    for path, count in seen.items():
        if count > 1:
            yield ValidationIssue(
                severity="error",
                code="duplicate_path",
                path=path,
                message=f"rule {path} appears {count} times in input",
            )


REPEAL_RATIO_LIMIT = 0.10


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
            severity="error",
            code="unannounced_repeal_wave",
            path="(corpus)",
            message=(
                f"{len(changeset.rules_repealed)} repeals out of {in_scope_total} "
                f"in-scope rules ({ratio:.1%}) exceeds {REPEAL_RATIO_LIMIT:.0%} threshold"
            ),
        )


def _check_content_hash_changed_only_when_text_changed(changeset: Changeset):
    """Defensive: if the differ classified a rule as unchanged, the parsed
    content_hash MUST equal the prior one; if amended, they MUST differ. Guards
    against a parser bug that silently produces different hashes for the same
    bytes (or identical hashes across an edit)."""
    for change in changeset.rules_unchanged:
        if change.parsed.content_hash != change.prior_content_hash:
            yield ValidationIssue(
                severity="error",
                code="hash_drift_unchanged",
                path=change.parsed.path,
                message="parsed unchanged rule but content_hash differs from prior",
            )
    for change in changeset.rules_amended:
        if change.parsed.content_hash == change.prior_content_hash:
            yield ValidationIssue(
                severity="error",
                code="hash_drift_amended",
                path=change.parsed.path,
                message="parsed amended rule but content_hash matches prior",
            )


def _flag_unparsed_content_chapters(parsed: ParseResult):
    """Chapters that are not reserved yet yielded zero rules use a non-Rule
    structure (Forms, Canons, Roman-numeral standards) the current extractor
    does not handle. Surface as a warning so the gap is visible but the run
    still proceeds — the chapter node is created without rule children."""
    for ch in parsed.chapters:
        if not ch.reserved and not ch.rules and ch.parse_notes:
            yield ValidationIssue(
                severity="warning",
                code="unparsed_content_chapter",
                path=ch.path,
                message=(
                    f"chapter {ch.number} ({ch.title!r}) parsed 0 rules: "
                    f"{'; '.join(ch.parse_notes)}"
                ),
            )
