from allauth.account.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from . forms import  CreateUserForm
from django.contrib.auth import authenticate, login, logout
from .forms import UploadFilesForm
from .forms import ClientForm
from django.conf import settings
import os
from django.core import serializers
import json
from docsAppR.models import Client
from django.http import HttpResponse
from django.template.loader import render_to_string
#from xhtml2pdf import pisa  # For xhtml2pdf
# from weasyprint import HTML  # Uncomment if using WeasyPrint
import math
from django.shortcuts import render, get_object_or_404
#from django.template.loader import render_to_string
#from django.http import HttpResponse
from django.urls import reverse
#import pisa
import logging
from io import BytesIO
from django.core.mail import EmailMessage
from django.contrib import messages
from docsAppR.models import File
from openpyxl import load_workbook
from .config.excel_mappings import SCOPE_FORM_MAPPINGS
import platform
from pathlib import Path
import tempfile
from django.core.files.base import ContentFile
import shutil
from django.http import JsonResponse
import re
import time
# Set up logging
logger = logging.getLogger(__name__)

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
#
#
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
    return redirect('')

@login_required
def create(request):
    client = Client.objects.all()

    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
        else:
            return render(request, 'account/create.html',{'form': form, 'client': client})
        
    if request.method == "GET":
        form = ClientForm()
    
    context = {
        'form': form,
        'client' : client
    }
    return render(request, 'account/create.html', context)

@login_required
def checklist(request):
    labels = ["CLG", "LIT", "HVC", "MISC-1", "WAL", "ELE", "FLR", "BB", "MISC-2", "DOR", "OPEN", "WDW", "WDT"]
    activity = []
    labelValues = []
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

@login_required
def labels(request):
    claims = Client.objects.all()
    
    # Get rooms for selected claim
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
        except Client.DoesNotExist:
            rooms = []
            logger.error(f"Client not found: {selected_claim_id}")
    
    # Handle POST request (just the placeholder for now)
    if request.method == 'POST':
        try:
            claim_id = request.POST.get('claim')
        
            # Process the room labels data from the form
            room_labels = {}
            for key, value in request.POST.items():
                if key.startswith('room_labels['):
                    room_name = key[len('room_labels['):-1]  # Extract room name from room_labels[name]
                try:
                    count = int(value)
                    if count > 0:  # Only include rooms with at least 1 label
                        room_labels[room_name] = count
                except ValueError:
                    continue
        
            # Store the data in session (optional, if you need it later)
            request.session['room_labels_data'] = {
                'claim_id': claim_id,
                'room_labels': room_labels
            }
        
            # Generate and return PDF response
            return generate_room_labels_pdf(request)
            
        except Exception as e:
            logger.error(f"Error in POST processing: {str(e)}")
            return HttpResponse(f"An error occurred while processing the form: {str(e)}", status=500)
    
    context = {
        'claims': claims,
        'rooms': rooms,
        'selected_claim_id': selected_claim_id
    }
    
    return render(request, 'account/labels.html', context)

logger = logging.getLogger(__name__)

import os
import json
import tempfile
import platform
import logging
import math
import re
from pathlib import Path
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.core.files.base import ContentFile
from openpyxl import load_workbook

# Assuming this is defined elsewhere in your project
from .models import Client, File

logger = logging.getLogger(__name__)

import os
import re
import math
import tempfile
import platform
import logging
from pathlib import Path
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404

# Import Spire.XLS (you'll need to install this)
try:
    from spire.xls import *
    from spire.xls.common import *
except ImportError:
    raise ImportError("Spire.XLS is required. Install with: pip install spire-xls")

logger = logging.getLogger(__name__)
import os
import re
import math
import tempfile
import logging
import platform
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404

# Set up logging
logger = logging.getLogger(__name__)

