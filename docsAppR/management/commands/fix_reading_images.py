"""
Django management command to fix ReadingImage records where the filename 
doesn't match the actual file path.

Save this file as: your_app/management/commands/fix_reading_images.py
Run with: python manage.py fix_reading_images
"""

from django.core.management.base import BaseCommand
from docsAppR.models import ReadingImage  # Replace 'your_app' with your actual app name
import os


class Command(BaseCommand):
    help = 'Fix ReadingImage records where filename and file path are out of sync'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))
        
        images = ReadingImage.objects.all()
        total = images.count()
        fixed = 0
        errors = 0
        
        self.stdout.write(f'Processing {total} images...\n')
        
        for image in images:
            try:
                if not image.file:
                    self.stdout.write(self.style.ERROR(f'  ✗ Image {image.id}: No file attached'))
                    errors += 1
                    continue
                
                # Get the actual file path and check if it exists
                expected_path = image.file.path
                expected_filename = os.path.basename(expected_path)
                
                # Check if the file exists at the expected path
                if os.path.exists(expected_path):
                    # File exists where Django thinks it is
                    if image.filename != expected_filename:
                        self.stdout.write(
                            self.style.NOTICE(
                                f'  ℹ Image {image.id}: Filename mismatch but file exists at expected location'
                            )
                        )
                        self.stdout.write(f'    DB filename: {image.filename}')
                        self.stdout.write(f'    Actual file: {expected_filename}')
                        
                        if not dry_run:
                            image.filename = expected_filename
                            image.extract_values_from_filename()
                            image.save()
                            self.stdout.write(self.style.SUCCESS(f'    ✓ Updated filename to match file path'))
                        fixed += 1
                    continue
                
                # File doesn't exist at expected path - search for it in the same directory
                file_dir = os.path.dirname(expected_path)
                
                if not os.path.exists(file_dir):
                    self.stdout.write(
                        self.style.ERROR(
                            f'  ✗ Image {image.id}: Directory does not exist: {file_dir}'
                        )
                    )
                    errors += 1
                    continue
                
                # Look for a file matching the stored filename
                possible_path = os.path.join(file_dir, image.filename)
                
                if os.path.exists(possible_path):
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ! Image {image.id}: File path mismatch - fixing'
                        )
                    )
                    self.stdout.write(f'    Expected: {expected_path}')
                    self.stdout.write(f'    Found at: {possible_path}')
                    
                    if not dry_run:
                        # Update the file field to point to the correct location
                        old_file_name = image.file.name
                        new_file_name = os.path.join(
                            os.path.dirname(old_file_name), 
                            image.filename
                        )
                        image.file.name = new_file_name
                        image.save()
                        self.stdout.write(self.style.SUCCESS(f'    ✓ Fixed file path'))
                    fixed += 1
                else:
                    # File not found anywhere - list what's in the directory
                    files_in_dir = os.listdir(file_dir)
                    self.stdout.write(
                        self.style.ERROR(
                            f'  ✗ Image {image.id}: File not found'
                        )
                    )
                    self.stdout.write(f'    Looking for: {image.filename}')
                    self.stdout.write(f'    In directory: {file_dir}')
                    self.stdout.write(f'    Files in directory: {", ".join(files_in_dir[:10])}')
                    if len(files_in_dir) > 10:
                        self.stdout.write(f'    ... and {len(files_in_dir) - 10} more')
                    errors += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'  ✗ Image {image.id}: Unexpected error: {str(e)}'
                    )
                )
                errors += 1
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'Total images processed: {total}'))
        if dry_run:
            self.stdout.write(self.style.WARNING(f'Would fix: {fixed}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Fixed: {fixed}'))
        self.stdout.write(self.style.ERROR(f'Errors: {errors}'))
        self.stdout.write('='*60)
        
        if dry_run and fixed > 0:
            self.stdout.write(
                self.style.NOTICE(
                    '\nRun without --dry-run to apply these fixes'
                )
            )