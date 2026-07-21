from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0013_room_sources'),
    ]

    operations = [
        migrations.CreateModel(
            name='PPRBoxCount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='box_count',
                    to='cps_report.cpsreportsession',
                )),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='PPRBoxCountRoom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_name', models.CharField(max_length=200)),
                ('order', models.PositiveIntegerField(default=0)),
                ('small', models.PositiveIntegerField(default=0)),
                ('medium', models.PositiveIntegerField(default=0)),
                ('large', models.PositiveIntegerField(default=0)),
                ('box_wrapped', models.PositiveIntegerField(default=0)),
                ('picture_mirror', models.PositiveIntegerField(default=0)),
                ('plant_vase', models.PositiveIntegerField(default=0)),
                ('tv', models.PositiveIntegerField(default=0)),
                ('wardrobe', models.PositiveIntegerField(default=0)),
                ('mattress', models.PositiveIntegerField(default=0)),
                ('dish_pack', models.PositiveIntegerField(default=0)),
                ('glass_pack', models.PositiveIntegerField(default=0)),
                ('boots_pans', models.PositiveIntegerField(default=0)),
                ('box_count', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rooms',
                    to='cps_report.pprboxcount',
                )),
            ],
            options={
                'ordering': ['order', 'room_name'],
            },
        ),
    ]
