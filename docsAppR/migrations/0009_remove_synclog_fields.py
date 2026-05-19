from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0008_add_comprehensive_ale_fields'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='synclog',
            options={},  # clears ordering
        ),

        migrations.RemoveIndex(
            model_name='synclog',
            name='docsAppR_sy_client__10fcfd_idx',
        ),
        migrations.RemoveIndex(
            model_name='synclog',
            name='docsAppR_sy_sync_st_bd4435_idx',
        ),
        migrations.RemoveIndex(
            model_name='synclog',
            name='docsAppR_sy_timesta_937a13_idx',
        ),
    ]
