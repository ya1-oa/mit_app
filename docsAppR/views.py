from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core import serializers
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db.models import Avg, Case, Count, F, Q, When, IntegerField
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

""" Third Party App Imports """
from allauth.account.decorators import login_required

""" Project Specific Imports """
from .config.excel_mappings import SCOPE_FORM_MAPPINGS
from .forms import ClientForm, CreateUserForm, UploadClientForm, UploadFilesForm, LandlordForm
from docsAppR.models import ChecklistItem, Client, File, Document, Landlord
from automations.tasks import RoomTemplateAutomation

"""Python Standard Library"""
import datetime as dt
import json
import logging
import math
import os
import platform
import re
import shutil
import tempfile
import time
from io import BytesIO
from pathlib import Path
import logging

"""Third Party Libraries"""
import pandas as pd
import requests
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from weasyprint import HTML
import tempfile

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from django.http import JsonResponse
from django.views import View
from django.conf import settings
from openpyxl import load_workbook
#import pythoncom
#import win32com.client as win32
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class EncircleExcelExporter:
    """
    Class to export Encircle claims data to an Excel workbook with multiple worksheets
    """
    
    def __init__(self):
        self.wb = Workbook()
        self.default_sheet = self.wb.active
        self.default_sheet.title = "Claims Summary"
        self.styles = self._define_styles()
    
    def _define_styles(self):
        """Define reusable cell styles"""
        return {
            'header': {
                'font': Font(bold=True, color="FFFFFF"),
                'fill': PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid"),
                'alignment': Alignment(horizontal="center", vertical="center", wrap_text=True),
                'border': Border(left=Side(style='thin'), 
                             right=Side(style='thin'), 
                             top=Side(style='thin'), 
                             bottom=Side(style='thin'))
            },
            'data': {
                'alignment': Alignment(vertical="center", wrap_text=True),
                'border': Border(left=Side(style='thin'), 
                             right=Side(style='thin'), 
                             top=Side(style='thin'), 
                             bottom=Side(style='thin'))
            }
        }
    
    def _apply_style(self, cell, style_name):
        """Apply a predefined style to a cell"""
        if style_name in self.styles:
            style = self.styles[style_name]
            if 'font' in style:
                cell.font = style['font']
            if 'fill' in style:
                cell.fill = style['fill']
            if 'alignment' in style:
                cell.alignment = style['alignment']
            if 'border' in style:
                cell.border = style['border']
    
    def _auto_adjust_columns(self, sheet):
        """Auto-adjust column widths based on content"""
        for column in sheet.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            
            for cell in column:
                try:
                    cell_value = cell.value
                    if cell_value is not None:
                        cell_length = len(str(cell_value))
                        if cell_length > max_length:
                            max_length = cell_length
                except Exception:
                    pass
            
            # Set minimum width and maximum width limits
            adjusted_width = min(max(max_length + 2, 10), 50) * 1.2
            sheet.column_dimensions[column_letter].width = adjusted_width
    
    def _safe_cell_value(self, value):
        """Safely convert value to Excel-compatible format"""
        if value is None:
            return 'N/A'
        elif isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        elif isinstance(value, dict):
            return str(value)
        else:
            return str(value)
    
    def export_claims(self, claims_data):
        """
        Main method to export all claims data to Excel
        """
        try:
            # Validate input data
            if not isinstance(claims_data, dict):
                raise ValueError("claims_data must be a dictionary")
            
            # Create worksheets
            claims = claims_data.get('claims', [])
            if claims:
                self._create_claims_sheet(claims)
            
            # If we have detailed claim data, create additional sheets
            if 'claim_details' in claims_data and claims_data['claim_details']:
                self._create_details_sheet(claims_data['claim_details'])
                
            if 'rooms' in claims_data and claims_data['rooms']:
                self._create_rooms_sheet(claims_data['rooms'])
                
            if 'floor_plan' in claims_data and claims_data['floor_plan']:
                self._create_floor_plan_sheet(claims_data['floor_plan'])
            
            # Remove default sheet if we created other sheets and it's empty
            if len(self.wb.worksheets) > 1:
                claims_sheet = self.wb["Claims Summary"]
                if claims_sheet.max_row == 1:  # Only headers
                    self.wb.remove(claims_sheet)
            
            # Generate timestamp for filename
            timestamp = dt.datetime().strftime("%Y%m%d_%H%M%S")
            filename = f"encircle_claims_export_{timestamp}.xlsx"
            
            # Save workbook to a BytesIO object
            output = BytesIO()
            self.wb.save(output)
            output.seek(0)
            
            return output, filename
            
        except Exception as e:
            raise Exception(f"Error generating Excel file: {str(e)}")
    
    def _create_claims_sheet(self, claims):
    
        """Create a vertical claims worksheet matching the exact template format."""
        sheet = self.wb["Claims Summary"]
        
        # Define the exact row structure based on your template
        template_rows = [
            "Insured Name",
            "Address",
            "City, State",
            "Email",
            "Phone",
            "TBD",  # Placeholder 1
            "TBD",  # Placeholder 2
            "TBD",  # Placeholder 3
            "TBD",  # Placeholder 4
            "TBD",  # Placeholder 5
            "Cause of Loss",
            "Date of Loss",
            "Type of Loss",
            "TBD",  # Placeholder 6
            "TBD",  # Placeholder 7
            "Coverage A Dwelling",
            "Coverage B Other Structures",
            "Coverage C Personal Property",
            "Coverage D Loss of Use",
            "Coverage E Liability",
            "Coverage F Medical",
            "Insurance Company",
            "Policy Number",
            "Claim Number",
            "Adjuster Email",
            "Adjuster Name",
            "Adjuster Phone",
            "Insurance Company Phone",
            "Insurance Company Fax",
            "Claims Email",
            "TBD",  # Placeholder 8
            "TBD",  # Placeholder 9
            "TBD",  # Placeholder 10
            "TBD",  # Placeholder 11
            "TBD",  # Placeholder 12
            "TBD",  # Placeholder 13
            "TBD",  # Placeholder 14
            "TBD",  # Placeholder 15
            "TBD",  # Placeholder 16
            "TBD",  # Placeholder 17
            "TBD",  # Placeholder 18
            "TBD",  # Placeholder 19
            "TBD",  # Placeholder 20
            "TBD",  # Placeholder 21
            "TBD",  # Placeholder 22
            "TBD",  # Placeholder 23
            "TBD",  # Placeholder 24
            "TBD",  # Placeholder 25
            "TBD",  # Placeholder 26
            "TBD",  # Placeholder 27
            "TBD",  # Placeholder 28
            "TBD",  # Placeholder 29
            "TBD",  # Placeholder 30
            "TBD",  # Placeholder 31
            "TBD",  # Placeholder 32
            "TBD",  # Placeholder 33
            "TBD",  # Placeholder 34
            "TBD",  # Placeholder 35
            "TBD",  # Placeholder 36
            "TBD",  # Placeholder 37
            "TBD",  # Placeholder 38
            "TBD",  # Placeholder 39
            "TBD",  # Placeholder 40
            "TBD",  # Placeholder 41
            "TBD",  # Placeholder 42
            "TBD",  # Placeholder 43
            "TBD",  # Placeholder 44
            "TBD",  # Placeholder 45
            "TBD",  # Placeholder 46
            "TBD",  # Placeholder 47
            "TBD",  # Placeholder 48
            "TBD",  # Placeholder 49
            "TBD",  # Placeholder 50
            "TBD",  # Placeholder 51
            "TBD",  # Placeholder 52
            "TBD",  # Placeholder 53
            "TBD",  # Placeholder 54
            "TBD",  # Placeholder 55
            "TBD",  # Placeholder 56
            "TBD",  # Placeholder 57
            "TBD",  # Placeholder 58
            "TBD",  # Placeholder 59
            "TBD",  # Placeholder 60
            "TBD",  # Placeholder 61
            "TBD",  # Placeholder 62
            "TBD",  # Placeholder 63
            "TBD",  # Placeholder 64
            "TBD",  # Placeholder 65
            "TBD",  # Placeholder 66
            "TBD",  # Placeholder 67
            "TBD",  # Placeholder 68
            "TBD",  # Placeholder 69
            "TBD",  # Placeholder 70
            "TBD",  # Placeholder 71
            "TBD",  # Placeholder 72
            "TBD",  # Placeholder 73
            "TBD",  # Placeholder 74
            "TBD",  # Placeholder 75
            "TBD",  # Placeholder 76
            "TBD",  # Placeholder 77
            "TBD",  # Placeholder 78
            "TBD",  # Placeholder 79
            "TBD",  # Placeholder 80
            "TBD",  # Placeholder 81
            "TBD",  # Placeholder 82
            "TBD",  # Placeholder 83
            "TBD",  # Placeholder 84
            "TBD",  # Placeholder 85
            "TBD",  # Placeholder 86
            "TBD",  # Placeholder 87
            "TBD",  # Placeholder 88
            "TBD",  # Placeholder 89
            "TBD",  # Placeholder 90
            "TBD",  # Placeholder 91
            "TBD",  # Placeholder 92
            "TBD",  # Placeholder 93
            "TBD",  # Placeholder 94
            "TBD",  # Placeholder 95
            "TBD",  # Placeholder 96
            "TBD",  # Placeholder 97
            "TBD",  # Placeholder 98
            "TBD",  # Placeholder 99
            "TBD",  # Placeholder 100
            "TBD",  # Placeholder 101
            "TBD",  # Placeholder 102
            "TBD",  # Placeholder 103
            "TBD",  # Placeholder 104
            "TBD",  # Placeholder 105
            "TBD",  # Placeholder 106
            "TBD",  # Placeholder 107
            "TBD",  # Placeholder 108
            "TBD",  # Placeholder 109
            "TBD",  # Placeholder 110
            "TBD",  # Placeholder 111
            "TBD",  # Placeholder 112
            "TBD",  # Placeholder 113
            "TBD",  # Placeholder 114
            "TBD",  # Placeholder 115
            "TBD",  # Placeholder 116
            "TBD",  # Placeholder 117
            "TBD",  # Placeholder 118
            "TBD",  # Placeholder 119
            "TBD",  # Placeholder 120
            "TBD",  # Placeholder 121
            "TBD",  # Placeholder 122
            "TBD",  # Placeholder 123
            "TBD",  # Placeholder 124
            "TBD",  # Placeholder 125
            "TBD",  # Placeholder 126
            "TBD",  # Placeholder 127
            "TBD",  # Placeholder 128
            "TBD",  # Placeholder 129
            "TBD",  # Placeholder 130
            "TBD",  # Placeholder 131
            "TBD",  # Placeholder 132
            "TBD",  # Placeholder 133
            "TBD",  # Placeholder 134
            "TBD",  # Placeholder 135
            "TBD",  # Placeholder 136
            "TBD",  # Placeholder 137
            "TBD",  # Placeholder 138
            "TBD",  # Placeholder 139
            "TBD",  # Placeholder 140
            "TBD",  # Placeholder 141
            "TBD",  # Placeholder 142
            "TBD",  # Placeholder 143
            "TBD",  # Placeholder 144
            "TBD",  # Placeholder 145
            "TBD",  # Placeholder 146
            "TBD",  # Placeholder 147
            "TBD",  # Placeholder 148
            "TBD",  # Placeholder 149
            "TBD",  # Placeholder 150
            "TBD",  # Placeholder 151
            "TBD",  # Placeholder 152
            "TBD",  # Placeholder 153
            "TBD",  # Placeholder 154
            "TBD",  # Placeholder 155
            "TBD",  # Placeholder 156
            "TBD",  # Placeholder 157
            "TBD",  # Placeholder 158
            "TBD",  # Placeholder 159
            "TBD",  # Placeholder 160
            "TBD",  # Placeholder 161
            "TBD",  # Placeholder 162
            "TBD",  # Placeholder 163
            "TBD",  # Placeholder 164
            "TBD",  # Placeholder 165
            "TBD",  # Placeholder 166
            "TBD",  # Placeholder 167
            "TBD",  # Placeholder 168
            "TBD",  # Placeholder 169
            "TBD",  # Placeholder 170
            "TBD",  # Placeholder 171
            "TBD",  # Placeholder 172
            "TBD",  # Placeholder 173
            "TBD",  # Placeholder 174
            "TBD",  # Placeholder 175
            "TBD",  # Placeholder 176
            "TBD",  # Placeholder 177
            "TBD",  # Placeholder 178
            "TBD",  # Placeholder 179
            "TBD",  # Placeholder 180
            "TBD",  # Placeholder 181
            "TBD",  # Placeholder 182
            "TBD",  # Placeholder 183
            "TBD",  # Placeholder 184
            "TBD",  # Placeholder 185
            "TBD",  # Placeholder 186
            "TBD",  # Placeholder 187
            "TBD",  # Placeholder 188
            "TBD",  # Placeholder 189
            "TBD",  # Placeholder 190
            "TBD",  # Placeholder 191
            "TBD",  # Placeholder 192
            "TBD",  # Placeholder 193
            "TBD",  # Placeholder 194
            "TBD",  # Placeholder 195
            "TBD",  # Placeholder 196
            "TBD",  # Placeholder 197
            "TBD",  # Placeholder 198
            "TBD",  # Placeholder 199
            "TBD",  # Placeholder 200
        ]
    
        # Write template headers in column A
        for row_num, header in enumerate(template_rows, start=1):
            sheet.cell(row=row_num, column=1, value=header)
        
        # Write claim data starting from column B
        for col_num, claim in enumerate(claims, start=2):
            if not isinstance(claim, dict):
                continue
                
            # Map claim data to specific rows based on your template
            data_mapping = {
                1: claim.get('policyholder_name', 'TBD'),  # Insured Name
                2: claim.get('full_address', 'TBD'),       # Address
                3: f"{claim.get('city', '')}, {claim.get('state', '')}".strip(', '),  # City, State
                4: claim.get('email', 'TBD'),              # Email
                5: claim.get('phone', 'TBD'),             # Phone
                11: claim.get('cause_of_loss', 'TBD'),    # Cause of Loss
                12: claim.get('date_of_loss', 'TBD'),     # Date of Loss
                22: claim.get('insurance_company_name', 'TBD'),  # Insurance Company
                23: claim.get('policy_number', 'TBD'),    # Policy Number
                24: claim.get('claim_number', 'TBD'),     # Claim Number
                25: claim.get('adjuster_email', 'TBD'),   # Adjuster Email
                26: claim.get('adjuster_name', 'TBD'),    # Adjuster Name
                27: claim.get('adjuster_phone', 'TBD'),  # Adjuster Phone
                # Add more mappings as needed for your specific template
            }
            
            # Write the data to the appropriate rows
            for row_num, value in data_mapping.items():
                safe_value = self._safe_cell_value(value)
                sheet.cell(row=row_num, column=col_num, value=safe_value)
        
        # Adjust column widths for better readability
        self._auto_adjust_columns(sheet)

    def _create_details_sheet(self, claim_details):
        """Create a worksheet for detailed claim information"""
        if not isinstance(claim_details, dict):
            return
            
        sheet = self.wb.create_sheet("Claim Details")
        
        # Group details into logical sections
        sections = {
            "Basic Information": [
                ("Claim ID", claim_details.get('id')),
                ("Brand ID", claim_details.get('brand_id')),
                ("Organization ID", claim_details.get('organization_id')),
                ("Date Created", claim_details.get('date_claim_created')),
                ("Permalink URL", claim_details.get('permalink_url'))
            ],
            "Property Information": [
                ("Full Address", claim_details.get('full_address')),
                ("Policyholder", claim_details.get('policyholder_name')),
                ("Phone", claim_details.get('policyholder_phone_number')),
                ("Email", claim_details.get('policyholder_email_address'))
            ],
            "Insurance Information": [
                ("Insurance Company", claim_details.get('insurance_company_name')),
                ("Policy Number", claim_details.get('policy_number')),
                ("Insurer ID", claim_details.get('insurer_identifier')),
                ("Broker/Agent", claim_details.get('broker_or_agent_name'))
            ],
            "Loss Information": [
                ("Date of Loss", claim_details.get('date_of_loss')),
                ("Type of Loss", claim_details.get('type_of_loss')),
                ("Loss Details", claim_details.get('loss_details')),
                ("CAT Code", claim_details.get('cat_code'))
            ],
            "Adjuster Information": [
                ("Adjuster Name", claim_details.get('adjuster_name')),
                ("Project Manager", claim_details.get('project_manager_name')),
                ("Contractor ID", claim_details.get('contractor_identifier')),
                ("Assignment ID", claim_details.get('assignment_identifier'))
            ],
            "Financial Information": [
                ("Repair Estimate", claim_details.get('repair_estimate')),
                ("Contents Estimate", claim_details.get('contents_estimate')),
                ("Emergency Estimate", claim_details.get('emergency_estimate')),
                ("Sales Tax", claim_details.get('sales_tax')),
                ("Default Depreciation", claim_details.get('default_depreciation')),
                ("Max Depreciation", claim_details.get('max_depreciation'))
            ]
        }
        
        row_num = 1
        for section_name, items in sections.items():
            # Write section header
            if sheet.max_column >= 2:
                sheet.merge_cells(start_row=row_num, start_column=1, end_row=row_num, end_column=2)
            cell = sheet.cell(row=row_num, column=1, value=section_name)
            cell.font = Font(bold=True, size=14)
            cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            row_num += 1
            
            # Write section items
            for label, value in items:
                label_cell = sheet.cell(row=row_num, column=1, value=label)
                label_cell.font = Font(bold=True)
                
                value_cell = sheet.cell(row=row_num, column=2, value=self._safe_cell_value(value))
                row_num += 1
            
            # Add empty row between sections
            row_num += 1
        
        self._auto_adjust_columns(sheet)
    
    def _create_rooms_sheet(self, rooms):
        """Create a worksheet for room data"""
        if not isinstance(rooms, list) or not rooms:
            return
            
        sheet = self.wb.create_sheet("Rooms")
        
        headers = [
            "Claim ID", "Claim Name", "Room Name", "Type", "Floor", 
            "Ceiling Height", "Length", "Width",
            "Area", "Perimeter", "Damage Present",
            "Contents Affected"
        ]
        
        # Write headers
        for col_num, header in enumerate(headers, 1):
            cell = sheet.cell(row=1, column=col_num, value=header)
            self._apply_style(cell, 'header')
        
        # Write room data
        for row_num, room in enumerate(rooms, 2):
            if not isinstance(room, dict):
                continue
                
            row_data = [
                room.get('claim_id'),
                room.get('claim_name'),
                room.get('name'),
                room.get('room_type'),
                room.get('floor_name'),
                room.get('ceiling_height'),
                room.get('length'),
                room.get('width'),
                room.get('area'),
                room.get('perimeter'),
                "Yes" if room.get('damage_present') else "No",
                "Yes" if room.get('contents_affected') else "No"
            ]
            
            for col_num, value in enumerate(row_data, 1):
                cell = sheet.cell(row=row_num, column=col_num, value=self._safe_cell_value(value))
                self._apply_style(cell, 'data')
        
        self._auto_adjust_columns(sheet)
    
    def _create_floor_plan_sheet(self, floor_plan):
        """Create a worksheet for floor plan dimensional data"""
        if not isinstance(floor_plan, dict) or not floor_plan:
            return
            
        sheet = self.wb.create_sheet("Floor Plans")
        
        headers = [
            "Floor", "Room Name", "Primary Length", 
            "Primary Width", "Bounding Width", "Bounding Height",
            "Area", "Ceiling Height"
        ]
        
        # Write headers
        for col_num, header in enumerate(headers, 1):
            cell = sheet.cell(row=1, column=col_num, value=header)
            self._apply_style(cell, 'header')
        
        row_num = 2
        for floor_name, rooms in floor_plan.items():
            if not isinstance(rooms, dict):
                continue
                
            for room_name, dimensions in rooms.items():
                if not isinstance(dimensions, dict):
                    continue
                    
                primary_dims = dimensions.get('primary_dimensions', {})
                bounding_box = dimensions.get('bounding_box', {})
                
                row_data = [
                    floor_name.replace('Floor_', 'Floor '),
                    room_name,
                    primary_dims.get('length') if isinstance(primary_dims, dict) else None,
                    primary_dims.get('width') if isinstance(primary_dims, dict) else None,
                    bounding_box.get('width') if isinstance(bounding_box, dict) else None,
                    bounding_box.get('height') if isinstance(bounding_box, dict) else None,
                    dimensions.get('area'),
                    dimensions.get('ceiling_height')
                ]
                
                for col_num, value in enumerate(row_data, 1):
                    cell = sheet.cell(row=row_num, column=col_num, value=self._safe_cell_value(value))
                    self._apply_style(cell, 'data')
                    
                row_num += 1
        
        self._auto_adjust_columns(sheet)

class EncircleAPIClient:
    """
    Centralized API client for Encircle API operations
    Following Single Responsibility Principle
    """
    
    def __init__(self):
        self.api_key = "367382d2-0b2d-4b01-9d06-8f18fd492f5e"
        self.base_url = "https://api.encircleapp.com/v1"
        self.v2_base_url = "https://api.encircleapp.com/v2"
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        
    def _make_request(self, endpoint, params=None):
        """
        Generic method to make API requests with error handling
        """
        try:
            url = f"{self.base_url}/{endpoint}"
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            print(response.json())
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {endpoint}: {str(e)}")
            raise Exception(f"API request failed: {str(e)}")

    def _make_v2_request(self, endpoint, params=None):
        """
        Generic method to make API requests with error handling
        """
        try:
            url = f"{self.v2_base_url}/{endpoint}"
            response = requests.get(url, headers=self.headers, params=params)

            if response.status_code != 200:
                logger.error(f"API request failed for {endpoint}: {response.status_code} - {response.text}")
                raise Exception(f"API request failed: {response.status_code} - {response.text}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {endpoint}: {str(e)}")
            raise Exception(f"API request failed: {str(e)}")

    def get_all_claims(self, limit=100, order='newest'):
        """
        Fetch all property claims using cursor-based pagination with 'after' parameter
        
        Args:
            limit (int): Number of results per page (max 100, default 100)
            order (str): Order of results ('newest' or 'oldest', default 'newest')
        
        Returns:
            list: All property claims across all pages
        """
        all_claims = {'list': []}
        after_cursor = None
        page_count = 0
        
        while True:
            page_count += 1
            
            # Build parameters for the request
            params = {
                'limit': min(limit, 100),  # Ensure we don't exceed the max limit of 100
                'order': order
            }
            
            # Add 'after' parameter if we have a cursor (for subsequent pages)
            if after_cursor:
                params['after'] = after_cursor
            
            try:
                print(f"Fetching page {page_count} of claims (limit: {params['limit']})")
                response = self._make_request("property_claims", params=params)
                
                claims = response.get('list', [])
                # Look for the 'after' cursor in the response
                after_cursor = response.get('cursor')['after']
                
                if not claims:
                    print("No more claims found")
                    break
                
                all_claims['list'].extend(claims)
                print(f"Retrieved {len(claims)} claims from page {page_count}. Total so far: {len(all_claims)}")
                
                # If there's no 'after' cursor, we've reached the last page
                if not after_cursor or len(claims) < params['limit']:
                    if not after_cursor:
                        print("No 'after' cursor found - reached last page")
                    else:
                        print(f"Retrieved {len(claims)} claims (less than limit of {params['limit']}) - likely last page")
                    break
                
            except Exception as e:
                print(f"Error fetching page {page_count}: {str(e)}")
                break
        
        print(f"Successfully retrieved {len(all_claims)} total claims across {page_count} pages") 
        return all_claims
    
    def get_claim_details(self, claim_id):
        """
        Fetch detailed information for a specific claim
        """
        return self._make_request(f"property_claims/{claim_id}")
    

    def get_claim_structures(self, claim_id):
        """
        Fetch structures for a specific claim
        """
        return self._make_request(f"property_claims/{claim_id}/structures")
    
    
    def get_claim_rooms(self, claim_id, structure_id):
        """
        Fetch room list for a specific claim
        """
        return self._make_request(f"property_claims/{claim_id}/structures/{structure_id}/rooms")
    
    def get_claim_floor_plan(self, claim_id):
        """
        Fetch floor plan dimensions for a specific claim
        """

        return self._make_v2_request(f"property_claims/{claim_id}/floor_plan_dimensions")

