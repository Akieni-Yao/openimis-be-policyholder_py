# Generated by Django 3.2.22 on 2024-04-24 13:40

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('policyholder', '0030_auto_20240423_1711'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalpolicyholder',
            name='form_ims',
            field=models.BooleanField(db_column='FormIMS', default=False),
        ),
        migrations.AddField(
            model_name='policyholder',
            name='form_ims',
            field=models.BooleanField(db_column='FormIMS', default=False),
        ),
    ]
