from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts"

    def ready(self):
        # Connect the auth-signal receivers that write the security audit
        # trail (login success/failure, logout). Imported here so the handlers
        # register exactly once, after the app registry is populated.
        from . import signals  # noqa: F401