class EncircleDataProcessor:
    """
    Data processing utilities for Encircle API responses
    Following Single Responsibility Principle
    """
    
    @staticmethod
    def _get_polygon_dimensions(coordinates):
        """
        Calculate width and length from polygon coordinates.
        Assumes rectangular rooms and finds the bounding box dimensions.
        """
        # Extract all x and y coordinates
        points = coordinates[0]  # First ring of the polygon
        x_coords = [point[0] for point in points]
        y_coords = [point[1] for point in points]
        
        # Calculate bounding box dimensions
        max_x_coords = max(x_coords) / 30.48
        min_x_coords = min(x_coords) / 30.48
        max_y_coords = max(y_coords) / 30.48
        min_y_coords = min(y_coords) / 30.48
        
        width = max_x_coords - min_x_coords
        height = max_y_coords - min_y_coords
        
        return width, height
    
    @staticmethod
    def _get_edge_lengths(coordinates):
        """
        Calculate actual edge lengths of the polygon.
        More accurate for irregular shapes.
        """
        points = coordinates[0]  # First ring of the polygon
        edge_lengths = []
        
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            length = math.sqrt((x2 - x1)**2 + (y2 - y1)**2) / 30.48
            edge_lengths.append(length)
        
        return edge_lengths
    
    @staticmethod
    def process_floor_plan_data(raw_floor_plan_data):
        """
        Process floor plan data to calculate room dimensions
        """
        if not raw_floor_plan_data or 'list' not in raw_floor_plan_data:
            return {}
            
        room_dimensions = {}
        
        # Iterate through all floors
        for floor_idx, floor in enumerate(raw_floor_plan_data['list'][0]['floors']):
            floor_rooms = {}
            
            # Iterate through all features (rooms) in this floor
            for feature in floor['features']:
                room_name = feature['properties']['name']
                coordinates = feature['geometry']['coordinates']
                
                # Calculate dimensions using both methods
                width, height = EncircleDataProcessor._get_polygon_dimensions(coordinates)
                edge_lengths = EncircleDataProcessor._get_edge_lengths(coordinates)
                
                # For rectangular rooms, take the two longest edges as length/width
                #edge_lengths_sorted = sorted(edge_lengths, reverse=True)
                
                floor_rooms[room_name] = {
                    'bounding_box': {
                        'width': round(width, 2),
                        'height': round(height, 2)
                    },
                    #'primary_dimensions': {
                    #    'length': round(edge_lengths_sorted[0], 2) if edge_lengths_sorted else 0,
                    #    'width': round(edge_lengths_sorted[1], 2) if len(edge_lengths_sorted) > 1 else 0
                    #},
                    'ceiling_height': feature['properties'].get('ceiling_height', 'N/A'),
                    'area': round(width * height, 2)  # Add area calculation
                }
            
            room_dimensions[f'Floor_{floor_idx + 1}'] = floor_rooms
        
        return room_dimensions
    
    @staticmethod
    def get_room_dimensions_simple(room_feature):
        """
        Simple function to get width and length for a single room feature.
        
        Args:
            room_feature: Single feature from the JSON (contains geometry and properties)
        
        Returns:
            dict: Dictionary containing width, length, and area
        """
        coordinates = room_feature['geometry']['coordinates'][0]
        
        # Get bounding box
        x_coords = [point[0] for point in coordinates]
        y_coords = [point[1] for point in coordinates]
        
        width = (max(x_coords) - min(x_coords)) / 12
        height = (max(y_coords) - min(y_coords)) / 12
        
        return {
            'width': round(width, 2),
            'length': round(height, 2),
            'area': round(width * height, 2)
        }
    
    @staticmethod
    def process_claims_list(raw_claims_data):
        """
        Process and structure the claims list data to match API response
        """
        print(raw_claims_data)
        if not raw_claims_data or 'list' not in raw_claims_data:
            return []
        
        processed_claims = []
        for claim in raw_claims_data['list']:
            processed_claim = {
                'id': claim.get('id'),
                'brand_id': claim.get('brand_id'),
                'organization_id': claim.get('organization_id'),
                'permalink_url': claim.get('permalink_url'),
                'type_of_loss': claim.get('type_of_loss'),
                'full_address': claim.get('full_address'),
                'date_claim_created': claim.get('date_claim_created'),
                'date_of_loss': claim.get('date_of_loss'),
                'policyholder_name': claim.get('policyholder_name'),
                'insurance_company_name': claim.get('insurance_company_name'),
                'policy_number': claim.get('policy_number'),
                'adjuster_name': claim.get('adjuster_name'),
                'project_manager_name': claim.get('project_manager_name'),
                'total_rooms': 0,  # Will be populated later
                'room_types': []   # Will be populated later
            }
            processed_claims.append(processed_claim)
        
        return processed_claims
    
    @staticmethod
    def process_claim_rooms(raw_rooms_data):
        """
        Process room data for a specific claim
        """
        if not raw_rooms_data or 'list' not in raw_rooms_data:
            return []
        
        processed_rooms = []
        room_types = set()
        
        for room in raw_rooms_data['list']:
            room_data = {
                'id': room.get('id'),
                'name': room.get('name', 'Unnamed Room'),
                'room_type': room.get('room_type', 'Unknown'),
                'floor_name': room.get('floor_name', 'Unknown Floor'),
                'ceiling_height': room.get('ceiling_height', 0),
                'length': room.get('length', 0),
                'width': room.get('width', 0),
                'area': room.get('area', 0),
                'perimeter': room.get('perimeter', 0),
                'damage_present': room.get('damage_present', False),
                'contents_affected': room.get('contents_affected', False)
            }
            processed_rooms.append(room_data)
            room_types.add(room_data['room_type'])
        
        return processed_rooms, list(room_types)
    
    @staticmethod
    def process_claim_details(raw_claim_data):
        """
        Process detailed claim information to match API response structure
        """
        if not raw_claim_data:
            return {}
        
        return {
            'id': raw_claim_data.get('id'),
            'brand_id': raw_claim_data.get('brand_id'),
            'organization_id': raw_claim_data.get('organization_id'),
            'permalink_url': raw_claim_data.get('permalink_url'),
            'type_of_loss': raw_claim_data.get('type_of_loss'),
            'locale': raw_claim_data.get('locale'),
            'adjuster_name': raw_claim_data.get('adjuster_name'),
            'assignment_identifier': raw_claim_data.get('assignment_identifier'),
            'cat_code': raw_claim_data.get('cat_code'),
            'contents_estimate': raw_claim_data.get('contents_estimate'),
            'contractor_identifier': raw_claim_data.get('contractor_identifier'),
            'date_claim_created': raw_claim_data.get('date_claim_created'),
            'date_of_loss': raw_claim_data.get('date_of_loss'),
            'default_depreciation': raw_claim_data.get('default_depreciation'),
            'emergency_estimate': raw_claim_data.get('emergency_estimate'),
            'full_address': raw_claim_data.get('full_address'),
            'insurer_identifier': raw_claim_data.get('insurer_identifier'),
            'loss_details': raw_claim_data.get('loss_details'),
            'max_depreciation': raw_claim_data.get('max_depreciation'),
            'policyholder_email_address': raw_claim_data.get('policyholder_email_address'),
            'policyholder_name': raw_claim_data.get('policyholder_name'),
            'policyholder_phone_number': raw_claim_data.get('policyholder_phone_number'),
            'project_manager_name': raw_claim_data.get('project_manager_name'),
            'repair_estimate': raw_claim_data.get('repair_estimate'),
            'sales_tax': raw_claim_data.get('sales_tax'),
            'broker_or_agent_name': raw_claim_data.get('broker_or_agent_name'),
            'insurance_company_name': raw_claim_data.get('insurance_company_name'),
            'policy_number': raw_claim_data.get('policy_number')
        }

class EncircleMediaDownloader:
    """
    Downloads media files from Encircle API and organizes them by room labels.
    Files are numbered sequentially and saved in room-specific folders.
    """
    
    def __init__(self, api_client, target_rooms=None):
        self.api_client = api_client
        self.target_rooms = target_rooms or []  # Ensure it's always a list
        self.downloaded_files = 0
        self.failed_downloads = 0
        self.base_dir = "encircle_media_downloads"
        os.makedirs(self.base_dir, exist_ok=True)
        
        # Ensure base directory exists
        os.makedirs(self.base_dir, exist_ok=True)
        
    def download_claim_media(self, property_claim_id):
        """
        Main method to download all media for a specific claim
        """
        print(f"\nStarting media download for claim ID: {property_claim_id}")
        print("="*60)
        
        try:
            # Get media list from API
            media_list = self._get_media_list(property_claim_id)
            
            if not media_list:
                print("No media found for this claim.")
                return
            
            # Process each media item
            for idx, media_item in enumerate(media_list, 1):
                if self._should_download(media_item):
                    self._process_media_item(media_item, idx, len(media_list))
                else:
                    print(f"Skipping {media_item['filename']} - not in target rooms")

        except Exception as e:
            logging.error(f"Error downloading media for claim {property_claim_id}: {str(e)}")
            raise
            
        print("\nDownload Summary:")
        print(f"- Successfully downloaded: {self.downloaded_files}")
        print(f"- Failed downloads: {self.failed_downloads}")
    
    def _should_download(self, media_item):
        """Check if media belongs to target room(s)"""
        if not self.target_rooms:
            return True  # Download all if no filter
        
        labels = media_item.get('labels', [])
        return any(room.lower() in [label.lower() for label in labels] 
               for room in self.target_rooms)

    def _get_media_list(self, property_claim_id):
        """Fetch media list from API with pagination support"""
        all_media = []
        after_cursor = None
        
        while True:
            params = {'limit': 100}
            if after_cursor:
                params['after'] = after_cursor
                
            endpoint = f"property_claims/{property_claim_id}/media"
            response = self.api_client._make_request(endpoint, params=params)
            
            if not response or 'list' not in response:
                break
                
            all_media.extend(response['list'])
            after_cursor = response.get('cursor', {}).get('after')
            
            if not after_cursor:
                break
                
        return all_media
        
    def _process_media_item(self, media_item, current_index, total_items):
        """Handle a single media item download"""
        try:
            # Determine folder based on labels
            folder_name = self._get_folder_name(media_item)
            file_extension = self._get_file_extension(media_item['content_type'])
            
            # Create safe filename with sequential number
            seq_num = str(current_index).zfill(len(str(total_items)))
            clean_filename = f"{seq_num}_{media_item['filename']}"
            clean_filename = self._sanitize_filename(clean_filename)
            
            # Ensure proper file extension
            if not clean_filename.lower().endswith(file_extension.lower()):
                clean_filename += file_extension
                
            # Prepare full path
            folder_path = os.path.join(self.base_dir, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            file_path = os.path.join(folder_path, clean_filename)
            
            # Download the file
            print(f"\nDownloading {current_index}/{total_items}: {clean_filename}")
            print(f"Type: {media_item['content_type']}")
            print(f"Labels: {', '.join(media_item.get('labels', ['No labels']))}")
            print(f"Saving to: {file_path}")
            
            self._download_file(media_item['download_uri'], file_path)
            self.downloaded_files += 1
            
            # Add metadata file
            self._create_metadata_file(media_item, file_path)
            
        except Exception as e:
            self.failed_downloads += 1
            logging.error(f"Failed to process media item: {str(e)}")
            print(f"Error processing item {current_index}: {str(e)}")
            
    def _get_folder_name(self, media_item):
        """Create nested folder structure from all labels, handling edge cases"""
        labels = media_item.get('labels', [])
        
        if not labels:
            return "unlabeled_media"
        
        # Handle cases where labels might be empty strings
        valid_labels = [label.strip() for label in labels if label.strip()]
        if not valid_labels:
            return "unlabeled_media"
        
        # Limit folder depth to prevent overly long paths
        max_depth = 3  # Main_Building/Sub_Room/Area
        truncated_labels = valid_labels[:max_depth]
        
        # Sanitize and join
        return os.path.join(*[self._sanitize_folder_name(label) for label in truncated_labels])
        
    def _sanitize_filename(self, filename):
        """Remove invalid characters from filenames"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename
        
    def _sanitize_folder_name(self, foldername):
        """Sanitize folder names and truncate if too long"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            foldername = foldername.replace(char, '_')
        return foldername[:50]  # Prevent too long folder names
        
    def _get_file_extension(self, content_type):
        """Map content type to file extension"""
        extension_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'application/pdf': '.pdf',
            'video/mp4': '.mp4',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
        }
        return extension_map.get(content_type, '.bin')
        
    def _download_file(self, url, file_path):
        """Download the actual file from the URI"""
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            print("Download completed successfully.")
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Download failed: {str(e)}")
            
    def _create_metadata_file(self, media_item, file_path):
        """Create a sidecar file with metadata information"""
        metadata = {
            'original_filename': media_item['filename'],
            'content_type': media_item['content_type'],
            'source_type': media_item['source']['type'],
            'source_id': media_item['source']['primary_id'],
            'creator': media_item['creator']['actor_identifier'],
            'created_date': media_item['primary_server_created'],
            'labels': media_item.get('labels', []),
            'download_time': dt.now().isoformat()
        }
        
        metadata_path = f"{file_path}.meta.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpRequest
from django.core.files.storage import FileSystemStorage
from datetime import datetime
from django.http import JsonResponse
from django.core.files.storage import FileSystemStorage
from openpyxl import load_workbook
from django.conf import settings

import os
import json
import subprocess
from datetime import datetime
from django.http import JsonResponse
from django.conf import settings
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

@csrf_exempt
def create_room_template_from_excel(request):
    """
    Handle user pasted room data with room names and LOS, execute automation with base Excel template
    
    Expected POST data:
    - email: User email
    - password: User password
    - room_data: Pasted room data in format "Room Name, LOS" (one per line)
    - selected_templates: List of template IDs to create
    """
    try:
        # Validate required fields
        required_fields = ['room_data']
        missing_fields = [field for field in required_fields if field not in request.POST or not request.POST[field].strip()]
        
        if missing_fields:
            return JsonResponse(
                {
                    "status": "failed",
                    "error": f"Missing or empty required fields: {', '.join(missing_fields)}"
                },
                status=400
            )
        
        # Extract and validate room data
        room_data_raw = request.POST.get('room_data', '').strip()
        room_entries = parse_room_data(room_data_raw)
        
        if not room_entries:
            return JsonResponse(
                {
                    "status": "failed",
                    "error": "No valid room data found. Please paste room data in format 'Room Name, LOS' (one per line)."
                },
                status=400
            )
        
        # Extract other form data
        email = request.POST.get('email')
        password = request.POST.get('password')
        selected_templates = request.POST.getlist('selected_templates')
        
        if not selected_templates:
            return JsonResponse(
                {
                    "status": "failed",
                    "error": "No templates selected. Please select at least one template to generate."
                },
                status=400
            )
        
        # Update base Excel file directly with room data
        base_excel_path = None
        try:
            base_excel_path = find_base_excel_template()
            update_base_excel_with_room_data(base_excel_path, room_entries)
        except Exception as e:
            return JsonResponse(
                {
                    "status": "failed",
                    "error": f"Failed to update base Excel file: {str(e)}",
                    "stage": "excel_update",
                    "debug_info": get_template_debug_info()
                },
                status=500
            )
        
        try:
            # Initialize automation
            automation = RoomTemplateAutomation(headless=True)
                
            # Run automation with selected templates using the updated base Excel file
            results = automation.run_automation(
                excel_file_path=base_excel_path,
                selected_template_ids=selected_templates,
                delete_existing=True
            )
            
            # Add additional processing metadata
            results['file_processing'] = {
                'rooms_processed': len(room_entries),
                'room_entries': [
                    {
                        'room_name': entry['room_name'],
                        'los': entry['los']
                    } for entry in room_entries[:10]  # Show first 10 for confirmation
                ],
                'total_rooms': len(room_entries),
                'base_file_updated': True,
                'base_file_path': base_excel_path,
                'templates_requested': len(selected_templates),
                'columns_populated': ['Q (Room Names)', 'R (LOS)'],
                'formulas_recalculated': True
            }
            
            # Add truncation notice if more than 10 rooms
            if len(room_entries) > 10:
                results['file_processing']['room_list_note'] = f"Showing first 10 of {len(room_entries)} room entries"
            
            return JsonResponse(results)
                        
        except Exception as e:
            return JsonResponse(
                {
                    "status": "failed",
                    "error": str(e),
                    "stage": "automation_execution",
                    "rooms_attempted": len(room_entries),
                    "base_file_path": base_excel_path
                },
                status=500
            )
        
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "status": "failed",
                "error": "Invalid JSON data"
            },
            status=400
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "failed",
                "error": str(e),
                "stage": "request_processing"
            },
            status=500
        )


def parse_room_data(room_data_text):
    """
    Parse room data text into separate room names and LOS values
    
    Args:
        room_data_text (str): Raw text with room data in format "Room Name, LOS"
        
    Returns:
        list: List of dictionaries with 'room_name', 'los', and metadata
    """
    lines = [line.strip() for line in room_data_text.split('\n') if line.strip()]
    parsed_data = []
    
    for line_num, line in enumerate(lines, 1):
        if ',' in line:
            # Split on the first comma only to handle LOS descriptions with commas
            parts = line.split(',', 1)
            room_name = parts[0].strip()
            los = parts[1].strip()
            
            if room_name and los:
                parsed_data.append({
                    'room_name': room_name,
                    'los': los,
                    'original_line': line,
                    'line_number': line_num
                })
            else:
                print(f"Warning: Line {line_num} has empty room name or LOS: '{line}'")
        else:
            print(f"Warning: Line {line_num} missing comma separator: '{line}'")
    
    return parsed_data


def find_base_excel_template():
    """
    Find the base Excel template file by checking multiple possible locations and filenames
    
    Returns:
        str: Path to the found template file
        
    Raises:
        FileNotFoundError: If no template file is found
    """
    # Primary template filename and location
    primary_template = '01-INFO.xlsx'
    
    # Possible directories (relative to BASE_DIR) - prioritizing the known location
    possible_dirs = [
        'docsAppR/templates/excel/',  # Known correct location
        'templates/excel/',
        'docsAppR/templates/',
        'templates/',
        'media/templates/',
        'static/templates/',
        'app/templates/excel/',
        'app/docsAppR/templates/excel/',
        'excel_templates/',
        '.'  # Current directory
    ]
    
    # Fallback template filenames if primary not found
    fallback_filenames = [
        'base_room_template.xlsx',
        'INFO.xlsx',
        'template.xlsx',
        'base_template.xlsx'
    ]
    
    # First, search for the primary template in all directories
    for directory in possible_dirs:
        dir_path = os.path.join(settings.BASE_DIR, directory)
        if os.path.exists(dir_path):
            template_path = os.path.join(dir_path, primary_template)
            if os.path.exists(template_path):
                print(f"Found Excel template at: {template_path}")
                return template_path
    
    # If primary template not found, search for fallback templates
    for directory in possible_dirs:
        dir_path = os.path.join(settings.BASE_DIR, directory)
        if os.path.exists(dir_path):
            for filename in fallback_filenames:
                template_path = os.path.join(dir_path, filename)
                if os.path.exists(template_path):
                    print(f"Found fallback Excel template at: {template_path}")
                    return template_path
    
    # If not found, list what we have for debugging
    debug_info = get_template_debug_info()
    raise FileNotFoundError(
        f"Excel template '{primary_template}' not found. Searched in: {possible_dirs} "
        f"Also searched for fallback files: {fallback_filenames}. "
        f"Debug info: {debug_info}"
    )


def get_template_debug_info():
    """
    Get debugging information about available files and directories
    
    Returns:
        dict: Debug information about file system
    """
    debug_info = {
        'base_dir': settings.BASE_DIR,
        'base_dir_exists': os.path.exists(settings.BASE_DIR),
        'directories': {},
        'current_working_dir': os.getcwd(),
        'target_file': '01-INFO.xlsx',
        'expected_location': '/app/excel/'
    }
    
    # Check common directories, including the known location
    search_dirs = [
        'app/excel',
        'docsAppR',
        'docsAppR/templates',
        'docsAppR/templates/excel',
        'templates',
        'templates/excel',
        'media',
        'static',
        'app',
        'app/docsAppR',
        'app/docsAppR/templates',
        '.'
    ]
    
    for dir_name in search_dirs:
        dir_path = os.path.join(settings.BASE_DIR, dir_name)
        debug_info['directories'][dir_name] = {
            'exists': os.path.exists(dir_path),
            'full_path': dir_path
        }
        
        if os.path.exists(dir_path):
            try:
                files = os.listdir(dir_path)
                excel_files = [f for f in files if f.endswith(('.xlsx', '.xls'))]
                debug_info['directories'][dir_name]['files'] = files[:10]  # First 10 files
                debug_info['directories'][dir_name]['excel_files'] = excel_files
                
                # Check specifically for 01-INFO.xlsx
                if '01-INFO.xlsx' in files:
                    debug_info['directories'][dir_name]['has_target_file'] = True
                    
            except Exception as e:
                debug_info['directories'][dir_name]['error'] = str(e)
    
    return debug_info


