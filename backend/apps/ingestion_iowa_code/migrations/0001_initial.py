from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("corpus", "0003_seed_iowa_code"),
    ]

    operations = [
        migrations.CreateModel(
            name="RawIngestion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "source_kind",
                    models.CharField(
                        choices=[
                            ("probe_json", "Probe JSON"),
                            ("legis_rtf", "legis.iowa.gov RTF"),
                            ("legis_html", "legis.iowa.gov HTML"),
                            ("attorney_json", "Attorney-supplied JSON"),
                        ],
                        max_length=32,
                    ),
                ),
                ("code_year", models.PositiveIntegerField()),
                ("fetched_at", models.DateTimeField(auto_now_add=True)),
                ("fetched_from", models.CharField(blank=True, max_length=500)),
                (
                    "content_hash",
                    models.CharField(db_index=True, max_length=64, unique=True),
                ),
                ("byte_size", models.PositiveBigIntegerField()),
                ("storage_path", models.CharField(max_length=500)),
                ("notes", models.TextField(blank=True)),
            ],
            options={"ordering": ("-fetched_at",)},
        ),
        migrations.CreateModel(
            name="IngestionRun",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("nodes_added", models.PositiveIntegerField(default=0)),
                ("nodes_amended", models.PositiveIntegerField(default=0)),
                ("nodes_repealed", models.PositiveIntegerField(default=0)),
                ("nodes_unchanged", models.PositiveIntegerField(default=0)),
                ("validation_errors", models.JSONField(blank=True, default=list)),
                ("log", models.TextField(blank=True)),
                (
                    "raw",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="runs",
                        to="ingestion_iowa_code.rawingestion",
                    ),
                ),
            ],
            options={"ordering": ("-started_at",)},
        ),
    ]
