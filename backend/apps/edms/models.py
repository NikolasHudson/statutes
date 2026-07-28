"""Hudson EDMSpro — tables for court-filing routing.

The custody model this app is built around, and the reason its schema looks the
way it does:

**Filing bytes never touch Hudson.** The browser extension fetches the PDF from
the court's EDMS using the attorney's own session and PUTs it straight to a
Microsoft Graph *upload session* — a pre-authenticated, single-file, time-limited
URL this server mints. So there is no ``FileField`` anywhere in this module and
there never will be: :class:`FilingSync` is an audit log of *where a document
went*, not a copy of it. (A test asserts the absence, because the one-line
regression — "just store the PDF while we debug this" — would quietly turn a
provable guarantee into a retention policy.)

The single exception is :class:`CrowdsourceArtifact`, and it is not an exception
to the custody model so much as the other half of it: a user who explicitly opts
in sends us a copy, we stream it to a private bucket, and we write a row here
naming it. That row exists for exactly one reason — so the bucket is not an
anonymous heap that we could never purge on request. Nothing in this app reads
the bucket.

**Corpus segregation.** Nothing here is an ``apps.corpus`` ``Node``. Filings are
not law and must never surface in search, browse, chat RAG, research or MCP. The
future Motions & Orders Library gets its own tables in this app for the same
reason: separate tables make leakage impossible by construction rather than a
matter of per-endpoint discipline. A test asserts this app imports nothing from
``apps.corpus``.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from .crypto import decrypt_secret, encrypt_secret

# Defaults shared by the model fields, the API schemas and the template
# renderer. Keep them here so "what does a brand-new user get" has one answer.
DEFAULT_NAMING_TEMPLATE = "{date}_{case_num}_{doc_title}"
DEFAULT_CASE_FOLDER_TEMPLATE = "{case_number}"
DEFAULT_ROOT_FOLDER = "Hudson EDMSpro"


class Provider(models.TextChoices):
    ONEDRIVE = "onedrive", "OneDrive"
    # Registered but not implemented in v1 — the provider column exists so
    # adding Drive later is a new client module, not a migration of live rows.
    GDRIVE = "gdrive", "Google Drive"


class EdmsSettings(models.Model):
    """Per-user EDMSpro preferences. The server, not the extension, is the
    source of truth: the route endpoint reads these on every save, so a device
    that has never opened the settings page still files documents correctly."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="edms_settings",
    )
    cloud_provider = models.CharField(
        max_length=16, choices=Provider.choices, blank=True, default=Provider.ONEDRIVE
    )
    # Where the per-case folders get created. ``_id`` is what the OneDrive
    # folder picker returns; ``_path`` is what the template renderer builds
    # paths under and what a human reads back in the UI.
    default_destination_folder_id = models.CharField(max_length=512, blank=True, default="")
    default_destination_path = models.CharField(max_length=1024, blank=True, default="")
    naming_template = models.CharField(max_length=256, default=DEFAULT_NAMING_TEMPLATE)
    case_folder_template = models.CharField(
        max_length=256, default=DEFAULT_CASE_FOLDER_TEMPLATE
    )
    # Default OFF, and the ONLY path that may set it True is the SPA consent
    # screen on a session-authenticated request (enforced in api.py, asserted by
    # test): a headless caller must never be able to enroll a user into sharing
    # their filings. Turning it off is allowed from anywhere and is PROSPECTIVE
    # ONLY — it stops future intake and removes nothing already contributed.
    crowdsource_opt_in = models.BooleanField(default=False)
    crowdsource_opt_in_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EDMSpro settings"
        verbose_name_plural = "EDMSpro settings"

    def __str__(self) -> str:
        return f"EDMSpro settings for user {self.user_id}"


class CloudIntegration(models.Model):
    """A connected cloud-storage account and its OAuth tokens.

    Tokens are Fernet-encrypted at rest (:mod:`apps.edms.crypto`) and are read
    only inside this process, only to talk to the provider. They are never
    serialized into an API response and never handed to the extension — the
    extension receives a per-file upload URL and nothing else. That asymmetry is
    the whole point of the split-custody design.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="edms_integrations",
    )
    provider = models.CharField(max_length=16, choices=Provider.choices)
    access_token_enc = models.TextField(blank=True, default="")
    refresh_token_enc = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    account_email = models.CharField(max_length=320, blank=True, default="")
    account_name = models.CharField(max_length=200, blank=True, default="")
    connected_at = models.DateTimeField(auto_now_add=True)
    # Set when a refresh comes back invalid_grant (revoked consent, password
    # rotation, 90-day idle). Drives the amber "Reconnect" state in the SPA
    # instead of failing every save with an opaque error.
    needs_reconnect = models.BooleanField(default=False)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "provider"], name="edms_uniq_user_provider"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.account_email or self.user_id}"

    # -- token accessors ---------------------------------------------------
    # Properties rather than fields so no code path can accidentally read a
    # plaintext attribute off a queryset ``.values()`` or a serializer that
    # walks model fields.

    @property
    def access_token(self) -> str:
        return decrypt_secret(self.access_token_enc)

    @access_token.setter
    def access_token(self, raw: str) -> None:
        self.access_token_enc = encrypt_secret(raw)

    @property
    def refresh_token(self) -> str:
        return decrypt_secret(self.refresh_token_enc)

    @refresh_token.setter
    def refresh_token(self, raw: str) -> None:
        self.refresh_token_enc = encrypt_secret(raw)

    def mark_healthy(self) -> None:
        if self.needs_reconnect or self.last_error:
            self.needs_reconnect = False
            self.last_error = ""
            self.save(update_fields=["needs_reconnect", "last_error"])

    def mark_needs_reconnect(self, error: str) -> None:
        self.needs_reconnect = True
        self.last_error = error[:500]
        self.save(update_fields=["needs_reconnect", "last_error"])


class CaseFolderMapping(models.Model):
    """Per-case override of where a case's filings land and how they're named.

    Empty fields mean "fall back to the user's :class:`EdmsSettings`". This is
    what the extension's per-case gear popover edits, in place, while the
    attorney is looking at the docket."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="edms_case_folders",
    )
    case_number = models.CharField(max_length=64, db_index=True)
    provider = models.CharField(max_length=16, choices=Provider.choices, blank=True, default="")
    folder_id = models.CharField(max_length=512, blank=True, default="")
    folder_path = models.CharField(max_length=1024, blank=True, default="")
    naming_template = models.CharField(max_length=256, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "case_number"], name="edms_uniq_user_case"
            ),
        ]
        ordering = ("case_number",)

    def __str__(self) -> str:
        return f"{self.case_number} -> {self.folder_path}"


