from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.forms import ModelForm
import os
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.conf import settings

class CustomUserManager(BaseUserManager):
    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        if not email:
            raise ValueError("The given email must be set")     
           
        email = self.normalize_email(email)

        user = self.model(email=email, **extra_fields)

        user.set_password(password)

        user.save(using=self._db)

        return user
    
    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)
    
    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(
                "Superuser must have is_staff=True."
            )
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(
                "Superuser must have is_superuser=True."
            )
        return self._create_user(email, password, **extra_fields)
    
class CustomUser(AbstractUser):
    email = models.EmailField("email", unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = CustomUserManager()

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='customuser_set',
        related_query_name='customuser',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='customuser_set',
        related_query_name='customuser',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def __str__(self):
        return self.email

    def __str__(self):
        return self.username    
     
class Client(models.Model):
    #Customer
    pOwner = models.CharField(max_length=255, blank=True)
    pAddress = models.CharField(max_length=255, blank=True)
    pCityStateZip = models.CharField(max_length=255, blank=True)
    cEmail = models.CharField(max_length=255, blank=True)
    cPhone = models.CharField(max_length=255, blank=True)
    coOwner2 = models.CharField(max_length=255, blank=True)
    cPhone2 = models.CharField(max_length=255, blank=True)
    cAddress2 = models.CharField(max_length=255, blank=True)
    cCityStateZip2 = models.CharField(max_length=255, blank=True)
    cEmail2 = models.CharField(max_length=255, blank=True)

    #Claim
    causeOfLoss = models.CharField(max_length=255, blank=True)
    dateOfLoss = models.DateTimeField(blank=True)
    rebuildType1 = models.CharField(max_length=255, blank=True)
    rebuildType2 = models.CharField(max_length=255, blank=True)
    rebuildType3 = models.CharField(max_length=255, blank=True)
    demo = models.BooleanField(default=False)
    mitigation = models.BooleanField(default=False)
    otherStructures = models.BooleanField(default=False)
    replacement = models.BooleanField(default=False)
    CPSCLNCONCGN = models.BooleanField(default=False)
    yearBuilt = models.CharField(max_length=255, blank=True)
    contractDate = models.DateTimeField(null=True)
    lossOfUse = models.CharField(max_length=255, blank=True)
    breathingIssue = models.CharField(max_length=255, blank=True)
    hazardMaterialRemediation = models.CharField(max_length=255, blank=True)

    #Insurance
    insuranceCo_Name = models.CharField(max_length=255, blank=True)
    insAddressOvernightMail = models.CharField(max_length=255, blank=True)
    insCityStateZip = models.CharField(max_length=255, blank=True)
    insuranceCoPhone = models.CharField(max_length=255, blank=True)
    insWebsite = models.CharField(max_length=255, blank=True)
    insMailingAddress = models.CharField(max_length=255, blank=True)
    insMailCityStateZip = models.CharField(max_length=255, blank=True)
    claimNumber = models.CharField(max_length=255, blank=True)
    policyNumber = models.CharField(max_length=255, blank=True)
    emailInsCo = models.CharField(max_length=255, blank=True)
    deskAdjusterDA = models.CharField(max_length=255, blank=True)
    DAPhone = models.CharField(max_length=255, blank=True)
    DAPhExt = models.CharField(max_length=255, blank=True)
    DAEmail = models.CharField(max_length=255, blank=True)
    fieldAdjusterName = models.CharField(max_length=255, blank=True)
    phoneFieldAdj = models.CharField(max_length=255, blank=True)
    fieldAdjEmail = models.CharField(max_length=255, blank=True)
    adjContents = models.CharField(max_length=255, blank=True)
    adjCpsPhone = models.CharField(max_length=255, blank=True)
    adjCpsEmail = models.CharField(max_length=255, blank=True)
    emsAdj = models.CharField(max_length=255, blank=True)
    emsAdjPhone = models.CharField(max_length=255, blank=True)
    emsTmpEmail = models.CharField(max_length=255, blank=True)
    attLossDraftDept = models.CharField(max_length=255, blank=True)

    #Rooms
    newCustomerID = models.CharField(max_length=255, blank=True)
    roomID = models.CharField(max_length=255, blank=True)
    roomArea1 = models.CharField(max_length=255, blank=True)
    roomArea2 = models.CharField(max_length=255, blank=True)
    roomArea3 = models.CharField(max_length=255, blank=True)
    roomArea4 = models.CharField(max_length=255, blank=True)
    roomArea5 = models.CharField(max_length=255, blank=True)
    roomArea6 = models.CharField(max_length=255, blank=True)
    roomArea7 = models.CharField(max_length=255, blank=True)
    roomArea8 = models.CharField(max_length=255, blank=True)
    roomArea9 = models.CharField(max_length=255, blank=True)
    roomArea10 = models.CharField(max_length=255, blank=True)
    roomArea11 = models.CharField(max_length=255, blank=True)
    roomArea12 = models.CharField(max_length=255, blank=True)
    roomArea13 = models.CharField(max_length=255, blank=True)
    roomArea14 = models.CharField(max_length=255, blank=True)
    roomArea15 = models.CharField(max_length=255, blank=True)
    roomArea16 = models.CharField(max_length=255, blank=True)
    roomArea17 = models.CharField(max_length=255, blank=True)
    roomArea18 = models.CharField(max_length=255, blank=True)
    roomArea19 = models.CharField(max_length=255, blank=True)
    roomArea20 = models.CharField(max_length=255, blank=True)
    roomArea21 = models.CharField(max_length=255, blank=True)
    roomArea22 = models.CharField(max_length=255, blank=True)
    roomArea23 = models.CharField(max_length=255, blank=True)
    roomArea24 = models.CharField(max_length=255, blank=True)
    roomArea25 = models.CharField(max_length=255, blank=True)

    #Mortgage
    mortgageCo = models.CharField(max_length=255, blank=True)
    mortgageAccountCo = models.CharField(max_length=255, blank=True)
    mortgageContactPerson = models.CharField(max_length=255, blank=True)
    mortgagePhoneContact = models.CharField(max_length=255, blank=True)
    mortgagePhoneExtContact = models.CharField(max_length=255, blank=True)
    mortgageAttnLossDraftDept = models.CharField(max_length=255, blank=True)
    mortgageOverNightMail = models.CharField(max_length=255, blank=True)
    mortgageCityStZipOVN = models.CharField(max_length=255, blank=True)
    mortgageEmail = models.CharField(max_length=255, blank=True)
    mortgageWebsite = models.CharField(max_length=255, blank=True)
    mortgageCoFax = models.CharField(max_length=255, blank=True)
    mortgageMailingAddress = models.CharField(max_length=255, blank=True)
    mortgageInitialOfferPhase1ContractAmount = models.CharField(max_length=255, blank=True)

    #Cash Flow
    drawRequest = models.CharField(max_length=255, blank=True)

    #Contractor
    coName = models.CharField(max_length=255, blank=True)
    coWebsite = models.CharField(max_length=255, blank=True)
    coEmailstatus = models.CharField(max_length=255, blank=True)
    coAddress = models.CharField(max_length=255, blank=True)
    coCityState = models.CharField(max_length=255, blank=True)
    coAddress2 = models.CharField(max_length=255, blank=True)
    coCityState2 = models.CharField(max_length=255, blank=True)
    coCityState3 = models.CharField(max_length=255, blank=True)
    coLogo1 = models.CharField(max_length=255, blank=True)
    coLogo2 = models.CharField(max_length=255, blank=True)
    coLogo3 = models.CharField(max_length=255, blank=True)
    coRepPH = models.CharField(max_length=255, blank=True)
    coREPEmail = models.CharField(max_length=255, blank=True)
    coPhone2 = models.CharField(max_length=255, blank=True)
    TinW9 = models.CharField(max_length=255, blank=True)
    fedExAccount = models.CharField(max_length=255, blank=True)
    
    #Claim reporting
    claimReportDate = models.DateTimeField(null=True)
    insuranceCustomerServiceRep = models.CharField(max_length=255, blank=True)
    timeOfClaimReport = models.CharField(max_length=255, blank=True)
    phoneExt = models.CharField(max_length=255, blank=True)
    tarpExtTMPOk = models.BooleanField(default=False)
    IntTMPOk = models.BooleanField(default=False)
    DRYPLACUTOUTMOLDSPRAYOK = models.BooleanField(default=False)
    
    #ALE
    lossOfUseALE = models.CharField(max_length=255, blank=True) #boolean field, if yes displaty form for lessor info
    tenantLesee = models.CharField(max_length=255, blank=True)
    propertyAddressStreet = models.CharField(max_length=255, blank=True)
    propertyCityStateZip = models.CharField(max_length=255, blank=True)
    customerEmail = models.CharField(max_length=255, blank=True)
    cstOwnerPhoneNumber = models.CharField(max_length=255, blank=True)
    causeOfLoss = models.CharField(max_length=255, blank=True)
    dateOfLoss = models.DateTimeField(null=True)
    contractDate = models.DateTimeField(null=True)
    insuranceCoName = models.CharField(max_length=255, blank=True)
    claimNumber = models.CharField(max_length=255, blank=True)
    policyClaimNumber = models.CharField(max_length=255, blank=True)
    emailInsCo = models.CharField(max_length=255, blank=True)
    deskAdjusterDA = models.CharField(max_length=255, blank=True)
    DAPhone = models.CharField(max_length=255, blank=True)
    DAPhExtNumber = models.CharField(max_length=255, blank=True)
    DAEmail = models.CharField(max_length=255, blank=True)
    startDate = models.DateTimeField(null=True)
    endDate = models.DateTimeField(null=True)
    lessor = models.CharField(max_length=255, blank=True)
    propertyAddressStreet = models.CharField(max_length=255, blank=True)
    propertyCityStateZip = models.CharField(max_length=255, blank=True)
    customerEmail = models.CharField(max_length=255, blank=True)
    cstOwnerPhoneNumber = models.CharField(max_length=255, blank=True)
    bedrooms = models.CharField(max_length=255, blank=True)
    termsAmount = models.CharField(max_length=255, blank=True)
    completion_percent = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def update_completion_stats(self):
        """Calculate and update completion percentages"""
        from .models import ChecklistItem  # Avoid circular import
        
        # Get all checklist items for this client
        items = self.checklist_items.all()
        total_items = items.count()
        completed_items = items.filter(is_completed=True).count()
        
        # Calculate overall completion
        self.completion_percent = int((completed_items / total_items * 100) if total_items > 0 else 0)
        
        # Calculate completion by category
        self.category_completion = {
            'MIT': self._calculate_category_completion('MIT'),
            'CPS': self._calculate_category_completion('CPS'),
            'PPR': self._calculate_category_completion('PPR')
        }
        self.save()
    
    def _calculate_category_completion(self, category):
        items = self.checklist_items.filter(document_category=category)
        total = items.count()
        completed = items.filter(is_completed=True).count()
        return int((completed / total * 100) if total > 0 else 0)

    def __str__(self):
        return self.pOwner    
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from .signals import create_checklist_items_for_client
        create_checklist_items_for_client(self)

# each file is linked to a customer ID, and it provides a path to the file on the server
class File(models.Model):
    filename = models.CharField(max_length=255)
    size = models.IntegerField()
    file = models.FileField(upload_to="documents/%Y/%m/%d/")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.filename
    
    def delete(self, *args, **kwargs):
        # Delete the file from storage when model is deleted
        if self.file:
            if os.path.isfile(self.file.path):
                os.remove(self.file.path)
        super().delete(*args, **kwargs)
    
    def get_file_extension(self):
        return os.path.splitext(self.filename)[1]
    
    def get_file_size_display(self):
        """Returns human-readable file size"""
        size = self.size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

class Landlord(models.Model):
    # Basic Information
    full_name = models.CharField(max_length=100, verbose_name="Lessor Legal Name", blank=True, null=True)
    address = models.TextField(verbose_name="Lessor Mailing Address", blank=True, null=True)
    city = models.CharField(max_length=50, verbose_name="Lessor City", blank=True, null=True)
    state = models.CharField(max_length=2, verbose_name="Lessor State", blank=True, null=True)
    zip_code = models.CharField(max_length=10, verbose_name="Lessor Zip Code", blank=True, null=True)
    phone = models.CharField(max_length=20, verbose_name="Lessor Primary Phone", blank=True, null=True)
    email = models.EmailField(verbose_name="Lessor Email Address", blank=True, null=True)

    # Rental Property Information
    property_address = models.TextField(verbose_name="Rental Property Address", blank=True, null=True)
    property_city = models.CharField(max_length=50, verbose_name="Rental Property City", blank=True, null=True)
    property_state = models.CharField(max_length=2, verbose_name="Rental Property State", blank=True, null=True)
    property_zip = models.CharField(max_length=10, verbose_name="Rental Property Zip", blank=True, null=True)
    term_start_date = models.DateField(verbose_name="Rental Term Start Date", null=True)
    term_end_date = models.DateField(verbose_name="Rental Term End Date", null=True)
    
    # Agreement Defaults
    default_rent_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    default_security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    default_rent_due_day = models.PositiveSmallIntegerField(default=1)
    default_late_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    default_late_fee_start_day = models.PositiveSmallIntegerField(default=5)
    default_eviction_day = models.PositiveSmallIntegerField(default=10)
    default_nsf_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    default_max_occupants = models.PositiveSmallIntegerField(default=10)
    default_parking_spaces = models.PositiveSmallIntegerField(default=2)
    default_parking_fee = models.PositiveSmallIntegerField(default=0)
    default_inspection_fee = models.DecimalField(max_digits=10, decimal_places=2, default=300.00)
    bedrooms = models.PositiveSmallIntegerField(default=1)
    rental_months = models.PositiveSmallIntegerField(blank=True, null=True)
    
    contact_person_1 = models.CharField(
        max_length=100, 
        verbose_name="Lessor Contact Person",
        blank=True, 
        null=True
    )
    contact_person_2 = models.CharField(
        max_length=100, 
        verbose_name="Lessor Second Contact Person",
        blank=True, 
        null=True
    )
    contact_phone = models.CharField(
        max_length=20, 
        verbose_name="Contact Phone Number",
        blank=True, 
        null=True
    )
    contact_email = models.EmailField(
        verbose_name="Lessor Contact Email Address",
        blank=True, 
        null=True
    )
    
    # Real Estate Company Information (Added Fields)
    real_estate_company = models.CharField(
        max_length=100, 
        verbose_name="Real Estate Company Name",
        blank=True, 
        null=True
    )
    company_mailing_address = models.TextField(
        verbose_name="Company Mailing Address",
        blank=True, 
        null=True
    )
    company_city = models.CharField(
        max_length=50,
        blank=True, 
        null=True
    )
    company_state = models.CharField(
        max_length=2,
        blank=True, 
        null=True
    )
    company_zip = models.CharField(
        max_length=10,
        blank=True, 
        null=True
    )
    company_contact_person = models.CharField(
        max_length=100,
        verbose_name="Company Contact Person",
        blank=True, 
        null=True
    )
    company_phone = models.CharField(
        max_length=20,
        verbose_name="Company Phone Number",
        blank=True, 
        null=True
    )
    company_email = models.EmailField(
        verbose_name="Company Email Address",
        blank=True, 
        null=True
    )
    broker_name = models.CharField(
        max_length=100,
        verbose_name="Owner/Broker Name",
        blank=True, 
        null=True
    )
    broker_phone = models.CharField(
        max_length=20,
        verbose_name="Broker Phone Number",
        blank=True, 
        null=True
    )
    broker_email = models.EmailField(
        verbose_name="Broker Email Address",
        blank=True, 
        null=True
    )


    # Meta Information
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.full_name} - {self.property_address}"
    
    @property
    def company_full_address(self):
        return f"{self.company_mailing_address}, {self.company_city}, {self.company_state} {self.company_zip}"

    @property
    def full_address(self):
        return f"{self.address}, {self.city}, {self.state} {self.zip_code}"
    
    @property
    def property_full_address(self):
        return f"{self.property_address}, {self.property_city}, {self.property_state} {self.property_zip}"

