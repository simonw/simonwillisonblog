# Generated by Django 5.1 on 2024-08-13 22:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("feedstats", "0002_longer_user_agent_field"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="subscribercount",
            constraint=models.UniqueConstraint(
                fields=("path", "user_agent", "count", "created"),
                name="unique_subscriber_count",
            ),
        ),
    ]
