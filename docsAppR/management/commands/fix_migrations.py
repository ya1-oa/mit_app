"""
Management command to fix migration inconsistencies
Run with: python manage.py fix_migrations
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Fixes migration inconsistencies by clearing docsAppR migration history'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('This will clear the migration history for docsAppR app'))
        self.stdout.write(self.style.WARNING('Make sure your database schema is correct before proceeding!'))

        confirm = input('Are you sure you want to continue? (yes/no): ')

        if confirm.lower() != 'yes':
            self.stdout.write(self.style.ERROR('Operation cancelled'))
            return

        try:
            cursor = connection.cursor()

            # Clear docsAppR migration history
            self.stdout.write('Clearing docsAppR migration history...')
            cursor.execute("DELETE FROM django_migrations WHERE app='docsAppR';")
            connection.commit()

            self.stdout.write(self.style.SUCCESS('Successfully cleared migration history'))
            self.stdout.write(self.style.SUCCESS('Now run: python manage.py migrate docsAppR --fake-initial'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            connection.rollback()
