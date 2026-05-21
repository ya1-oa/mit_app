from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0023_add_damaged_value_choice'),
    ]

    operations = [
        # Widen room_name to accommodate long Encircle entry strings
        migrations.AlterField(
            model_name='room',
            name='room_name',
            field=models.CharField(max_length=512),
        ),
        # Remove the unique_together constraint so base + generated entries
        # can coexist for the same client
        migrations.AlterUniqueTogether(
            name='room',
            unique_together=set(),
        ),
        # Add the flag distinguishing base rooms from generated entries
        migrations.AddField(
            model_name='room',
            name='is_encircle_entry',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='True = generated numbered Encircle room entry; False = editable base room name',
            ),
        ),
        # Add compound index for efficient filtering
        migrations.AddIndex(
            model_name='room',
            index=models.Index(
                fields=['client', 'is_encircle_entry'],
                name='docsappr_room_client_is_encircle_idx',
            ),
        ),
    ]
