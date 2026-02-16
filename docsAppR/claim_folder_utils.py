"""
Claim Folder Management Utilities

This module provides functions for creating and managing claim folder structures
on the server filesystem, replacing the previous OneDrive-based approach.
"""

import os
import re
import json
import shutil
from pathlib import Path
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


# Standard folder structure for claims
# This matches the OneDrive structure exactly:
# - Main folders: EXT EMS, MIT, CPS, BASIC DOCS OUT, REBUILD, Templates, BU
# - Each main folder (except Templates) has: FINAL V2, SPLM subfolders and various .txt files
# - Templates folder contains all Excel templates

def get_folder_structure(folder_name):
    """
    Generate complete folder structure matching OneDrive structure.

    Args:
        folder_name: Client folder name (e.g., "ClientName@Address")

    Returns:
        dict: Folder structure with paths and files to create
    """
    # Main folder names
    main_folders = {
        'EXT_EMS': f"EXT EMS {folder_name}",
        'MIT': f"MIT {folder_name}",
        'CPS': f"CPS {folder_name}",
        'BASIC_DOCS_OUT': f"BASIC DOCS OUT {folder_name}",
        'REBUILD': f"REBUILD {folder_name}",
        'TEMPLATES': f"Templates {folder_name}",
        'BU': f"BU {folder_name}"
    }

    # Standard subfolders for all main folders except Templates
    standard_subfolders = ['FINAL V2', 'SPLM']

    # Text files to create in each main folder (except Templates)
    text_files = {
        '.0 EMAIL #1.txt': '',
        '7. EMAIL #2.txt': '',
        '11. OTHER #3.txt': '',
    }

    structure = {
        'folders': [],
        'files': {}
    }

    # Create structure for each main folder
    for key, folder_name in main_folders.items():
        structure['folders'].append(folder_name)

        if key != 'TEMPLATES':  # Templates folder doesn't get subfolders or txt files
            # Add subfolders
            for subfolder in standard_subfolders:
                structure['folders'].append(f"{folder_name}/{subfolder}")

            # Add text files
            for txt_file, content in text_files.items():
                file_path = f"{folder_name}/{txt_file}"
                structure['files'][file_path] = content

    return structure


def get_claims_root():
    """Get the root directory for all claim folders"""
    claims_root = os.path.join(settings.MEDIA_ROOT, 'claims')
    os.makedirs(claims_root, exist_ok=True)
    return claims_root


