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

    issues.extend(_check_every_section_has_heading(parsed))
    issues.extend(_check_section_paths_unique(parsed))
    issues.extend(_check_referred_to_resolve(parsed))
    issues.extend(_check_repeal_volume(changeset))
    issues.extend(_check_content_hash_changed_only_when_text_changed(changeset))

    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise ValidationError(errors + [i for i in issues if i.severity != "error"])
    return issues


def _check_every_section_has_heading(parsed: ParseResult):
    for sec in parsed.iter_sections():
        if not sec.heading.strip():
            yield ValidationIssue(
                severity="error",
                code="missing_heading",
                path=sec.path,
                message=f"section {sec.number} has no heading",
            )


def _check_section_paths_unique(parsed: ParseResult):
    seen: dict[str, int] = {}
    for sec in parsed.iter_sections():
        seen[sec.path] = seen.get(sec.path, 0) + 1
    for path, count in seen.items():
        if count > 1:
            yield ValidationIssue(
                severity="error",
                code="duplicate_path",
                path=path,
                message=f"section {path} appears {count} times in input",
            )


def _check_referred_to_resolve(parsed: ParseResult):
    """Internal cross-references should point at sections we have. We only
    warn — the input is a sample, so unresolved refs are expected, but a
    full-corpus run should keep this list small."""
    known = {sec.path for sec in parsed.iter_sections()}
    for sec in parsed.iter_sections():
        for ref in sec.referred_to_in:
            if ref not in known:
                yield ValidationIssue(
                    severity="warning",
                    code="unresolved_cross_reference",
                    path=sec.path,
                    message=f"referred_to_in cites {ref!r} which is not in this run",
                )


REPEAL_RATIO_LIMIT = 0.10


def _check_repeal_volume(changeset: Changeset):
    """A repeal wave > 10% of the in-scope sections is almost certainly a
    parser bug or a partial input. Block it."""
    in_scope_total = (
        len(changeset.sections_added)
        + len(changeset.sections_amended)
        + len(changeset.sections_unchanged)
        + len(changeset.sections_repealed)
    )
    if in_scope_total == 0:
        return
    ratio = len(changeset.sections_repealed) / in_scope_total
    if ratio > REPEAL_RATIO_LIMIT:
        yield ValidationIssue(
            severity="error",
            code="unannounced_repeal_wave",
            path="(corpus)",
            message=(
                f"{len(changeset.sections_repealed)} repeals out of {in_scope_total} "
                f"in-scope sections ({ratio:.1%}) exceeds {REPEAL_RATIO_LIMIT:.0%} threshold"
            ),
        )


def _check_content_hash_changed_only_when_text_changed(changeset: Changeset):
    """Defensive: content_hash is computed from normalized body. If the
    differ classified a section as unchanged, the parsed content_hash MUST
    equal the prior one. If amended, they MUST differ. The parser bug we are
    guarding against would silently produce different hashes for the same
    bytes."""
    for change in changeset.sections_unchanged:
        if change.parsed.content_hash != change.prior_content_hash:
            yield ValidationIssue(
                severity="error",
                code="hash_drift_unchanged",
                path=change.parsed.path,
                message="parsed unchanged section but content_hash differs from prior",
            )
    for change in changeset.sections_amended:
        if change.parsed.content_hash == change.prior_content_hash:
            yield ValidationIssue(
                severity="error",
                code="hash_drift_amended",
                path=change.parsed.path,
                message="parsed amended section but content_hash matches prior",
            )
