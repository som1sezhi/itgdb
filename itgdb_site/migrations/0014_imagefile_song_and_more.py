# Generated by Django 5.0 on 2024-08-15 06:45

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('itgdb_site', '0013_remove_chart_density_graph'),
    ]

    operations = [
        migrations.AddField(
            model_name='imagefile',
            name='song',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='itgdb_site.song'),
        ),
        migrations.AddConstraint(
            model_name='imagefile',
            constraint=models.CheckConstraint(check=models.Q(('pack__isnull', False), ('song__isnull', False), _negated=True), name='cannot_belong_to_both_pack_and_single'),
        ),
    ]
