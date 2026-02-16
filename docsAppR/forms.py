from typing import Any
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django import forms
from django.forms.widgets import PasswordInput, TextInput
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from .models import (
    CustomUser,
    Client,
    Document,
    Landlord,
    EmailSchedule,
    File,                # <-- add this
    Room, WorkType, RoomWorkTypeValue,  # if you use the room formset
)
from django.forms import inlineformset_factory
from django.utils import timezone

class CreateUserForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ['email', 'username']

class UploadFilesForm(forms.Form):
    title = forms.CharField()
    file = forms.FileField()

class UploadClientForm(forms.Form):
    #
    pOwner = forms.CharField()
    pAddress = forms.CharField()
    pCityStateZip = forms.CharField()
    cEmail = forms.CharField()
    cPhone = forms.CharField()
    coOwner2 = forms.CharField()
    cPhone2 = forms.CharField()
    cAddress2 = forms.CharField()
    cCityStateZip2 = forms.CharField()
    cEmail2 = forms.CharField()

    #Claim
    causeOfLoss = forms.CharField()
    dateOfLoss = forms.DateField()
    rebuildType1 = forms.CharField()
    rebuildType2 = forms.CharField()
    rebuildType3 = forms.CharField()
    demo = forms.BooleanField()
    mitigation = forms.BooleanField()
    otherStructures = forms.BooleanField()
    replacement = forms.BooleanField()
    CPSCLNCONCGN = forms.BooleanField()
    yearBuilt = forms.CharField()
    contractDate = forms.DateField()
    breathingIssue = forms.CharField()
    hazardMaterialRemediation = forms.CharField()

    #Insurance
    insuranceCoName = forms.CharField()
    insAddressOvernightMail = forms.CharField()
    insCityStateZip = forms.CharField()
    insuranceCoPhone = forms.CharField()
    insWebsite = forms.CharField()
    insMailingAddress = forms.CharField()
    insMailCityStateZip = forms.CharField()
    claimNumber = forms.CharField()
    policyNumber = forms.CharField()
    emailInsCo = forms.CharField()
    deskAdjusterDA = forms.CharField()
    DAPhone = forms.CharField()
    DAPhExtNumber = forms.CharField()
    DAEmail = forms.CharField()
    fieldAdjusterName = forms.CharField()
    phoneFieldAdj = forms.CharField()
    fieldAdjEmail = forms.CharField()
    adjContents = forms.CharField()
    adjCpsPhone = forms.CharField()
    adjCpsEmail = forms.CharField()
    emsAdj = forms.CharField()
    emsAdjPhone = forms.CharField()
    emsTmpEmail = forms.CharField()
    attLossDraftDept = forms.CharField()

    #Rooms
    newCustomerID = forms.CharField()
    roomID = forms.CharField()
    roomArea1 = forms.CharField()
    roomArea2 = forms.CharField()
    roomArea3 = forms.CharField()
    roomArea4 = forms.CharField()
    roomArea6 = forms.CharField()
    roomArea7 = forms.CharField()
    roomArea8 = forms.CharField()
    roomArea9 = forms.CharField()
    roomArea10 = forms.CharField()
    roomArea11 = forms.CharField()
    roomArea12 = forms.CharField()
    roomArea13 = forms.CharField()
    roomArea14 = forms.CharField()
    roomArea15 = forms.CharField()
    roomArea16 = forms.CharField()
    roomArea17 = forms.CharField()
    roomArea18 = forms.CharField()
    roomArea19 = forms.CharField()
    roomArea20 = forms.CharField()
    roomArea21 = forms.CharField()
    roomArea22 = forms.CharField()
    roomArea23 = forms.CharField()
    roomArea24 = forms.CharField()
    roomArea25 = forms.CharField()

    #Mortgage
    mortgageCo = forms.CharField()
    mortgageAccountCo = forms.CharField()
    mortgageContactPerson = forms.CharField()
    mortgagePhoneContact = forms.CharField()
    mortgagePhoneExtContact = forms.CharField()
    mortgageAttnLossDraftDept = forms.CharField()
    mortgageOverNightMail = forms.CharField()
    mortgageCityStZipOVN = forms.CharField()
    mortgageEmail = forms.CharField()
    mortgageWebsite = forms.CharField()
    mortgageCoFax = forms.CharField()
    mortgageMailingAddress = forms.CharField()
    mortgageInitialOfferPhase1ContractAmount = forms.CharField()

    #Cash Flow
    drawRequest = forms.CharField()

    #Contractor
    coName = forms.CharField()
    coWebsite = forms.CharField()
    coEmailstatus = forms.CharField()
    coAddress = forms.CharField()
    coCityState = forms.CharField()
    coAddress2 = forms.CharField()
    coCityState2 = forms.CharField()
    coCityState3 = forms.CharField()
    coLogo1 = forms.CharField()
    coLogo2 = forms.CharField()
    coLogo3 = forms.CharField()
    coRepPH = forms.CharField()
    coREPEmail = forms.CharField()
    coPhone2 = forms.CharField()
    TinW9 = forms.CharField()
    fedExAccount = forms.CharField()
    
    #Claim reporting
    claimReportDate = forms.DateField()
    insuranceCustomerServiceRep = forms.CharField()
    timeOfClaimReport = forms.CharField()
    phoneExt = forms.CharField()
    tarpExtTMPOk = forms.BooleanField()
    IntTMPOk = forms.BooleanField()
    DRYPLACUTOUTMOLDSPRAYOK = forms.BooleanField()
    
    #ALE
    lossOfUseALE = forms.CharField()
    tenantLesee = forms.CharField() #this is the info that the ALE needs to produce the lease
    propertyAddressStreet = forms.CharField()
    propertyCityStateZip = forms.CharField()
    customerEmail = forms.CharField()
    cstOwnerPhoneNumber = forms.CharField()
    causeOfLoss = forms.CharField()
    dateOfLoss = forms.DateField()
    contractDate = forms.DateField()
    insuranceCoName = forms.CharField()
    claimNumber = forms.CharField()
    policyClaimNumber = forms.CharField()
    emailInsCo = forms.CharField()
    deskAdjusterDA = forms.CharField()
    DAPhone = forms.CharField()
    DAPhExtNumber = forms.CharField()
    DAEmail = forms.CharField()
    startDate = forms.DateField()
    endDate = forms.DateField()
    lessor = forms.CharField()
    propertyAddressStreet = forms.CharField()
    propertyCityStateZip = forms.CharField()
    customerEmail = forms.CharField()
    cstOwnerPhoneNumber = forms.CharField()
    bedrooms = forms.CharField()
    termsAmount = forms.CharField()
    endDate = forms.DateField()


