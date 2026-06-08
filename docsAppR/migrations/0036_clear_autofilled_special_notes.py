from django.db import migrations


def clear_autofilled_special_notes(apps, schema_editor):
    """
    Remove the auto-generated lessee summary that used to be written into
    Lease.special_notes, e.g.:
        "Lessee: THOMAS, ANITA | Phone: (216) 315-2040 | Email: A@EM | ..."

    Detection is conservative — only values that match that machine-generated
    shape are cleared, so any genuinely user-entered note is left untouched.
    """
    Lease = apps.get_model('docsAppR', 'Lease')
    LABELS = ('Lessee:', 'Phone:', 'Email:', 'Home Address:')
    for lease in Lease.objects.exclude(special_notes='').only('id', 'special_notes').iterator():
        sn = (lease.special_notes or '').strip()
        looks_autofilled = (
            sn.startswith('Lessee:')
            or (' | ' in sn and any(lbl in sn for lbl in LABELS))
        )
        if looks_autofilled:
            lease.special_notes = ''
            lease.save(update_fields=['special_notes'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0035_client_ale_rental_security_deposit'),
    ]

    operations = [
        migrations.RunPython(clear_autofilled_special_notes, noop_reverse),
    ]
