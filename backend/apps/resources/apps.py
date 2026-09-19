from django.apps import AppConfig


class ResourcesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.resources"
    verbose_name = "Reference resources"

    def ready(self):
        # Importing the registry imports every dataset module, which is what
        # makes `sync_resource <slug>` and the API routers resolvable. Kept in
        # ready() so the import happens once, after the app registry is loaded.
        from . import registry  # noqa: F401
