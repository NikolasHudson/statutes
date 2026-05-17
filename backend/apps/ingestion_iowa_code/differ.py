"""Compute the changeset between a ParseResult and the current Node state.

The shape of a changeset is intentionally boring: four lists, each holding
ParsedSection (or, for repeals, the existing path string). The writer turns
them into ORM operations; the differ never touches the DB write side.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.corpus.models import Node, NodeVersion, Source

from .parser import ParsedChapter, ParsedSection, ParseResult


@dataclass
class SectionChange:
    parsed: ParsedSection
    prior_content_hash: str | None  # None for additions


@dataclass
class ChapterChange:
    parsed: ParsedChapter
    is_new: bool


@dataclass
class Changeset:
    chapters_added: list[ChapterChange] = field(default_factory=list)
    chapters_unchanged: list[ChapterChange] = field(default_factory=list)
    sections_added: list[SectionChange] = field(default_factory=list)
    sections_amended: list[SectionChange] = field(default_factory=list)
    sections_unchanged: list[SectionChange] = field(default_factory=list)
    sections_repealed: list[str] = field(default_factory=list)  # paths

    @property
    def is_empty(self) -> bool:
        return not (
            self.chapters_added
            or self.sections_added
            or self.sections_amended
            or self.sections_repealed
        )

    def summary(self) -> dict[str, int]:
        return {
            "chapters_added": len(self.chapters_added),
            "sections_added": len(self.sections_added),
            "sections_amended": len(self.sections_amended),
            "sections_unchanged": len(self.sections_unchanged),
            "sections_repealed": len(self.sections_repealed),
        }


def diff_against_db(parsed: ParseResult, source: Source) -> Changeset:
    """Compare a ParseResult with the persisted Node tree under ``source``.

    "Current version" means the NodeVersion that is effective today, i.e.
    effective_to IS NULL. Older closed versions are ignored for diffing — the
    history is preserved by the writer when it closes the prior version.
    """

    cs = Changeset()

    parsed_chapter_paths = {ch.path for ch in parsed.chapters}
    parsed_section_paths = {s.path for s in parsed.iter_sections()}

    existing_nodes: dict[str, Node] = {
        n.path: n for n in Node.objects.filter(source=source).only(
            "id", "path", "is_repealed", "node_type__key"
        ).select_related("node_type")
    }
    existing_section_paths = {
        path
        for path, node in existing_nodes.items()
        if node.node_type.key == "section" and not node.is_repealed
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

    for section in parsed.iter_sections():
        prior = current_versions.get(section.path)
        if prior is None:
            cs.sections_added.append(
                SectionChange(parsed=section, prior_content_hash=None)
            )
            continue

        if prior.content_hash == section.content_hash:
            cs.sections_unchanged.append(
                SectionChange(parsed=section, prior_content_hash=prior.content_hash)
            )
        else:
            cs.sections_amended.append(
                SectionChange(parsed=section, prior_content_hash=prior.content_hash)
            )

    # Repeals: only sections under chapters that the input *covers*. We do not
    # repeal sections from chapters absent in this run — a probe ingest of
    # chapter 1 must not repeal chapter 2.
    for path in existing_section_paths - parsed_section_paths:
        chapter_prefix = path.split(".", 1)[0]
        if chapter_prefix in parsed_chapter_paths:
            cs.sections_repealed.append(path)

    return cs
