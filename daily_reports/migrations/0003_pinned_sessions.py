from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('daily_reports', '0002_prioritytask'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyreportconfig',
            name='pinned_ppr_sessions',
            field=models.JSONField(blank=True, default=list,
                help_text='List of CPSReportSession IDs to feature in the daily report'),
        ),
        migrations.AddField(
            model_name='dailyreportconfig',
            name='pinned_leases',
            field=models.JSONField(blank=True, default=list,
                help_text='List of Lease IDs to feature in the daily report'),
        ),
    ]
