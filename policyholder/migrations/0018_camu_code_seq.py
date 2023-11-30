# Generated by Django 3.2.19 on 2023-09-22 14:52

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('policyholder', '0017_auto_20230126_0903'),
    ]

    operations = [
        migrations.RunSQL("""
            CREATE SEQUENCE IF NOT EXISTS public.camu_code_seq
            INCREMENT 1
            START 1
            MINVALUE 1
            MAXVALUE 9223372036854775807
            CACHE 1;
        """, reverse_sql="""DROP SEQUENCE IF EXISTS public.camu_code_seq;"""),
    ]