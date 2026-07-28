"""Destination resolution: templates, precedence, and the hostile inputs.

Court metadata is scraped from someone else's HTML, so "the case caption
contains a slash" is a Tuesday, not an attack. These tests pin the two things
that must hold for every input: a filing always lands somewhere findable, and no
rendered value can climb out of the folder it was routed to.
"""

from __future__ import annotations

import datetime as dt

from django.test import TestCase

from apps.edms.models import CaseFolderMapping, EdmsSettings
from apps.edms.routing import (
    FilingMeta,
    render_filename,
    render_folder,
    resolve_destination,
)

from ._factories import make_user


class RenderFolderTests(TestCase):
    def test_tokens_substituted(self):
        meta = FilingMeta(
            case_number="CVCV012345",
            docket_num="D0064",
            filer="Smith",
            county="Polk",
            row_date=dt.date(2024, 3, 15),
        )
        self.assertEqual(
            render_folder("{county}/{year}/{case_number}", meta),
            "Polk/2024/CVCV012345",
        )

    def test_repeated_token_renders_every_occurrence(self):
        meta = FilingMeta(case_number="CV1")
        self.assertEqual(render_folder("{case_number}/{case_number}", meta), "CV1/CV1")

    def test_empty_tokens_collapse_rather_than_making_blank_levels(self):
        meta = FilingMeta(case_number="CV1")  # no filer, no docket
        self.assertEqual(render_folder("{filer}/{case_number}/{docket_num}", meta), "CV1")

    def test_everything_empty_falls_back_to_case_number(self):
        self.assertEqual(render_folder("{filer}", FilingMeta(case_number="CV1")), "CV1")

    def test_nothing_at_all_falls_back_to_misc(self):
        self.assertEqual(render_folder("{filer}", FilingMeta(case_number="")), "misc")

    def test_year_comes_from_row_date_then_today(self):
        meta = FilingMeta(case_number="CV1", row_date=dt.date(2019, 5, 1))
        self.assertEqual(render_folder("{year}", meta), "2019")
        self.assertEqual(
            render_folder("{year}", FilingMeta(case_number="CV1"), today=dt.date(2026, 1, 1)),
            "2026",
        )

    def test_traversal_and_reserved_characters_are_neutralized(self):
        meta = FilingMeta(case_number="../../etc", filer='a:b|c"d')
        rendered = render_folder("{case_number}/{filer}", meta)
        self.assertNotIn("..", rendered)
        for char in ':|"':
            self.assertNotIn(char, rendered)


class RenderFilenameTests(TestCase):
    def test_default_template(self):
        meta = FilingMeta(
            case_number="CVCV012345",
            doc_title="Motion to Dismiss",
            row_date=dt.date(2024, 3, 15),
        )
        self.assertEqual(
            render_filename("{date}_{case_num}_{doc_title}", meta),
            "2024-03-15_CVCV012345_Motion to Dismiss.pdf",
        )

    def test_missing_date_is_labelled_not_blank(self):
        meta = FilingMeta(case_number="CV1", doc_title="Order")
        self.assertTrue(render_filename("{date}_{doc_title}", meta).startswith("undated_"))

    def test_empty_token_does_not_leave_doubled_separators(self):
        meta = FilingMeta(case_number="CV1", doc_title="Order")  # no doc_type
        self.assertEqual(render_filename("{case_num}_{doc_type}_{doc_title}", meta), "CV1_Order.pdf")

    def test_pdf_suffix_added_once(self):
        meta = FilingMeta(case_number="CV1", doc_title="Order.pdf")
        self.assertEqual(render_filename("{doc_title}", meta), "Order.pdf")

    def test_slash_in_title_cannot_create_a_directory(self):
        meta = FilingMeta(case_number="CV1", doc_title="Motion/Resistance")
        self.assertNotIn("/", render_filename("{doc_title}", meta))


class ResolveDestinationTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.meta = FilingMeta(
            case_number="CVCV012345",
            doc_title="Motion",
            row_date=dt.date(2024, 3, 15),
        )

    def test_defaults_when_nothing_configured(self):
        dest = resolve_destination(self.user, self.meta)
        self.assertEqual(dest.folder_path, "Hudson EDMSpro/CVCV012345")
        self.assertEqual(dest.filename, "2024-03-15_CVCV012345_Motion.pdf")

    def test_user_settings_root_and_template(self):
        EdmsSettings.objects.create(
            user=self.user,
            default_destination_path="Documents/Casework",
            case_folder_template="{year}/{case_number}",
            naming_template="{case_num}-{doc_title}",
        )
        dest = resolve_destination(self.user, self.meta)
        self.assertEqual(dest.folder_path, "Documents/Casework/2024/CVCV012345")
        self.assertEqual(dest.filename, "CVCV012345-Motion.pdf")

    def test_case_override_wins_and_is_not_nested_under_the_root(self):
        EdmsSettings.objects.create(
            user=self.user, default_destination_path="Documents/Casework"
        )
        CaseFolderMapping.objects.create(
            user=self.user,
            case_number="CVCV012345",
            folder_path="Clients/Acme/Litigation",
            naming_template="{doc_title}",
        )
        dest = resolve_destination(self.user, self.meta)
        self.assertEqual(dest.folder_path, "Clients/Acme/Litigation")
        self.assertEqual(dest.filename, "Motion.pdf")

    def test_override_for_a_different_case_is_ignored(self):
        CaseFolderMapping.objects.create(
            user=self.user, case_number="OTHER", folder_path="Elsewhere"
        )
        self.assertEqual(
            resolve_destination(self.user, self.meta).folder_path,
            "Hudson EDMSpro/CVCV012345",
        )

    def test_another_users_override_is_ignored(self):
        other = make_user("other@example.com")
        CaseFolderMapping.objects.create(
            user=other, case_number="CVCV012345", folder_path="Their/Folder"
        )
        self.assertEqual(
            resolve_destination(self.user, self.meta).folder_path,
            "Hudson EDMSpro/CVCV012345",
        )