def create_claim_folder_structure(client, created_by=None):
    """
    Create the standard folder structure for a claim on the server.
    This matches the OneDrive folder structure exactly.

    Args:
        client: Client model instance
        created_by: User who created the structure (optional)

    Returns:
        dict: Created folder information including path and template folder location

    Raises:
        OSError: If folder creation fails
    """
    try:
        # Generate client-specific folder name (ClientName@Address format)
        client_folder_name = f"{client.pOwner}@{client.pAddress}" if client.pOwner and client.pAddress else f"Client_{client.id}"
        # Clean for filesystem
        safe_folder_name = re.sub(r'[<>:"/\\|?*]', '_', client_folder_name)

        # Get or create the folder path
        if not client.server_folder_path:
            client.server_folder_path = os.path.join(get_claims_root(), safe_folder_name)

        claim_folder = client.server_folder_path

        # Create main folder
        os.makedirs(claim_folder, exist_ok=True)
        logger.info(f"Created claim folder: {claim_folder}")

        # Get the folder structure definition
        structure = get_folder_structure(safe_folder_name)

        # Create all folders
        for folder_path in structure['folders']:
            full_path = os.path.join(claim_folder, folder_path)
            os.makedirs(full_path, exist_ok=True)
            logger.info(f"Created folder: {folder_path}")

        # Create all text files
        for file_path, content in structure['files'].items():
            full_file_path = os.path.join(claim_folder, file_path)
            with open(full_file_path, 'w') as f:
                f.write(content)
            logger.info(f"Created file: {file_path}")

        # Create a metadata file in the root
        metadata = {
            'client_id': client.id,
            'client_name': client.pOwner,
            'address': client.pAddress,
            'claim_number': client.claimNumber,
            'folder_name': safe_folder_name,
            'created_at': timezone.now().isoformat(),
            'created_by': created_by.email if created_by else None,
        }

        metadata_path = os.path.join(claim_folder, 'claim_metadata.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Update client record
        client.folder_created_at = timezone.now()
        if created_by:
            client.last_modified_by = created_by
        client.save(update_fields=['server_folder_path', 'folder_created_at', 'last_modified_by'])

        logger.info(f"Created complete folder structure for claim {client.id}")

        # Return information about created structure
        return {
            'claim_folder': claim_folder,
            'templates_folder': os.path.join(claim_folder, f"Templates {safe_folder_name}"),
            'folder_name': safe_folder_name,
            'created_folders': structure['folders'],
            'created_files': list(structure['files'].keys())
        }

    except Exception as e:
        logger.error(f"Failed to create claim folder structure: {str(e)}")
        raise


def save_rooms_to_json(client):
    """
    Save room data to JSON file in the Templates folder.
    This will later be used to populate the 01-ROOMS Excel template.

    Args:
        client: Client model instance with rooms

    Returns:
        str: Path to the saved JSON file
    """
    try:
        # Use consistent helper function to get templates folder path
        templates_folder = get_templates_folder(client)
        os.makedirs(templates_folder, exist_ok=True)

        # Get rooms data
        rooms_data = {
            'client_id': client.id,
            'client_name': client.pOwner,
            'address': client.pAddress,
            'updated_at': timezone.now().isoformat(),
            'rooms': []
        }

        for room in client.rooms.all().order_by('sequence'):
            room_info = {
                'id': str(room.id),
                'name': room.room_name,
                'sequence': room.sequence,
                'work_types': {}
            }

            # Add work type values
            for wt_value in room.work_type_values.select_related('work_type'):
                room_info['work_types'][str(wt_value.work_type.work_type_id)] = {
                    'value_type': wt_value.value_type,
                    'numeric_value': str(wt_value.numeric_value) if wt_value.numeric_value else None,
                    'notes': wt_value.notes
                }

            rooms_data['rooms'].append(room_info)

        # Save to Templates folder as JSON
        rooms_file = os.path.join(templates_folder, '01-ROOMS_data.json')
        with open(rooms_file, 'w') as f:
            json.dump(rooms_data, f, indent=2)

        logger.info(f"Saved {len(rooms_data['rooms'])} rooms to {rooms_file}")
        return rooms_file

    except Exception as e:
        logger.error(f"Failed to save rooms data: {str(e)}")
        raise


def save_client_info_to_json(client):
    """
    Save client information to JSON file in the Templates folder.
    This will later be used to populate the 01-INFO Excel template.

    Args:
        client: Client model instance

    Returns:
        str: Path to the saved JSON file
    """
    try:
        # Use consistent helper function to get templates folder path
        templates_folder = get_templates_folder(client)
        os.makedirs(templates_folder, exist_ok=True)

        # Build client data dictionary - COMPLETE client information
        # Matching InfoTemplateGenerator.FIELD_MAPPING to ensure all fields are exported
        client_data = {
            'client_id': client.id,
            'updated_at': timezone.now().isoformat(),

            # Property Owner / Customer Info
            'customer': {
                'pOwner': client.pOwner or '',
                'pAddress': client.pAddress or '',
                'pCityStateZip': client.pCityStateZip or '',
                'cEmail': client.cEmail or '',
                'cPhone': client.cPhone or '',
                'coOwner2': client.coOwner2 or '',
                'cPhone2': client.cPhone2 or '',
                'cAddress2': client.cAddress2 or '',
                'cCityStateZip2': getattr(client, 'cCityStateZip2', '') or '',
                'cEmail2': client.cEmail2 or '',
            },

            # Claim Details
            'claim': {
                'claimNumber': client.claimNumber or '',
                'policyNumber': client.policyNumber or '',
                'causeOfLoss': client.causeOfLoss or '',
                'dateOfLoss': client.dateOfLoss.isoformat() if client.dateOfLoss else '',
                'contractDate': client.contractDate.isoformat() if client.contractDate else '',
                'yearBuilt': client.yearBuilt or '',
            },

            # Insurance Company Info
            'insurance': {
                'insuranceCo_Name': client.insuranceCo_Name or '',
                'insuranceCoPhone': client.insuranceCoPhone or '',
                'deskAdjusterDA': client.deskAdjusterDA or '',
                'DAPhone': client.DAPhone or '',
                'DAEmail': client.DAEmail or '',
                'DAPhExt': getattr(client, 'DAPhExt', '') or '',
                'fieldAdjusterName': client.fieldAdjusterName or '',
                'phoneFieldAdj': client.phoneFieldAdj or '',
                'fieldAdjEmail': client.fieldAdjEmail or '',
            },

            # Mortgage Info
            'mortgage': {
                'mortgageCo': client.mortgageCo or '',
                'mortgageAccountCo': client.mortgageAccountCo or '',
                'mortgageContactPerson': client.mortgageContactPerson or '',
                'mortgagePhoneContact': client.mortgagePhoneContact or '',
                'mortgageEmail': client.mortgageEmail or '',
            },

            # Contractor Info
            'contractor': {
                'coName': client.coName or '',
                'coWebsite': client.coWebsite or '',
                'coAddress': client.coAddress or '',
                'coPhone': getattr(client, 'coPhone', '') or '',
            },
        }

        # Save to Templates folder
        info_file = os.path.join(templates_folder, '01-INFO_data.json')
        with open(info_file, 'w') as f:
            json.dump(client_data, f, indent=2)

        logger.info(f"Saved client info to {info_file}")
        return info_file

    except Exception as e:
        logger.error(f"Failed to save client info: {str(e)}")
        raise


def load_rooms_from_json(client):
    """
    Load room data from JSON file in the Templates folder.

    Args:
        client: Client model instance

    Returns:
        dict: Rooms data or None if file doesn't exist
    """
    try:
        claim_folder = client.get_server_folder_path()

        # Get the folder name for this client
        client_folder_name = f"{client.pOwner}@{client.pAddress}" if client.pOwner and client.pAddress else f"Client_{client.id}"
        safe_folder_name = re.sub(r'[<>:"/\\|?*]', '_', client_folder_name)

        # Load from Templates folder
        templates_folder = os.path.join(claim_folder, f"Templates {safe_folder_name}")
        rooms_file = os.path.join(templates_folder, '01-ROOMS_data.json')

        if os.path.exists(rooms_file):
            with open(rooms_file, 'r') as f:
                return json.load(f)
        return None

    except Exception as e:
        logger.error(f"Failed to load rooms data: {str(e)}")
        return None


def get_folder_files(client, folder_type=None):
    """
    Get list of files in a claim folder.

    Args:
        client: Client model instance
        folder_type: Optional folder type filter (e.g., '82-MIT', '01-INFO')

    Returns:
        list: List of file dictionaries with metadata
    """
    try:
        claim_folder = client.get_server_folder_path()

        if not os.path.exists(claim_folder):
            return []

        search_path = claim_folder
        if folder_type:
            search_path = os.path.join(claim_folder, folder_type)

        files = []
        for root, dirs, filenames in os.walk(search_path):
            for filename in filenames:
                # Skip metadata and internal JSON data files
                if filename.endswith('.json'):
                    continue

                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, claim_folder)

                # Determine folder type
                parts = rel_path.split(os.sep)
                file_folder_type = parts[0] if len(parts) > 0 else 'OTHER'

                stat_info = os.stat(filepath)
                files.append({
                    'filename': filename,
                    'relative_path': rel_path,
                    'folder_type': file_folder_type,
                    'size': stat_info.st_size,
                    'modified': timezone.datetime.fromtimestamp(stat_info.st_mtime),
                    'full_path': filepath,
                })

        return files

    except Exception as e:
        logger.error(f"Failed to get folder files: {str(e)}")
        return []


