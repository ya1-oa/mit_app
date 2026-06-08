"""
Sync the canonical lease document templates into the Document model.

The lease generation engine (lease_manager/signature_views.py) renders three
core documents — Engagement Agreement, Term Sheet, Month to Month Rental —
preferring an admin-uploaded Document.file when present, and falling back to the
bundled static repo template when that file is missing from the media volume.

This command (re)uploads the current, cleaned static templates as the official
Document records, so the uploaded copy and the repo copy never diverge. Run it
once after deploying, and again any time you edit one of the static lease
templates:

    python manage.py sync_lease_templates
    python manage.py sync_lease_templates --user admin@example.com

It is idempotent: re-running simply refreshes each Document's file with the
current template content. Existing records keep their category / document_type /
created_by; only the file + size are refreshed.
"""
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from docsAppR.models import Document, DocumentCategory

User = get_user_model()

# (Document.name, static template path under docsAppR/templates/, document_type)
LEASE_TEMPLATES = [
    ('Engagement Agreement',  'account/short_term.html', 'lease'),
    ('Term Sheet',            'account/term_sheet.html', 'lease'),
    ('Month to Month Rental', 'account/lease.html',      'lease'),
]

CATEGORY_NAME = 'Lease Documents'
CATEGORY_SLUG = 'lease-documents'


class Command(BaseCommand):
    help = 'Upload the cleaned static lease templates as canonical Document records.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            dest='user_email',
            default=None,
            help='Email of the user to set as created_by on NEW records '
                 '(defaults to the first superuser).',
        )

    def handle(self, *args, **options):
        # Document.created_by is required (PROTECT) — resolve a user for new records.
        owner = self._resolve_user(options.get('user_email'))

        # Document.category is required (PROTECT) — ensure a category exists.
        category, cat_created = DocumentCategory.objects.get_or_create(
            slug=CATEGORY_SLUG,
            defaults={'name': CATEGORY_NAME, 'icon': 'fas fa-file-contract'},
        )
        if cat_created:
            self.stdout.write(self.style.SUCCESS(f'Created category "{CATEGORY_NAME}".'))

        created = updated = skipped = 0

        for name, rel_path, doc_type in LEASE_TEMPLATES:
            abs_path = os.path.join(settings.BASE_DIR, 'docsAppR', 'templates', rel_path)
            if not os.path.exists(abs_path):
                self.stderr.write(self.style.WARNING(
                    f'SKIP "{name}": static template not found at {abs_path}'
                ))
                skipped += 1
                continue

            with open(abs_path, 'r', encoding='utf-8') as fh:
                data = fh.read().encode('utf-8')
            filename = f"{name.lower().replace(' ', '_')}.html"  # e.g. term_sheet.html

            existing = list(Document.objects.filter(name=name))
            if existing:
                # Refresh every record sharing this name (robust to duplicates).
                for doc in existing:
                    self._write_file(doc, filename, data)
                    doc.size = len(data)
                    doc.save()
                updated += len(existing)
                extra = f' ({len(existing)} records)' if len(existing) > 1 else ''
                self.stdout.write(self.style.SUCCESS(
                    f'UPDATED "{name}"{extra} → {len(data):,} bytes'
                ))
            else:
                doc = Document(
                    name=name,
                    category=category,
                    document_type=doc_type,
                    created_by=owner,
                    description='Canonical lease template (synced from repo).',
                    size=len(data),
                )
                self._write_file(doc, filename, data)
                doc.save()
                created += 1
                self.stdout.write(self.style.SUCCESS(
                    f'CREATED "{name}" → {doc.file.name} ({len(data):,} bytes)'
                ))

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\nDone. {created} created, {updated} updated, {skipped} skipped.'
        ))
        self.stdout.write(
            'These Document records are now the canonical lease templates. The '
            'generator prefers them and falls back to the repo copy if a file '
            'ever goes missing again.'
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _write_file(self, doc, filename, data):
        """Replace the record's file with fresh content (one file per record)."""
        if doc.file and doc.file.name:
            try:
                doc.file.delete(save=False)  # drop the old (possibly-missing) file
            except Exception:
                pass
        doc.file.save(filename, ContentFile(data), save=False)

    def _resolve_user(self, user_email):
        if user_email:
            try:
                return User.objects.get(email=user_email)
            except User.DoesNotExist:
                raise CommandError(f'No user with email {user_email!r}.')
        owner = User.objects.filter(is_superuser=True).order_by('id').first()
        if owner is None:
            owner = User.objects.order_by('id').first()
        if owner is None:
            raise CommandError(
                'No users exist to set as Document.created_by. '
                'Create a superuser first, or pass --user <email>.'
            )
        return owner