class DocumentCategory(models.Model):
    """Categories for organizing documents (e.g., Leases, Claims, Landlord Docs)"""
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    icon = models.CharField(max_length=50, blank=True)  # For UI icons
    
    class Meta:
        verbose_name_plural = "Document Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name

class Document(models.Model):
    """Enhanced document model with categorization"""
    DOCUMENT_TYPES = (
        ('lease', 'Lease Agreement'),
        ('claim', 'Insurance Claim'),
        ('landlord', 'Landlord Document'),
        ('contract', 'Contract'),
        ('invoice', 'Invoice'),
        ('report', 'Report'),
        ('other', 'Other'),
    )
    
    name = models.CharField(max_length=255)
    category = models.ForeignKey(DocumentCategory, on_delete=models.PROTECT)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    file = models.FileField(
        upload_to="documents/%Y/%m/%d/",
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'html'])
        ]
    )
    size = models.PositiveIntegerField(editable=False)  # In bytes
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_documents'
    )
    
    # Related objects (optional foreign keys)
    claim = models.ForeignKey(
        Client,  # Assuming you have a Claim model
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='documents'
    )
    landlord = models.ForeignKey(Landlord, on_delete=models.SET_NULL, null=True, blank=True)
    # Potential Property Field for different property
    #property = models.ForeignKey(
    #    'properties.Property',  # If you have a Property model
    #    on_delete=models.CASCADE,
    #    null=True,
    #    blank=True,
    #    related_name='documents'
    #)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document_type']),
            models.Index(fields=['category']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_document_type_display()})"
    
    def save(self, *args, **kwargs):
        """Calculate file size before saving"""
        if self.file and not self.size:
            self.size = self.file.size
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Delete the file from storage when model is deleted"""
        if self.file:
            if os.path.isfile(self.file.path):
                os.remove(self.file.path)
        super().delete(*args, **kwargs)
    
    def get_file_extension(self):
        return os.path.splitext(self.file.name)[1].lower()
    
    def get_file_size_display(self):
        """Returns human-readable file size"""
        size = self.size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def get_absolute_url(self):
        return reverse('document-detail', kwargs={'pk': self.pk})


class ChecklistItem(models.Model):
    DOCUMENT_TYPES = [
        # MIT Documents
        ('MIT_AUTH', 'MIT General Authorization'),
        ('MIT_AGREE', 'MIT Customer Agreement'),
        ('MIT_W9', 'MIT W9 Form'),
        ('MIT_VERIFY', 'MIT Jobsite Verification'),
        ('MIT_EQUIP', 'MIT Equipment Pictures'),
        ('MIT_INVOICE', 'MIT Xactimate Invoice'),
        ('MIT_OVERVIEW', 'MIT Job Overview Pictures'),
        ('MIT_DRYLOG', 'MIT Dry Logs Reports'),
        ('MIT_EMAIL', 'MIT Email Cover Sheet'),
        
        # CPS Documents
        ('CPS_AUTH', 'CPS General Authorization'),
        ('CPS_AGREE', 'CPS Customer Agreement'),
        ('CPS_W9', 'CPS W9 Form'),
        ('CPS_VERIFY', 'CPS Jobsite Verification'),
        ('CPS_BOXCOUNT', 'CPS Box Count Report'),
        ('CPS_BOXPHOTO', 'CPS Box Count Photo Report'),
        ('CPS_CUSTPICS', 'CPS Customer Pics'),
        ('CPS_CUSTLIST', 'CPS Customer List'),
        ('CPS_INVOICE', 'CPS Xactimate Packout Invoice'),
        ('CPS_ESX', 'CPS ESX File'),
        ('CPS_OVERVIEW', 'CPS Job Overview Pictures'),
        ('CPS_DAY1', 'CPS Day1 Overview Pics'),
        ('CPS_DAY2', 'CPS Day2 Work In Progress'),
        ('CPS_DAY3', 'CPS Day3 Storage Pics'),
        ('CPS_DAY4', 'CPS Day4 Demo/Reset Pics'),
        ('CPS_EMAIL', 'CPS Email Cover Sheet'),
        
        # PPR Documents
        ('PPR_SCHEDULE', 'PPR Schedule of Loss'),
        ('PPR_PHOTOREP', 'PPR Items Photo Report'),
        ('PPR_CUSTPICS', 'PPR Customer Pics'),
        ('PPR_CUSTLIST', 'PPR Customer List'),
        ('PPR_EMAIL', 'PPR Email Cover Sheet'),
    ]
    
    DOCUMENT_CATEGORIES = [
        ('MIT', 'Mitigation'),
        ('CPS', 'Contents Processing'),
        ('PPR', 'Property Repair'),
    ]
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='checklist_items')
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    document_category = models.CharField(max_length=3, choices=DOCUMENT_CATEGORIES)
    is_completed = models.BooleanField(default=False)
    required = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Automatically set document category based on type
        if self.document_type.startswith('MIT'):
            self.document_category = 'MIT'
        elif self.document_type.startswith('CPS'):
            self.document_category = 'CPS'
        elif self.document_type.startswith('PPR'):
            self.document_category = 'PPR'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.client.pOwner}"

    class Meta:
        ordering = ['document_category', 'document_type']

class DocumentTemplate(models.Model):
    name = models.CharField(max_length=255)
    document_type = models.CharField(max_length=20, choices=ChecklistItem.DOCUMENT_TYPES)
    template_file = models.FileField(upload_to='document_templates/')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name



#class ExactimatePrices():
#    id =
#    CAT =
#    Sel =
#    Desc =
#    Unic =
#    Qty =
#    Unit Cost =
#    Item Amount =
#    Group Code =
#    Group Description =


#class TimeCalc():
#    boxType = 
#    workType = 
#    timeMinutes = 
#    timeHrs = 
