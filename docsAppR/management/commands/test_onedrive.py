# docsAppR/management/commands/test_onedrive.py

from django.core.management.base import BaseCommand
from docsAppR.onedrive_manager import OneDriveManager
import json


class Command(BaseCommand):
    help = 'Test OneDrive connection and list root folder contents'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Testing OneDrive connection...'))

        try:
            # Initialize OneDrive manager
            manager = OneDriveManager()
            self.stdout.write("✓ OneDrive manager initialized")

            # Test authentication
            manager.authenticate()
            self.stdout.write(self.style.SUCCESS("✓ Authentication successful"))

            # Get drive ID
            drive_id = manager.get_drive_id()
            self.stdout.write(f"✓ Drive ID: {drive_id}")

            # List root folder contents
            self.stdout.write("\nListing root folder contents:")
            root_contents = manager.list_folder_contents('root')

            if not root_contents:
                self.stdout.write(self.style.WARNING("  No items found in root folder"))
                return

            # Display folders
            folders = [item for item in root_contents if 'folder' in item]
            if folders:
                self.stdout.write(self.style.SUCCESS(f"\n  Folders ({len(folders)}):"))
                for folder in folders:
                    self.stdout.write(f"    📁 {folder['name']}")

            # Display files
            files = [item for item in root_contents if 'file' in item]
            if files:
                self.stdout.write(self.style.SUCCESS(f"\n  Files ({len(files)}):"))
                for file in files:
                    size_mb = file.get('size', 0) / (1024 * 1024)
                    self.stdout.write(f"    📄 {file['name']} ({size_mb:.2f} MB)")

            self.stdout.write(self.style.SUCCESS("\n✅ OneDrive connection test completed successfully!"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())
