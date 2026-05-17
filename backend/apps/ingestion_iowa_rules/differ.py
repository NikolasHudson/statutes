"""Compute the changeset between a ParseResult and the current Node state.

Same boring shape as the Iowa Code differ: lists of ParsedRule (or, for
repeals, the existing path string). The writer turns them into ORM
operations; the differ never touches the DB write side.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.corpus.models import Node, NodeVersion, Source

from .parser import ParsedChapter, ParsedRule, ParseResult


@dataclass
class RuleChange:
    parsed: ParsedRule
    prior_content_hash: str | None  # None for additions


@dataclass
class ChapterChange:
    parsed: ParsedChapter
    is_new: bool


@dataclass
class Changeset:
    chapters_added: list[ChapterChange] = field(default_factory=list)
    chapters_unchanged: list[ChapterChange] = field(default_factory=list)
    rules_added: list[RuleChange] = field(default_factory=list)
    rules_amended: list[RuleChange] = field(default_factory=list)
    rules_unchanged: list[RuleChange] = field(default_factory=list)
    rules_repealed: list[str] = field(default_factory=list)  # paths

    @property
    def is_empty(self) -> bool:
        return not (
            self.chapters_added
            or self.rules_added
            or self.rules_amended
            or self.rules_repealed
        )

    def summary(self) -> dict[str, int]:
        return {
            "chapters_added": len(self.chapters_added),
            "rules_added": len(self.rules_added),
            "rules_amended": len(self.rules_amended),
            "rules_unchanged": len(self.rules_unchanged),
            "rules_repealed": len(self.rules_repealed),
        }


def diff_against_db(parsed: ParseResult, source: Source) -> Changeset:
    """Compare a ParseResult with the persisted Node tree under ``source``.

    "Current version" means the NodeVersion effective today (effective_to IS
    NULL). Older closed versions are ignored for diffing — history is
    preserved by the writer when it closes the prior version.
    """

    cs = Changeset()

    parsed_chapter_paths = {ch.path for ch in parsed.chapters}
    parsed_rule_paths = {r.path for r in parsed.iter_rules()}

    existing_nodes: dict[str, Node] = {
        n.path: n
        for n in Node.objects.filter(source=source)
        .only("id", "path", "is_repealed", "node_type__key")
        .select_related("node_type")
    }
    existing_rule_paths = {
        path
        for path, node in existing_nodes.items()
        if node.node_type.key == "rule" and not node.is_repealed
    }
    existing_chapter_paths = {
        path
        for path, node in existing_nodes.items()
        if node.node_type.key == "chapter"
    }

    current_versions: dict[str, NodeVersion] = {
        nv.node.path: nv
        for nv in NodeVersion.objects.filter(
            node__source=source, effective_to__isnull=True
        ).select_related("node")
    }

    for chapter in parsed.chapters:
        if chapter.path in existing_chapter_paths:
            cs.chapters_unchanged.append(ChapterChange(parsed=chapter, is_new=False))
        else:
            cs.chapters_added.append(ChapterChange(parsed=chapter, is_new=True))

    for rule in parsed.iter_rules():
        prior = current_versions.get(rule.path)
        if prior is None:
            cs.rules_added.append(RuleChange(parsed=rule, prior_content_hash=None))
            continue

        if prior.content_hash == rule.content_hash:
            cs.rules_unchanged.append(
                RuleChange(parsed=rule, prior_content_hash=prior.content_hash)
            )
        else:
            cs.rules_amended.append(
                RuleChange(parsed=rule, prior_content_hash=prior.content_hash)
            )

    # Repeals: only rules under chapters the input *covers*. A run that omits a
    # chapter must not repeal that chapter's rules.
    for path in existing_rule_paths - parsed_rule_paths:
        chapter_prefix = _chapter_of(path)
        if chapter_prefix in parsed_chapter_paths:
            cs.rules_repealed.append(path)

    return cs


def _chapter_of(rule_path: str) -> str:
    """Chapter prefix of a rule path: the digits before the first ':' or '.'."""
    for i, ch in enumerate(rule_path):
        if ch in ":.":
            return rule_path[:i]
    return rule_path