class ClientForm(forms.ModelForm):
    # nice datetime pickers
    dateOfLoss = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )
    contractDate = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )

    class Meta:
        model = Client
        # IMPORTANT: no roomArea* fields here anymore
        fields = [
            # Customer
            'pOwner', 'pAddress', 'pCityStateZip', 'cEmail', 'cPhone',
            'coOwner2', 'cPhone2', 'cAddress2', 'cCityStateZip2', 'cEmail2',

            # Claim
            'causeOfLoss', 'dateOfLoss', 'rebuildType1', 'rebuildType2', 'rebuildType3',
            'demo', 'mitigation', 'otherStructures', 'replacement', 'CPSCLNCONCGN',
            'yearBuilt', 'contractDate', 'breathingIssue', 'hazardMaterialRemediation',

            # Insurance (match the actual model field names)
            'insuranceCo_Name', 'insAddressOvernightMail', 'insCityStateZip', 'insuranceCoPhone',
            'insWebsite', 'insMailingAddress', 'insMailCityStateZip', 'claimNumber', 'policyNumber',
            'emailInsCo', 'deskAdjusterDA', 'DAPhone', 'DAPhExt', 'DAEmail', 'fieldAdjusterName',
            'phoneFieldAdj', 'fieldAdjEmail', 'adjContents', 'adjCpsPhone', 'adjCpsEmail',
            'emsAdj', 'emsAdjPhone', 'emsTmpEmail', 'attLossDraftDept',

            # IDs you already had
            'newCustomerID', 'roomID',

            # Mortgage
            'mortgageCo', 'mortgageAccountCo', 'mortgageContactPerson', 'mortgagePhoneContact',
            'mortgagePhoneExtContact', 'mortgageAttnLossDraftDept', 'mortgageOverNightMail',
            'mortgageCityStZipOVN', 'mortgageEmail', 'mortgageWebsite', 'mortgageCoFax',
            'mortgageMailingAddress', 'drawRequest',

            # Contractor
            'coName', 'coWebsite', 'coEmailstatus', 'coAddress', 'coCityState', 'coAddress2',
            'coCityState2', 'coCityState3', 'coLogo1', 'coLogo2', 'coLogo3', 'coRepPH', 'coREPEmail',
            'coPhone2', 'TinW9', 'fedExAccount',

            # Claim reporting
            'claimReportDate', 'insuranceCustomerServiceRep', 'timeOfClaimReport', 'phoneExt',
            'tarpExtTMPOk', 'IntTMPOk', 'DRYPLACUTOUTMOLDSPRAYOK',

            # ALE - Comprehensive Fields (updated to match new model fields)
            'lossOfUseALE',
            # Lessee Info
            'ale_lessee_name', 'ale_lessee_home_address', 'ale_lessee_city_state_zip',
            'ale_lessee_email', 'ale_lessee_phone',
            # Rental Info
            'ale_rental_bedrooms', 'ale_rental_months', 'ale_rental_start_date',
            'ale_rental_end_date', 'ale_rental_amount_per_month',
            # Lessor Info
            'ale_lessor_name', 'ale_lessor_leased_address', 'ale_lessor_city_zip',
            'ale_lessor_phone', 'ale_lessor_email', 'ale_lessor_mailing_address',
            'ale_lessor_mailing_city_zip', 'ale_lessor_contact_person',
            # Real Estate Company
            'ale_re_company_name', 'ale_re_mailing_address', 'ale_re_city_zip',
            'ale_re_contact_person', 'ale_re_phone', 'ale_re_email',
            'ale_re_owner_broker_name', 'ale_re_owner_broker_phone', 'ale_re_owner_broker_email',
        ]


