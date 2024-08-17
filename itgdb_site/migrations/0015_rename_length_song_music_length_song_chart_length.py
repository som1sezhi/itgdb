# Generated by Django 5.0 on 2024-08-17 02:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('itgdb_site', '0014_imagefile_song_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='song',
            old_name='length',
            new_name='music_length',
        ),
        migrations.AddField(
            model_name='song',
            name='chart_length',
            field=models.FloatField(default=0.0),
            preserve_default=False,
        ),
    ]