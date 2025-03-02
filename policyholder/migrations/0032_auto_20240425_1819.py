# Generated by Django 3.2.22 on 2024-04-25 18:19

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('policyholder', '0031_auto_20240424_1340'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalpolicyholder',
            name='is_rejected',
            field=models.BooleanField(db_column='IsRejected', default=False),
        ),
        migrations.AddField(
            model_name='historicalpolicyholder',
            name='is_rework',
            field=models.BooleanField(db_column='IsRework', default=False),
        ),
        migrations.AddField(
            model_name='historicalpolicyholder',
            name='rejected_reason',
            field=models.CharField(blank=True, db_column='RejectedReason', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='historicalpolicyholder',
            name='rework_comment',
            field=models.CharField(blank=True, db_column='ReworkComment', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='historicalpolicyholder',
            name='rework_option',
            field=models.CharField(blank=True, db_column='ReworkOption', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='historicalpolicyholder',
            name='status',
            field=models.CharField(blank=True, db_column='Status', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='policyholder',
            name='is_rejected',
            field=models.BooleanField(db_column='IsRejected', default=False),
        ),
        migrations.AddField(
            model_name='policyholder',
            name='is_rework',
            field=models.BooleanField(db_column='IsRework', default=False),
        ),
        migrations.AddField(
            model_name='policyholder',
            name='rejected_reason',
            field=models.CharField(blank=True, db_column='RejectedReason', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='policyholder',
            name='rework_comment',
            field=models.CharField(blank=True, db_column='ReworkComment', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='policyholder',
            name='rework_option',
            field=models.CharField(blank=True, db_column='ReworkOption', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='policyholder',
            name='status',
            field=models.CharField(blank=True, db_column='Status', max_length=255, null=True),
        ),
    ]