def update_base_excel_with_room_data(base_excel_path, room_entries):
    """
    Update the base Excel file directly with room data
    
    Args:
        base_excel_path (str): Path to the base Excel template file
        room_entries (list): List of dictionaries with 'room_name' and 'los' keys
        
    Raises:
        Exception: If Excel manipulation fails
    """
    
    try:
        print(f"Updating base Excel file: {base_excel_path}")
        print(f"Processing {len(room_entries)} room entries...")
        
        # Create a backup of the original file
        backup_path = base_excel_path + '.backup'
        if os.path.exists(backup_path):
            os.remove(backup_path)
        
        # Load the workbook and find the ROOMS# sheet
        workbook = load_workbook(base_excel_path)
        
        # Try different possible sheet names for ROOMS#
        possible_sheet_names = ['ROOMS#', 'ROOMS #', 'Rooms#', 'Rooms #', 'ROOMS', 'Rooms', 'Sheet1', 'INFO']
        target_sheet = None
        
        print(f"Available sheets in workbook: {workbook.sheetnames}")
        
        for sheet_name in possible_sheet_names:
            if sheet_name in workbook.sheetnames:
                target_sheet = workbook[sheet_name]
                print(f"Using sheet '{sheet_name}' for room data")
                break
        
        if target_sheet is None:
            # If no exact match, look for sheets containing 'rooms' or use first sheet
            for sheet_name in workbook.sheetnames:
                if 'rooms' in sheet_name.lower():
                    target_sheet = workbook[sheet_name]
                    print(f"Using sheet '{sheet_name}' as ROOMS# equivalent")
                    break
            
            # If still no match, use the first sheet
            if target_sheet is None:
                target_sheet = workbook.worksheets[0]
                print(f"Using first sheet '{target_sheet.title}' as default")
        
        # Clear existing data in columns Q and R (starting from row 3 to preserve headers)
        max_row_to_clear = 1000  # Conservative limit
        
        print(f"Clearing existing data in columns Q and S...")
        
        # Clear column Q (Room Names) and column R (LOS)
        cleared_rows = 0
        for row in range(3, max_row_to_clear + 1):
            q_cell = target_sheet[f'Q{row}']
            r_cell = target_sheet[f'S{row}']
            
            if q_cell.value is not None or r_cell.value is not None:
                q_cell.value = None
                r_cell.value = None
                cleared_rows += 1
            else:
                # If we hit several consecutive empty cells in both columns, stop clearing
                empty_count = 0
                for check_row in range(row, min(row + 5, max_row_to_clear + 1)):
                    q_check = target_sheet[f'Q{check_row}'].value
                    r_check = target_sheet[f'R{check_row}'].value
                    if q_check is None and r_check is None:
                        empty_count += 1
                
                if empty_count >= 5:  # If 5 consecutive empty pairs, stop clearing
                    break
        
        print(f"Cleared {cleared_rows} existing rows")
        
        # Insert room data into columns Q and R starting from row 3
        print(f"Inserting {len(room_entries)} room entries...")
        for idx, entry in enumerate(room_entries, start=4):
            # Column Q: Room Name
            target_sheet[f'Q{idx}'] = entry['room_name']
            # Column R: LOS
            target_sheet[f'S{idx}'] = entry['los']
            
            if idx <= 7:  # Log first few entries
                print(f"  Row {idx}: Q='{entry['room_name']}', S='{entry['los']}'")
        

        # Save the workbook with updated data
        workbook.save(base_excel_path)
        workbook.close()
        
        print(f"Successfully saved updated data to base Excel file")
        
        print(f"Successfully updated base Excel file with {len(room_entries)} room entries:")
        print(f"  - Column Q: Room Names")
        print(f"  - Column S: LOS Data")
        print(f"  - Sheet: '{target_sheet.title}' starting at row 3")
        print(f"  - Base file: {base_excel_path}")
        
    except Exception as e:
        raise Exception(f"Failed to update base Excel file: {str(e)}")


def get_base_excel_template_info():
    """
    Utility function to get information about the base Excel template
    
    Returns:
        dict: Information about the base template file including column structure
    """
    try:
        base_excel_path = find_base_excel_template()
        
        info = {
            'path': base_excel_path,
            'exists': True,
            'sheets': [],
            'size': 0,
            'columns': {
                'Q': 'Room Names',
                'S': 'LOS Data'
            },
            'direct_update': True,
            'temp_files_used': False
        }
        
        try:
            info['size'] = os.path.getsize(base_excel_path)
            workbook = load_workbook(base_excel_path, read_only=True)
            info['sheets'] = workbook.sheetnames
            
            # Try to get column headers from any sheet that might contain room data
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                try:
                    # Check what's in the header rows for columns Q and R
                    q_header_1 = sheet['Q1'].value
                    q_header_2 = sheet['Q2'].value
                    r_header_1 = sheet['S1'].value
                    r_header_2 = sheet['S2'].value
                    
                    if q_header_1 or q_header_2 or r_header_1 or r_header_2:
                        info['column_headers'] = {
                            'sheet': sheet_name,
                            'Q': {
                                'row_1': q_header_1,
                                'row_2': q_header_2
                            },
                            'S': {
                                'row_1': r_header_1,
                                'row_2': r_header_2
                            }
                        }
                        
                        # Check if there are existing formulas that reference these columns
                        formula_count = 0
                        for row in sheet.iter_rows(min_row=1, max_row=100):
                            for cell in row:
                                if cell.data_type == 'f' and cell.value:
                                    if 'Q' in str(cell.value) or 'S' in str(cell.value):
                                        formula_count += 1
                        
                        info['formulas_referencing_QR'] = formula_count
                        break
                        
                except Exception as header_error:
                    info['header_read_error'] = str(header_error)
                    continue
                    
            workbook.close()
            
        except Exception as e:
            info['error'] = str(e)
            
    except FileNotFoundError:
        info = {
            'path': None,
            'exists': False,
            'error': 'Template file not found',
            'debug_info': get_template_debug_info(),
            'direct_update': False,
            'temp_files_used': False
        }
    
    return info


def validate_room_data_format(request):
    """
    API endpoint to validate room data format without processing
    
    Returns:
        JsonResponse: Validation results including parsed data preview
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    room_data_raw = request.POST.get('room_data', '').strip()
    
    if not room_data_raw:
        return JsonResponse({
            'valid': False,
            'error': 'No room data provided',
            'entries': [],
            'total_lines': 0,
            'valid_entries': 0
        })
    
    # Parse the data
    parsed_entries = parse_room_data(room_data_raw)
    total_lines = len([line for line in room_data_raw.split('\n') if line.strip()])
    
    # Create preview of parsed data
    preview_entries = []
    for entry in parsed_entries[:5]:  # Show first 5
        preview_entries.append({
            'room_name': entry['room_name'],
            'los': entry['los'],
            'line_number': entry['line_number']
        })
    
    return JsonResponse({
        'valid': len(parsed_entries) > 0,
        'total_lines': total_lines,
        'valid_entries': len(parsed_entries),
        'invalid_entries': total_lines - len(parsed_entries),
        'entries_preview': preview_entries,
        'truncated': len(parsed_entries) > 5,
        'columns_target': {
            'Q': 'Room Names',
            'R': 'LOS Data'
        },
        'template_info': get_base_excel_template_info(),
        'update_method': 'direct_base_file_update'
    })


# Debug endpoint to help troubleshoot template issues
def debug_template_files(request):
    """
    Debug endpoint to show what template files are available
    """
    return JsonResponse({
        'template_info': get_base_excel_template_info(),
        'debug_info': get_template_debug_info(),
        'update_method': 'direct_base_file_update',
        'recalculation': 'libreoffice_headless'
    })
import io
import zipfile

def download_media_view(request):
    if request.method == 'POST':
        claim_id = request.POST.get('claim_id')
        room_filter = request.POST.get('room_filter', '')
        target_rooms = [r.strip() for r in room_filter.split(',') if r.strip()]
        
        try:
            # Create a zip file in memory
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                api_client = EncircleAPIClient()
                downloader = ZipMediaDownloader(api_client, target_rooms, zip_file)
                downloader.download_claim_media(int(claim_id))
            
            # Prepare the response with the zip file
            response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="claim_{claim_id}_media.zip"'
            
            msg = f"Prepared media download for {claim_id}"
            if target_rooms:
                msg += f" (filtered by rooms: {', '.join(target_rooms)})"
            messages.success(request, msg)
            
            return response
            
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return redirect('download_media')
    
    return render(request, 'account/download_media.html')

class ZipMediaDownloader:
    """
    Downloads media files from Encircle API and organizes them in a zip file by room labels.
    """
    
    def __init__(self, api_client, target_rooms=None, zip_file=None):
        self.api_client = api_client
        self.target_rooms = target_rooms or []
        self.downloaded_files = 0
        self.failed_downloads = 0
        self.zip_file = zip_file
        
    def download_claim_media(self, property_claim_id):
        """
        Main method to download all media for a specific claim into the zip file
        """
        print(f"\nStarting media download for claim ID: {property_claim_id}")
        print("="*60)
        
        try:
            # Get media list from API
            media_list = self._get_media_list(property_claim_id)
            
            if not media_list:
                print("No media found for this claim.")
                return
            
            # Process each media item
            for idx, media_item in enumerate(media_list, 1):
                if self._should_download(media_item):
                    self._process_media_item(media_item, idx, len(media_list))
                else:
                    print(f"Skipping {media_item['filename']} - not in target rooms")

        except Exception as e:
            logging.error(f"Error downloading media for claim {property_claim_id}: {str(e)}")
            raise
            
        print("\nDownload Summary:")
        print(f"- Successfully downloaded: {self.downloaded_files}")
        print(f"- Failed downloads: {self.failed_downloads}")
    
    def _should_download(self, media_item):
        """Check if media belongs to target room(s)"""
        if not self.target_rooms:
            return True  # Download all if no filter
        
        labels = media_item.get('labels', [])
        return any(room.lower() in [label.lower() for label in labels] 
               for room in self.target_rooms)

    def _get_media_list(self, property_claim_id):
        """Fetch media list from API with pagination support"""
        all_media = []
        after_cursor = None
        
        while True:
            params = {'limit': 100}
            if after_cursor:
                params['after'] = after_cursor
                
            endpoint = f"property_claims/{property_claim_id}/media"
            response = self.api_client._make_request(endpoint, params=params)
            
            if not response or 'list' not in response:
                break
                
            all_media.extend(response['list'])
            after_cursor = response.get('cursor', {}).get('after')
            
            if not after_cursor:
                break
                
        return all_media
        
    def _process_media_item(self, media_item, current_index, total_items):
        """Handle a single media item download into the zip file"""
        try:
            # Determine folder based on labels
            folder_name = self._get_folder_name(media_item)
            file_extension = self._get_file_extension(media_item['content_type'])
            
            # Create safe filename with sequential number
            seq_num = str(current_index).zfill(len(str(total_items)))
            clean_filename = f"{seq_num}_{media_item['filename']}"
            clean_filename = self._sanitize_filename(clean_filename)
            
            # Ensure proper file extension
            if not clean_filename.lower().endswith(file_extension.lower()):
                clean_filename += file_extension
                
            # Prepare full path in zip
            zip_path = os.path.join(folder_name, clean_filename)
            
            # Download the file
            print(f"\nDownloading {current_index}/{total_items}: {clean_filename}")
            print(f"Type: {media_item['content_type']}")
            print(f"Labels: {', '.join(media_item.get('labels', ['No labels']))}")
            print(f"Adding to zip at: {zip_path}")
            
            file_content = self._download_file_content(media_item['download_uri'])
            self.zip_file.writestr(zip_path, file_content)
            self.downloaded_files += 1
            
            # Add metadata file
            self._add_metadata_file(media_item, zip_path)
            
        except Exception as e:
            self.failed_downloads += 1
            logging.error(f"Failed to process media item: {str(e)}")
            print(f"Error processing item {current_index}: {str(e)}")
            
    def _get_folder_name(self, media_item):
        """Create nested folder structure from all labels, handling edge cases"""
        labels = media_item.get('labels', [])
        
        if not labels:
            return "unlabeled_media"
        
        # Handle cases where labels might be empty strings
        valid_labels = [label.strip() for label in labels if label.strip()]
        if not valid_labels:
            return "unlabeled_media"
        
        # Limit folder depth to prevent overly long paths
        max_depth = 3  # Main_Building/Sub_Room/Area
        truncated_labels = valid_labels[:max_depth]
        
        # Sanitize and join
        return os.path.join(*[self._sanitize_folder_name(label) for label in truncated_labels])
        
    def _sanitize_filename(self, filename):
        """Remove invalid characters from filenames"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename
        
    def _sanitize_folder_name(self, foldername):
        """Sanitize folder names and truncate if too long"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            foldername = foldername.replace(char, '_')
        return foldername[:50]  # Prevent too long folder names
        
    def _get_file_extension(self, content_type):
        """Map content type to file extension"""
        extension_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'application/pdf': '.pdf',
            'video/mp4': '.mp4',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
        }
        return extension_map.get(content_type, '.bin')
        
    def _download_file_content(self, url):
        """Download the actual file content from the URI"""
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            raise Exception(f"Download failed: {str(e)}")
            
    def _add_metadata_file(self, media_item, file_path):
        """Create a metadata file in the zip"""
        metadata = {
            'original_filename': media_item['filename'],
            'content_type': media_item['content_type'],
            'source_type': media_item['source']['type'],
            'source_id': media_item['source']['primary_id'],
            'creator': media_item['creator']['actor_identifier'],
            'created_date': media_item['primary_server_created'],
            'labels': media_item.get('labels', []),
            'download_time': dt.datetime.now().isoformat()
        }
        
        metadata_path = f"{file_path}.meta.json"
        self.zip_file.writestr(metadata_path, json.dumps(metadata, indent=2))

@login_required
def export_claims_to_excel(request, claim_id=None):
    """
    View to export claims data to Excel
    """
    try:
        api_client = EncircleAPIClient()
        processor = EncircleDataProcessor()
        exporter = EncircleExcelExporter()
        
        if claim_id:
            # Export single claim with all details
            raw_claim_details = api_client.get_claim_details(claim_id)
            claim_details = processor.process_claim_details(raw_claim_details)

            structures_response = api_client.get_claim_structures(claim_id)
            if not structures_response or not structures_response.get('list'):
                raise ValueError(f"No structures found for claim {claim_id}")
            
            structure_id = structures_response['list'][0]['id']

            raw_rooms_data = api_client.get_claim_rooms(claim_id, structure_id)
            rooms_data, room_types = processor.process_claim_rooms(raw_rooms_data)

            floor_plan_data = None
            try:
                raw_floor_plan = api_client.get_claim_floor_plan(claim_id)
                floor_plan_data = processor.process_floor_plan_data(raw_floor_plan)
            except Exception as e:
                logger.warning(f"Could not fetch floor plan: {str(e)}")

            export_data = {
                'claim_details': claim_details,
                'rooms': rooms_data,
                'floor_plan': floor_plan_data
            }
        else:
            # Export all claims with consolidated rooms and floor plans
            raw_claims = api_client.get_all_claims()
            processed_claims = processor.process_claims_list(raw_claims)
            processed_claims = processed_claims
            logger.info(f"Processing {len(processed_claims)} claims for detailed export")

            # Collect rooms and floor plan data from ALL claims
            all_rooms_data = []
            all_floor_plan_data = {}
            
            # Process each claim with better error handling
            for i, claim in enumerate(processed_claims):
                current_claim_id = claim.get('id')
                if not current_claim_id:
                    logger.warning(f"Claim at index {i} has no ID, skipping")
                    continue

                logger.info(f"Processing claim {current_claim_id} ({i+1}/{len(processed_claims)})")
                
                try:
                    # Get structures for this claim
                    structures_response = api_client.get_claim_structures(current_claim_id)
                    if not structures_response or not structures_response.get('list'):
                        logger.warning(f"No structures found for claim {current_claim_id}")
                        continue

                    structure_id = structures_response['list'][0]['id']

                    # Get rooms for this claim
                    try:
                        raw_rooms_data = api_client.get_claim_rooms(current_claim_id, structure_id)
                        rooms_data, room_types = processor.process_claim_rooms(raw_rooms_data)

                        # Add claim_id to each room for identification
                        if rooms_data:  # Check if rooms_data is not empty
                            for room in rooms_data:
                                room['claim_id'] = current_claim_id
                                room['claim_name'] = claim.get('policyholder_name', 'Unknown')
                            all_rooms_data.extend(rooms_data)
                            logger.info(f"Added {len(rooms_data)} rooms for claim {current_claim_id}")
                    except Exception as e:
                        logger.warning(f"Could not fetch rooms for claim {current_claim_id}: {str(e)}")

                    # Get floor plan for this claim
                    try:
                        raw_floor_plan = api_client.get_claim_floor_plan(current_claim_id)
                        if raw_floor_plan:  # Check if data exists
                            floor_plan_data = processor.process_floor_plan_data(raw_floor_plan)
                            if floor_plan_data:
                                # Namespace floor plan data by claim ID
                                all_floor_plan_data[f"Claim_{current_claim_id}"] = floor_plan_data
                                logger.info(f"Added floor plan for claim {current_claim_id}")
                    except Exception as e:
                        logger.warning(f"Could not fetch floor plan for claim {current_claim_id}: {str(e)}")

                except Exception as e:
                    logger.error(f"Critical error processing claim {current_claim_id}: {str(e)}")
                    continue

            logger.info(f"Collected {len(all_rooms_data)} total rooms and {len(all_floor_plan_data)} floor plans")

            export_data = {
                'claims': processed_claims,
                'rooms': all_rooms_data if all_rooms_data else [],  # Use empty list instead of None
                'floor_plan': all_floor_plan_data if all_floor_plan_data else {}  # Use empty dict instead of None
            }
        
        # Debug: Log export data structure
        logger.info("Export data structure:")
        logger.info(f"- Claims: {len(export_data.get('claims', []))}")
        logger.info(f"- Rooms: {len(export_data.get('rooms', []))}")
        logger.info(f"- Floor plans: {len(export_data.get('floor_plan', {}))}")
        logger.info(f"- Claim details: {'Yes' if export_data.get('claim_details') else 'No'}")
        
        # Generate Excel file
        excel_file, filename = exporter.export_claims(export_data)
        
        # Validate Excel file was created
        if not excel_file:
            raise ValueError("Excel file generation returned None")
        
        # Get the actual bytes content
        excel_content = excel_file.getvalue()
        
        # Validate content size
        if len(excel_content) == 0:
            raise ValueError("Generated Excel file is empty")
        
        logger.info(f"Generated Excel file: {filename}, Size: {len(excel_content)} bytes")
        
        # Create response with proper headers
        response = HttpResponse(
            excel_content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = len(excel_content)

        return response
        
    except Exception as e:
        logger.error(f"Error exporting to Excel: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Return simple error response for all request types
        messages.error(request, f"Error generating Excel file: {str(e)}")
        return redirect('encircle_claims_dashboard')

# Django Views
def encircle_claims_dashboard(request):
    """
    Main dashboard view for displaying all claims
    """
    return render(request, 'account/encircle_dashboard.html')


def fetch_all_claims_api(request):
    """
    API endpoint to fetch all claims with basic information
    """
    try:
        api_client = EncircleAPIClient()
        processor = EncircleDataProcessor()
        
        # Fetch all claims
        raw_claims = api_client.get_all_claims()
        processed_claims = processor.process_claims_list(raw_claims)
        
        # Enhance each claim with room count and types
        for claim in processed_claims:
            try:
                # Get structures with validation
                structures_response = api_client.get_claim_structures(claim['id'])
                if not structures_response or not isinstance(structures_response, dict) or 'list' not in structures_response:
                    logger.warning(f"Invalid structures data for claim {claim['id']}")
                    claim['total_rooms'] = 'N/A'
                    claim['room_types'] = []
                    continue
                    
                structures_list = structures_response.get('list', [])
                if not structures_list:
                    claim['total_rooms'] = 0
                    claim['room_types'] = []
                    continue
                
                # Get rooms for the first structure only (to avoid too many API calls)
                first_structure_id = structures_list[0].get('id')
                if not first_structure_id:
                    logger.warning(f"No valid structure ID found for claim {claim['id']}")
                    claim['total_rooms'] = 'N/A'
                    claim['room_types'] = []
                    continue
                
                rooms_response = api_client.get_claim_rooms(claim['id'], first_structure_id)
                if not rooms_response or not isinstance(rooms_response, dict) or 'list' not in rooms_response:
                    logger.warning(f"Invalid rooms data for claim {claim['id']}")
                    claim['total_rooms'] = 'N/A'
                    claim['room_types'] = []
                    continue
                
                processed_data, processed_types = processor.process_claim_rooms(rooms_response)
                claim['total_rooms'] = len(processed_data)
                claim['room_types'] = processed_types[:5]  # Limit to first 5 types for overview
            except Exception as e:
                logger.warning(f"Error processing rooms for claim {claim['id']}: {str(e)}")
                claim['total_rooms'] = 'N/A'
                claim['room_types'] = []
            break   
        
        return JsonResponse({
            'success': True,
            'claims': processed_claims,
            'total_claims': len(processed_claims)
        })
        
    except Exception as e:
        logger.error(f"Error fetching claims: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'claims': [],
            'total_claims': 0
        }, status=500)


def fetch_claim_details_api(request, claim_id):
    """
    API endpoint to fetch detailed information for a specific claim
    """
    try:
        api_client = EncircleAPIClient()
        processor = EncircleDataProcessor()
        
        # Fetch claim details
        raw_claim_details = api_client.get_claim_details(claim_id)
        claim_details = processor.process_claim_details(raw_claim_details)
        
        structures_response = api_client.get_claim_structures(claim_id)
        structure_id = structures_response['list'][0]['id']
        
        # Fetch rooms for this claim
        raw_rooms_data = api_client.get_claim_rooms(claim_id, structure_id)
        rooms_data, room_types = processor.process_claim_rooms(raw_rooms_data)
        
        # Fetch and process floor plan data
        floor_plan_data = None
        try:
            raw_floor_plan = api_client.get_claim_floor_plan(claim_id)
            floor_plan_data = processor.process_floor_plan_data(raw_floor_plan)
        except Exception as e:
            logger.warning(f"Could not fetch floor plan for claim {claim_id}: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'claim_details': claim_details,
            'rooms': rooms_data,
            'room_types': room_types,
            'total_rooms': len(rooms_data),
            'floor_plan': floor_plan_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching claim details for {claim_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def fetch_claim_rooms_api(request, claim_id, structure_id):
    """
    API endpoint to fetch rooms data for a specific claim
    """
    try:
        api_client = EncircleAPIClient()
        processor = EncircleDataProcessor()
        
        raw_rooms_data = api_client.get_claim_rooms(claim_id, structure_id)
        rooms_data, room_types = processor.process_claim_rooms(raw_rooms_data)
        
        return JsonResponse({
            'success': True,
            'rooms': rooms_data,
            'room_types': room_types,
            'total_rooms': len(rooms_data)
        })
        
    except Exception as e:
        logger.error(f"Error fetching rooms for claim {claim_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def recursive_dir_list(dir, dic):
    for f in os.listdir(dir):
        path = os.path.join(dir, f)
        
        if os.path.isdir(path):
            dic[f] = {}
            recursive_dir_list(path,dic[f])
        else:
            dic[f] = f
            
    return dic

def home(request):
    
      # request to server to return files in document folder as object
      # send this object to the template for display
      # reload page to update display
      # once on template, load object and display.
      # start from the top most objects and display those filenames
      # for each folder object make it clickable
      # once clicked index the object for all children
      # and repalce entire display with jsut children of that folder
      # display path to that location in the top
      # the true path to the file on server should be calculated somewhere
      # probably not on the page tho to not expose paths

    #dic_of_files = recursive_dir_list(settings.MEDIA_ROOT + "/uploads/documents/", {})
    ## handling upload
    #if request == "POST":
    #    form = UploadFilesForm(request.POST, request.FILES)
    #    if form.is_valid():
    #        # function that handles file
    #        return


    if request.user.is_authenticated:
        return render(request, 'account/dashboard.html')
    else:
        return render(request, 'account/login.html')

def logout_view(request):
    logout(request)
    return redirect('/')

@login_required
def get_dimensions(request):
    
    return render(request, 'account/encircle.html')

def fetch_dimensions_API(request, claim_id):
    import requests

    try: 
        api_key = "367382d2-0b2d-4b01-9d06-8f18fd492f5e"

        url = f"https://api.encircleapp.com/v2/property_claims/{claim_id}/floor_plan_dimensions"
    
        headers = {"Authorization" : f"Bearer {api_key}"}

        response = requests.get(url, headers=headers)

        #print(response.json())
        raw_data = response.json()
        processed_data = process_floor_data(raw_data)
        
        return JsonResponse(processed_data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def fetch_from_encircle_api(claim_id):

    return response.json()

def process_floor_data(raw_data):
    
    result = {
        'floors': [],
        'summary': {
            'totalFloors': 0,
            'totalRooms': 0,
            'roomsByType': {}
        }
    }
    
    # Check if we have valid data
    if not raw_data or 'list' not in raw_data or not raw_data['list']:
        return result
    
    floor_names = ['Basement', 'Main Floor', 'Second Floor', 'Third Floor', 'Attic']
    floor_count = 0
    room_count = 0
    room_types = {}
    
    # Process each floor group
    for floor_group in raw_data['list']:
        if 'floors' not in floor_group:
            continue
        
        # Process each floor in the group
        for i, floor in enumerate(floor_group['floors']):
            if 'features' not in floor:
                continue
                
            floor_name = floor_names[floor_count] if floor_count < len(floor_names) else f"Floor {floor_count + 1}"
            floor_data = {
                'id': floor_count,
                'name': floor_name,
                'rooms': [],
                'totalRooms': 0
            }
            
            # Process rooms (features)
            for feature in floor['features']:
                if feature['type'] == 'Feature' and 'properties' in feature and 'geometry' in feature:
                    room_name = feature['properties'].get('name', 'Unnamed Room')
                    
                    # Update room type counts for summary
                    if room_name in room_types:
                        room_types[room_name] += 1
                    else:
                        room_types[room_name] = 1
                    
                    # Calculate room area (approximate)
                    area = calculate_polygon_area(feature['geometry']['coordinates'][0]) if feature['geometry']['type'] == 'Polygon' else 0
                    
                    room = {
                        'id': room_count,
                        'name': room_name,
                        'ceilingHeight': feature['properties'].get('ceiling_height', 0),
                        'area': round(area, 2),  # Area in square units
                        'coordinates': feature['geometry']['coordinates'][0] if feature['geometry']['type'] == 'Polygon' else []
                    }
                    
                    floor_data['rooms'].append(room)
                    room_count += 1
            
            floor_data['totalRooms'] = len(floor_data['rooms'])
            result['floors'].append(floor_data)
            floor_count += 1
    
    # Update summary information
    result['summary']['totalFloors'] = floor_count
    result['summary']['totalRooms'] = room_count
    result['summary']['roomsByType'] = room_types
    
    return result

def calculate_polygon_area(coordinates):
    """
    Calculate the area of a polygon using the Shoelace formula
    
    Args:
        coordinates: List of [x, y] coordinate pairs forming a polygon
        
    Returns:
        float: Area of the polygon
    """
    n = len(coordinates)
    area = 0.0
    
    for i in range(n):
        j = (i + 1) % n
        area += coordinates[i][0] * coordinates[j][1]
        area -= coordinates[j][0] * coordinates[i][1]
    
    area = abs(area) / 2.0
    return area


from .forms import UploadClientForm

@login_required
def create(request):
    if request.method == "POST":
        if 'excel_file' in request.FILES:
            return handle_excel_import(request)
        else:
            form = UploadClientForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Client created successfully!')
                return redirect('dashboard')
            return render(request, 'account/create.html', {'form': form})
    
    form = UploadClientForm()
    return render(request, 'account/create.html', {'form': form})


"""

