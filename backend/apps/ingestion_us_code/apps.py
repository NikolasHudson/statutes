from django.apps import AppConfig


class IngestionUsCodeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ingestion_us_code"
    label = "ingestion_us_code"
    verbose_name = "United States Code ingestion"