def copy_file_to_claim_folder(client, source_file_path, destination_folder_type, new_filename=None):
    """
    Copy a file to the claim folder.

    Args:
        client: Client model instance
        source_file_path: Path to source file
        destination_folder_type: Destination folder (e.g., '82-MIT', '01-INFO')
        new_filename: Optional new filename (defaults to original)

    Returns:
        str: Path to copied file
    """
    try:
        claim_folder = client.get_server_folder_path()
        dest_folder = os.path.join(claim_folder, destination_folder_type)
        os.makedirs(dest_folder, exist_ok=True)

        filename = new_filename or os.path.basename(source_file_path)
        dest_path = os.path.join(dest_folder, filename)

        # Copy file
        shutil.copy2(source_file_path, dest_path)
        logger.info(f"Copied file to {dest_path}")

        return dest_path

    except Exception as e:
        logger.error(f"Failed to copy file: {str(e)}")
        raise


def delete_claim_folder(client, archive=True):
    """
    Delete or archive a claim folder.

    Args:
        client: Client model instance
        archive: If True, move to archive folder instead of deleting

    Returns:
        bool: Success status
    """
    try:
        claim_folder = client.get_server_folder_path()

        if not os.path.exists(claim_folder):
            logger.warning(f"Claim folder does not exist: {claim_folder}")
            return True

        if archive:
            # Move to archive
            archive_root = os.path.join(settings.MEDIA_ROOT, 'claims_archive')
            os.makedirs(archive_root, exist_ok=True)

            archive_name = f"{client.get_folder_name()}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
            archive_path = os.path.join(archive_root, archive_name)

            shutil.move(claim_folder, archive_path)
            logger.info(f"Archived claim folder to {archive_path}")
        else:
            # Permanent delete
            shutil.rmtree(claim_folder)
            logger.info(f"Deleted claim folder: {claim_folder}")

        # Clear client folder path
        client.server_folder_path = ''
        client.save(update_fields=['server_folder_path'])

        return True

    except Exception as e:
        logger.error(f"Failed to delete/archive claim folder: {str(e)}")
        return False


