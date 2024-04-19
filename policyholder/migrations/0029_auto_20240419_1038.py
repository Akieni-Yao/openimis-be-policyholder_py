# Generated by Django 3.2.22 on 2024-04-19 10:38

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('policyholder', '0028_auto_20240417_1451'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalpolicyholder',
            name='is_approved',
            field=models.BooleanField(db_column='IsApproved', default=False),
        ),
        migrations.AddField(
            model_name='policyholder',
            name='is_approved',
            field=models.BooleanField(db_column='IsApproved', default=False),
        ),
        migrations.AlterField(
            model_name='historicalpolicyholder',
            name='code',
            field=models.CharField(db_column='PolicyHolderCode', max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name='policyholder',
            name='code',
            field=models.CharField(db_column='PolicyHolderCode', max_length=32, null=True),
        ),
    ]