# ---- ROOMS + WORK TYPES ----
class RoomWithWorkTypesForm(forms.ModelForm):
    """
    A Room form that dynamically adds one ChoiceField per WorkType:
    wt_100, wt_200, ... with choices = Room.LOS_TRAVEL_CHOICES
    Saving the form updates/creates RoomWorkTypeValue rows for that room.
    """
    class Meta:
        model = Room
        fields = ['room_name', 'sequence']
        widgets = {
            'sequence': forms.NumberInput(attrs={'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        # instance is a Room (may be unsaved when creating)
        super().__init__(*args, **kwargs)

        # add dynamic fields for every WorkType
        work_types = WorkType.objects.all().order_by('work_type_id')

        # pre-load existing values (if room exists)
        existing = {}
        if self.instance and self.instance.pk:
            existing_qs = self.instance.work_type_values.select_related('work_type')
            existing = {
                wtv.work_type.work_type_id: wtv.value_type
                for wtv in existing_qs
            }

        for wt in work_types:
            field_name = f'wt_{wt.work_type_id}'
            self.fields[field_name] = forms.ChoiceField(
                label=f'{wt.work_type_id} – {wt.name}',
                choices=Room.LOS_TRAVEL_CHOICES,
                required=False,
                initial=existing.get(wt.work_type_id, 'NA'),
                widget=forms.Select(attrs={'class': 'form-select'})
            )

    def save(self, commit=True):
        room = super().save(commit=commit)

        # Ensure we have a saved room before touching related values
        if commit and room.pk:
            work_types = WorkType.objects.all()
            for wt in work_types:
                field_name = f'wt_{wt.work_type_id}'
                value = self.cleaned_data.get(field_name) or 'NA'
                obj, _created = RoomWorkTypeValue.objects.get_or_create(
                    room=room,
                    work_type=wt,
                    defaults={'value_type': value}
                )
                if obj.value_type != value:
                    obj.value_type = value
                    obj.save()

        # If commit=False, caller must persist both room and values later
        return room

RoomFormSet = inlineformset_factory(
    parent_model=Client,
    model=Room,
    form=RoomWithWorkTypesForm,
    fields=['room_name', 'sequence'],
    extra=1,
    can_delete=True,
)


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['name', 'category', 'document_type', 'file', 'description', 'claim']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Additional validation if needed
            if file.size > 10 * 1024 * 1024:  # 10MB limit
                raise forms.ValidationError("File too large (max 10MB)")
        return file


class LandlordForm(forms.ModelForm):
    class Meta:
        model = Landlord
        fields = '__all__'
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'property_address': forms.Textarea(attrs={'rows': 3}),
            'term_start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'term_end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'lease_special_notes': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Enter any special instructions or notes for this lease...'}),
        }
        labels = {
            'contact_person_1': "Lessor Contact Person",
            'contact_person_2': "Lessor Contact Person 2",
            'contact_phone': "Lessor Contact Phone#",
            'contact_email': "Lessor Contact Person Email",
            'real_estate_company': "Real Estate Company",
            'company_contact_person': "Real Estate Contact Person",
            'broker_name': "Owner/Broker",
            'term_start_date': "Lease Start Date",
            'term_end_date': "Lease End Date",
            'lease_special_notes': "Special Lease Instructions/Notes",
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to all fields
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
        

class EmailForm(forms.Form):
    # Use your existing models
    documents = forms.ModelMultipleChoiceField(
        queryset=Document.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    attachments = forms.ModelMultipleChoiceField(
        queryset=File.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Optional raw files to attach"
    )

    recipients = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Enter email addresses separated by commas',
            'rows': 3
        }),
        help_text="Separate multiple emails with commas"
    )
    subject = forms.CharField(max_length=255)
    body = forms.CharField(widget=forms.Textarea(attrs={'rows': 6}))

    # Immediate vs scheduled send
    send_now = forms.BooleanField(initial=True, required=False)
    scheduled_time = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text="Leave empty to send immediately"
    )

    # Open tracking
    notify_on_open = forms.BooleanField(
        initial=True,
        required=False,
        help_text="Send notification to admin when email is opened"
    )
    admin_notification_email = forms.EmailField(
        required=False,
        help_text="Email to receive open notifications"
    )

    # ---- validation helpers ----
    def clean_recipients(self):
        raw = self.cleaned_data['recipients']
        emails = [e.strip() for e in raw.split(',') if e.strip()]
        for e in emails:
            try:
                validate_email(e)
            except ValidationError:
                raise ValidationError(f"Invalid email address: {e}")
        # Return a list so the view can store directly to a JSONField
        return emails

    def clean(self):
        cleaned = super().clean()

        # If not sending now, require a scheduled time
        send_now = cleaned.get('send_now')
        scheduled_time = cleaned.get('scheduled_time')
        if not send_now and not scheduled_time:
            raise ValidationError("Please provide a scheduled time if 'Send now' is unchecked.")

        # If tracking is enabled, require an admin email
        notify_on_open = cleaned.get('notify_on_open')
        admin_email = cleaned.get('admin_notification_email')
        if notify_on_open and not admin_email:
            raise ValidationError("Admin notification email is required when open tracking is enabled.")

        return cleaned