def convert_excel_to_pdf_with_pages(excel_path, pdf_path, sheet_name, num_labels):
    """
    Convert specific Excel sheet to PDF with page range
    Works on both Windows and Linux platforms
    """
    # Calculate pages needed (2 labels per page)
    num_pages = math.ceil(num_labels / 2)
    
    try:
        system = platform.system()
        
        if system == "Windows":
            # Windows implementation using win32com
            import win32com.client
            import pythoncom
            
            # Initialize COM in this thread
            pythoncom.CoInitialize()
            excel = None
            
            try:
                # Create Excel application object
                excel = win32com.client.Dispatch("Excel.Application")
                excel.Visible = False
                excel.DisplayAlerts = False
                
                # Open workbook
                workbook = excel.Workbooks.Open(excel_path)
                
                # First, hide all sheets
                for i in range(1, workbook.Sheets.Count + 1):
                    try:
                        workbook.Sheets(i).Visible = 2  # xlSheetVeryHidden (2)
                    except:
                        pass
                
                # Find the sheet by name and make it visible
                target_sheet = None
                sheet_found = False
                for i in range(1, workbook.Sheets.Count + 1):
                    sheet = workbook.Sheets(i)
                    if sheet.Name == sheet_name:
                        sheet.Visible = -1  # xlSheetVisible (-1)
                        target_sheet = sheet
                        sheet_found = True
                        break
                
                if not sheet_found:
                    logger.error(f"Sheet {sheet_name} not found")
                    workbook.Close(False)
                    raise ValueError(f"Sheet {sheet_name} not found")
                
                # Activate the sheet
                target_sheet.Activate()
                
                # Calculate the range based on number of labels
                #rows_needed = math.ceil(num_labels / 2)  # Assuming 2 labels per row
                
                # Set print area if needed to limit output
                #if num_labels > 0:
                    # Determine rows to include (adjust based on your template)
                #    header_rows = 1  # Adjust based on template header size
                #    last_row = header_rows + num_labels
                #    target_sheet.PageSetup.PrintArea = f"$A$1:$Z${last_row}"
                
                # Configure page setup
                #target_sheet.PageSetup.Zoom = False
                #target_sheet.PageSetup.FitToPagesWide = 1
                #target_sheet.PageSetup.FitToPagesTall = num_pages
                
                # Save as PDF using sheet-specific export
                workbook.ActiveSheet.ExportAsFixedFormat(
                    Type=0,  # 0 = PDF
                    Filename=pdf_path,
                    Quality=0,
                    IncludeDocProperties=True,
                    IgnorePrintAreas=False,
                    OpenAfterPublish=False,
                    From=1,
                    To=num_pages
                )
                
                # Close workbook
                workbook.Close(False)
                return True
                
            except Exception as e:
                logger.error(f"Error in Excel processing: {str(e)}")
                raise
            finally:
                # Ensure Excel is properly closed
                if excel:
                    try:
                        excel.Quit()
                    except:
                        pass
                    
                    # Release COM objects
                    del excel
                
                # Uninitialize COM
                pythoncom.CoUninitialize()
                
        elif system == "Linux":
            # Linux implementation using LibreOffice headless mode
            import subprocess
                
            # Create a soffice command to convert Excel to PDF
            cmd = [
                'soffice',
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', os.path.dirname(pdf_path)
            ]
            
            # Try to select specific sheet
            sheet_param = f"--print-ranges={sheet_name}.A1:Z{num_labels + 1}"
            cmd.append(sheet_param)
            cmd.append(excel_path)
            
            # Execute the command
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Error converting with LibreOffice: {stderr.decode()}")
                raise Exception(f"LibreOffice conversion failed: {stderr.decode()}")
            
            # Rename the output file to the desired name
            # LibreOffice will create a file with the same name but .pdf extension
            libreoffice_pdf = os.path.splitext(excel_path)[0] + '.pdf'
            if os.path.exists(libreoffice_pdf) and libreoffice_pdf != pdf_path:
                os.rename(libreoffice_pdf, pdf_path)
            
            # For page range limitation, use PyPDF2 to extract pages
            if num_pages > 0:
                try:
                    import PyPDF2
                    
                    # Open the PDF
                    with open(pdf_path, 'rb') as file:
                        pdf_reader = PyPDF2.PdfReader(file)
                        pdf_writer = PyPDF2.PdfWriter()
                        
                        # Add only the required pages
                        for page_num in range(min(num_pages, len(pdf_reader.pages))):
                            pdf_writer.add_page(pdf_reader.pages[page_num])
                        
                        # Save the new PDF
                        with open(pdf_path + '.tmp', 'wb') as output_file:
                            pdf_writer.write(output_file)
                    
                    # Replace the original with the trimmed version
                    os.replace(pdf_path + '.tmp', pdf_path)
                    
                except ImportError:
                    logger.warning("PyPDF2 not installed. Cannot limit pages in PDF.")
        
        else:
            logger.error(f"Unsupported operating system: {system}")
            raise ValueError(f"Unsupported operating system: {system}")
            
    except Exception as e:
        logger.error(f"Error converting Excel to PDF: {str(e)}")
        raise

