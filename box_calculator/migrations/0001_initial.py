from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('docsAppR', '0023_add_damaged_value_choice'),
    ]

    operations = [
        migrations.CreateModel(
            name='BoxCalcSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('notes', models.TextField(blank=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='box_calc_sessions', to='docsAppR.client')),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='BoxCalcRoom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_name', models.CharField(max_length=100)),
                ('order', models.PositiveIntegerField(default=0)),
                ('room', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='box_calc_rooms', to='docsAppR.room')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rooms', to='box_calculator.boxcalcsession')),
            ],
            options={
                'ordering': ['order', 'room_name'],
            },
        ),
        migrations.CreateModel(
            name='BoxCalcItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(max_length=40)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('compartments', models.PositiveIntegerField(default=0)),
                ('note', models.CharField(blank=True, max_length=255)),
                ('ai_suggested', models.BooleanField(default=False)),
                ('order', models.PositiveIntegerField(default=0)),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='box_calculator.boxcalcroom')),
            ],
            options={
                'ordering': ['order', 'category'],
            },
        ),
    ]
