"""Account deletion purges a user's contributions from the bucket.

The rule Nick set: opting out is prospective — it stops new intake and removes
nothing already shared. Account *deletion* is the other case, and it has to
actually delete, which is only possible while the index rows still exist to name
the objects.

Hence ``pre_delete``, not ``post_delete``: ``CrowdsourceArtifact.submitted_by``
cascades, so by the time the user row is gone the keys are gone too and the
bucket would hold bytes nobody can attribute or remove. Running first — and
letting a storage failure propagate, aborting the whole delete inside Django's
transaction — means the two never diverge.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL, dispatch_uid="edms_purge_contributions")
def purge_contributions_on_user_delete(sender, instance, **kwargs):
    from .services import purge_user_contributions

    count = purge_user_contributions(instance, mark_purged=False)
    if count:
        logger.info(
            "edms: purged %s contributed object(s) for deleted user %s",
            count,
            instance.pk,
        )
