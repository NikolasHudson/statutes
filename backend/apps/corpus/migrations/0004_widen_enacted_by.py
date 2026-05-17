from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0003_seed_iowa_code"),
    ]

    operations = [
        migrations.AlterField(
            model_name="nodeversion",
            name="enacted_by",
            field=models.TextField(blank=True),
        ),
    ]