class EmailScheduleForm(forms.ModelForm):
    # Textarea to collect comma-separated emails, then we validate -> list for JSONField
    recipients = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Enter email addresses separated by commas',
            'rows': 3
        }),
        help_text="Separate multiple emails with commas"
    )

    class Meta:
        model = EmailSchedule
        fields = [
            'name', 'subject', 'body', 'recipients',
            'documents', 'attachments',
            'start_date', 'interval', 'custom_interval_days', 'repeat_count',
            'notify_on_open', 'admin_notification_email'
        ]
        widgets = {
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'interval': forms.Select(attrs={'id': 'interval-select'}),
            'documents': forms.CheckboxSelectMultiple,
            'attachments': forms.CheckboxSelectMultiple,
        }

    def clean_recipients(self):
        raw = self.cleaned_data['recipients']
        emails = [e.strip() for e in raw.split(',') if e.strip()]
        for e in emails:
            try:
                validate_email(e)
            except ValidationError:
                raise ValidationError(f"Invalid email address: {e}")
        # Return a list so the model's JSONField can accept it
        return emails

    def clean(self):
        cleaned = super().clean()

        interval = cleaned.get('interval')
        custom_days = cleaned.get('custom_interval_days')
        notify_on_open = cleaned.get('notify_on_open')
        admin_email = cleaned.get('admin_notification_email')

        if interval == 'custom' and not custom_days:
            raise ValidationError("Custom interval days is required for the custom interval.")

        if interval != 'custom':
            # normalize: clear custom days when not used
            cleaned['custom_interval_days'] = None

        if notify_on_open and not admin_email:
            raise ValidationError("Admin notification email is required when open tracking is enabled.")

        return cleaned


