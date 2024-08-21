# Generated by Django 5.0 on 2024-08-20 23:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('itgdb_site', '0016_imagefile_has_alpha'),
    ]

    operations = [
        migrations.AlterField(
            model_name='song',
            name='artist',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='song',
            name='artist_translit',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='song',
            name='credit',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='song',
            name='subtitle',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AlterField(
            model_name='song',
            name='subtitle_translit',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AlterField(
            model_name='song',
            name='title',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AlterField(
            model_name='song',
            name='title_translit',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]