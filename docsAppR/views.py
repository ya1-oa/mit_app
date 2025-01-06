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
from docsAppR.models import Claims
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa  # For xhtml2pdf
# from weasyprint import HTML  # Uncomment if using WeasyPrint


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
    allClients = Client.objects.all()
    abbrList = ["CLG", "LIT", "HVC", "MISC", "WAL", "ELE", "FLR", "BB", "MISC","DOR", "OPEN", "WDW", "WDT"]
    context = { 'clients' : allClients, : 'abbrList' : abbrList }

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


def generate_invoice_pdf(request, client_id):
    # Fetch the client data
    client = Client.objects.get(id=client_id)
    
    # Render the HTML template with the client context
    template_name = "account/createInvoice.html"
    context = {"client": client}
    html_content = render_to_string(template_name, context)
    
    # Generate the PDF
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename=Invoice_{client_id}.pdf"
    
    # Convert HTML to PDF using xhtml2pdf
    result = pisa.CreatePDF(html_content, dest=response)
    
    # Check for errors
    if result.err:
        return HttpResponse("An error occurred while generating the PDF.", status=500)

    return response