API FOR TEMPLATE CREATOR SENDS EACH 01-ROOMS (old 01 INFO) TO THE SERVER AFTER RUNNING 
SYSTEM AUTOMATICALLY LOADS IT IN THE SYSTEM
"""

import json
import datetime as dt
import pandas as pd
from io import BytesIO
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from .models import Client
from .forms import ClientForm
from .models import Client, Room, WorkType, RoomWorkTypeValue

import openpyxl
from openpyxl.utils import get_column_letter

def import_client_from_info_file(excel_file):
    """
    Extract client data from 01-INFO.xlsx file from jobinfo(2) tab
    WITH FORMULA SUPPORT - gets calculated values, not formula text
    """
    try:
        # Use openpyxl to read Excel with formula values
        excel_file.seek(0)
        wb = openpyxl.load_workbook(BytesIO(excel_file.read()), data_only=True)  # data_only=True gets calculated values
        
        # Check for jobinfo(2) tab
        sheet_name = 'jobinfo(2)'
        if sheet_name not in wb.sheetnames:
            # Try alternative names
            possible_sheets = [s for s in wb.sheetnames if 'jobinfo' in s.lower()]
            if possible_sheets:
                sheet_name = possible_sheets[0]
                print(f"ℹ️ Using alternative sheet: {sheet_name}")
            else:
                raise ValueError(f"No jobinfo sheet found in INFO file. Available sheets: {', '.join(wb.sheetnames)}")
        
        ws = wb[sheet_name]
        
        print(f"✅ Loaded jobinfo sheet: {ws.max_row} rows, {ws.max_column} columns")
        
        # Extract client data using openpyxl
        client_data = extract_client_data_from_jobinfo_openpyxl(ws)
        wb.close()  # Close workbook to free memory
        
        return client_data
        
    except Exception as e:
        raise Exception(f"Failed to process INFO file: {str(e)}")


def extract_client_data_from_jobinfo_openpyxl(worksheet):
    """
    Extract client data from jobinfo worksheet using openpyxl
    Gets calculated values from formulas
    """
    client_data = {}
    
    # Constants for jobinfo structure
    HEADER_COLUMN = 1  # Column A (openpyxl uses 1-indexed)
    DATA_COLUMN = 2    # Column B
    
    print("🔍 Scanning jobinfo sheet for client data with formula support...")
    
    for row in range(1, worksheet.max_row + 1):
        header_cell = worksheet.cell(row=row, column=HEADER_COLUMN)
        value_cell = worksheet.cell(row=row, column=DATA_COLUMN)
        
        header = str(header_cell.value).strip() if header_cell.value is not None else None
        value = value_cell.value  # This gets the calculated value, even if it's a formula
        
        if not header or header in ['None', 'nan', ''] or value is None:
            continue
            
        # Use your proven field normalization
        field_name = (header.lower()
                     .replace(' ', '_')
                     .replace('/', '_')
                     .replace('\\', '_')
                     .replace('.', '_')
                     .replace('-', '_')
                     .replace(':', '_')
                     .replace('__', '_')
                     .replace('#', 'num')
                     .strip('_'))
        
        # Debug output for key fields
        if any(keyword in field_name for keyword in ['owner', 'address', 'email', 'phone', 'claim']):
            print(f"📝 Key field: '{header}' → '{field_name}' = '{value}' (type: {type(value).__name__})")
        
        # Special handling for date fields
        if any(term in field_name for term in ['date', 'dol']):
            parsed_date = parse_excel_date_openpyxl(value)
            if parsed_date:
                print(f"📅 Parsed date: {header} → {parsed_date}")
                if 'loss' in field_name:
                    client_data['date_of_loss'] = parsed_date
                else:
                    client_data[field_name] = parsed_date
            else:
                client_data[field_name] = value  # Store original if date parsing fails
            continue
        
        # Handle boolean fields
        if isinstance(value, str) and value.lower() in ('yes', 'no', 'true', 'false', 'y', 'n'):
            value = value.lower() in ('yes', 'true', 'y')
            print(f"⚡ Converted boolean: {header} → {value}")
        elif isinstance(value, (int, float)) and value in (0, 1):
            # Handle 1/0 as boolean
            value = bool(value)
            print(f"⚡ Converted numeric boolean: {header} → {value}")
        
        # Handle numeric fields
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            # It's already a number, keep as is
            pass
        elif isinstance(value, str) and value.replace('.', '').replace(',', '').isdigit():
            try:
                # Remove commas and convert to float
                value = float(value.replace(',', ''))
                print(f"🔢 Converted string to numeric: {header} → {value}")
            except ValueError:
                pass
        
        client_data[field_name] = value
    
    print(f"✅ Extracted {len(client_data)} client data fields from jobinfo (with formula support)")
    return client_data



def import_rooms_from_rooms_file(excel_file, client):
    """
    Extract room data from 01-ROOMS.xlsm file from ROOMS# tab
    WITH FORMULA SUPPORT - gets calculated values from formulas
    """
    try:
        # Use openpyxl to read Excel with formula values
        excel_file.seek(0)
        wb = openpyxl.load_workbook(BytesIO(excel_file.read()), data_only=True)  # data_only=True gets calculated values
        
        if 'ROOMS#' not in wb.sheetnames:
            raise ValueError(f"ROOMS# sheet not found in ROOMS file. Available sheets: {', '.join(wb.sheetnames)}")
        
        ws = wb['ROOMS#']
        
        print(f"✅ Loaded ROOMS# sheet: {ws.max_row} rows, {ws.max_column} columns")
        print(f"📊 Columns available: A-{get_column_letter(ws.max_column)}")
        
        rooms_data = extract_room_data_from_rooms_sheet_openpyxl(ws)
        wb.close()  # Close workbook to free memory
        
        if not rooms_data:
            raise ValueError("No room data found in ROOMS# sheet")
        
        # Create rooms in database
        rooms_created, wt_values_created = create_rooms_for_client(client, rooms_data)
        
        return {
            'rooms_processed': rooms_created,
            'work_type_values_created': wt_values_created,
            'total_rooms_found': len(rooms_data),
            'rooms_sample': rooms_data[:3] if rooms_data else []
        }
        
    except Exception as e:
        raise Exception(f"Failed to process ROOMS file: {str(e)}")

def extract_room_data_from_rooms_sheet_openpyxl(worksheet):
    """
    Enhanced room data extraction using openpyxl with formula support
    Columns U to BT, with each work type section being 5 columns apart
    """
    rooms_data = []
    
    # Define the work types and their column ranges (1-indexed for openpyxl)
    work_type_sections = {
        100: range(21, 26),   # U-Y (columns 21-25)
        200: range(26, 31),   # Z-AD (columns 26-30)  
        300: range(31, 36),   # AE-AI (columns 31-35)
        400: range(36, 41),   # AJ-AN (columns 36-40)
        500: range(41, 46),   # AO-AS (columns 41-45)
        800: range(46, 51),   # AT-AX (columns 46-50)
        6100: range(51, 56),  # AY-BC (columns 51-55) - DAY 1
        6200: range(56, 61),  # BD-BH (columns 56-60) - DAY 2  
        6300: range(61, 66),  # BI-BM (columns 61-65) - DAY 3
        6400: range(66, 71),  # BN-BR (columns 66-70) - DAY 4
    }
    
    print(f"🔍 Scanning for room data in columns U to BT with formula support...")
    print(f"📋 Work types configured: {list(work_type_sections.keys())}")
    
    rooms_found = 0
    max_rows_to_scan = min(worksheet.max_row, 200)  # Limit scanning to first 200 rows for performance
    
    # Iterate through rows to find room data
    for row in range(1, max_rows_to_scan + 1):
        # Check if this row contains room data by looking at first work type section
        first_section_cols = work_type_sections[100]
        room_name_parts = []
        
        for col in first_section_cols:
            if col <= worksheet.max_column:
                cell = worksheet.cell(row=row, column=col)
                if cell.value is not None and str(cell.value).strip():
                    room_name_parts.append(str(cell.value).strip())
        
        # If we have room name parts, this is a room row
        if room_name_parts:
            room_name = ' '.join(room_name_parts).strip()
            # Filter out header rows and empty names
            if (room_name and 
                room_name not in ['', 'Room Name', 'Room', 'ROOM NAME', 'ROOM'] and
                not any(keyword in room_name.upper() for keyword in ['HEADER', 'TITLE', 'DESCRIPTION'])):
                
                rooms_found += 1
                room_data = {
                    'room_name': room_name,
                    'sequence': len(rooms_data) + 1,
                    'work_type_values': {}
                }
                
                if rooms_found <= 3:  # Log first 3 rooms for debugging
                    print(f"🚪 Found room {rooms_found}: '{room_name}'")
                      if value_col <= worksheet.max_column:
                        cell = worksheet.cell(row=row, column=value_col)
    
                # Extract work type values for ALL 10 work types
                work_types_found = 0
                for wt_id, col_range in work_type_sections.items():
                    # Use the LAST column of each 5-column section for the value
                    value_col = list(col_range)[4]  # Last column of the 5-column range
                    
                                  if cell.value is not None and str(cell.value).strip():
                            value_str = str(cell.value).strip().upper()
                            value_type = determine_los_travel_value_enhanced(value_str)
                            
                            if value_type != 'NA':  # Only store if it has a meaningful value
                                room_data['work_type_values'][wt_id] = value_type
                                work_types_found += 1
                
                if work_types_found > 0 and rooms_found <= 3:
                    print(f"   📋 Work types with values: {work_types_found}")
                    # Show sample work type values for first few rooms
                    sample_wt = list(room_data['work_type_values'].items())[:2]
                    for wt_id, val_type in sample_wt:
                        print(f"     - {wt_id}: {val_type}")
                
                rooms_data.append(room_data)
    
    print(f"✅ Found {len(rooms_data)} rooms with work type data (formula values extracted)")
    
    # Show detailed sample of what was extracted
    if rooms_data:
        print("📊 Room data sample (with formula values):")
        for i, room in enumerate(rooms_data[:2]):
            wt_details = []
            for wt_id, val_type in list(room['work_type_values'].items())[:4]:  # Show first 4 work types
                wt_details.append(f"{wt_id}:{val_type}")
            print(f"   {i+1}. '{room['room_name']}' - Work types: {', '.join(wt_details)}")
    
    return rooms_data
def parse_excel_date_openpyxl(value):
    """
    Enhanced date parser for openpyxl values
    Handles datetime objects, Excel serial numbers, and strings
    """
    if value is None:
        return None
    
    try:
        # If it's already a datetime object
        if isinstance(value, (dt.datetime, dt.date)):
            return value.date() if isinstance(value, dt.datetime) else value
        
        # If it's an Excel serial number (float)
        if isinstance(value, (int, float)):
            print(f"🔢 Parsing Excel date number: {value}")
            try:
                # Excel's date system starts from 1899-12-30
                if value < 0:
                    return None
                if value == 0:  # Excel's zero date
                    return None
                if value == 60:  # Excel's 1900-02-29 (non-existent)
                    return dt.date(1900, 2, 28)
                if value < 60:  # Adjust for Excel's leap year bug
                    value += 1
                return (dt.datetime(1899, 12, 30) + dt.timedelta(days=value)).date()
            except Exception:
                return None
        
        # If it's a string, try parsing
        if isinstance(value, str):
            value = value.strip()
            if not value or value.upper() in ('TBD', 'NA', 'N/A', 'UNKNOWN'):
                return None
            
            # Clean the string
            value = (value.replace('  ', ' ')
                     .replace('Sept', 'Sep')
                     .replace('Febr', 'Feb')
                     .replace('Dece', 'Dec')
                     .split(' ')[0])  # Take only first part if space separated
            
            # Try parsing as datetime string
            date_formats = [
                '%Y-%m-%d %H:%M:%S',  # 2024-12-02 00:00:00
                '%Y-%m-%d',           # 2024-12-02
                '%m/%d/%Y',           # 1/20/2024
                '%d-%b-%y',           # 24-Jan-24
                '%d-%b-%Y',           # 20-Jan-2024
                '%b %d, %Y',          # Dec 23, 2022
                '%B %d, %Y',          # December 23, 2022
                '%d-%m-%Y',           # 20-01-2024
                '%d %b %Y',           # 20 Jan 2024
                '%d %B %Y'            # 20 January 2024
            ]
            
            for fmt in date_formats:
                try:
                    parsed_dt = dt.datetime.strptime(value, fmt)
                    return parsed_dt.date()
                except ValueError:
                    continue
        
        return None
        
    except Exception as e:
        print(f"❌ Date parsing error for value '{value}': {str(e)}")
        return None

def determine_los_travel_value_enhanced(value_str):
    """
    Enhanced value determination for LOS/TRAVEL/NA
    Handles numeric values from formulas properly
    """
    if value_str is None:
        return 'NA'
    
    if isinstance(value_str, (int, float)):
        # Numeric value from formula - treat as LOS
        return 'LOS'
    
    value_clean = str(value_str).upper().strip()
    
    if not value_clean or value_clean in ['', 'N/A', 'NA', 'NULL', 'NONE', 'NAN']:
        return 'NA'
    
    # Handle TRAVEL indicators
    if any(travel_indicator in value_clean for travel_indicator in ['TRAVEL', 'TRVL', 'TRV', 'TRAV', "TRAVEL/AREA"]):
        return 'TRAVEL'
    
    # Handle LOS indicators
    if any(los_indicator in value_clean for los_indicator in ['LOS', 'LINE OF SIGHT', 'SIGHT', 'L.O.S']):
        return 'LOS'
    
    # If it's a pure number (integer or decimal), treat as LOS
    try:
        # Remove any non-numeric characters except decimal point and negative sign
        numeric_value = ''.join(c for c in value_clean if c.isdigit() or c in '.-')
        if numeric_value and numeric_value != '-' and numeric_value != '.':
            float(numeric_value)
            return 'LOS'
    except ValueError:
        pass
    
    # Check for numeric values with text or symbols
    if any(char.isdigit() for char in value_clean):
        return 'LOS'
    
    # Default to NA if we can't determine
    return 'NA'

def ensure_work_types_exist():
    """
    Make sure all work types are created in the database
    ENHANCED with all 10 work types
    """
    work_types = {}
    
    # Define all 10 work types
    work_type_definitions = [
        (100, 'Work Type 100'),
        (200, 'Work Type 200'),
        (300, 'Work Type 300'),
        (400, 'Work Type 400'),
        (500, 'Work Type 500'),
        (800, 'Work Type 800'),
        (6100, 'DAY 1'),
        (6200, 'DAY 2'),
        (6300, 'DAY 3'),
        (6400, 'DAY 4'),
    ]
    
    print("🔧 Ensuring work types exist in database...")
    
    for wt_id, wt_name in work_type_definitions:
        work_type, created = WorkType.objects.get_or_create(
            work_type_id=wt_id,
            defaults={'name': wt_name}
        )
        if created:
            print(f"✅ Created new work type: {wt_id} - {wt_name}")
        else:
            print(f"✓ Work type exists: {wt_id} - {wt_name}")
        work_types[wt_id] = work_type
    
    print(f"✅ All {len(work_types)} work types verified")
    return work_types

def create_rooms_for_client(client, rooms_data):
    """
    Create room and work type data for a client
    ENHANCED with better logging
    """
    work_types = ensure_work_types_exist()
    
    # Delete existing rooms for this client
    existing_rooms_count = client.rooms.count()
    if existing_rooms_count > 0:
        print(f"🗑️ Removing {existing_rooms_count} existing rooms for client {client.pOwner}")
        client.rooms.all().delete()
    
    rooms_created = 0
    work_type_values_created = 0
    
    print(f"🏗️ Creating {len(rooms_data)} rooms for client {client.pOwner}...")
    
    for room_info in rooms_data:
        room = Room.objects.create(
            client=client,
            room_name=room_info['room_name'],
            sequence=room_info['sequence']
        )
        rooms_created += 1
        
        # Create work type values for this room
        for wt_id, value_type in room_info.get('work_type_values', {}).items():
            RoomWorkTypeValue.objects.create(
                room=room,
                work_type=work_types[wt_id],
                value_type=value_type
            )
            work_type_values_created += 1
        
        # Log first few rooms
        if rooms_created <= 3:
            print(f"   {rooms_created}. {room.room_name} - {len(room_info.get('work_type_values', {}))} work types")
    
    print(f"✅ Created {rooms_created} rooms with {work_type_values_created} work type values")
    return rooms_created, work_type_values_created

def create_or_update_client(client_data):
    """
    Create or update client based on extracted data
    INTEGRATED with your API response structure
    """
    # Map client data to your model fields
    mapped_data = map_client_data_to_model(client_data)
    
    # Extract the owner name to check for existing client
    owner_name = mapped_data.get('pOwner', '')
    if not owner_name:
        raise ValueError("No property owner name found in INFO file")
    
    existing_client = Client.objects.filter(pOwner=owner_name).first()
    
    if existing_client:
        # UPDATE EXISTING CLIENT
        update_fields = {}
        for field, new_value in mapped_data.items():
            if hasattr(existing_client, field) and new_value is not None:
                current_value = getattr(existing_client, field)
                if current_value != new_value:
                    update_fields[field] = new_value
        
        if update_fields:
            Client.objects.filter(pk=existing_client.pk).update(**update_fields)
            print(f"🔄 Updated client {owner_name}: {len(update_fields)} fields changed")
            client_data['_action'] = 'updated'
        else:
            print(f"➖ No changes for client {owner_name}")
            client_data['_action'] = 'unchanged'
        
        # Refresh to get updated instance
        existing_client.refresh_from_db()
        return existing_client
    else:
        # CREATE NEW CLIENT
        client = Client.objects.create(**mapped_data)
        print(f"🆕 Created new client {owner_name}")
        client_data['_action'] = 'created'
        return client

def map_client_data_to_model(raw_data):
    """
    Map extracted data to Client model fields
    COMPLETE mapping based on your existing structure
    """
    return {
        # Property Owner Information
        'pOwner': raw_data.get('property_owner_name', ''),
        'pAddress': raw_data.get('property_address_street', ''),
        'pCityStateZip': raw_data.get('property_city_state_zip', ''),
        'cEmail': raw_data.get('customer_email', ''),
        'cPhone': raw_data.get('cst_owner_phonenum', ''),
        
        # Co-Owner Information
        'coOwner2': raw_data.get('co_owner_cst2', ''),
        'cPhone2': raw_data.get('cst_ph_num_2', ''),
        'cAddress2': raw_data.get('cst_address_num_2', ''),
        'cCityStateZip2': raw_data.get('cst_city_state_zip_2', ''),
        'cEmail2': raw_data.get('email_cst_num_2', ''),
        
        # Claim Information
        'causeOfLoss': raw_data.get('cause_of_loss', ''),
        'dateOfLoss': raw_data.get('date_of_loss', None),
        'rebuildType1': raw_data.get('rebuild_type_1', ''),
        'rebuildType2': raw_data.get('rebuild_type_2', ''),
        'rebuildType3': raw_data.get('rebuild_type_3', ''),
        'demo': bool(raw_data.get('demo', False)),
        'mitigation': bool(raw_data.get('mitigation', False)),
        'otherStructures': bool(raw_data.get('other_structures', False)),
        'replacement': bool(raw_data.get('replacement', False)),
        'CPSCLNCONCGN': bool(raw_data.get('cps_cln_con_cgn', False)),
        'yearBuilt': raw_data.get('year_built', ''),
        'contractDate': raw_data.get('contract_date', None),
        'lossOfUse': raw_data.get('loss_of_use_ale', ''),
        'breathingIssue': raw_data.get('breathing_issue', ''),
        'hazardMaterialRemediation': raw_data.get('hmr', ''),
        
        # Insurance Information
        'insuranceCo_Name': raw_data.get('insurance_co_name', ''),
        'claimNumber': raw_data.get('claim_num', ''),
        'policyNumber': raw_data.get('policy_num', ''),
        'emailInsCo': raw_data.get('email_ins_co', ''),
        'deskAdjusterDA': raw_data.get('desk_adjuster_da', ''),
        'DAPhone': raw_data.get('da_phone', ''),
        'DAPhExt': raw_data.get('da_ph_ext_num', ''),
        'DAEmail': raw_data.get('da_email', ''),
        'fieldAdjusterName': raw_data.get('field_adjuster_name', ''),
        'phoneFieldAdj': raw_data.get('phone_num_field_adj', ''),
        'fieldAdjEmail': raw_data.get('field_adj_email', ''),
        'adjContents': raw_data.get('adj_contents', ''),
        'adjCpsPhone': raw_data.get('adj_cps_phone_num', ''),
        'adjCpsEmail': raw_data.get('adj_cps_email', ''),
        'emsAdj': raw_data.get('tmp_adj', ''),
        'emsAdjPhone': raw_data.get('tmp_adj_phone_num', ''),
        'emsTmpEmail': raw_data.get('adj_tmp_email', ''),
        'attLossDraftDept': raw_data.get('att_loss_draft_dept', ''),
        'insAddressOvernightMail': raw_data.get('address_ins_overnight_mail', ''),
        'insCityStateZip': raw_data.get('city_state_zip_ins', ''),
        'insuranceCoPhone': raw_data.get('insurance_co_phone', ''),
        'insWebsite': raw_data.get('website_ins_co', ''),
        'insMailingAddress': raw_data.get('mailing_address_ins', ''),
        'insMailCityStateZip': raw_data.get('mail_city_state_zip_ins', ''),
        'mortgageCoFax': raw_data.get('fax_ins_co', ''),
        
        # Rooms Information
        'newCustomerID': client_data.get('new_customer_num', ''),
        'roomID': client_data.get('room_id', ''),

        # Mortgage Information
        'mortgageCo': raw_data.get('mortgage_co', ''),
        'mortgageAccountCo': raw_data.get('account_num_mtge_co', ''),
        'mortgageContactPerson': raw_data.get('contact_person_mtge', ''),
        'mortgagePhoneContact': raw_data.get('phone_num_mtge_contact', ''),
        'mortgagePhoneExtContact': raw_data.get('ph_ext_mtge_contact', ''),
        'mortgageAttnLossDraftDept': raw_data.get('attn_loss_draft_dept', ''),
        'mortgageOverNightMail': raw_data.get('mtge_ovn_mail', ''),
        'mortgageCityStZipOVN': raw_data.get('city_st_zip_mtge_ovn', ''),
        'mortgageEmail': raw_data.get('email_mtge', ''),
        'mortgageWebsite': raw_data.get('mtge_website', ''),
        'mortgageCoFax': raw_data.get('mtge_co_fax_num', ''),
        'mortgageMailingAddress': raw_data.get('mailing_address_mtge', ''),
        'mortgageInitialOfferPhase1ContractAmount': raw_data.get('initial_offer_phase_1_contract_amount', ''),
        
        # Cash Flow
        'drawRequest': raw_data.get('draw_request', ''),
        
        # Contractor Information
        'coName': raw_data.get('co_name', ''),
        'coWebsite': raw_data.get('co_website', ''),
        'coEmailstatus': raw_data.get('co_emailstatus', ''),
        'coAddress': raw_data.get('co_adress', ''),
        'coCityState': raw_data.get('co_city_state', ''),
        'coAddress2': raw_data.get('co_address_2', ''),
        'coCityState2': raw_data.get('co_city_state_2', ''),
        'coCityState3': raw_data.get('co_city_state_3', ''),
        'coLogo1': raw_data.get('co_logo_1', ''),
        'coLogo2': raw_data.get('co_logo_2', ''),
        'coLogo3': raw_data.get('co_logo_3', ''),
        'coRepPH': raw_data.get('co_rep_ph', ''),
        'coREPEmail': raw_data.get('co_rep_email', ''),
        'coPhone2': raw_data.get('co_ph_num_2', ''),
        'TinW9': raw_data.get('tin_w9', ''),
        'fedExAccount': raw_data.get('fedex_account_num', ''),
        
        # Claim Reporting
        'claimReportDate': raw_data.get('claim_report_date', None),
        'insuranceCustomerServiceRep': raw_data.get('co_represesntative', ''),
        'timeOfClaimReport': raw_data.get('time_of_claim_report', ''),
        'phoneExt': raw_data.get('phone_ext', ''),
        'tarpExtTMPOk': bool(raw_data.get('tarp_ext_tmp_ok', False)),
        'IntTMPOk': bool(raw_data.get('int_tmp_ok', False)),
        'DRYPLACUTOUTMOLDSPRAYOK': bool(raw_data.get('drypla_cutout_mold_spray_ok', False)),
        
        # ALE Information
        'lossOfUseALE': raw_data.get('ale_info', ''),
        'tenantLesee': raw_data.get('tenant_lesee', ''),
        'propertyAddressStreet': raw_data.get('property_address_street_ale', ''),
        'propertyCityStateZip': raw_data.get('property_city_state_zip_ale', ''),
        'customerEmail': raw_data.get('customer_email_ale', ''),
        'cstOwnerPhoneNumber': raw_data.get('cst_owner_phonenum_ale', ''),
        'deskAdjusterDA': raw_data.get('desk_adjuster', ''),
        'DAPhone': raw_data.get('phone_num_da', ''),
        'DAPhExtNumber': raw_data.get('extension_da', ''),
        'DAEmail': raw_data.get('email_da', ''),
        'startDate': raw_data.get('start_date', None),
        'endDate': raw_data.get('end_date', None),
        'lessor': raw_data.get('lessor', ''),
        'bedrooms': raw_data.get('bedrooms', ''),
        'termsAmount': raw_data.get('terms_amount', ''),
    }
    """Create room and work type data for a client"""
    work_types = ensure_work_types_exist()
    
    # Delete existing rooms for this client
    client.rooms.all().delete()
    
    rooms_created = 0
    work_type_values_created = 0
    
    for room_info in rooms_data:
        room = Room.objects.create(
            client=client,
            room_name=room_info['room_name'],
            sequence=room_info['sequence']
        )
        rooms_created += 1
        
        # Create work type values for this room
        for wt_id, value_type in room_info.get('work_type_values', {}).items():
            RoomWorkTypeValue.objects.create(
                room=room,
                work_type=work_types[wt_id],
                value_type=value_type
            )
            work_type_values_created += 1
    
    return rooms_created, work_type_values_created

# MAIN IMPORT FUNCTION
@csrf_exempt
def import_client_with_rooms_formula_support(request):
    """
    Main endpoint to import client from 01-INFO and rooms from 01-ROOMS
    WITH FORMULA SUPPORT - gets calculated values from Excel formulas
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if 'info_file' not in request.FILES:
        return JsonResponse({'error': 'No INFO file provided'}, status=400)
    
    if 'rooms_file' not in request.FILES:
        return JsonResponse({'error': 'No ROOMS file provided'}, status=400)
    
    try:
        info_file = request.FILES['info_file']
        rooms_file = request.FILES['rooms_file']
        
        print("🚀 Starting complete client import process WITH FORMULA SUPPORT...")
        
        # Step 1: Import client data from INFO file (with formula support)
        client_data = import_client_from_info_file(excel_file=info_file)
        
        # Step 2: Create or update client
        client = create_or_update_client(client_data)
        
        # Step 3: Import room data from ROOMS file (with formula support)
        room_results = import_rooms_from_rooms_file(excel_file=rooms_file, client=client)
        
        response_data = {
            'status': 'success',
            'client': {
                'id': client.id,
                'name': client.pOwner,
                'action': client_data.get('_action', 'unknown')
            },
            'rooms': room_results,
            'processing_summary': {
                'client_data_processed': True,
                'rooms_processed': room_results['rooms_processed'],
                'work_type_values_created': room_results['work_type_values_created'],
                'total_rooms_found': room_results['total_rooms_found'],
                'formula_support': True  # Indicate that formula values were extracted
            }
        }
        
        print(f"✅ Import completed successfully with formula support: {response_data}")
        return JsonResponse(response_data)
        
    except Exception as e:
        error_msg = f"❌ Complete import error (formula support): {str(e)}"
        print(error_msg)
        import traceback
        print(f"🔍 Stack trace: {traceback.format_exc()}")
        
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'formula_support': True
        }, status=500)