def get_room_index_from_name(room_name):
    """
    Extract the room index from room name
    Example: 'Living Room' from roomArea5 would return 5
    """
    # Try to find a number in the room name first (for UI display names)
    match = re.search(r'(\d+)', room_name)
    if match:
        return int(match.group(1))
    return None

def create_excel_from_template(template_path, output_path, sheet_name, room_index, claim_id):
    """
    Create a new Excel file from template with appropriate data
    Works on both Windows and Linux platforms
    """
    system = platform.system()
    
    if system == "Windows":
        # Windows implementation using win32com
        import win32com.client
        import pythoncom
        
        # Initialize COM in this thread
        pythoncom.CoInitialize()
        excel = None
        
        try:
            # Clean up filename - remove problematic characters
            dir_name = os.path.dirname(output_path)
            base_name = os.path.basename(output_path)
            
            # Remove extension first
            base_name_no_ext, ext = os.path.splitext(base_name)
            
            # Replace all non-alphanumeric characters (except underscores and dots)
            safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', base_name_no_ext)

               # Add timestamp and restore extension
            safe_name = f"{safe_name}_{int(time.time())}{ext}"
            safe_path = os.path.join(dir_name, safe_name)

            os.makedirs(dir_name, exist_ok=True)

            # Create Excel application object
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            
            # Open the template
            workbook = excel.Workbooks.Open(template_path)
            
            # Find the sheet by name
            sheet_found = False
            for i in range(1, workbook.Sheets.Count + 1):
                if workbook.Sheets(i).Name == sheet_name:
                    sheet_found = True
                    break
            
            if not sheet_found:
                logger.error(f"Sheet {sheet_name} not found")
                workbook.Close(False)
                return False
            
            # Save to the output path
            if ext == "xlsm":
                workbook.SaveAs(safe_path, FileFormat=51)
            workbook.SaveAs(safe_path)
            workbook.Close(True)
            
            # If we saved to a different path than requested, copy the file
            if safe_path != output_path and os.path.exists(safe_path):
                import shutil
                shutil.copy2(safe_path, output_path)
                os.remove(safe_path)
                
            return True
            
        except Exception as e:
            logger.error(f"Error creating Excel file with win32com: {str(e)}")
            return False
            
        finally:
            # Ensure Excel is properly closed
            if excel:
                try:
                    excel.Quit()
                except:
                    pass
                
                # Release COM objects
                del excel
                
            # Uninitialize COM
            pythoncom.CoUninitialize()
    
    elif system == "Linux":
        # Linux implementation - copy the template
        import shutil
        try:
            shutil.copy2(template_path, output_path)
            return True
        except Exception as e:
            logger.error(f"Error copying template on Linux: {str(e)}")
            return False
    
    else:
        logger.error(f"Unsupported operating system: {system}")
        return False

