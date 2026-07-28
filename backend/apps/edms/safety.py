"""Case types that are never crowdsourced, whatever the user opted into.

Iowa case-number prefixes encode the case type. Juvenile delinquency (JV),
juvenile dependency (JD) and adoption (AD) matters are confidential by statute
and by any reasonable reading of the professional-conduct rules, so a filing in
one of them must not reach the contribution bucket even from a user who has
opted in and even if they click "share this one".

Two properties this module is built for:

* **The server has the final say.** The extension runs the same check for UX
  (it hides the share affordance), but the check that matters is the one
  :mod:`apps.edms.api` runs on the intake path — a client-side filter is a
  convenience, never a control.
* **One list, two consumers.** ``GET /api/edms/safety`` serves these entries to
  both the extension and the SPA settings page, so the blocked set can never
  drift between what we enforce and what we tell the user we enforce.

Ported verbatim (prefixes) from the EDMSpro prototype's ``apps/routing/safety.py``;
the labels are new, for the read-only list the settings page renders.
"""

from __future__ import annotations

# prefix -> human label for the settings/extension list.
BLOCKED_PREFIXES: dict[str, str] = {
    "JV": "Juvenile delinquency",
    "JD": "Juvenile dependency / CINA",
    "AD": "Adoption",
}


def _normalize(case_number: str) -> str:
    """Upper-case, strip separators. Iowa case numbers appear as ``JVJV012345``,
    ``JV-012345`` and ``jv 012345`` depending on where they were scraped from;
    all three must hit the same rule."""
    return "".join(ch for ch in (case_number or "").upper() if ch.isalnum())


def is_blocked(case_number: str) -> bool:
    """True if this case number belongs to a confidential case type."""
    normalized = _normalize(case_number)
    return any(normalized.startswith(p) for p in BLOCKED_PREFIXES)


def blocked_reason(case_number: str) -> str:
    """The label of the rule that blocked ``case_number`` (``""`` if allowed).
    Stored on the artifact's ``safety_flags`` when a submission is refused, and
    returned in the 403 body so the extension can say why."""
    normalized = _normalize(case_number)
    for prefix, label in BLOCKED_PREFIXES.items():
        if normalized.startswith(prefix):
            return label
    return ""


def safety_list() -> list[dict[str, str]]:
    """The public shape of the list, shared by the SPA and the extension."""
    return [
        {"prefix": prefix, "label": label}
        for prefix, label in sorted(BLOCKED_PREFIXES.items())
    ]