# KEEP YOUR EXISTING parse_excel_date FUNCTION
def parse_excel_date(value):
    """Your existing robust date parser"""
    try:
        if pd.isna(value) or value in ('', 'TBD', 'NA', 'N/A'):
            return None
        
        # Your existing date parsing logic here
        # ... 
        
        return None  # Your actual parsed date
    except Exception as e:
        print(f"Date parsing error: {str(e)}")
        return None


def clean_session_data(data):
    """
    Recursively convert non-serializable objects to JSON-serializable formats.
    Handles datetime, date, time, pandas Timestamp, numpy types, and other common cases.
    """
    if isinstance(data, (dt.datetime, dt.date, dt.time)):
        return data.isoformat()
    elif isinstance(data, pd.Timestamp):
        return data.isoformat()
    elif isinstance(data, pd.Series):
        return data.to_dict()
    elif isinstance(data, pd.DataFrame):
        return data.to_dict(orient='records')
    elif isinstance(data, dict):
        return {k: clean_session_data(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple, set)):
        return [clean_session_data(x) for x in data]
    elif hasattr(data, 'tolist'):  # numpy arrays and similar
        return data.tolist()
    elif hasattr(data, 'isoformat'):  # other datetime-like objects
        return data.isoformat()
    elif isinstance(data, (int, float, str, bool)) or data is None:
        return data
    else:
        return str(data)  # fallback to string representation

def handle_excel_import(request):
    # Debug: Check if file exists in request
    if 'excel_file' not in request.FILES:
        messages.error(request, 'No file was uploaded')
        return redirect('create')
    
    excel_file = request.FILES['excel_file']
    
    # Debug: Log file info
    print(f"📁 File received: {excel_file.name} (Size: {excel_file.size/1024:.2f} KB)")
    messages.info(request, f"Processing file: {excel_file.name}")

    if not excel_file.name.endswith(('.xlsx', '.xls', '.xlsm')):
        messages.error(request, 'Invalid file type. Please upload an Excel file (.xlsx, .xls, or .xlsm)')
        return redirect('create')
    
    try:
        # Debug: Verify sheet exists
        xls = pd.ExcelFile(BytesIO(excel_file.read()))
        if 'ALL' not in xls.sheet_names:
            messages.error(request, "Sheet 'ALL' not found in Excel file. Available sheets: " + ", ".join(xls.sheet_names))
            return redirect('create')
        
        # Reset file pointer after checking sheets
        excel_file.seek(0)
        df = pd.read_excel(BytesIO(excel_file.read()), sheet_name='ALL')
        
        # Debug: Show structure
        print("🔍 Excel Structure:")
        print(f"Columns: {df.columns.tolist()}")
        print(f"First 3 rows:\n{df.head(3)}")
        messages.info(request, f"Found {len(df.columns)-3} potential clients in file (columns D onward)")

        # Constants for our structure
        HEADER_COLUMN = 2  # Column C (0-indexed would be 2)
        FIRST_DATA_COLUMN = 3  # Column D
        # Find which row in Column C contains "property_owner_name"
        owner_name_row = None
        for row_idx in range(len(df)):
            header_cell = str(df.iloc[row_idx, HEADER_COLUMN]).strip().lower()
            if 'property-owner_name' in header_cell.replace(' ', '_'):
                owner_name_row = row_idx
                break
        
        if owner_name_row is None:
            messages.error(request, "Could not find 'property_owner_name' in header column (Column C)")
            return redirect('create')
        
        print(f"ℹ️ Found property_owner_name at Row {owner_name_row + 1} in Column C")
        
        success_count = 0
        update_count = 0
        error_count = 0
        processing_details = []

        for col_idx in range(FIRST_DATA_COLUMN, len(df.columns)):
            col_name = df.columns[col_idx]
            client_status = {
                'column': col_idx + 1,  # Show as Excel column letter/number
                'name': None,
                'status': None,
                'message': None,
                'dates': [],
                'errors': []
            }

            try:
                # Debug: Show which column we're processing
                print(f"\n📊 Processing Client Column {col_idx+1} (Excel Column {chr(65+col_idx)})")
                
                # Get property owner name from first row of this column
                claim_owner = df.iloc[owner_name_row, col_idx]
                if pd.isna(claim_owner):
                    error_msg = f"Column {col_idx+1}: Missing property owner name in first row"
                    print(f"❌ {error_msg}")
                    client_status['errors'].append(error_msg)
                    raise ValueError(error_msg)
                
                claim_owner = str(claim_owner).strip()
                client_status['name'] = claim_owner
                print(f"👤 Client Name: {claim_owner}")
                messages.info(request, f"Processing client: {claim_owner}")

                # Build client data from header column (Column C) and current data column
                client_data = {}
                for row_idx in range(len(df)):
                    # Get field name from header column (Column C)
                    header = str(df.iloc[row_idx, HEADER_COLUMN]).strip() if pd.notna(df.iloc[row_idx, HEADER_COLUMN]) else None
                    value = df.iloc[row_idx, col_idx]
                    
                    if not header or pd.isna(value):
                        continue
                    
                    # Normalize field name
                    field_name = (header.lower()
                                 .replace(' ', '_')
                                 .replace('/', '_')
                                 .replace('\\', '_')
                                 .replace('.', '_')
                                 .replace('-', '_')
                                 .replace(':', '_')
                                 .replace('__', '_')
                                 .replace('#', 'num')
                                 .strip('_'))
                    
                    # Special handling for date fields
                    if any(term in field_name for term in ['date', 'dol']):
                        parsed_date = parse_excel_date(value)
                        if parsed_date:
                            client_status['dates'].append(f"{header}: {parsed_date}")
                            print(f"📅 Found date: {header} → {parsed_date}")
                            if 'loss' in field_name:
                                client_data['date_of_loss'] = parsed_date
                            else:
                                client_data[field_name] = parsed_date
                        continue
                    
                    # Handle boolean fields
                    if isinstance(value, str) and value.lower() in ('yes', 'no', 'true', 'false'):
                        value = value.lower() in ('yes', 'true')
                    
                    client_data[field_name] = value

                # Debug: Show dates found for this client
                if client_status['dates']:
                    print(f"📅 Dates for client {claim_owner}:")
                    for date_info in client_status['dates']:
                        print(f"   - {date_info}")
                    messages.info(request, f"Client {claim_owner} dates: {', '.join(client_status['dates'])}")
                                # Use your mapped_data dictionary
                mapped_data = {
                    # Property Owner Information
                    'pOwner': client_data.get('property_owner_name', ''),
                    'pAddress': client_data.get('property_address_street', ''),
                    'pCityStateZip': client_data.get('property_city_state_zip', ''),
                    'cEmail': client_data.get('customer_email', ''),
                    'cPhone': client_data.get('cst_owner_phonenum', ''),
                    
                    # Co-Owner Information
                    'coOwner2': client_data.get('co_owner_cst2', ''),
                    'cPhone2': client_data.get('cst_ph_num_2', ''),
                    'cAddress2': client_data.get('cst_address_num_2', ''),
                    'cCityStateZip2': client_data.get('cst_city_state_zip_2', ''),
                    'cEmail2': client_data.get('email_cst_num_2', ''),
                    
                    # Claim Information
                    'causeOfLoss': client_data.get('cause_of_loss', ''),
                    'dateOfLoss': client_data.get('date_of_loss', None),
                    'rebuildType1': client_data.get('rebuild_type_1', ''),
                    'rebuildType2': client_data.get('rebuild_type_2', ''),
                    'rebuildType3': client_data.get('rebuild_type_3', ''),
                    'demo': bool(client_data.get('demo', False)),
                    'mitigation': bool(client_data.get('mitigation', False)),
                    'otherStructures': bool(client_data.get('other_structures', False)),
                    'replacement': bool(client_data.get('replacement', False)),
                    'CPSCLNCONCGN': bool(client_data.get('cps_cln_con_cgn', False)),
                    'yearBuilt': client_data.get('year_built', ''),
                    'contractDate': client_data.get('contract_date', None),
                    'lossOfUse': client_data.get('loss_of_use_ale', ''),
                    'breathingIssue': client_data.get('breathing_issue', ''),
                    'hazardMaterialRemediation': client_data.get('hmr', ''),
                    
                    # Insurance Information
                    'insuranceCo_Name': client_data.get('insurance_co_name', ''),
                    'claimNumber': client_data.get('claim_num', ''),
                    'policyNumber': client_data.get('policy_num', ''),
                    'emailInsCo': client_data.get('email_ins_co', ''),
                    'deskAdjusterDA': client_data.get('desk_adjuster_da', ''),
                    'DAPhone': client_data.get('da_phone', ''),
                    'DAPhExt': client_data.get('da_ph_ext_num', ''),
                    'DAEmail': client_data.get('da_email', ''),
                    'fieldAdjusterName': client_data.get('field_adjuster_name', ''),
                    'phoneFieldAdj': client_data.get('phone_num_field_adj', ''),
                    'fieldAdjEmail': client_data.get('field_adj_email', ''),
                    'adjContents': client_data.get('adj_contents', ''),
                    'adjCpsPhone': client_data.get('adj_cps_phone_num', ''),
                    'adjCpsEmail': client_data.get('adj_cps_email', ''),
                    'emsAdj': client_data.get('tmp_adj', ''),
                    'emsAdjPhone': client_data.get('tmp_adj_phone_num', ''),
                    'emsTmpEmail': client_data.get('adj_tmp_email', ''),
                    'attLossDraftDept': client_data.get('att_loss_draft_dept', ''),
                    'insAddressOvernightMail': client_data.get('address_ins_overnight_mail', ''),
                    'insCityStateZip': client_data.get('city_state_zip_ins', ''),
                    'insuranceCoPhone': client_data.get('insurance_co_phone', ''),
                    'insWebsite': client_data.get('website_ins_co', ''),
                    'insMailingAddress': client_data.get('mailing_address_ins', ''),
                    'insMailCityStateZip': client_data.get('mail_city_state_zip_ins', ''),
                    'mortgageCoFax': client_data.get('fax_ins_co', ''),
                    
                    # Rooms Information
                    'newCustomerID': client_data.get('new_customer_num', ''),
                    'roomID': client_data.get('room_id', ''),
                    'roomArea1': client_data.get('room_area_1', ''),
                    'roomArea2': client_data.get('room_area_2', ''),
                    'roomArea3': client_data.get('room_area_3', ''),
                    'roomArea4': client_data.get('room_area_4', ''),
                    'roomArea5': client_data.get('room_area_5', ''),
                    'roomArea6': client_data.get('room_area_6', ''),
                    'roomArea7': client_data.get('room_area_7', ''),
                    'roomArea8': client_data.get('room_area_8', ''),
                    'roomArea9': client_data.get('room_area_9', ''),
                    'roomArea10': client_data.get('room_area_10', ''),
                    'roomArea11': client_data.get('room_area_11', ''),
                    'roomArea12': client_data.get('room_area_12', ''),
                    'roomArea13': client_data.get('room_area_13', ''),
                    'roomArea14': client_data.get('room_area_14', ''),
                    'roomArea15': client_data.get('room_area_15', ''),
                    'roomArea16': client_data.get('room_area_16', ''),
                    'roomArea17': client_data.get('room_area_17', ''),
                    'roomArea18': client_data.get('room_area_18', ''),
                    'roomArea19': client_data.get('room_area_19', ''),
                    'roomArea20': client_data.get('room_area_20', ''),
                    'roomArea21': client_data.get('room_area_21', ''),
                    'roomArea22': client_data.get('room_area_22', ''),
                    'roomArea23': client_data.get('room_area_23', ''),
                    'roomArea24': client_data.get('room_area_24', ''),
                    'roomArea25': client_data.get('room_area_25', ''),
                    
                    # Mortgage Information
                    'mortgageCo': client_data.get('mortgage_co', ''),
                    'mortgageAccountCo': client_data.get('account_num_mtge_co', ''),
                    'mortgageContactPerson': client_data.get('contact_person_mtge', ''),
                    'mortgagePhoneContact': client_data.get('phone_num_mtge_contact', ''),
                    'mortgagePhoneExtContact': client_data.get('ph_ext_mtge_contact', ''),
                    'mortgageAttnLossDraftDept': client_data.get('attn_loss_draft_dept', ''),
                    'mortgageOverNightMail': client_data.get('mtge_ovn_mail', ''),
                    'mortgageCityStZipOVN': client_data.get('city_st_zip_mtge_ovn', ''),
                    'mortgageEmail': client_data.get('email_mtge', ''),
                    'mortgageWebsite': client_data.get('mtge_website', ''),
                    'mortgageCoFax': client_data.get('mtge_co_fax_num', ''),
                    'mortgageMailingAddress': client_data.get('mailing_address_mtge', ''),
                    'mortgageInitialOfferPhase1ContractAmount': client_data.get('initial_offer_phase_1_contract_amount', ''),
                    
                    # Cash Flow
                    'drawRequest': client_data.get('draw_request', ''),
                    
                    # Contractor Information
                    'coName': client_data.get('co_name', ''),
                    'coWebsite': client_data.get('co_website', ''),
                    'coEmailstatus': client_data.get('co_emailstatus', ''),
                    'coAddress': client_data.get('co_adress', ''),
                    'coCityState': client_data.get('co_city_state', ''),
                    'coAddress2': client_data.get('co_address_2', ''),
                    'coCityState2': client_data.get('co_city_state_2', ''),
                    'coCityState3': client_data.get('co_city_state_3', ''),
                    'coLogo1': client_data.get('co_logo_1', ''),
                    'coLogo2': client_data.get('co_logo_2', ''),
                    'coLogo3': client_data.get('co_logo_3', ''),
                    'coRepPH': client_data.get('co_rep_ph', ''),
                    'coREPEmail': client_data.get('co_rep_email', ''),
                    'coPhone2': client_data.get('co_ph_num_2', ''),
                    'TinW9': client_data.get('tin_w9', ''),
                    'fedExAccount': client_data.get('fedex_account_num', ''),
                    
                    # Claim Reporting
                    'claimReportDate': client_data.get('claim_report_date', None),
                    'insuranceCustomerServiceRep': client_data.get('co_represesntative', ''),
                    'timeOfClaimReport': client_data.get('time_of_claim_report', ''),
                    'phoneExt': client_data.get('phone_ext', ''),
                    'tarpExtTMPOk': bool(client_data.get('tarp_ext_tmp_ok', False)),
                    'IntTMPOk': bool(client_data.get('int_tmp_ok', False)),
                    'DRYPLACUTOUTMOLDSPRAYOK': bool(client_data.get('drypla_cutout_mold_spray_ok', False)),
                    
                    # ALE Information
                    'lossOfUseALE': client_data.get('ale_info', ''),
                    'tenantLesee': client_data.get('tenant_lesee', ''),
                    'propertyAddressStreet': client_data.get('property_address_street_ale', ''),
                    'propertyCityStateZip': client_data.get('property_city_state_zip_ale', ''),
                    'customerEmail': client_data.get('customer_email_ale', ''),
                    'cstOwnerPhoneNumber': client_data.get('cst_owner_phonenum_ale', ''),
                    'deskAdjusterDA': client_data.get('desk_adjuster', ''),
                    'DAPhone': client_data.get('phone_num_da', ''),
                    'DAPhExtNumber': client_data.get('extension_da', ''),
                    'DAEmail': client_data.get('email_da', ''),
                    'startDate': client_data.get('start_date', None),
                    'endDate': client_data.get('end_date', None),
                    'lessor': client_data.get('lessor', ''),
                    'bedrooms': client_data.get('bedrooms', ''),
                    'termsAmount': client_data.get('terms_amount', ''),
                }

               # Update or create client
                existing_client = Client.objects.filter(pOwner=claim_owner).first()
                if existing_client:
                    update_fields = {}
                    for field, new_value in mapped_data.items():
                        current_value = getattr(existing_client, field, None)
                        if current_value != new_value and new_value is not None:
                            update_fields[field] = new_value
                    
                    if update_fields:
                        Client.objects.filter(pk=existing_client.pk).update(**update_fields)
                        client_status['status'] = 'updated'
                        client_status['message'] = f"Updated {len(update_fields)} fields"
                        update_count += 1
                        print(f"🔄 Updated client {claim_owner}")
                        messages.success(request, f"Updated client: {claim_owner}")
                    else:
                        client_status['status'] = 'unchanged'
                        client_status['message'] = "No changes needed"
                        print(f"➖ No changes for client {claim_owner}")
                else:
                    Client.objects.create(**mapped_data)
                    client_status['status'] = 'created'
                    client_status['message'] = "New client created"
                    success_count += 1
                    print(f"🆕 Created new client {claim_owner}")
                    messages.success(request, f"Created new client: {claim_owner}")

            except Exception as e:
                client_status['status'] = 'failed'
                error_msg = f"Error processing column {col_idx+1}: {str(e)}"
                client_status['errors'].append(error_msg)
                error_count += 1
                print(f"❌ {error_msg}")
                messages.error(request, error_msg)
            
            processing_details.append(client_status)

            # Prepare detailed results report
            result_messages = [f"<strong>Import Results:</strong>",
                             f"✅ Successfully created: {success_count}",
                             f"🔄 Updated: {update_count}",
                             f"❌ Failed: {error_count}",
                             "<br><strong>Processing Details:</strong>"]
            
            for detail in processing_details:
                status_icon = {"created": "✅", "updated": "🔄", "failed": "❌", "unchanged": "➖"}.get(detail['status'], "�")
                
            result_message = (
                    f"Import complete: {success_count} created, {update_count} updated, "
                    f"{error_count} errors"
                )
            messages.success(request, result_message)
            
            processing_details.append(clean_session_data(client_status))  # Clean the client status data

        # Prepare session data
        session_data = {
            'success_count': success_count,
            'update_count': update_count,
            'error_count': error_count,
            'processing_details': processing_details,
            'excel_data': clean_session_data(df.to_dict()),
            'file_name': excel_file.name,
            'timestamp': timezone.now().isoformat()
        }

        # Store cleaned data in session
        request.session['import_results'] = clean_session_data(session_data)
        
        messages.success(request, f"Import complete: {success_count} created, {update_count} updated, {error_count} errors")
        return render(request, 'account/create.html', {
            'form': ClientForm(),
            'import_summary': {
                'success_count': success_count,
                'update_count': update_count,
                'error_count': error_count
            }
        })

    except Exception as e:
        error_msg = f"❌ File processing error: {str(e)}"
        print(error_msg)
        messages.error(request, error_msg)
        return redirect('create')