# ==================== OneDrive Claim Creation Forms ====================

class OneDriveClientForm(forms.ModelForm):
    """Complete form for OneDrive claim creation workflow with ALL fields"""

    # Date pickers (no time component)
    dateOfLoss = forms.DateField(
        required=False,
        label='Date of Loss',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    contractDate = forms.DateField(
        required=False,
        label='Contract Date',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    claimReportDate = forms.DateField(
        required=False,
        label='Claim Report Date',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    startDate = forms.DateField(
        required=False,
        label='ALE Start Date',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    endDate = forms.DateField(
        required=False,
        label='ALE End Date',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    ale_rental_start_date = forms.DateField(
        required=False,
        label='Rental Start Date',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    ale_rental_end_date = forms.DateField(
        required=False,
        label='Rental End Date',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    class Meta:
        model = Client
        fields = [
            # Customer
            'pOwner', 'pAddress', 'pCityStateZip', 'cEmail', 'cPhone',
            'coOwner2', 'cPhone2', 'cAddress2', 'cCityStateZip2', 'cEmail2',

            # Claim
            'causeOfLoss', 'dateOfLoss', 'rebuildType1', 'rebuildType2', 'rebuildType3',
            'demo', 'mitigation', 'otherStructures', 'replacement', 'CPSCLNCONCGN',
            'yearBuilt', 'contractDate', 'breathingIssue', 'hazardMaterialRemediation',

            # Insurance
            'insuranceCo_Name', 'insAddressOvernightMail', 'insCityStateZip', 'insuranceCoPhone',
            'insWebsite', 'insMailingAddress', 'insMailCityStateZip', 'claimNumber', 'policyNumber',
            'emailInsCo', 'deskAdjusterDA', 'DAPhone', 'DAPhExt', 'DAEmail', 'fieldAdjusterName',
            'phoneFieldAdj', 'fieldAdjEmail', 'adjContents', 'adjCpsPhone', 'adjCpsEmail',
            'emsAdj', 'emsAdjPhone', 'emsTmpEmail', 'attLossDraftDept',

            # IDs
            'newCustomerID', 'roomID',

            # Mortgage
            'mortgageCo', 'mortgageAccountCo', 'mortgageContactPerson', 'mortgagePhoneContact',
            'mortgagePhoneExtContact', 'mortgageAttnLossDraftDept', 'mortgageOverNightMail',
            'mortgageCityStZipOVN', 'mortgageEmail', 'mortgageWebsite', 'mortgageCoFax',
            'mortgageMailingAddress', 'drawRequest',

            # Contractor
            'coName', 'coWebsite', 'coEmailstatus', 'coAddress', 'coCityState', 'coAddress2',
            'coCityState2', 'coCityState3', 'coLogo1', 'coLogo2', 'coLogo3', 'coRepPH', 'coREPEmail',
            'coPhone2', 'TinW9', 'fedExAccount',

            # Claim reporting
            'claimReportDate', 'insuranceCustomerServiceRep', 'timeOfClaimReport', 'phoneExt',
            'tarpExtTMPOk', 'IntTMPOk', 'DRYPLACUTOUTMOLDSPRAYOK',

            # ALE - Comprehensive Fields
            'lossOfUseALE',
            # Lessee Info
            'ale_lessee_name', 'ale_lessee_home_address', 'ale_lessee_city_state_zip',
            'ale_lessee_email', 'ale_lessee_phone',
            # Rental Info
            'ale_rental_bedrooms', 'ale_rental_months', 'ale_rental_start_date',
            'ale_rental_end_date', 'ale_rental_amount_per_month',
            # Lessor Info
            'ale_lessor_name', 'ale_lessor_leased_address', 'ale_lessor_city_zip',
            'ale_lessor_phone', 'ale_lessor_email', 'ale_lessor_mailing_address',
            'ale_lessor_mailing_city_zip', 'ale_lessor_contact_person',
            # Real Estate Company
            'ale_re_company_name', 'ale_re_mailing_address', 'ale_re_city_zip',
            'ale_re_contact_person', 'ale_re_phone', 'ale_re_email',
            'ale_re_owner_broker_name', 'ale_re_owner_broker_phone', 'ale_re_owner_broker_email',
        ]

        labels = {
            # Customer
            'pOwner': 'Primary Owner Name',
            'pAddress': 'Property Address',
            'pCityStateZip': 'City, State, ZIP',
            'cEmail': 'Email Address',
            'cPhone': 'Phone Number',
            'coOwner2': 'Co-Owner Name',
            'cPhone2': 'Co-Owner Phone',
            'cAddress2': 'Co-Owner Address',
            'cCityStateZip2': 'Co-Owner City, State, ZIP',
            'cEmail2': 'Co-Owner Email',

            # Claim
            'causeOfLoss': 'Cause of Loss',
            'rebuildType1': 'Rebuild Type 1',
            'rebuildType2': 'Rebuild Type 2',
            'rebuildType3': 'Rebuild Type 3',
            'demo': 'Demo Required',
            'mitigation': 'Mitigation Required',
            'otherStructures': 'Other Structures',
            'replacement': 'Replacement',
            'CPSCLNCONCGN': 'CPS/Clean/Content/General',
            'yearBuilt': 'Year Built',
            'breathingIssue': 'Breathing Issue',
            'hazardMaterialRemediation': 'Hazardous Material Remediation',

            # Insurance
            'insuranceCo_Name': 'Insurance Company Name',
            'insAddressOvernightMail': 'Overnight Mail Address',
            'insCityStateZip': 'City, State, ZIP',
            'insuranceCoPhone': 'Insurance Company Phone',
            'insWebsite': 'Insurance Website',
            'insMailingAddress': 'Mailing Address',
            'insMailCityStateZip': 'Mailing City, State, ZIP',
            'claimNumber': 'Claim Number',
            'policyNumber': 'Policy Number',
            'emailInsCo': 'Insurance Company Email',
            'deskAdjusterDA': 'Desk Adjuster Name',
            'DAPhone': 'Desk Adjuster Phone',
            'DAPhExt': 'Desk Adjuster Extension',
            'DAEmail': 'Desk Adjuster Email',
            'fieldAdjusterName': 'Field Adjuster Name',
            'phoneFieldAdj': 'Field Adjuster Phone',
            'fieldAdjEmail': 'Field Adjuster Email',
            'adjContents': 'Contents Adjuster',
            'adjCpsPhone': 'CPS Adjuster Phone',
            'adjCpsEmail': 'CPS Adjuster Email',
            'emsAdj': 'EMS Adjuster',
            'emsAdjPhone': 'EMS Adjuster Phone',
            'emsTmpEmail': 'EMS Temp Email',
            'attLossDraftDept': 'Attention Loss Draft Department',

            # IDs
            'newCustomerID': 'Customer ID',
            'roomID': 'Room ID',

            # Mortgage
            'mortgageCo': 'Mortgage Company',
            'mortgageAccountCo': 'Mortgage Account Number',
            'mortgageContactPerson': 'Mortgage Contact Person',
            'mortgagePhoneContact': 'Mortgage Phone',
            'mortgagePhoneExtContact': 'Mortgage Phone Extension',
            'mortgageAttnLossDraftDept': 'Attention Loss Draft Department',
            'mortgageOverNightMail': 'Overnight Mail Address',
            'mortgageCityStZipOVN': 'City, State, ZIP',
            'mortgageEmail': 'Mortgage Email',
            'mortgageWebsite': 'Mortgage Website',
            'mortgageCoFax': 'Mortgage Fax',
            'mortgageMailingAddress': 'Mailing Address',
            'drawRequest': 'Draw Request',

            # Contractor
            'coName': 'Contractor Name',
            'coWebsite': 'Contractor Website',
            'coEmailstatus': 'Contractor Email',
            'coAddress': 'Contractor Address',
            'coCityState': 'Contractor City, State',
            'coAddress2': 'Contractor Address 2',
            'coCityState2': 'Contractor City, State 2',
            'coCityState3': 'Contractor City, State 3',
            'coLogo1': 'Contractor Logo 1',
            'coLogo2': 'Contractor Logo 2',
            'coLogo3': 'Contractor Logo 3',
            'coRepPH': 'Contractor Rep Phone',
            'coREPEmail': 'Contractor Rep Email',
            'coPhone2': 'Contractor Phone 2',
            'TinW9': 'TIN/W9',
            'fedExAccount': 'FedEx Account',

            # Claim Reporting
            'insuranceCustomerServiceRep': 'Customer Service Representative',
            'timeOfClaimReport': 'Time of Claim Report',
            'phoneExt': 'Phone Extension',
            'tarpExtTMPOk': 'Tarp Ext/TMP Approved',
            'IntTMPOk': 'Int TMP Approved',
            'DRYPLACUTOUTMOLDSPRAYOK': 'Dry Place/Cutout/Mold Spray Approved',

            # ALE - Comprehensive Labels
            'lossOfUseALE': 'Loss of Use/ALE',
            # Lessee Info
            'ale_lessee_name': 'Lessee/Tenant Name',
            'ale_lessee_home_address': 'Lessee Home Address',
            'ale_lessee_city_state_zip': 'Lessee City, State, ZIP',
            'ale_lessee_email': 'Lessee Email',
            'ale_lessee_phone': 'Lessee Phone Number',
            # Rental Info
            'ale_rental_bedrooms': 'Number of Bedrooms',
            'ale_rental_months': 'Number of Months',
            'ale_rental_start_date': 'Rental Start Date',
            'ale_rental_end_date': 'Rental End Date',
            'ale_rental_amount_per_month': 'Amount Per Month',
            # Lessor Info
            'ale_lessor_name': 'Lessor Name',
            'ale_lessor_leased_address': 'Leased Property Address',
            'ale_lessor_city_zip': 'Lessor City, ZIP',
            'ale_lessor_phone': 'Lessor Phone',
            'ale_lessor_email': 'Lessor Email',
            'ale_lessor_mailing_address': 'Lessor Mailing Address',
            'ale_lessor_mailing_city_zip': 'Lessor Mailing City, ZIP',
            'ale_lessor_contact_person': 'Lessor Contact Person',
            # Real Estate Company
            'ale_re_company_name': 'Real Estate Company',
            'ale_re_mailing_address': 'RE Mailing Address',
            'ale_re_city_zip': 'RE City, ZIP',
            'ale_re_contact_person': 'RE Contact Person',
            'ale_re_phone': 'RE Company Phone',
            'ale_re_email': 'RE Company Email',
            'ale_re_owner_broker_name': 'Owner/Broker Name',
            'ale_re_owner_broker_phone': 'Owner/Broker Phone',
            'ale_re_owner_broker_email': 'Owner/Broker Email',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to all fields
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'


class RoomSelectionForm(forms.Form):
    """Form for selecting a source claim to load rooms from"""

    source_claim = forms.ModelChoiceField(
        queryset=Client.objects.all().order_by('-created_at'),
        required=False,
        empty_label="Select a claim to copy rooms from...",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_source_claim'
        }),
        label='Load rooms from existing claim'
    )

    def __init__(self, *args, **kwargs):
        exclude_client_id = kwargs.pop('exclude_client_id', None)
        super().__init__(*args, **kwargs)

        if exclude_client_id:
            self.fields['source_claim'].queryset = self.fields['source_claim'].queryset.exclude(
                id=exclude_client_id
            )


class BulkWorkTypeForm(forms.Form):
    """Form for applying work types to all rooms at once (100s series)"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Get all work types that apply to all rooms (100s series)
        bulk_work_types = WorkType.objects.filter(
            applies_to_all_rooms=True,
            is_active=True
        ).order_by('display_order')

        # Create a select field for each bulk work type
        for wt in bulk_work_types:
            field_name = f'bulk_wt_{wt.work_type_id}'
            self.fields[field_name] = forms.ChoiceField(
                choices=[
                    ('', '---'),
                    ('NA', 'NA'),
                    ('LOS', 'LOS'),
                    ('TRAVEL', 'TRAVEL'),
                ],
                required=False,
                widget=forms.Select(attrs={
                    'class': 'form-select form-select-sm'
                }),
                label=f'WT{wt.work_type_id}'
            )