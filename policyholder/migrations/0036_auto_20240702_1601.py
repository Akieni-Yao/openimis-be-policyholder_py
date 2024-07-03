# Generated by Django 3.2.22 on 2024-07-02 16:01

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('policyholder', '0035_auto_20240702_1531'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalpolicyholder',
            name='erp_partner_access_id',
            field=models.CharField(blank=True, db_column='ErpPartnerAccessID', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='policyholder',
            name='erp_partner_access_id',
            field=models.CharField(blank=True, db_column='ErpPartnerAccessID', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='historicalpolicyholder',
            name='erp_partner_id',
            field=models.IntegerField(blank=True, db_column='ErpPartnerID', null=True),
        ),
        migrations.AlterField(
            model_name='policyholder',
            name='erp_partner_id',
            field=models.IntegerField(blank=True, db_column='ErpPartnerID', null=True),
        ),
    ]