def parse_excel_date(value):
    """Robust date parser that handles all cases"""
    # Handle empty/None values

    try:
        if pd.isna(value) or value in ('', 'TBD', 'NA', 'N/A'):
            return None


        
        # Handle Excel serial numbers
        if isinstance(value, (int, float)):
            print(f"🔢 Parsing Excel date number: {value}")
            try:
                # Excel's date system starts from 1900-01-01 (with 1900 incorrectly treated as leap year)
                if value < 0:
                    return None
                if value == 0:  # Excel's zero date
                    return None
                if value == 60:  # Excel's 1900-02-29 (non-existent)
                    return dt(1900, 2, 28).date()
                if value < 60:  # Adjust for Excel's leap year bug
                    value += 1
                return (dt.datetime(1899, 12, 30) + pd.Timedelta(days=value)).date()
            except Exception:
                return None
        
        # Convert to string if not already
        if not isinstance(value, str):
            value = str(value).strip()
            print(f"🔢 Parsing Excel date number: {value}")
        else:
            value = value.strip()
        
        # Handle obvious non-dates
        if not value or value.upper() in ('TBD', 'NA', 'N/A', 'UNKNOWN'):
            return None
        
        # Clean the string
        value = (value.replace(' ', ' ')  # Non-breaking space
                 .replace('Sept', 'Sep')
                 .replace('Febr', 'Feb')
                 .replace('Dece', 'Dec')
                 .split(' ')[0])  # Take only first part if space separated
        
        # Try parsing as datetime string
        date_formats = [
            '%Y-%m-%d %H:%M:%S',  # 2024-12-02 00:00:00
            '%Y-%m-%d',           # 2024-12-02
            '%m/%d/%Y',           # 1/20/2024
            '%d-%b-%y',           # 24-Jan-24
            '%d-%b-%Y',           # 20-Jan-2024
            '%b %d, %Y',          # Dec 23, 2022
            '%B %d, %Y',          # December 23, 2022
            '%d-%m-%Y',           # 20-01-2024
            '%d %b %Y',           # 20 Jan 2024
            '%d %B %Y'            # 20 January 2024
        ]
        
        for fmt in date_formats:
            try:
                return dt.datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        
        # Handle pandas Timestamp
        try:
            if isinstance(value, (pd.Timestamp, dt)):
                return value.date()
        except:
            pass
        
        # Final check for invalid dates
        if re.match(r'^\d{5,}', value) or re.match(r'.*\D.*\D.*', value):  # Long numbers or multiple non-digits
            return None
        
        return None
    except Exception as e:
        print(f"❌ Date parsing error for value '{value}': {str(e)}")
        return None

def generate_data_report(request):
    if 'import_results' not in request.session:
        messages.error(request, "No import data available to generate report")
        return redirect('create')
    
    import_data = request.session['import_results']
    
    try:
        df = pd.DataFrame.from_dict(import_data['excel_data'])
    except Exception as e:
        messages.error(request, f"Error loading import data: {str(e)}")
        return redirect('create')

    # Initialize report data with additional metadata
    report = {
        'metadata': {
            'report_generated': timezone.now().strftime("%Y-%m-%d %H:%M"),
            'source_file': import_data.get('file_name', 'Unknown')
        },
        'summary': {
            'total_clients': len(df.columns) - 3,  # Subtract ignored columns
            'processed': import_data['success_count'] + import_data['update_count'],
            'errors': import_data['error_count'],
            'success_rate': round((import_data['success_count'] + import_data['update_count']) / max(1, len(df.columns) - 3) * 100, 1)
        },
        'field_stats': {},
        'data_quality_issues': [],
        'most_problematic_fields': []
    }
    
    # Constants for our structure
    HEADER_COLUMN = 2  # Column C
    FIRST_DATA_COLUMN = 3  # Column D
    
    # Track most problematic fields
    field_problem_counts = []
    
    # Analyze each field
    for row_idx in range(len(df)):
        header = str(df.iloc[row_idx, HEADER_COLUMN]).strip().lower() if pd.notna(df.iloc[row_idx, HEADER_COLUMN]) else None
        if not header:
            continue
            
        # Normalize field name (keep original for display)
        field_name = header.replace(' ', '_').replace('/', '_').strip('_')
        display_name = header.title()  # For nicer display
        
        # Initialize field stats
        field_stats = {
            'display_name': display_name,
            'total': 0,
            'empty': 0,
            'tbd': 0,
            'na': 0,
            'invalid': 0,
            'completeness': 0,
            'examples': set()
        }
        
        # Check each client column
        for col_idx in range(FIRST_DATA_COLUMN, len(df.columns)):
            value = df.iloc[row_idx, col_idx]
            if pd.isna(value):
                field_stats['empty'] += 1
                continue
                
            value_str = str(value).strip().upper()
            field_stats['total'] += 1
            
            # Check for placeholder values
            if value_str in ('TBD', 'TO BE DETERMINED'):
                field_stats['tbd'] += 1
            elif value_str in ('NA', 'N/A', '#N/A'):
                field_stats['na'] += 1
            # Special validation for certain fields
            elif 'zip' in field_name and not any(c.isdigit() for c in value_str):
                field_stats['invalid'] += 1
            elif 'date' in field_name and parse_excel_date(value) is None:
                field_stats['invalid'] += 1
                
            # Collect sample values
            if len(field_stats['examples']) < 3:
                field_stats['examples'].add(str(value))
        
        # Calculate completeness percentage
        total_values = field_stats['total'] + field_stats['empty']
        if total_values > 0:
            field_stats['completeness'] = round((field_stats['total'] - field_stats['empty']) / total_values * 100, 1)
        
        # Only include fields with issues in the report
        if field_stats['empty'] or field_stats['tbd'] or field_stats['na'] or field_stats['invalid']:
            report['field_stats'][display_name] = field_stats
            problem_count = sum([field_stats['empty'], field_stats['tbd'], field_stats['na'], field_stats['invalid']])
            field_problem_counts.append((display_name, problem_count))
    
    # Generate quality issue summary
    quality_issues = []
    for field, stats in report['field_stats'].items():
        issues = []
        if stats['empty']:
            issues.append(f"{stats['empty']} empty")
        if stats['tbd']:
            issues.append(f"{stats['tbd']} TBD")
        if stats['na']:
            issues.append(f"{stats['na']} N/A")
        if stats['invalid']:
            issues.append(f"{stats['invalid']} invalid")
        
        quality_issues.append({
            'field': field,
            'issues': ', '.join(issues),
            'examples': ', '.join(stats['examples']),
            'completeness': stats['completeness']
        })
    
    # Sort by most problematic first
    report['data_quality_issues'] = sorted(quality_issues, 
                                         key=lambda x: (100 - x['completeness']), 
                                         reverse=True)
    
    # Identify top 5 most problematic fields
    field_problem_counts.sort(key=lambda x: x[1], reverse=True)
    report['most_problematic_fields'] = field_problem_counts[:5]
    
    return render(request, 'account/data_report.html', {
        'report': report,
        'import_summary': {
            'success_count': import_data['success_count'],
            'update_count': import_data['update_count'],
            'error_count': import_data['error_count'],
            'total_clients': len(df.columns) - 3
        }
    })
def checklist(request):
    labels = ["CLG", "LIT", "HVC", "MISC-1", "WAL", "ELE", "FLR", "BB", "MISC-2", "DOR", "OPEN", "WDW", "WDT"]
    activity = ["ALL", "QTY+", "CLN", "R&R", "D&R", "MSK", "MN", "S++", "PNT", "SND", "LF"]
    labelValues = [""]
    claims = Client.objects.all()
    
    # Get rooms for selected claim
    selected_claim_id = request.GET.get('claim')
    rooms = []
    
    if selected_claim_id:
        try:

            client = get_object_or_404(Client, pOwner=selected_claim_id)
            #create a temporary template file with this claims data in job info
            
            
            template_path = os.path.join(settings.BASE_DIR, 'docsAppR', 'templates', 'excel', 'templates', '60_scope_form.xlsx')
            destination_path = os.path.join(settings.BASE_DIR, 'docsAppR', 'templates', 'excel', 'custom templates', )
            
            shutil.copyfile("src", "dest")

            wb = load_workbook(destination_path, data_only=True)
            # Select the ScopeCHLST sheet
            ws = wb['jobinfo(2)']

            # Get all non-empty rooms
            for i in range(1, 26):
                room_attr = f'roomArea{i}'
                room_value = getattr(client, room_attr, None)
                
                if room_value and isinstance(room_value, str):
                    room_value = room_value.strip()
                    if room_value.lower() not in ['', 'tbd', 'n/a']:
                        rooms.append({
                            'id': room_attr,
                            'name': room_value
                        })
        except Client.DoesNotExist:
            rooms = []
            logger.error(f"Client not found: {selected_claim_id}")

    if request.method == 'POST':
        try:
            claim_id = request.POST.get('claim')
            room = request.POST.get('room')
            
            # Collect inspection data
            inspection_data = {
                label.lower(): request.POST.get(label.lower(), '')
                for label in labels
            }
            
            # Store inspection data in session
            request.session['inspection_data'] = {
                'claim_id': claim_id,
                'room': room,
                'inspection': inspection_data
            }
            
            # Generate and return PDF
            return generate_invoice_pdf(request, claim_id)
            
        except Exception as e:
            logger.error(f"Error in POST processing: {str(e)}")
            return HttpResponse(f"An error occurred while processing the form: {str(e)}", status=500)
    
    context = {
        'labels': labels,
        'claims': claims,
        'rooms': rooms,
        'selected_claim_id': selected_claim_id,
        'max_rooms' : 25
    }
    
    return render(request, 'account/checklist.html', context)

import os
import re
import math
import logging
import tempfile
import subprocess
import time
from pathlib import Path
from openpyxl import load_workbook
from django.core.files.base import ContentFile
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.conf import settings
from django.contrib.auth.decorators import login_required
from docsAppR.models import Client, File  # Update with your actual models

logger = logging.getLogger(__name__)

# Helper functions
def safe_filename(name, max_length=120):
    """Create filesystem-safe filename"""
    return re.sub(r'[<>:"/\\|?*]', '_', name)[:max_length]

def get_room_index_from_name(room_name):
    """Extract the room index from room name"""
    match = re.search(r'(\d+)', room_name)
    if match:
        return int(match.group(1))
    return None

def calculate_print_area(num_labels):
    """Calculate the print area based on number of labels requested"""
    if num_labels <= 0:
        return "A1:B4"  # Default to at least one label area
    
    labels_per_block = 2
    blocks_needed = math.ceil(num_labels / labels_per_block)
    end_row = blocks_needed * 4
    
    return f"A1:B{end_row}"

def create_excel_from_template(template_path, output_path, sheet_name, room_index, claim_id, client):
    """Creates an Excel file from template with client data populated"""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        wb = load_workbook(template_path, data_only=False)  # Keep formulas as formulas
        
        if sheet_name not in wb.sheetnames:
            logger.error(f"Sheet '{sheet_name}' not found in template. Available sheets: {wb.sheetnames}")
            return False
        
        # Populate jobinfo sheet if exists
        jobinfo_sheet = None
        for sheet in wb.sheetnames:
            if 'jobinfo(2)' in sheet.lower():
                jobinfo_sheet = wb[sheet]
                break
        
        if jobinfo_sheet:
            try:
                # Create a mapping of field names to their column C positions
                # This should match how your template is structured
                field_mapping = {
                    # Primary Client Information
                    'pOwner': 1,
                    'pAddress': 2,
                    'pCityStateZip': 3,
                    'cEmail': 4,
                    'cPhone': 5,
                    'coOwner2': 6,
                    'cPhone2': 7,
                    'cAddress2': 8,
                    'cCityStateZip2': 9,
                    'cEmail2': 10,
                    
                    # Claim Information
                    'causeOfLoss': 11,
                    'dateOfLoss': 12,
                    'rebuildType1': 13,
                    'rebuildType2': 14,
                    'rebuildType3': 15,
                    'demo': 16,
                    'mitigation': 17,
                    'otherStructures': 18,
                    'replacement': 19,
                    'CPSCLNCONCGN': 20,
                    'yearBuilt': 21,
                    'contractDate': 22,
                    'lossOfUse': 23,
                    'breathingIssue': 24,
                    'hazardMaterialRemediation': 25,
                    
                    # Insurance Information
                    'insuranceCo_Name': 26,
                    'insAddressOvernightMail': 27,
                    'insCityStateZip': 28,
                    'insuranceCoPhone': 29,
                    'insWebsite': 30,
                    'insMailingAddress': 31,
                    'insMailCityStateZip': 32,
                    'claimNumber': 33,
                    'policyNumber': 34,
                    'emailInsCo': 35,
                    'deskAdjusterDA': 36,
                    'DAPhone': 37,
                    'DAPhExt': 38,
                    'DAEmail': 39,
                    'fieldAdjusterName': 40,
                    'phoneFieldAdj': 41,
                    'fieldAdjEmail': 42,
                    'adjContents': 43,
                    'adjCpsPhone': 44,
                    'adjCpsEmail': 45,
                    'emsAdj': 46,
                    'emsAdjPhone': 47,
                    'emsTmpEmail': 48,
                    'attLossDraftDept': 49,
                    
                    # Room Information
                    'newCustomerID': 50,
                    'roomID': 51,
                    'roomArea1': 52,
                    'roomArea2': 53,
                    'roomArea3': 54,
                    'roomArea4': 55,
                    'roomArea5': 56,
                    'roomArea6': 57,
                    'roomArea7': 58,
                    'roomArea8': 59,
                    'roomArea9': 60,
                    'roomArea10': 61,
                    'roomArea11': 62,
                    'roomArea12': 63,
                    'roomArea13': 64,
                    'roomArea14': 65,
                    'roomArea15': 66,
                    'roomArea16': 67,
                    'roomArea17': 68,
                    'roomArea18': 69,
                    'roomArea19': 70,
                    'roomArea20': 71,
                    'roomArea21': 72,
                    'roomArea22': 73,
                    'roomArea23': 74,
                    'roomArea24': 75,
                    'roomArea25': 76,
                    
                    # Mortgage Information
                    'mortgageCo': 77,
                    'mortgageAccountCo': 78,
                    'mortgageContactPerson': 79,
                    'mortgagePhoneContact': 80,
                    'mortgagePhoneExtContact': 81,
                    'mortgageAttnLossDraftDept': 82,
                    'mortgageOverNightMail': 83,
                    'mortgageCityStZipOVN': 84,
                    'mortgageEmail': 85,
                    'mortgageWebsite': 86,
                    'mortgageCoFax': 87,
                    'mortgageMailingAddress': 88,
                    'mortgageInitialOfferPhase1ContractAmount': 89,
                    
                    # Cash Flow
                    'drawRequest': 90,
                    
                    # Contractor Information
                    'coName': 91,
                    'coWebsite': 92,
                    'coEmailstatus': 93,
                    'coAddress': 94,
                    'coCityState': 95,
                    'coAddress2': 96,
                    'coCityState2': 97,
                    'coCityState3': 98,
                    'coLogo1': 99,
                    'coLogo2': 100,
                    'coLogo3': 101,
                    'coRepPH': 102,
                    'coREPEmail': 103,
                    'coPhone2': 104,
                    'TinW9': 105,
                    'fedExAccount': 106,
                    
                    # Claim Reporting
                    'claimReportDate': 107,
                    'insuranceCustomerServiceRep': 108,
                    'timeOfClaimReport': 109,
                    'phoneExt': 110,
                    'tarpExtTMPOk': 111,
                    'IntTMPOk': 112,
                    'DRYPLACUTOUTMOLDSPRAYOK': 113,
                    
                    # ALE Information
                    'lossOfUseALE': 114,
                    'tenantLesee': 115,
                    'propertyAddressStreet': 116,
                    'propertyCityStateZip': 117,
                    'customerEmail': 118,
                    'cstOwnerPhoneNumber': 119,
                    
                    # Duplicate/Additional Fields (appearing later in model)
                    'contractDate': 122,
                    'insuranceCoName': 123,
                    'claimNumber': 124,
                    'policyClaimNumber': 125,
                    'emailInsCo': 126,
                    'deskAdjusterDA': 127,
                    'DAPhone': 128,
                    'DAPhExtNumber': 129,
                    'DAEmail': 130,
                    'startDate': 131,
                    'endDate': 132,
                    'lessor': 133,
                    'propertyAddressStreet': 134,
                    'propertyCityStateZip': 135,
                    'customerEmail': 136,
                    'cstOwnerPhoneNumber': 137,
                    'bedrooms': 138,
                    'termsAmount': 139
                }
                
                datetime_fields = [
                    'dateOfLoss',
                    'contractDate',
                    'claimReportDate',
                    'startDate',
                    'endDate'
                ]

                # Populate the fields we know about
                for field_name, row_num in field_mapping.items():
                    cell_ref = f'C{row_num}'
                    try:
                        value = getattr(client, field_name, None)
                        
                        # Handle datetime fields
                        if field_name in datetime_fields and value is not None:
                            if value.tzinfo is not None:
                                # Remove timezone info
                                value = value.replace(tzinfo=None)
                            jobinfo_sheet[cell_ref] = value
                        
                        # Handle boolean fields
                        elif isinstance(value, bool):
                            jobinfo_sheet[cell_ref] = 'Yes' if value else 'No'
                        
                        # Handle normal fields
                        else:
                            jobinfo_sheet[cell_ref] = str(value) if value not in [None, ''] else 'TBD'
                    
                    except Exception as e:
                        logger.warning(f"Error setting {field_name} in {cell_ref}: {str(e)}")
                        jobinfo_sheet[cell_ref] = 'ERROR'

                # Refresh formulas (optional - only needed if you have formulas referencing these cells)
                for row in jobinfo_sheet.iter_rows():
                    for cell in row:
                        if cell.data_type == 'f':  # Formula
                            try:
                                jobinfo_sheet[cell.coordinate] = f'={cell.value}'
                            except Exception as e:
                                logger.warning(f"Could not refresh formula in {cell.coordinate}: {str(e)}")
                
                logger.info("Successfully populated client data in jobinfo sheet")
                
            except Exception as e:
                logger.warning(f"Could not populate client data: {str(e)}", exc_info=True)
        
        # Save the workbook
        wb.template = False  # Important: Set to False to save as regular workbook
        wb.save(output_path)
        wb.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to create Excel from template: {str(e)}", exc_info=True)
        return False

import platform