def ensure_folder_exists(folder_path):
    """
    Ensure a folder exists, creating it if necessary.

    Args:
        folder_path: Path to folder

    Returns:
        bool: True if folder exists or was created
    """
    try:
        os.makedirs(folder_path, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create folder {folder_path}: {str(e)}")
        return False


def copy_templates_to_claim_folder(client, templates_source_dir=None):
    """
    Copy Excel templates from the templates/excel/active folder to the claim's Templates folder.

    Args:
        client: Client model instance
        templates_source_dir: Optional source directory (defaults to settings.BASE_DIR/docsAppR/templates/excel/active)

    Returns:
        list: List of copied template filenames
    """
    try:
        # Get destination Templates folder using the consistent helper function
        templates_folder = get_templates_folder(client)
        claim_folder = client.get_server_folder_path()

        # Derive safe_folder_name from the claim folder path (consistent with create_claim_folder_structure)
        claim_folder_basename = os.path.basename(claim_folder)
        if not claim_folder_basename or claim_folder_basename == 'claims':
            client_folder_name = f"{client.pOwner}@{client.pAddress}" if client.pOwner and client.pAddress else f"Client_{client.id}"
            safe_folder_name = re.sub(r'[<>:"/\\|?*]', '_', client_folder_name)
        else:
            safe_folder_name = claim_folder_basename
        os.makedirs(templates_folder, exist_ok=True)

        # Get source templates directory
        if not templates_source_dir:
            templates_source_dir = os.path.join(
                settings.BASE_DIR,
                'docsAppR',
                'templates',
                'excel',
                'active'
            )

        if not os.path.exists(templates_source_dir):
            logger.warning(f"Templates source directory not found: {templates_source_dir}")
            return []

        copied_files = []

        import glob

        # ── Copy Excel templates (xlsx/xlsm) — all go into the same Templates folder ──
        excel_files = []
        excel_files.extend(glob.glob(os.path.join(templates_source_dir, '*.xlsx')))
        excel_files.extend(glob.glob(os.path.join(templates_source_dir, '*.xlsm')))
        excel_files = [f for f in excel_files if not os.path.basename(f).startswith('~$')]

        for template_path in excel_files:
            try:
                template_filename = os.path.basename(template_path)
                base_name = os.path.splitext(template_filename)[0]
                ext = os.path.splitext(template_filename)[1]
                new_filename = f"{base_name}-{safe_folder_name}{ext}"

                dest_path = os.path.join(templates_folder, new_filename)

                shutil.copy2(template_path, dest_path)
                copied_files.append(new_filename)
                logger.info(f"Copied template: {new_filename}")

            except Exception as e:
                logger.error(f"Failed to copy template {template_filename}: {str(e)}")
                continue

        # ── Copy W9 PDF as-is (no client name suffix) ──
        w9_source = os.path.join(
            settings.BASE_DIR, 'docsAppR', 'templates', 'excel', '3-W9-EIN-APC.pdf'
        )
        if os.path.exists(w9_source):
            try:
                shutil.copy2(w9_source, os.path.join(templates_folder, '3-W9-EIN-APC.pdf'))
                copied_files.append('3-W9-EIN-APC.pdf')
                logger.info("Copied 3-W9-EIN-APC.pdf to templates folder")
            except Exception as e:
                logger.error(f"Failed to copy W9 PDF: {e}")

        logger.info(f"Copied {len(copied_files)} files to {templates_folder}")
        return copied_files

    except Exception as e:
        logger.error(f"Failed to copy templates: {str(e)}")
        return []


def get_templates_folder(client):
    """
    Get the path to the Templates folder for a client.

    Args:
        client: Client model instance

    Returns:
        str: Path to Templates folder
    """
    claim_folder = client.get_server_folder_path()

    # Derive folder name from the claim folder path (consistent with create_claim_folder_structure)
    # The claim folder is like: /app/media/claims/Smith, BOB TEST@831 Gertrude Place NW,
    # We need the last part of the path to build the Templates subfolder name
    claim_folder_basename = os.path.basename(claim_folder)

    # If the basename doesn't match expected pattern, fall back to computing it
    if not claim_folder_basename or claim_folder_basename == 'claims':
        client_folder_name = f"{client.pOwner}@{client.pAddress}" if client.pOwner and client.pAddress else f"Client_{client.id}"
        safe_folder_name = re.sub(r'[<>:"/\\|?*]', '_', client_folder_name)
    else:
        safe_folder_name = claim_folder_basename

    return os.path.join(claim_folder, f"Templates {safe_folder_name}")


def populate_excel_templates(client, templates_folder=None):
    """
    Populate ALL Excel templates with raw client data via pure XML/ZIP surgery.
    Every template with a jobinfo(2) sheet gets raw values in Column C.
    External links are stripped to prevent "repair file" prompts.

    Args:
        client: Client model instance
        templates_folder: Optional templates folder path

    Returns:
        dict: Results with populated files list and any errors
    """
    from .tasks import populate_excel_templates as tasks_populate
    return tasks_populate(client, templates_folder)


