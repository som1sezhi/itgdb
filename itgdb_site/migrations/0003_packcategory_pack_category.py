# Generated by Django 5.0 on 2024-03-17 02:58

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('itgdb_site', '0002_chart_itgdb_site__steps_t_777d99_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='PackCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
            ],
        ),
        migrations.AddField(
            model_name='pack',
            name='category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='itgdb_site.packcategory'),
        ),
    ]