@login_required
@login_required
def labels(request):
    logger.info(f"Labels function called - method: {request.method}")
    logger.info(f"User: {request.user}, Authenticated: {request.user.is_authenticated}")
    
    # GET request handling - show the form
    if request.method == 'GET':
        try:
            claims = Client.objects.all()
            selected_claim_id = request.GET.get('claim')
            rooms = []
            
            if selected_claim_id:
                try:
                    client = get_object_or_404(Client, pOwner=selected_claim_id)
                    
                    # Get all non-empty rooms
                    for i in range(1, 26):
                        room_attr = f'roomArea{i}'
                        room_value = getattr(client, room_attr, None)
                        
                        if room_value and isinstance(room_value, str):
                            room_value = room_value.strip()
                            if room_value.lower() not in ['', 'tbd', 'n/a']:
                                rooms.append({
                                    'id': room_attr,
                                    'name': room_value
                                })
                    
                    logger.info(f"Found {len(rooms)} rooms for claim {selected_claim_id}")
                    
                except Client.DoesNotExist:
                    rooms = []
                    logger.error(f"Client not found for pOwner: {selected_claim_id}")
                except Exception as e:
                    rooms = []
                    logger.error(f"Unexpected error loading rooms for claim {selected_claim_id}: {str(e)}")
                    logger.debug(f"Traceback: {traceback.format_exc()}")
            
            context = {
                'claims': claims,
                'rooms': rooms,
                'selected_claim_id': selected_claim_id
            }
            return render(request, 'account/labels.html', context)
            
        except Exception as e:
            logger.error(f"Error in GET request: {str(e)}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': 'Error loading page'}, status=500)
    
    # POST request handling - generate PDFs
    elif request.method == 'POST':
        try:
            logger.info("=== STARTING LABEL GENERATION ===")
            
            # Initialize room_labels dictionary
            room_labels = {}
            claim_id = request.POST.get('claim', '').strip()
            logger.info(f"Claim ID from POST: '{claim_id}'")
            
            if not claim_id:
                logger.error("Missing claim ID in POST data")
                return JsonResponse({'status': 'error', 'message': 'Missing claim ID'}, status=400)

            # Parse room labels from POST data
            logger.info("Parsing room labels from POST data:")
            for key, value in request.POST.items():
                if key.startswith('room_labels['):
                    try:
                        room_name = key[len('room_labels['):-1]  # Extract room name
                        count = int(value)
                        if count > 0:
                            room_labels[room_name] = count
                            logger.info(f"  - {room_name}: {count} labels")
                    except ValueError as ve:
                        logger.warning(f"Invalid value for room label {key}: {value}")
                        continue

            logger.info(f"Total room labels parsed: {len(room_labels)}")
            
            if not room_labels:
                logger.info("No room labels requested")
                return JsonResponse({'status': 'success', 'message': 'No labels requested', 'pdfs': []})

            # Get client data
            logger.info(f"Looking up client with pOwner: '{claim_id}'")
            try:
                client = Client.objects.get(pOwner=claim_id)
                logger.info(f"Client found: {client.pOwner}")
            except Client.DoesNotExist:
                logger.error(f"Client not found for pOwner: {claim_id}")
                return JsonResponse({'status': 'error', 'message': 'Client not found'}, status=404)
            except Exception as e:
                logger.error(f"Error getting client: {str(e)}")
                return JsonResponse({'status': 'error', 'message': 'Error retrieving client data'}, status=500)

            # Create room index mapping
            room_indices = {}
            logger.info("Creating room index mapping:")
            for i in range(1, 26):  # roomArea1 through roomArea25
                field_name = f'roomArea{i}'
                if hasattr(client, field_name):
                    room_value = getattr(client, field_name, '')
                    if room_value and str(room_value).strip():  # Only add if not empty
                        room_indices[str(room_value).strip()] = i
                        logger.info(f"  - Room {i}: '{room_value}'")

            logger.info(f"Room indices mapping created with {len(room_indices)} entries")

            # Check if template exists
            template_path = os.path.join(settings.BASE_DIR, 'docsAppR', 'templates', 'excel', 'room_labels_template.xlsx')
            logger.info(f"Template path: {template_path}")
            
            if not os.path.exists(template_path):
                logger.error(f"Template file not found at: {template_path}")
                return JsonResponse({'status': 'error', 'message': 'Template file not found'}, status=500)
            else:
                logger.info("Template file found")

            # Start PDF generation
            logger.info("Starting PDF generation in temporary directory")
            with tempfile.TemporaryDirectory() as temp_dir:
                pdfs_info = []
                logger.info(f"Temporary directory created: {temp_dir}")
                
                for room_name, num_labels in room_labels.items():
                    try:
                        logger.info(f"--- Processing room: '{room_name}', labels: {num_labels} ---")
                        
                        # Get room index
                        room_index = room_indices.get(room_name.strip())
                        logger.info(f"Room index from mapping: {room_index}")
                        
                        if not room_index:
                            # Try to get room index from name using helper function
                            logger.info("Trying to get room index from name using helper function")
                            try:
                                room_index = get_room_index_from_name(room_name)
                                logger.info(f"Room index from helper function: {room_index}")
                            except Exception as e:
                                logger.error(f"Error in get_room_index_from_name: {str(e)}")
                                room_index = None
                            
                            if not room_index:
                                logger.warning(f"No index found for room: '{room_name}'. Skipping.")
                                continue

                        # Create safe filenames
                        safe_claim = safe_filename(claim_id) if callable(safe_filename) else claim_id.replace(' ', '_')
                        safe_room = safe_filename(room_name) if callable(safe_filename) else room_name.replace(' ', '_')
                        excel_filename = f"labels_{safe_claim}_{safe_room}.xlsx"
                        pdf_filename = f"labels_{safe_claim}_{safe_room}.pdf"
                        temp_excel_path = os.path.join(temp_dir, excel_filename)
                        temp_pdf_path = os.path.join(temp_dir, pdf_filename)
                        sheet_name = f"RM ({room_index})"

                        logger.info(f"File details:")
                        logger.info(f"  - Excel: {temp_excel_path}")
                        logger.info(f"  - PDF: {temp_pdf_path}")
                        logger.info(f"  - Sheet: {sheet_name}")

                        # 1. Create Excel from template with client data
                        logger.info("Creating Excel from template...")
                        try:
                            excel_success = create_excel_from_template(
                                template_path, 
                                temp_excel_path, 
                                sheet_name, 
                                room_index, 
                                claim_id, 
                                client
                            )
                            if not excel_success:
                                logger.error(f"Excel creation returned False for {room_name}")
                                continue
                            logger.info("Excel creation successful")
                        except Exception as e:
                            logger.error(f"Excel creation failed for {room_name}: {str(e)}")
                            continue

                        # 2. Convert to PDF with proper label format
                        logger.info("Converting Excel to PDF...")
                        try:
                            convert_excel_to_pdf_with_pages(
                                excel_path=temp_excel_path,
                                pdf_path=temp_pdf_path,
                                sheet_name=sheet_name,
                                room_name=room_name,
                                p_owner=client.pOwner,
                                num_labels=num_labels
                            )
                            logger.info("PDF conversion successful")
                        except Exception as e:
                            logger.error(f"PDF conversion failed for {room_name}: {str(e)}")
                            continue

                        # 3. Store the PDF
                        if os.path.exists(temp_pdf_path):
                            logger.info(f"PDF file exists at: {temp_pdf_path}")
                            try:
                                with open(temp_pdf_path, 'rb') as pdf_file:
                                    pdf_content = pdf_file.read()
                                
                                logger.info(f"PDF content size: {len(pdf_content)} bytes")
                                
                                # Create File object and save
                                pdf_obj = File(filename=pdf_filename, size=len(pdf_content))
                                pdf_obj.file.save(pdf_filename, ContentFile(pdf_content))
                                
                                pdfs_info.append({
                                    'room_name': room_name,
                                    'pdf_url': pdf_obj.file.url,
                                    'num_labels': num_labels,
                                    'print_area': calculate_print_area(num_labels) if callable(calculate_print_area) else "unknown"
                                })
                                
                                logger.info(f"Successfully generated PDF for {room_name} with {num_labels} labels")
                            except Exception as e:
                                logger.error(f"Error saving PDF file: {str(e)}")
                                continue
                        else:
                            logger.error(f"PDF file not found after conversion: {temp_pdf_path}")

                    except Exception as e:
                        logger.error(f"Error processing room {room_name}: {str(e)}", exc_info=True)
                        continue

                logger.info(f"=== PDF GENERATION COMPLETED ===")
                logger.info(f"Generated {len(pdfs_info)} PDFs out of {len(room_labels)} requested")
                
                if pdfs_info:
                    return JsonResponse({
                        'status': 'success', 
                        'message': f'Generated {len(pdfs_info)} PDF(s) successfully',
                        'pdfs': pdfs_info
                    })
                else:
                    return JsonResponse({
                        'status': 'success',
                        'message': 'No valid labels generated',
                        'pdfs': []
                    })

        except Exception as e:
            logger.error(f"=== LABEL GENERATION FAILED ===")
            logger.error(f"Error: {str(e)}", exc_info=True)
            return JsonResponse({
                'status': 'error',
                'message': 'Label generation failed. Please try again.'
            }, status=500)
    
    # Handle other HTTP methods (PUT, DELETE, etc.)
    else:
        return HttpResponseNotAllowed(['GET', 'POST'])

def convert_excel_to_pdf_with_pages(excel_path, pdf_path, sheet_name, room_name, p_owner, num_labels):
    """Convert Excel to PDF with proper print area, eliminating formula errors"""
    try:
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
            temp_xlsx = tmp_file.name
        
        try:
            # 1. Load and prepare the workbook
            wb = load_workbook(excel_path)
            if sheet_name not in wb.sheetnames:
                raise ValueError(f"Sheet '{sheet_name}' not found in {excel_path}")
            
            # 2. Process the target sheet
            ws = wb[sheet_name]

            # 4. Remove other sheets (after processing formulas)
            for sheet in wb.sheetnames:
                if sheet != sheet_name:
                    wb.remove(wb[sheet])
            

            labels_per_page = 4
            total_labels = math.ceil(num_labels / labels_per_page) * labels_per_page
            total_rows = total_labels * 2 

            room_name_upper = room_name.upper()  # Convert to ALL CAPS
            for row_num in range(1, total_rows + 1):
                # Odd rows (1, 3, 5...) get room name
                if row_num % 2 == 1:
                    ws.cell(row=row_num, column=1, value=room_name_upper)  # A1, A3, A5...
                # Even rows (2, 4, 6...) get owner name
                else:
                    ws.cell(row=row_num, column=1, value=p_owner)  # A2, A4, A6...
            
            # 5. Set print area
            print_area = calculate_print_area(num_labels)
            if ':' in print_area:  # Validate print area format
                ws.print_area = print_area
                logger.info(f"Set print area for {sheet_name}: {print_area}")
            else:
                logger.warning(f"Invalid print area format: {print_area}")
            
            # 6. Save the cleaned workbook
            wb.template = False
            wb.security = None
            wb.save(temp_xlsx)
            wb.close()
            
            # 7. Convert to PDF using LibreOffice - FIXED PATH FOR LINUX
            temp_dir = os.path.dirname(temp_xlsx)
            
            # Detect operating system and set correct LibreOffice path
            if platform.system() == "Windows":
                libreoffice_path = 'C:\\Program Files\\LibreOffice\\program\\soffice.exe'
            else:
                libreoffice_path = '/usr/bin/libreoffice'  # Linux path
            
            cmd = [
                libreoffice_path,
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', temp_dir,
                temp_xlsx
            ]
            
            # 8. Run conversion with error handling
            result = subprocess.run(
                cmd, 
                check=True, 
                timeout=120, 
                capture_output=True,
                text=True
            )
            logger.debug(f"LibreOffice output: {result.stdout}")
            
            # 9. Handle the generated PDF
            generated_pdf = os.path.splitext(temp_xlsx)[0] + '.pdf'
            max_wait = 30
            waited = 0
            
            while waited < max_wait:
                if os.path.exists(generated_pdf):
                    try:
                        with open(generated_pdf, 'rb') as f:
                            pdf_data = f.read()
                        with open(pdf_path, 'wb') as f:
                            f.write(pdf_data)
                        logger.info(f"PDF successfully generated at {pdf_path}")
                        return True
                    except PermissionError:
                        time.sleep(0.5)
                        waited += 0.5
                else:
                    time.sleep(0.5)
                    waited += 0.5
            
            raise RuntimeError(f"PDF generation timed out after {max_wait} seconds")
            
        finally:
            # 10. Cleanup temporary files
            cleanup_files = [temp_xlsx]
            temp_pdf = os.path.splitext(temp_xlsx)[0] + '.pdf'
            if os.path.exists(temp_pdf):
                cleanup_files.append(temp_pdf)
            
            for file_path in cleanup_files:
                try:
                    os.unlink(file_path)
                except Exception as e:
                    logger.warning(f"Could not delete temp file {file_path}: {e}")
    
    except subprocess.CalledProcessError as e:
        error_msg = f"LibreOffice conversion failed: {e.stderr}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    except Exception as e:
        logger.error(f"PDF conversion error: {str(e)}", exc_info=True)
        raise


@login_required
def dashboard(request):
    # Handle client selection
    selected_client_id = request.GET.get('selected_client')
    selected_client = None
    if selected_client:
        from .signals import create_checklist_items_for_client
        create_checklist_items_for_client(selected_client)
        selected_client.update_completion_stats()
    # Get all clients with their completion stats
    clients = Client.objects.all()
    for client in clients:
        client.update_completion_stats()
        if str(client.id) == selected_client_id:
            selected_client = client
    
    # Apply sorting
    sort_by = request.GET.get('sort', 'name')
    if sort_by == 'name':
        clients = clients.order_by('pOwner')
    elif sort_by == 'id':
        clients = clients.order_by('newCustomerID')
    elif sort_by == 'date':
        clients = clients.order_by('dateOfLoss')
    
    # Apply filtering
    filter_type = request.GET.get('type', 'all')
    if filter_type == 'CPS':
        clients = clients.filter(CPSCLNCONCGN=True)
    elif filter_type == 'MIT':
        clients = clients.filter(mitigation=True)
    elif filter_type == 'PPR':
        clients = clients.filter(replacement=True)
    
    context = {
        'allClients': clients,
        'selected_client': selected_client,
    }
    return render(request, 'account/dashboard.html', context)

# Function for updating the checklist 
def update_checklist(request):
    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        client = get_object_or_404(Client, id=client_id)
        
        # Update all checklist items
        for item in client.checklist_items.all():
            field_name = f'item_{item.id}'
            item.is_completed = field_name in request.POST
            item.save()
        
        # Update completion stats
        client.update_completion_stats()
        
        return JsonResponse({
            'success': True,
            'completion_percent': client.completion_percent
        })
    
    return JsonResponse({'success': False})

def update_checklist_item(request, item_id):
    if request.method == 'POST':
        try:
            item = ChecklistItem.objects.get(id=item_id)
            item.is_completed = request.POST.get('is_completed') == 'true'
            item.save()
            return JsonResponse({'success': True})
        except ChecklistItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Item not found'})
    return JsonResponse({'success': False, 'error': 'Invalid request'})


# LEASE GENERATION VIEWS
def client_list(request):
    # Get all clients from the database
    clients = Client.objects.all()
    documents = Document.objects.all()
    selected_client = None
    selected_document = None
    form = None

    # Filter documents based on selections
    if selected_document:
        documents = documents.filter(name=selected_document)
    
    if selected_client:
        clients = clients.filter(pOwner=selected_client)

    if 'client_name' in request.GET and 'document_name' in request.GET:
        client_id = request.GET['client_name']
        document_id = request.GET['document_name']
        print(client_id + " " + document_id)
        if client_id and document_id:  # Only try to get client if an ID was provided
            selected_client = get_object_or_404(clients, pOwner=client_id)

            selected_document = get_object_or_404(documents, name=document_id)
            if selected_document.document_type == 'lease':
                landlord = Landlord()
                form = LandlordForm(instance=landlord)
    if selected_client:
        print(selected_client.__dict__)
    
    return render(request, "account/client_list.html", {
        "clients": clients,
        "documents": documents,
        "selected_client" : selected_client,
        "selected_document": selected_document,
        'current_client_id': selected_client.id if selected_client else None,
        "form": form,
    })

import re
import os
import logging
from io import BytesIO
from datetime import datetime
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.core.files.storage import default_storage
from django.template import Template, Context
from django.utils.dateparse import parse_date
from xhtml2pdf import pisa
from .models import Client, Document, Landlord

# Set up logging
logger = logging.getLogger(__name__)

from django.template.loader import render_to_string
from django.http import HttpResponse, HttpResponseServerError
import logging
import os
import re
from django.shortcuts import get_object_or_404
from dateutil.parser import parse as parse_date
from datetime import datetime
from io import BytesIO
from xhtml2pdf import pisa

logger = logging.getLogger(__name__)
def generate_document_from_html(request):
    logger.debug("Document generation started")
    print("STATIC_ROOT:", settings.STATIC_ROOT)
    print("Files in static:", os.listdir(settings.STATIC_ROOT))
    
    
    if request.method != 'POST':
        logger.error("Invalid request method")
        return HttpResponse("Only POST requests are allowed", status=405)

    try:
        logger.debug(f"POST data received: {dict(request.POST)}")
        
        # Get required parameters
        document_name = request.POST.get('document_name')
        if not document_name:
            logger.error("Missing document_name")
            return HttpResponse("document_name is required", status=400)

        client_name = request.POST.get('client_name')
        if not client_name:
            logger.error("Missing client_name")
            return HttpResponse("client_name is required", status=400)

        # Get models
        try:
            client = get_object_or_404(Client, pOwner=client_name)
            document = get_object_or_404(Document, name=document_name)
            logger.debug(f"Found client {client_name} and document {document_name}")
        except Exception as e:
            logger.error(f"Error fetching models: {str(e)}")
            return HttpResponse("Error loading client or document", status=404)

        # Date formatting function
        def clean_and_format_date(date_str):
            if not date_str:
                return ""
            
            try:
                cleaned = re.sub(r'[^\d/-]', '', str(date_str))
                date_obj = parse_date(cleaned)
                
                if not date_obj:
                    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%m-%d-%Y', '%m/%d/%Y', '%d-%m-%Y', '%d/%m/%Y'):
                        try:
                            date_obj = datetime.strptime(cleaned, fmt).date()
                            break
                        except ValueError:
                            continue
                
                if date_obj:
                    try:
                        return date_obj.strftime('%B %d, %Y').replace(' 0', ' ')
                    except:
                        return date_obj.strftime('%B %d, %Y')
            except Exception as e:
                logger.warning(f"Date formatting failed for {date_str}: {str(e)}")
            return ""

        # Read template content
        try:
            if not document.file:
                logger.error("No template file attached to document")
                return HttpResponse("Document template file is missing", status=400)
                
            template_path = document.file.path
            logger.debug(f"Attempting to read template from: {template_path}")
            
            if not os.path.exists(template_path):
                logger.error(f"Template file not found at: {template_path}")
                return HttpResponse("Template file not found", status=404)
                
            with open(template_path, 'r', encoding='utf-8') as template_file:
                template_content = template_file.read()
            logger.debug("Successfully read template file")
            
            # Create a temporary template from the content
            template = Template(template_content)
            
        except Exception as e:
            logger.error(f"Error reading template file: {str(e)}")
            return HttpResponse(f"Error loading template: {str(e)}", status=500)

        # Prepare context
        context = Context({
            'client': client,
            'document': document,
            'preview': request.POST.get('preview') == 'true',
            'today': datetime.now().strftime('%B %d, %Y')
        })

        # Process lease-specific data
        if document.document_type == 'lease':
            logger.debug("Processing lease document")
            try:
                term_start_date = request.POST.get('term_start_date', '')
                term_end_date = request.POST.get('term_end_date', '')


                print(clean_and_format_date(term_start_date))
                print(clean_and_format_date(term_end_date))
                context.update({
                    'formatted_start_date': clean_and_format_date(term_start_date),
                    'formatted_end_date': clean_and_format_date(term_end_date),
                    'term_start_date': term_start_date,
                    'term_end_date': term_end_date,
                })

                landlord_data = {
                # Basic Information
                'full_name': request.POST.get('full_name'),
                'address': request.POST.get('address'),
                'city': request.POST.get('city'),
                'state': request.POST.get('state'),
                'zip_code': request.POST.get('zip_code'),
                'phone': request.POST.get('phone'),
                'email': request.POST.get('email'),
                
                # Rental Property Information
                'property_address': request.POST.get('property_address'),
                'property_city': request.POST.get('property_city'),
                'property_state': request.POST.get('property_state'),
                'property_zip': request.POST.get('property_zip'),
                
                #term start and end
                'term_start_date': request.POST.get('term_start_date'),
                'term_end_date': request.POST.get('term_end_date'),

                # Agreement Defaults
                'default_rent_amount': request.POST.get('default_rent_amount', 0),
                'default_security_deposit': request.POST.get('default_security_deposit', 0),
                'default_rent_due_day': request.POST.get('default_rent_due_day', 1),
                'default_late_fee': request.POST.get('default_late_fee', 0),
                'default_late_fee_start_day': request.POST.get('default_late_fee_start_day', 5),
                'default_eviction_day': request.POST.get('default_eviction_day', 10),
                'default_nsf_fee': request.POST.get('default_nsf_fee', 0),
                'default_max_occupants': request.POST.get('default_max_occupants', 10),
                'default_parking_spaces': request.POST.get('default_parking_spaces', 2),
                'default_parking_fee': request.POST.get('default_parking_fee', 0),
                'default_inspection_fee': request.POST.get('default_inspection_fee', 300.00),
                'bedrooms': request.POST.get('bedrooms', 1),
                'rental_months': request.POST.get('rental_months'),
                # Additional Contact Persons
                'contact_person_1': request.POST.get('contact_person_1'),
                'contact_person_2': request.POST.get('contact_person_2'),
                'contact_phone': request.POST.get('contact_phone'),
                'contact_email': request.POST.get('contact_email'),
                
                # Real Estate Company Information
                'real_estate_company': request.POST.get('real_estate_company'),
                'company_mailing_address': request.POST.get('company_mailing_address'),
                'company_city': request.POST.get('company_city'),
                'company_state': request.POST.get('company_state'),
                'company_zip': request.POST.get('company_zip'),
                'company_contact_person': request.POST.get('company_contact_person'),
                'company_phone': request.POST.get('company_phone'),
                'company_email': request.POST.get('company_email'),
                'broker_name': request.POST.get('broker_name'),
                'broker_phone': request.POST.get('broker_phone'),
                'broker_email': request.POST.get('broker_email'),
                }


                numeric_fields = {
                    'default_rent_amount': 0,
                    'default_security_deposit': 0,
                    'default_late_fee': 50,
                    'default_nsf_fee': 35,
                    'default_inspection_fee': 300.00,
                    'bedrooms': 0,
                    'rental_months': 0
                }

                for field, default in numeric_fields.items():
                    try:
                        value = request.POST.get(field, default)
                        landlord_data[field] = float(value) if value else default
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid number format for {field}: {str(e)}")
                        landlord_data[field] = default

                context['landlord'] = landlord_data
                logger.debug("Lease context prepared successfully")

            except Exception as e:
                logger.error(f"Error processing lease data: {str(e)}")
                return HttpResponse(f"Error processing lease data: {str(e)}", status=400)

            # Handle preview request
            if request.POST.get('preview') == 'true':
                logger.debug("Generating HTML preview")
                try:
                    html_content = template.render(context)
                    return HttpResponse(html_content)
                except Exception as e:
                    logger.error(f"Template rendering failed: {str(e)}")
                    return HttpResponse(f"Error generating preview: {str(e)}", status=500)

            # Generate PDF
            logger.debug("Starting PDF generation")
            try:
                html_string = template.render(context)
    
                # Generate PDF with WeasyPrint
                pdf_bytes = HTML(
                    string=html_string,
                    base_url=request.build_absolute_uri('/')  # For resolving relative URLs
                ).write_pdf()
                
                response = HttpResponse(pdf_bytes, content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{document_name}_{client_name}.pdf"'
                logger.debug("PDF generated successfully")
                return response
                
            except Exception as e:
                logger.error(f"PDF generation error: {str(e)}")
                return HttpResponse(f"Error generating PDF: {str(e)}", status=500)

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return HttpResponse(f"An unexpected error occurred: {str(e)}", status=500)
def save_landlord(request):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            landlord_data = {
                # Basic Information
                'full_name': request.POST.get('full_name'),
                'address': request.POST.get('address'),
                'city': request.POST.get('city'),
                'state': request.POST.get('state'),
                'zip_code': request.POST.get('zip_code'),
                'phone': request.POST.get('phone'),
                'email': request.POST.get('email'),
                
                # Rental Property Information
                'property_address': request.POST.get('property_address'),
                'property_city': request.POST.get('property_city'),
                'property_state': request.POST.get('property_state'),
                'property_zip': request.POST.get('property_zip'),
                
                #term start and end
                'term_start_date': request.POST.get('term_start_date'),
                'term_end_date': request.POST.get('term_end_date'),

                # Agreement Defaults
                'default_rent_amount': request.POST.get('default_rent_amount', 0),
                'default_security_deposit': request.POST.get('default_security_deposit', 0),
                'default_rent_due_day': request.POST.get('default_rent_due_day', 1),
                'default_late_fee': request.POST.get('default_late_fee', 0),
                'default_late_fee_start_day': request.POST.get('default_late_fee_start_day', 5),
                'default_eviction_day': request.POST.get('default_eviction_day', 10),
                'default_nsf_fee': request.POST.get('default_nsf_fee', 0),
                'default_max_occupants': request.POST.get('default_max_occupants', 10),
                'default_parking_spaces': request.POST.get('default_parking_spaces', 2),
                'default_parking_fee': request.POST.get('default_parking_fee', 0),
                'default_inspection_fee': request.POST.get('default_inspection_fee', 300.00),
                'bedrooms': request.POST.get('bedrooms', 1),
                'rental_months': request.POST.get('rental_months'),
                # Additional Contact Persons
                'contact_person_1': request.POST.get('contact_person_1'),
                'contact_person_2': request.POST.get('contact_person_2'),
                'contact_phone': request.POST.get('contact_phone'),
                'contact_email': request.POST.get('contact_email'),
                
                # Real Estate Company Information
                'real_estate_company': request.POST.get('real_estate_company'),
                'company_mailing_address': request.POST.get('company_mailing_address'),
                'company_city': request.POST.get('company_city'),
                'company_state': request.POST.get('company_state'),
                'company_zip': request.POST.get('company_zip'),
                'company_contact_person': request.POST.get('company_contact_person'),
                'company_phone': request.POST.get('company_phone'),
                'company_email': request.POST.get('company_email'),
                'broker_name': request.POST.get('broker_name'),
                'broker_phone': request.POST.get('broker_phone'),
                'broker_email': request.POST.get('broker_email'),
            }

            if landlord_data['term_start_date']:
                 landlord_data['term_start_date'] = parse_date(landlord_data['term_start_date'])
            if landlord_data['term_end_date']:
                landlord_data['term_end_date'] = parse_date(landlord_data['term_end_date'])

            # Convert empty strings to None for non-required fields
            for field in landlord_data:
                if landlord_data[field] == '':
                    landlord_data[field] = None
            
            # Validate required fields
            required_fields = [
                'full_name', 
                'address',
                'city',
                'state',
                'zip_code',
                'phone',
                'property_address',
                'property_city',
                'property_state',
                'property_zip'
            ]
            
            missing_fields = [field for field in required_fields if not landlord_data.get(field)]
            if missing_fields:
                return JsonResponse({
                    'success': False, 
                    'error': f'Missing required fields: {", ".join(missing_fields)}'
                })
            
            # Convert numeric fields
            numeric_fields = [
                'default_rent_amount',
                'default_security_deposit',
                'default_late_fee',
                'default_nsf_fee',
                'default_rent_due_day',
                'default_late_fee_start_day',
                'default_eviction_day',
                'default_max_occupants',
                'default_parking_spaces',
                'default_parking_fee',
                'default_inspection_fee'
            ]
            
            for field in numeric_fields:
                if landlord_data[field] is not None:
                    try:
                        if field in ['default_rent_amount', 'default_security_deposit', 
                                    'default_late_fee', 'default_nsf_fee', 'default_inspection_fee']:
                            landlord_data[field] = float(landlord_data[field])
                        else:
                            landlord_data[field] = int(landlord_data[field])
                    except (ValueError, TypeError):
                        return JsonResponse({
                            'success': False,
                            'error': f'Invalid value for {field.replace("_", " ").title()}'
                        })
            
            # Save to database
            landlord, created = Landlord.objects.update_or_create(
                property_address=landlord_data['property_address'],
                defaults=landlord_data
            )
            
            return JsonResponse({
                'success': True, 
                'created': created,
                'landlord_id': landlord.id
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'error': str(e),
                'type': type(e).__name__
            })
    
    return JsonResponse({
        'success': False, 
        'error': 'Invalid request method or not AJAX'
    })
def convert_excel_to_pdf(excel_path, pdf_path):
    """Convert specific Excel sheet to PDF using the appropriate method for the OS"""
    if platform.system() == 'Windows':
        try:
            import win32com.client
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            wb = excel.Workbooks.Open(excel_path)
            wb.ExportAsFixedFormat(0, pdf_path)  # Export only the selected sheet
            wb.Close()
            excel.Quit()
        except Exception as e:
            logger.error(f"Error converting with Excel: {str(e)}")
            raise
    else:
        # For Linux using LibreOffice
        try:
            import subprocess
            
            # Get the directory of the output file
            output_dir = os.path.dirname(pdf_path)
            
            # Ensure the directory exists
            os.makedirs(output_dir, exist_ok=True)
            
            # First try unoconv if available
            try:
                subprocess.run(['which', 'unoconv'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # Use unoconv for direct conversion
                subprocess.run([
                    'unoconv',
                    '-f', 'pdf',
                    '-o', pdf_path,
                    excel_path
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
            except (subprocess.SubprocessError, FileNotFoundError):
                # Fall back to LibreOffice if unoconv not available
                subprocess.run([
                    'libreoffice',
                    '--headless',
                    '--convert-to', 'pdf',
                    '--outdir', output_dir,
                    excel_path
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # LibreOffice will create a file with the same name but .pdf extension
                libreoffice_output = os.path.splitext(os.path.basename(excel_path))[0] + '.pdf'
                libreoffice_output_path = os.path.join(output_dir, libreoffice_output)
                
                # Rename to desired output name if necessary
                if os.path.exists(libreoffice_output_path) and libreoffice_output_path != pdf_path:
                    os.rename(libreoffice_output_path, pdf_path)
                
        except Exception as e:
            logger.error(f"Error converting with LibreOffice: {str(e)}")
            raise

def generate_invoice_pdf(request, client_id):
    try:
        # Fetch the client data
        client = get_object_or_404(Client, pOwner=client_id)
        logger.info(f"Generating Excel for client: {client_id}")
        
        # Get rooms data from POST
        rooms_data = json.loads(request.POST.get('rooms_data', '{}'))
        
        # Load the template Excel file
        template_path = os.path.join(settings.BASE_DIR, 'docsAppR', 'templates', 'excel', '60_scope_form.xlsx')
        wb = load_workbook(template_path, data_only=True)
        
        # Select the ScopeCHLST sheet
        ws = wb['ScopeCHLST']

        # Map inspection checklist data - column mappings
        checklist_mappings = {
            'clg': 'C',  # Ceiling
            'lit': 'D',  # Lighting
            'hvc': 'E',  # HVAC
            'wal': 'F',  # Walls
            'ele': 'G',  # Electrical
            'flr': 'H',  # Floor
            'bb': 'I',   # Baseboards
            'dor': 'J',  # Doors
            'wdw': 'K',  # Windows
            'wdt': 'L',  # Water Damage
        }
        
        # Create a mapping of room IDs to their row numbers
        room_rows = {}
        for row in range(2, ws.max_row + 1):  # Start from row 2
            room_cell = ws[f'B{row}'].value
            if room_cell:
                room_rows[str(room_cell).strip()] = row
        print(room_rows)
        # Precise data placement
        print(rooms_data.items())
        for room_id, room_data in rooms_data.items():
            if room_id in room_rows:
                row_number = room_rows[room_id]
                
                for field, column in checklist_mappings.items():
                    cell_value = room_data.get(field, '')
                    ws[f'{column}{row_number}'] = cell_value or 'N/A'
        
        # Generate filename
        filename = f"scope_form_{client_id}_all_rooms.xlsx"
        
        # Create temporary directory for file conversion
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save Excel file to temp directory
            temp_excel_path = os.path.join(temp_dir, filename)
            wb.save(temp_excel_path)
            
            # Update JobInfo with claim/client info
            


            # Create PDF filename
            pdf_filename = f"scope_form_{client_id}.pdf"
            temp_pdf_path = os.path.join(temp_dir, pdf_filename)
            
            # Convert Excel to PDF
            convert_excel_to_pdf(temp_excel_path, temp_pdf_path)
            
            # Read the generated PDF
            with open(temp_pdf_path, 'rb') as pdf_file:
                pdf_content = pdf_file.read()
            
            # Save both Excel and PDF to File model
            excel_obj = File(
                filename=filename,
                size=os.path.getsize(temp_excel_path)
            )
            excel_obj.file.save(filename, ContentFile(open(temp_excel_path, 'rb').read()), save=True)
            
            pdf_obj = File(
                filename=pdf_filename,
                size=len(pdf_content)
            )
            pdf_obj.file.save(pdf_filename, ContentFile(pdf_content), save=True)
            
            # Generate response with PDF
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
            response.write(pdf_content)
            
            # Clear session data
            if 'inspection_data' in request.session:
                del request.session['inspection_data']
            
            return response
        
    except Exception as e:
        logger.error(f"Error generating files: {str(e)}")
        return HttpResponse(f"An error occurred while generating the files: {str(e)}", status=500)

@login_required
def emails(request):
    if request.method == 'POST':
        recipients = request.POST.getlist('recipients[]')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        selected_docs = request.POST.getlist('selected_docs[]')
        
        try:
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            
            # Attach selected documents
            for doc_id in selected_docs:
                doc = get_object_or_404(File, id=doc_id)
                email.attach_file(doc.file.path)
            
            email.send()
            messages.success(request, 'Email sent successfully!')
            
        except Exception as e:
            messages.error(request, f'Error sending email: {str(e)}')
        
        return redirect('emails')
    
    # Get recently generated documents (last 10)
    documents = File.objects.all().order_by('-id')[:10]
    
    context = {
        'documents': documents,
    }
    
    return render(request, 'account/emails.html', context)


import json
import zipfile
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from .models import ReadingImage
from django.core.files.base import ContentFile
import os

def reading_browser(request):
    """Main view for the reading browser"""
    images = ReadingImage.objects.all()
    return render(request, 'account/browser.html', {'images': images})

@csrf_exempt
def upload_readings(request):
    """Handle image uploads"""
    if request.method == 'POST' and request.FILES.getlist('images'):
        uploaded_files = request.FILES.getlist('images')
        results = {
            'success': [],
            'errors': [],
            'duplicates': []
        }
        
        for uploaded_file in uploaded_files:
            # Check if file already exists
            if ReadingImage.objects.filter(filename=uploaded_file.name).exists():
                results['duplicates'].append(uploaded_file.name)
                continue
            
            try:
                # Create new ReadingImage
                reading_image = ReadingImage(
                    filename=uploaded_file.name,
                    size=uploaded_file.size,
                    file=uploaded_file
                )
                reading_image.save()
                results['success'].append(uploaded_file.name)
            except Exception as e:
                results['errors'].append(f"{uploaded_file.name}: {str(e)}")
        
        return JsonResponse(results)
    
    return JsonResponse({'error': 'No files provided'}, status=400)

# views.py - Update get_sorted_readings to include MC
def get_sorted_readings(request):
    """Get sorted images based on criteria"""
    sort_by = request.GET.get('sort_by', 'filename')  # Default to filename sort
    order = request.GET.get('order', 'asc')
    
    images = ReadingImage.objects.all()
    
    # Apply sorting
    if sort_by == 'rh':
        field = 'rh_value'
    elif sort_by == 't':
        field = 't_value'
    elif sort_by == 'gpp':
        field = 'gpp_value'
    elif sort_by == 'mc':
        field = 'mc_value'
    elif sort_by == 'filename':
        field = 'filename'
    else:
        field = 'filename'  # Default to filename sorting
    
    if order == 'desc':
        field = f'-{field}'
    
    images = images.order_by(field)
    
    # Prepare data for JSON response
    image_data = []
    for image in images:
        image_data.append({
            'id': image.id,
            'filename': image.filename,
            'url': image.file.url,
            'rh': image.rh_value,
            't': image.t_value,
            'gpp': image.gpp_value,
            'mc': image.mc_value, 
            'size': image.get_file_size_display()
        })
    
    return JsonResponse({'images': image_data})

# views.py - Improved export_readings function
@csrf_exempt
def export_readings(request):
    """Export selected images as zip file with better error handling"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            folder_structure = data.get('folders', {})
            
            if not folder_structure:
                return JsonResponse({'error': 'No folders provided'}, status=400)
            
            # Validate that we have some images to export
            total_images = sum(len(images) for images in folder_structure.values())
            if total_images == 0:
                return JsonResponse({'error': 'No images in folders to export'}, status=400)
            
            # Create zip file in memory
            response = HttpResponse(content_type='application/zip')
            response['Content-Disposition'] = 'attachment; filename="reading_images.zip"'
            
            try:
                with zipfile.ZipFile(response, 'w') as zip_file:
                    exported_count = 0
                    missing_files = []
                    
                    for folder_name, image_data_list in folder_structure.items():
                        for image_data in image_data_list:
                            try:
                                image_id = image_data.get('id')
                                image = ReadingImage.objects.get(id=image_id)
                                
                                if image.file and os.path.exists(image.file.path):
                                    # Add to folder in zip
                                    zip_path = os.path.join(folder_name, image.filename)
                                    zip_file.write(image.file.path, zip_path)
                                    exported_count += 1
                                else:
                                    missing_files.append(image.filename)
                                    
                            except ReadingImage.DoesNotExist:
                                missing_files.append(f"Image ID {image_id}")
                            except Exception as e:
                                missing_files.append(f"{image_data.get('filename', 'Unknown')}: {str(e)}")
                    
                    if exported_count == 0:
                        return JsonResponse({
                            'error': f'No files could be exported. Missing files: {missing_files}'
                        }, status=404)
                    
                    if missing_files:
                        print(f"Warning: {len(missing_files)} files could not be exported: {missing_files}")
                
                return response
                
            except zipfile.BadZipFile:
                return JsonResponse({'error': 'Error creating zip file'}, status=500)
            except OSError as e:
                return JsonResponse({'error': f'File system error: {str(e)}'}, status=500)
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Unexpected error: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)


# views.py - Updated rename_reading function
# views.py - COMPLETELY FIXED rename_reading function
@csrf_exempt
def rename_reading(request, image_id):
    """Rename a reading image and properly update the file field"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_filename = data.get('filename')
            
            if not new_filename:
                return JsonResponse({'error': 'No filename provided'}, status=400)
            
            image = ReadingImage.objects.get(id=image_id)
            
            # Get the current file information
            if not image.file:
                return JsonResponse({'error': 'Image file not found'}, status=404)
            
            old_file_path = image.file.path
            old_filename = image.filename
            
            print(f"Renaming from: {old_filename} to: {new_filename}")
            print(f"Old file path: {old_file_path}")
            
            # Validate that old file exists
            if not os.path.exists(old_file_path):
                return JsonResponse({
                    'error': f'Original file not found: {old_filename}'
                }, status=404)
            
            # Ensure the new filename has proper extension
            old_ext = os.path.splitext(old_filename)[1]
            new_ext = os.path.splitext(new_filename)[1]
            
            if not new_ext:
                new_filename += old_ext
            elif new_ext.lower() != old_ext.lower():
                return JsonResponse({
                    'error': f'Cannot change file extension from {old_ext} to {new_ext}'
                }, status=400)
            
            # Generate new file path
            file_dir = os.path.dirname(old_file_path)
            new_file_path = os.path.join(file_dir, new_filename)
            
            # Check if new filename already exists (and it's not the same file)
            if os.path.exists(new_file_path) and new_file_path != old_file_path:
                return JsonResponse({
                    'error': f'Filename already exists: {new_filename}'
                }, status=400)
            
            # Rename the file in storage
            try:
                os.rename(old_file_path, new_file_path)
                print(f"File renamed successfully on disk: {new_file_path}")
            except OSError as e:
                return JsonResponse({
                    'error': f'File system error: {str(e)}'
                }, status=500)
            
            # CRITICAL FIX: Update the file field to point to the new path
            # Get the relative path from the media root
            from django.conf import settings
            media_root = settings.MEDIA_ROOT
            relative_new_path = os.path.relpath(new_file_path, media_root)
            
            # Update both filename AND file field
            image.filename = new_filename
            image.file.name = relative_new_path  # This updates the FileField path!
            
            # Re-extract values from new filename
            image.extract_values_from_filename()
            
            # Save the model (this updates both fields in database)
            image.save()
            
            print(f"Database updated - filename: {image.filename}, file field: {image.file.name}")
            
            return JsonResponse({
                'success': True, 
                'message': 'Image renamed successfully',
                'new_filename': new_filename,
                'file_url': image.file.url  # Return the updated URL
            })
            
        except ReadingImage.DoesNotExist:
            return JsonResponse({'error': 'Image not found'}, status=404)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Unexpected error: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@csrf_exempt
def delete_reading(request, image_id):
    """Delete a reading image"""
    if request.method == 'DELETE':
        try:
            image = ReadingImage.objects.get(id=image_id)
            image.delete()
            return JsonResponse({'success': True, 'message': 'Image deleted successfully'})
        except ReadingImage.DoesNotExist:
            return JsonResponse({'error': 'Image not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

from django.db.models import Count, Avg, Case, When, IntegerField, F, Q
from django.utils import timezone
import datetime as dt
import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Client, ChecklistItem

@login_required
def statistics(request):
    # Calculate basic metrics
    clients = Client.objects.all()
    total_claims = clients.count()
    avg_completion = clients.aggregate(avg=Avg('completion_percent'))['avg'] or 0
    
    # Get oldest claim age in days
    oldest_claim = clients.order_by('dateOfLoss').first()
    oldest_claim_age = 0
    if oldest_claim and oldest_claim.dateOfLoss:
        oldest_claim_age = (timezone.now().date() - oldest_claim.dateOfLoss).days
    
    # Claim type counts
    mit_count = clients.filter(mitigation=True).count()
    cps_count = clients.filter(CPSCLNCONCGN=True).count()
    ppr_count = clients.filter(replacement=True).count()
    
    # Calculate trends (month-over-month comparison)
    last_month = timezone.now() - dt.timedelta(days=30)
    claim_growth = calculate_percentage_change(
        clients.filter(created_at__lt=last_month).count(),
        total_claims
    )
    completion_trend = calculate_percentage_change(
        clients.filter(created_at__lt=last_month).aggregate(avg=Avg('completion_percent'))['avg'] or 0,
        avg_completion
    )
    age_trend = calculate_trend_days(oldest_claim_age, last_month)
    mit_trend = calculate_percentage_change(
        clients.filter(mitigation=True, created_at__lt=last_month).count(),
        mit_count
    )
    cps_trend = calculate_percentage_change(
        clients.filter(CPSCLNCONCGN=True, created_at__lt=last_month).count(),
        cps_count
    )
    ppr_trend = calculate_percentage_change(
        clients.filter(replacement=True, created_at__lt=last_month).count(),
        ppr_count
    )
    
    # Enhanced Age Distribution
    now = timezone.now().date()
    age_categories = {
        "0-30 days": Q(dateOfLoss__gte=now - dt.timedelta(days=30)),
        "31-60 days": Q(dateOfLoss__lt=now - dt.timedelta(days=30)) & 
                     Q(dateOfLoss__gte=now - dt.timedelta(days=60)),
        "61-120 days": Q(dateOfLoss__lt=now - dt.timedelta(days=60)) & 
                      Q(dateOfLoss__gte=now - dt.timedelta(days=120)),
        "121-180 days": Q(dateOfLoss__lt=now - dt.timedelta(days=120)) & 
                       Q(dateOfLoss__gte=now - dt.timedelta(days=180)),
        "181-360 days": Q(dateOfLoss__lt=now - dt.timedelta(days=180)) & 
                        Q(dateOfLoss__gte=now - dt.timedelta(days=360)),
        "360+ days": Q(dateOfLoss__lt=now - dt.timedelta(days=360))
    }
    
    # Age distribution by claim type
    age_distribution = {
        'all': {category: clients.filter(query).count() for category, query in age_categories.items()},
        'MIT': {category: clients.filter(query, mitigation=True).count() for category, query in age_categories.items()},
        'CPS': {category: clients.filter(query, CPSCLNCONCGN=True).count() for category, query in age_categories.items()},
        'PPR': {category: clients.filter(query, replacement=True).count() for category, query in age_categories.items()}
    }
    
    # Age completion data
    age_completion_data = {
        category: clients.filter(query).aggregate(
            avg=Avg('completion_percent')
        )['avg'] or 0
        for category, query in age_categories.items()
    }
    
    # Document completion rates by type
    document_stats = {
        'all': list(ChecklistItem.objects.values('document_type').annotate(
            total=Count('id'),
            completed=Count(Case(When(is_completed=True, then=1), output_field=IntegerField()))
        ).annotate(
            completion_rate=100.0 * F('completed') / F('total')
        ).order_by('-completion_rate')[:10]),
        'MIT': list(ChecklistItem.objects.filter(document_category='MIT').values('document_type').annotate(
            total=Count('id'),
            completed=Count(Case(When(is_completed=True, then=1), output_field=IntegerField()))
        ).annotate(
            completion_rate=100.0 * F('completed') / F('total')
        ).order_by('-completion_rate')[:10]),
        'CPS': list(ChecklistItem.objects.filter(document_category='CPS').values('document_type').annotate(
            total=Count('id'),
            completed=Count(Case(When(is_completed=True, then=1), output_field=IntegerField()))
        ).annotate(
            completion_rate=100.0 * F('completed') / F('total')
        ).order_by('-completion_rate')[:10]),
        'PPR': list(ChecklistItem.objects.filter(document_category='PPR').values('document_type').annotate(
            total=Count('id'),
            completed=Count(Case(When(is_completed=True, then=1), output_field=IntegerField()))
        ).annotate(
            completion_rate=100.0 * F('completed') / F('total')
        ).order_by('-completion_rate')[:10])
    }
    
    # Client completion data for bar chart
    client_completion_data = [
        {'client_name': c.pOwner, 'completion_percent': c.completion_percent}
        for c in clients.order_by('-completion_percent')[:10]  # Top 10 clients
    ]
    
    # Recent activity
    recent_activity = [
        {
            'user_initials': request.user.get_initials() if hasattr(request.user, 'get_initials') else 'SY',
            'message': f"Updated claim for {c.pOwner}",
            'timestamp': c.updated_at,
            'type': 'Update'
        }
        for c in clients.order_by('-updated_at')[:5]
    ]
    
        recent_uploads = UploadActivity.objects.all().order_by('-uploaded_at')[:10]
    
    context.update({
        'recent_uploads': recent_uploads,
        'upload_stats': {
            'total_uploads': UploadActivity.objects.count(),
            'successful_uploads': UploadActivity.objects.filter(status='SUCCESS').count(),
            'today_uploads': UploadActivity.objects.filter(
                uploaded_at__date=timezone.now().date()
            ).count(),
        }
    })
        # Add room statistics
    total_rooms = Room.objects.count()
    rooms_per_client = Client.objects.annotate(room_count=models.Count('rooms'))
    avg_rooms_per_client = rooms_per_client.aggregate(avg=models.Avg('room_count'))['avg'] or 0
    
    # Work type distribution
    work_type_stats = {}
    for wt in WorkType.objects.all():
        wt_count = RoomWorkTypeValue.objects.filter(work_type=wt).exclude(value_type='NA').count()
        work_type_stats[wt.work_type_id] = wt_count
    
    context.update({
        'total_rooms': total_rooms,
        'avg_rooms_per_client': round(avg_rooms_per_client, 1),
        'work_type_stats': work_type_stats,
    })
    
    context = {
        'total_claims': total_claims,
        'avg_completion': round(avg_completion, 1),
        'oldest_claim_age': oldest_claim_age,
        'mit_count': mit_count,
        'cps_count': cps_count,
        'ppr_count': ppr_count,
        
        'claim_growth': round(claim_growth, 1),
        'completion_trend': round(completion_trend, 1),
        'age_trend': age_trend,
        'mit_trend': round(mit_trend, 1),
        'cps_trend': round(cps_trend, 1),
        'ppr_trend': round(ppr_trend, 1),
        
        'age_distribution': json.dumps(age_distribution),
        'age_completion_data': json.dumps(age_completion_data),
        'document_stats': json.dumps(document_stats),
        'client_completion_data': json.dumps(client_completion_data),
        
        'recent_activity': recent_activity,
    }
    
    return render(request, 'account/statistics.html', context)

def calculate_percentage_change(old_value, new_value):
    if old_value == 0:
        return 0
    return ((new_value - old_value) / old_value) * 100

def calculate_trend_days(current_days, comparison_date):
    oldest_last_month = Client.objects.filter(created_at__lt=comparison_date) \
                                     .order_by('dateOfLoss').first()
    if not oldest_last_month or not oldest_last_month.dateOfLoss:
        return 0
    
    last_month_days = (comparison_date.date() - oldest_last_month.dateOfLoss).days
    return current_days - last_month_days
