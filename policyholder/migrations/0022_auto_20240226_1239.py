# Generated by Django 3.2.21 on 2024-02-26 12:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('policyholder', '0021_auto_20231201_1516'),
    ]

    operations = [
        migrations.CreateModel(
            name='PolicyHolderExcption',
            fields=[
                ('id', models.AutoField(db_column='InsureeExptionID', primary_key=True, serialize=False)),
                ('status', models.CharField(db_column='Status', max_length=255, null=True)),
                ('exception_reason', models.CharField(db_column='ExceptionReason', max_length=255, null=True)),
                ('rejection_reason', models.CharField(db_column='RejectionReason', max_length=255, null=True)),
                ('created_by', models.CharField(db_column='CreatedBy', max_length=56, null=True)),
                ('modified_by', models.CharField(db_column='ModifiedBy', max_length=56, null=True)),
                ('created_time', models.DateTimeField(auto_now_add=True, db_column='CreatedTime', null=True)),
                ('modified_time', models.DateTimeField(auto_now=True, db_column='ModifiedTime', null=True)),
                ('policy_holder', models.ForeignKey(db_column='PolicyHolder', on_delete=django.db.models.deletion.DO_NOTHING, to='policyholder.policyholder')),
            ],
            options={
                'db_table': 'tblPolicyHolderException',
                'managed': True,
            },
        ),
    ]