# Generated by Django 5.0 on 2024-08-20 04:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('itgdb_site', '0015_rename_length_song_music_length_song_chart_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='imagefile',
            name='has_alpha',
            field=models.BooleanField(default=False),
            preserve_default=False,
        ),
    ]
