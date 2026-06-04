from django.apps import AppConfig


class IngestionCaselawConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ingestion_caselaw"
    label = "ingestion_caselaw"
    verbose_name = "Iowa caselaw ingestion"
