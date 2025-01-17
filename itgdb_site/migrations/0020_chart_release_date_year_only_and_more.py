# Generated by Django 5.0 on 2024-12-08 09:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('itgdb_site', '0019_alter_chart_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='chart',
            name='release_date_year_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='pack',
            name='release_date_year_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='song',
            name='release_date_year_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name='chart',
            constraint=models.CheckConstraint(check=models.Q(('release_date_year_only', False), ('release_date__isnull', False), _connector='OR'), name='cannot_limit_chart_date_to_only_the_year_if_date_is_null'),
        ),
        migrations.AddConstraint(
            model_name='pack',
            constraint=models.CheckConstraint(check=models.Q(('release_date_year_only', False), ('release_date__isnull', False), _connector='OR'), name='cannot_limit_pack_date_to_only_the_year_if_date_is_null'),
        ),
        migrations.AddConstraint(
            model_name='song',
            constraint=models.CheckConstraint(check=models.Q(('release_date_year_only', False), ('release_date__isnull', False), _connector='OR'), name='cannot_limit_song_date_to_only_the_year_if_date_is_null'),
        ),
    ]