class FilingSync(models.Model):
    """One "save this filing to my cloud" operation — metadata only.

    Written when the extension asks for a destination (``pending_upload``),
    completed when the server has independently confirmed with Graph that the
    item exists (``success``). The client's word is never enough: a client that
    says "done" proves nothing, so ``complete`` re-reads the item from the
    provider before this row is allowed to claim success."""

    class Status(models.TextChoices):
        PENDING_UPLOAD = "pending_upload", "Awaiting upload"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="edms_syncs",
    )
    # -- docket metadata scraped from the court page ------------------------
    case_number = models.CharField(max_length=64, db_index=True)
    case_type = models.CharField(max_length=128, blank=True, default="")
    docket_num = models.CharField(max_length=64, blank=True, default="")
    cms_doc_id = models.CharField(max_length=64, blank=True, default="")
    doc_title = models.CharField(max_length=512, blank=True, default="")
    doc_type = models.CharField(max_length=128, blank=True, default="")
    row_date = models.DateField(null=True, blank=True)
    filer = models.CharField(max_length=256, blank=True, default="")
    county = models.CharField(max_length=128, blank=True, default="")
    judge = models.CharField(max_length=256, blank=True, default="")
    # -- destination + outcome ---------------------------------------------
    provider = models.CharField(max_length=16, choices=Provider.choices, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING_UPLOAD
    )
    error = models.TextField(blank=True, default="")
    destination_path = models.CharField(max_length=1024, blank=True, default="")
    destination_filename = models.CharField(max_length=256, blank=True, default="")
    cloud_item_id = models.CharField(max_length=128, blank=True, default="")
    cloud_web_url = models.URLField(max_length=1024, blank=True, default="")
    # Graph upload sessions expire (~15 minutes). Kept so the history UI can say
    # "expired" rather than "pending" forever, and so a retry is a new session.
    upload_expires_at = models.DateTimeField(null=True, blank=True)
    byte_size = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_number}/{self.doc_title} [{self.status}]"


class CrowdsourceArtifact(models.Model):
    """Index row for one opted-in contribution sitting in the private bucket.

    Deliberately inert. There is no read endpoint, no admin download, no
    processing job and no library surface in v1 — the bucket is written and then
    left alone until redaction and a contribution policy exist. This row is what
    makes the bucket purgeable (account deletion, a written removal request, a
    retention rule); without it the bucket is bytes nobody can attribute.

    ``submitted_by`` cascades on purpose. A departing user's objects are deleted
    from the bucket by the ``pre_delete`` receiver in :mod:`apps.edms.signals`
    *before* the cascade removes the rows that name them, so the cascade can
    never orphan bytes. Do not relax this to ``SET_NULL``: an artifact with no
    submitter is an object we can no longer honour a deletion request for.
    """

    class Status(models.TextChoices):
        STORED = "stored", "Stored (awaiting redaction policy)"
        PURGED = "purged", "Purged"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="edms_contributions",
    )
    # Where the bytes are. bucket is denormalized so a later bucket move leaves
    # old rows still resolvable.
    bucket = models.CharField(max_length=128)
    object_key = models.CharField(max_length=512, unique=True)
    byte_size = models.BigIntegerField(default=0)
    content_type = models.CharField(max_length=128, blank=True, default="")
    sha256 = models.CharField(max_length=64, blank=True, default="")
    # -- docket metadata, for the eventual library's filters ----------------
    case_number = models.CharField(max_length=64, blank=True, default="", db_index=True)
    case_type = models.CharField(max_length=128, blank=True, default="", db_index=True)
    doc_type = models.CharField(max_length=128, blank=True, default="", db_index=True)
    doc_title = models.CharField(max_length=512, blank=True, default="")
    county = models.CharField(max_length=128, blank=True, default="")
    row_date = models.DateField(null=True, blank=True)
    # What the safety filter concluded at intake time, so a later policy change
    # can be audited against what was actually applied.
    safety_flags = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.STORED)
    created_at = models.DateTimeField(auto_now_add=True)
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["submitted_by", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.case_type or 'artifact'}/{self.doc_type} [{self.status}]"
