from django.apps import AppConfig


class EdmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.edms"
    verbose_name = "Hudson EDMSpro"

    def ready(self):
        # Registers the pre_delete receiver that purges a departing user's
        # crowdsourced objects out of the bucket BEFORE the cascade removes the
        # index rows that name them. See signals.py.
        from . import signals  # noqa: F401
