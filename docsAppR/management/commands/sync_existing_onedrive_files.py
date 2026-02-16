"""
Management command to scan and import existing OneDrive folder structure and files.
This is useful for initial setup to sync existing claims already in OneDrive.

Usage:
    python manage.py sync_existing_onedrive_files
    python manage.py sync_existing_onedrive_files --folder-path "Specific Folder Path"
    python manage.py sync_existing_onedrive_files --claim-id 123
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from docsAppR.models import Client, OneDriveFolder, OneDriveFile, SyncLog
from docsAppR.file_manager import OneDriveManager  # TODO: Rename class
import json
from datetime import datetime


class Command(BaseCommand):
    help = 'Scan and import existing OneDrive folder structure and files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--folder-path',
            type=str,
            help='Specific folder path to sync (e.g., "John Doe@123 Main Street")',
        )
        parser.add_argument(
            '--claim-id',
            type=int,
            help='Specific claim ID to sync',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes',
        )

    def handle(self, *args, **options):
        folder_path = options.get('folder_path')
        claim_id = options.get('claim_id')
        dry_run = options.get('dry_run', False)

        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('OneDrive Existing Files Sync'))
        self.stdout.write(self.style.SUCCESS('=' * 70))

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        try:
            # Initialize OneDrive manager
            self.stdout.write('Initializing OneDrive manager...')
            manager = OneDriveManager()

            if claim_id:
                # Sync specific claim
                self.sync_claim(manager, claim_id, dry_run)
            elif folder_path:
                # Sync specific folder
                self.sync_folder_path(manager, folder_path, dry_run)
            else:
                # Scan all root folders
                self.scan_root_folders(manager, dry_run)

            self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
            self.stdout.write(self.style.SUCCESS('Sync completed successfully!'))
            self.stdout.write(self.style.SUCCESS('=' * 70))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\nError: {str(e)}'))
            raise

    def sync_claim(self, manager, claim_id, dry_run):
        """Sync a specific claim by ID"""
        self.stdout.write(f'\nSyncing claim ID: {claim_id}')

        try:
            client = Client.objects.get(id=claim_id)
            self.stdout.write(f'Found claim: {client.pOwner} - {client.claimNumber}')

            # Generate expected folder path
            folder_name = f"{client.pOwner}@{client.pAddress}"
            self.sync_folder_path(manager, folder_name, dry_run, client)

        except Client.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Claim {claim_id} not found'))

    def sync_folder_path(self, manager, folder_path, dry_run, client=None):
        """Sync a specific folder path"""
        self.stdout.write(f'\nSearching for folder: {folder_path}')

        try:
            # Search for the folder in OneDrive
            folder_id = self.find_folder_by_path(manager, folder_path)

            if not folder_id:
                self.stdout.write(self.style.WARNING(f'Folder not found: {folder_path}'))
                return

            self.stdout.write(self.style.SUCCESS(f'Found folder: {folder_id}'))

            # Get folder metadata
            folder_metadata = manager.get_file_metadata(folder_id)

            # Find or create client if not provided
            if not client:
                client = self.find_or_create_client_from_folder(folder_metadata, dry_run)

            if client and not dry_run:
                # Sync the folder and its contents
                self.sync_folder_tree(manager, folder_id, folder_path, client, dry_run)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error syncing folder: {str(e)}'))

    def scan_root_folders(self, manager, dry_run):
        """Scan all folders in the root directory"""
        self.stdout.write('\nScanning root directory for claim folders...')

        try:
            # List all folders in root
            items = manager.list_folder_contents('root')

            claim_folders = []
            for item in items:
                if item.get('folder'):
                    name = item.get('name', '')
                    # Look for folders matching pattern: "Name@Address"
                    if '@' in name:
                        claim_folders.append(item)

            self.stdout.write(f'Found {len(claim_folders)} potential claim folders')

            for folder in claim_folders:
                folder_name = folder.get('name')
                folder_id = folder.get('id')

                self.stdout.write(f'\n{"-" * 70}')
                self.stdout.write(f'Processing: {folder_name}')

                # Try to find matching client
                client = self.find_client_by_folder_name(folder_name)

                if client:
                    self.stdout.write(self.style.SUCCESS(f'Matched to client: {client.pOwner}'))
                    if not dry_run:
                        self.sync_folder_tree(manager, folder_id, folder_name, client, dry_run)
                else:
                    self.stdout.write(self.style.WARNING(f'No matching client found for: {folder_name}'))
                    self.stdout.write('Consider creating the client first or using --folder-path')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error scanning root: {str(e)}'))

    def sync_folder_tree(self, manager, folder_id, folder_path, client, dry_run):
        """Recursively sync folder tree and files"""
        self.stdout.write(f'\nSyncing folder tree: {folder_path}')

        try:
            # Create or update OneDriveFolder record
            if not dry_run:
                od_folder, created = OneDriveFolder.objects.update_or_create(
                    client=client,
                    folder_path=folder_path,
                    defaults={
                        'onedrive_id': folder_id,
                        'last_synced_from_onedrive': datetime.now(),
                    }
                )
                action = 'Created' if created else 'Updated'
                self.stdout.write(f'  {action} folder record: {folder_path}')
            else:
                self.stdout.write(f'  [DRY RUN] Would create/update folder: {folder_path}')

            # Get folder contents
            items = manager.list_folder_contents(folder_id)

            file_count = 0
            subfolder_count = 0

            for item in items:
                item_name = item.get('name')
                item_id = item.get('id')

                if item.get('folder'):
                    # Subfolder - recurse
                    subfolder_count += 1
                    subfolder_path = f"{folder_path}/{item_name}"
                    self.sync_folder_tree(manager, item_id, subfolder_path, client, dry_run)

                elif item.get('file'):
                    # File - create record
                    file_count += 1
                    if not dry_run:
                        file_size = item.get('size', 0)
                        etag = item.get('eTag', '')
                        modified = item.get('lastModifiedDateTime', '')

                        OneDriveFile.objects.update_or_create(
                            folder=od_folder,
                            file_name=item_name,
                            defaults={
                                'onedrive_id': item_id,
                                'file_size_bytes': file_size,
                                'etag': etag,
                                'last_modified_onedrive': modified,
                                'last_synced_to_django': datetime.now(),
                                'sync_status': 'synced',
                            }
                        )
                        self.stdout.write(f'    File: {item_name} ({file_size} bytes)')
                    else:
                        self.stdout.write(f'    [DRY RUN] Would sync file: {item_name}')

            if file_count > 0 or subfolder_count > 0:
                self.stdout.write(self.style.SUCCESS(
                    f'  Synced {file_count} files and {subfolder_count} subfolders'
                ))

            # Create sync log
            if not dry_run and file_count > 0:
                SyncLog.objects.create(
                    client=client,
                    folder=od_folder,
                    sync_direction='onedrive_to_django',
                    sync_status='success',
                    items_synced=file_count,
                    duration_seconds=0,
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error syncing folder tree: {str(e)}'))
            if not dry_run:
                SyncLog.objects.create(
                    client=client,
                    sync_direction='onedrive_to_django',
                    sync_status='error',
                    error_message=str(e),
                )

    def find_folder_by_path(self, manager, folder_path):
        """Find a folder by path in OneDrive"""
        try:
            # Try to get the folder by path
            # Assuming folder is in root, try direct lookup
            parts = folder_path.split('/')
            root_folder = parts[0]

            items = manager.list_folder_contents('root')

            for item in items:
                if item.get('name') == root_folder and item.get('folder'):
                    return item.get('id')

            return None

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error finding folder: {str(e)}'))
            return None

    def find_client_by_folder_name(self, folder_name):
        """Find a client by parsing folder name (Name@Address)"""
        try:
            if '@' not in folder_name:
                return None

            parts = folder_name.split('@')
            owner_name = parts[0].strip()
            address = '@'.join(parts[1:]).strip() if len(parts) > 1 else ''

            # Try to find matching client
            clients = Client.objects.filter(pOwner__icontains=owner_name)

            if address:
                clients = clients.filter(pAddress__icontains=address)

            if clients.count() == 1:
                return clients.first()
            elif clients.count() > 1:
                self.stdout.write(self.style.WARNING(
                    f'Multiple clients found for {folder_name}, using first match'
                ))
                return clients.first()

            return None

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error finding client: {str(e)}'))
            return None

    def find_or_create_client_from_folder(self, folder_metadata, dry_run):
        """Find or optionally create a client from folder metadata"""
        folder_name = folder_metadata.get('name', '')

        client = self.find_client_by_folder_name(folder_name)

        if client:
            return client

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[DRY RUN] No client found for folder: {folder_name}'
            ))
            return None

        # For now, don't auto-create clients - require manual creation
        self.stdout.write(self.style.WARNING(
            f'No client found for folder: {folder_name}'
        ))
        self.stdout.write('Please create the client manually first, then run sync again')

        return None
