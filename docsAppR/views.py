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
from xhtml2pdf import pisa  # For xhtml2pdf
# from weasyprint import HTML  # Uncomment if using WeasyPrint

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
def dashboard(request):
    #displays clients from database by client name
    #has a search bar above, that lets you search for clients
    #when you click on a client you get to see full client data on the side
    # and documents for that client
    allClients = Client.objects.all()

    context = {
        'allClients' : allClients,
    }

    
    
    return render(request, 'account/dashboard.html', context)



def client_list(request):
    # Get all clients from the database
    clients = Client.objects.all()
    return render(request, "account/client_list.html", {"clients": clients})


def convert_excel_to_pdf(excel_path, pdf_path):
    """Convert Excel file to PDF using the appropriate method for the OS"""
    if platform.system() == 'Windows':
        try:
            import win32com.client
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            wb = excel.Workbooks.Open(excel_path)
            wb.ExportAsFixedFormat(0, pdf_path)  # 0 = PDF format
            wb.Close()
            excel.Quit()
        except Exception as e:
            logger.error(f"Error converting with Excel: {str(e)}")
            raise
    else:
        # For Linux/Mac using LibreOffice
        import subprocess
        try:
            subprocess.run([
                'libreoffice', '--headless', '--convert-to', 'pdf',
                '--outdir', str(Path(pdf_path).parent),
                excel_path
            ], check=True)
        except Exception as e:
            logger.error(f"Error converting with LibreOffice: {str(e)}")
            raise

def generate_invoice_pdf(request, client_id):
    try:
        # Fetch the client data
        client = get_object_or_404(Client, pOwner=client_id)
        logger.info(f"Generating Excel for client: {client_id}")
        
        # Get inspection data from session
        inspection_data = request.session.get('inspection_data', {})
        
        # Load the template Excel file
        template_path = os.path.join(settings.BASE_DIR, 'docsAppR', 'templates', 'excel', '60_scope_form.xlsx')
        wb = load_workbook(template_path)
        
        # Select the ScopeCHLST sheet
        ws = wb['ScopeCHLST']
        
        # Map the inspection data to Excel cells
        #cell_mappings = SCOPE_FORM_MAPPINGS['client_info']
        checklist_mappings = SCOPE_FORM_MAPPINGS['checklist']
        
        # Client information
        #ws[cell_mappings['client_name']] = client.pOwner
        #ws[cell_mappings['client_address']] = getattr(client, 'pAddress', '')
        #ws[cell_mappings['date_of_loss']] = getattr(client, 'dateOfLoss', '')
        #ws[cell_mappings['claim_number']] = getattr(client, 'claimNumber', '')
        #ws[cell_mappings['room_name']] = inspection_data.get('room', '')
        
        # Map inspection checklist data
        checklist_mappings = {
            'CLG': 'C3',  # Ceiling
            'LIT': 'C4',  # Lighting
            'HVC': 'C5',  # HVAC
            'WAL': 'C6',  # Walls
            'ELE': 'C7',  # Electrical
            'FLR': 'C8',  # Floor
            'BB': 'C9',   # Baseboards
            'DOR': 'C10',  # Doors
            'WDW': 'C11',  # Windows
            'WDT': 'C12',  # Water Damage
        }
        
        # Fill in inspection data
        inspection = inspection_data.get('inspection', {})
        for key, cell in checklist_mappings.items():
            if key in inspection:
                ws[cell] = inspection[key]
        
        # Generate filename
        room_name = inspection_data.get('room', 'unknown_room')
        filename = f"scope_form_{client_id}_{room_name}.xlsx"
        
        # Create temporary directory for file conversion
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save Excel file to temp directory
            temp_excel_path = os.path.join(temp_dir, filename)
            wb.save(temp_excel_path)
            
            # Create PDF filename
            pdf_filename = f"scope_form_{client_id}_{room_name}.pdf"
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