def generate_room_labels_pdf(request):
    """Generate room labels PDF based on user input"""
    try:
        # Get claim ID and room labels data
        claim_id = request.POST.get('claim')
        room_labels = {}
        
        # Parse room labels data - format is room_labels[room_name]=count
        for key, value in request.POST.items():
            if key.startswith('room_labels['):
                room_name = key[len('room_labels['):-1]  # Extract room name from room_labels[name]
                try:
                    count = int(value)
                    if count > 0:  # Only include rooms with at least 1 label
                        room_labels[room_name] = count
                except ValueError:
                    continue
        
        # Return early if no labels were requested
        if not claim_id or not room_labels:
            return JsonResponse({'status': 'success', 'message': 'No labels requested', 'pdfs': []})
        
        # Get client data
        client = get_object_or_404(Client, pOwner=claim_id)
        
        # Create mapping from room names to their indices in the Client model
        room_indices = {}
        
        # Get all roomArea fields from client
        for i in range(1, 26):  # roomArea1 through roomArea25
            field_name = f'roomArea{i}'
            if hasattr(client, field_name) and getattr(client, field_name):
                room_value = getattr(client, field_name)
                room_indices[room_value] = i
        
        # Load the template Excel file
        template_path = os.path.join(settings.BASE_DIR, 'docsAppR', 'templates', 'excel', 'room_labels_template.xlsm')
        
        # Create a temporary directory for file operations
        with tempfile.TemporaryDirectory() as temp_dir:
            # Results to collect PDFs for each room
            pdfs_info = []
            
            # Process each room
            for room_name, num_labels in room_labels.items():
                # Skip if no labels requested
                if num_labels <= 0:
                    continue
                
                # Get the room index - first check our mapping from client model
                room_index = room_indices.get(room_name)
                
                # If not found, try to extract a number from the room name
                if room_index is None:
                    room_index = get_room_index_from_name(room_name)
                    
                # If still not found, skip this room
                if room_index is None:
                    logger.warning(f"Could not determine room index for {room_name}")
                    continue
                
                sheet_name = f"RM ({room_index})"
                
                # Create filenames for the temporary files
                excel_filename = f"room_labels_{claim_id}_{room_name}.xlsm"
                temp_excel_path = os.path.join(temp_dir, excel_filename)
                
                # Create PDF filename
                pdf_filename = f"room_labels_{claim_id}_{room_name}.pdf"
                temp_pdf_path = os.path.join(temp_dir, pdf_filename)
                
                # Create Excel file from template
                if not create_excel_from_template(template_path, temp_excel_path, sheet_name, room_index, claim_id):
                    logger.warning(f"Failed to create Excel file for {room_name}")
                    continue
                
                # Convert Excel to PDF with specific sheet and page range based on label count
                convert_excel_to_pdf_with_pages(temp_excel_path, temp_pdf_path, sheet_name, num_labels)
                
                # Check if PDF was created
                if not os.path.exists(temp_pdf_path):
                    logger.warning(f"PDF was not created for {room_name}")
                    continue
                
                # Read the generated PDF
                with open(temp_pdf_path, 'rb') as pdf_file:
                    pdf_content = pdf_file.read()
                
                # Save the PDF to the File model
                pdf_obj = File(
                    filename=pdf_filename,
                    size=len(pdf_content)
                )
                pdf_obj.file.save(pdf_filename, ContentFile(pdf_content), save=True)
                
                # Add to our results
                pdfs_info.append({
                    'room_name': room_name,
                    'pdf_url': pdf_obj.file.url,
                    'num_labels': num_labels
                })
            
            # If no PDFs were generated, return a message
            if not pdfs_info:
                return JsonResponse({'status': 'success', 'message': 'No valid labels to generate', 'pdfs': []})
                
            # Return JSON response with PDF URLs
            return JsonResponse({
                'status': 'success', 
                'pdfs': pdfs_info
            })
            
    except Exception as e:
        logger.error(f"Error generating room labels: {str(e)}")
        return JsonResponse({
            'status': 'error', 
            'message': str(e)
        }, status=500)

@login_required
def dashboard(request):
    #displays clients from database by client name
    #has a search bar above, that lets you search for clients
    #whe ients = Client.objects.all()

    context = {
        'allClients' : allClients,
    }

    
    
    return render(request, 'account/dashboard.html', context)



def client_list(request):
    # Get all clients from the database
    clients = Client.objects.all()
    return render(request, "account/client_list.html", {"clients": clients})


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
        # For Linux/Mac using LibreOffice
        import subprocess
        try:
            # First convert to PDF with all sheets
            temp_pdf = pdf_path.replace('.pdf', '_temp.pdf')
            subprocess.run([
                'libreoffice', '--headless', '--convert-to', 'pdf',
                '--outdir', str(Path(pdf_path).parent),
                excel_path
            ], check=True)
            
            # Then use pdftk to extract just the first page (ScopeCHLST sheet)
            subprocess.run([
                'pdftk', temp_pdf,
                'cat', '1',  # Extract only first page
                'output', pdf_path
            ], check=True)
            
            # Clean up temporary file
            os.remove(temp_pdf)
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