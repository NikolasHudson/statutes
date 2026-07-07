"""The retention purge must cover BOTH confidential tables.

ChatTrace was purged from day one; VerificationRun (user-document quote
fragments + upload filenames) was originally missed and grew forever — the
2026-07 chat-history audit's top backend finding. These tests pin the fix.
"""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.api.models import ChatTrace, VerificationRun


def _age(obj, days: int) -> None:
    # created_at is auto_now_add — backdate via queryset update.
    type(obj).objects.filter(pk=obj.pk).update(
        created_at=timezone.now() - timedelta(days=days)
    )


class PurgeTracesTests(TestCase):
    def setUp(self):
        self.old_trace = ChatTrace.objects.create(question="old", answer="a")
        _age(self.old_trace, 10)
        self.new_trace = ChatTrace.objects.create(question="new", answer="a")
        self.old_run = VerificationRun.objects.create(source_name="old.docx")
        _age(self.old_run, 10)
        self.new_run = VerificationRun.objects.create(source_name="new.docx")

    def test_purges_both_tables_past_window(self):
        call_command("purge_chat_traces", days=7, stdout=StringIO())
        self.assertFalse(
            ChatTrace.objects.filter(pk=self.old_trace.pk).exists()
        )
        self.assertFalse(
            VerificationRun.objects.filter(pk=self.old_run.pk).exists()
        )
        self.assertTrue(
            ChatTrace.objects.filter(pk=self.new_trace.pk).exists()
        )
        self.assertTrue(
            VerificationRun.objects.filter(pk=self.new_run.pk).exists()
        )

    def test_dry_run_deletes_nothing_and_reports_both(self):
        out = StringIO()
        call_command("purge_chat_traces", days=7, dry_run=True, stdout=out)
        self.assertEqual(ChatTrace.objects.count(), 2)
        self.assertEqual(VerificationRun.objects.count(), 2)
        self.assertIn("1 chat trace(s)", out.getvalue())
        self.assertIn("1 verification run(s)", out.getvalue())

    def test_nonpositive_window_purges_nothing(self):
        call_command("purge_chat_traces", days=0, stdout=StringIO())
        self.assertEqual(ChatTrace.objects.count(), 2)
        self.assertEqual(VerificationRun.objects.count(), 2)
