from django.apps import AppConfig


class CorpusConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.corpus"
    label = "corpus"
    verbose_name = "Corpus"

    def ready(self):
        # Registers the connection_created receiver that widens hnsw.ef_search.
        from . import signals  # noqa: F401
