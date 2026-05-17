from django.apps import AppConfig


class IngestionIowaCodeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ingestion_iowa_code"
    label = "ingestion_iowa_code"
    verbose_name = "Iowa Code ingestion"
