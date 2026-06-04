"""Per-record validation for parsed caselaw.

Unlike the Iowa Code validator (which validates a whole ParseResult and raises
on errors), caselaw is bulk public data streamed one record at a time: a single
bad record must not abort a multi-hundred-thousand-record ingest. So validation
here is advisory — it returns issues; the writer's own skip logic (no date → no
version, empty body → container only) is what actually protects the corpus.
The command tallies issue codes into the run log for auditability.
"""

from __future__ import annotations

from dataclasses import dataclass

from .parser import ParsedDecision, ParsedOpinion

_KNOWN_COURTS = ("iowa", "iowactapp")


@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning"
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


def validate_decision(parsed: ParsedDecision) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if parsed.date_filed is None:
        issues.append(ValidationIssue(
            "error", "decision_no_date", parsed.path,
            f"unparseable/missing date_filed {parsed.date_filed_raw!r}; "
            "no NodeVersion can be dated",
        ))
    if not parsed.heading.strip():
        issues.append(ValidationIssue(
            "warning", "decision_no_name", parsed.path, "no case name",
        ))
    if parsed.court_id not in _KNOWN_COURTS:
        issues.append(ValidationIssue(
            "warning", "decision_unexpected_court", parsed.path,
            f"court_id {parsed.court_id!r} not in {_KNOWN_COURTS}",
        ))
    return issues


def validate_opinion(parsed: ParsedOpinion) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not parsed.body_text.strip():
        issues.append(ValidationIssue(
            "warning", "opinion_empty_body", parsed.path,
            "no text in any opinion column; node created as a container only",
        ))
    if parsed.type_prefix == "999":
        issues.append(ValidationIssue(
            "warning", "opinion_unknown_type", parsed.path,
            f"unrecognized opinion type {parsed.op_type!r}; heading defaulted",
        ))
    return issues
