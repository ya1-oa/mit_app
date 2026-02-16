from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.forms import ModelForm
import os
import re
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
import uuid
import hashlib
import json
from datetime import timedelta


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
    # Server-based folder tracking (replaces OneDrive)
    server_folder_path = models.CharField(max_length=500, blank=True, help_text="Path to claim folder on server")
    folder_created_at = models.DateTimeField(null=True, blank=True, help_text="When folder structure was created")
    last_file_modified = models.DateTimeField(null=True, blank=True, help_text="Last time any file was changed")
    last_modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_modified_claims',
        help_text="User who last modified files"
    )

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
    dateOfLoss = models.DateTimeField(null=True, blank=True)
    rebuildType1 = models.CharField(max_length=255, blank=True)
    rebuildType2 = models.CharField(max_length=255, blank=True)
    rebuildType3 = models.CharField(max_length=255, blank=True)
    demo = models.BooleanField(default=False)
    mitigation = models.BooleanField(default=False)
    otherStructures = models.BooleanField(default=False)
    replacement = models.BooleanField(default=False)
    CPSCLNCONCGN = models.BooleanField(default=False)
    yearBuilt = models.CharField(max_length=255, blank=True)
    contractDate = models.DateTimeField(null=True, blank=True)
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
    claimReportDate = models.DateTimeField(null=True, blank=True)
    insuranceCustomerServiceRep = models.CharField(max_length=255, blank=True)
    timeOfClaimReport = models.CharField(max_length=255, blank=True)
    phoneExt = models.CharField(max_length=255, blank=True)
    tarpExtTMPOk = models.BooleanField(default=False)
    IntTMPOk = models.BooleanField(default=False)
    DRYPLACUTOUTMOLDSPRAYOK = models.BooleanField(default=False)
    
    # ALE (Additional Living Expenses) - Comprehensive Fields
    lossOfUseALE = models.CharField(max_length=255, blank=True, help_text="Loss of Use/ALE - Yes/No")

    # LESSEE INFO (Tenant/Customer using ALE)
    ale_lessee_name = models.CharField(max_length=255, blank=True, help_text="Lessee/Tenant Name")
    ale_lessee_home_address = models.CharField(max_length=255, blank=True, help_text="Lessee Home Address")
    ale_lessee_city_state_zip = models.CharField(max_length=255, blank=True, help_text="Lessee City, State, ZIP")
    ale_lessee_email = models.CharField(max_length=255, blank=True, help_text="Lessee Email")
    ale_lessee_phone = models.CharField(max_length=255, blank=True, help_text="Lessee Phone Number")

    # RENTAL INFO
    ale_rental_bedrooms = models.CharField(max_length=50, blank=True, help_text="Number of Bedrooms")
    ale_rental_months = models.CharField(max_length=50, blank=True, help_text="Number of Months")
    ale_rental_start_date = models.DateField(null=True, blank=True, help_text="Rental Start Date")
    ale_rental_end_date = models.DateField(null=True, blank=True, help_text="Rental End Date")
    ale_rental_amount_per_month = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Amount Per Month")

    # LESSOR INFO (Landlord/Property Owner renting to customer)
    ale_lessor_name = models.CharField(max_length=255, blank=True, help_text="Lessor Legal Name")
    ale_lessor_leased_address = models.CharField(max_length=255, blank=True, help_text="Leased Property Address")
    ale_lessor_city_zip = models.CharField(max_length=255, blank=True, help_text="Lessor City, ZIP")
    ale_lessor_phone = models.CharField(max_length=255, blank=True, help_text="Lessor Phone Number")
    ale_lessor_email = models.CharField(max_length=255, blank=True, help_text="Lessor Email")
    ale_lessor_mailing_address = models.CharField(max_length=255, blank=True, help_text="Lessor Mailing Address")
    ale_lessor_mailing_city_zip = models.CharField(max_length=255, blank=True, help_text="Lessor Mailing City, ZIP")
    ale_lessor_contact_person = models.CharField(max_length=255, blank=True, help_text="Lessor Contact Person")

    # REAL ESTATE COMPANY (for ALE rental)
    ale_re_company_name = models.CharField(max_length=255, blank=True, help_text="Real Estate Company Name")
    ale_re_mailing_address = models.CharField(max_length=255, blank=True, help_text="RE Company Mailing Address")
    ale_re_city_zip = models.CharField(max_length=255, blank=True, help_text="RE Company City, ZIP")
    ale_re_contact_person = models.CharField(max_length=255, blank=True, help_text="RE Company Contact Person")
    ale_re_phone = models.CharField(max_length=255, blank=True, help_text="RE Company Phone")
    ale_re_email = models.CharField(max_length=255, blank=True, help_text="RE Company Email")
    ale_re_owner_broker_name = models.CharField(max_length=255, blank=True, help_text="Owner/Broker Name")
    ale_re_owner_broker_phone = models.CharField(max_length=255, blank=True, help_text="Owner/Broker Phone")
    ale_re_owner_broker_email = models.CharField(max_length=255, blank=True, help_text="Owner/Broker Email")

    # Encircle integration
    encircle_claim_id = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Encircle property claim ID (set after push to Encircle)"
    )
    encircle_synced_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Last time this claim was pushed to Encircle"
    )

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
    

    def get_rooms_data(self):
        """Get all rooms with their work type values"""
        rooms_data = []
        for room in self.rooms.all().prefetch_related('work_type_values__work_type'):
            room_info = {
                'room_name': room.room_name,
                'sequence': room.sequence,
                'work_types': {}
            }
            for wt_value in room.work_type_values.all():
                room_info['work_types'][wt_value.work_type.work_type_id] = wt_value.value_type
            rooms_data.append(room_info)
        return rooms_data

    def _calculate_category_completion(self, category):
        items = self.checklist_items.filter(document_category=category)
        total = items.count()
        completed = items.filter(is_completed=True).count()
        return int((completed / total * 100) if total > 0 else 0)

    def __str__(self):
        return self.pOwner

    def get_folder_name(self):
        """Generate standardized folder name for server storage"""
        # Clean the address to make it filesystem-safe
        # Format: ClientName@Address (NO ID prefix - consistent with create_claim_folder_structure)
        safe_owner = re.sub(r'[<>:"/\\|?*]', '_', self.pOwner or 'Unknown')
        safe_address = re.sub(r'[<>:"/\\|?*]', '_', self.pAddress or 'NoAddress')
        return f"{safe_owner}@{safe_address}"

    def get_server_folder_path(self):
        """Get the full path to the claim folder on the server"""
        if self.server_folder_path:
            return self.server_folder_path
        # Default path pattern
        return os.path.join(settings.MEDIA_ROOT, 'claims', self.get_folder_name())

    def get_templates_folder(self):
        """Get path to Templates folder for this claim"""
        from .claim_folder_utils import get_templates_folder
        return get_templates_folder(self)

    def ensure_folder_structure_exists(self):
        """Ensure server folder structure exists, create if missing"""
        import os
        from .claim_folder_utils import create_claim_folder_structure

        folder_path = self.get_server_folder_path()
        if not os.path.exists(folder_path):
            create_claim_folder_structure(self)
        return True

    def calculate_hash(self):
        """Calculate hash for change detection"""
        data = {
            'pOwner': self.pOwner,
            'pAddress': self.pAddress,
            'claimNumber': self.claimNumber,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from .signals import create_checklist_items_for_client
        create_checklist_items_for_client(self)

class WorkType(models.Model):
    """Definition of work types (100, 200, 300, 400, 500, 800, 900)"""
    WORK_TYPE_CHOICES = [
        (100, 'Work Type 100'),
        (200, 'Work Type 200'),
        (300, 'Work Type 300'),
        (400, 'Work Type 400'),
        (500, 'Work Type 500'),
        (800, 'Work Type 800'),
        (900, 'Work Type 900 - HMR'),
        (6100, 'DAY 1'),
        (6200, 'DAY 2'),
        (6300, 'DAY 3'),
        (6400, 'DAY 4'),
    ]

    work_type_id = models.IntegerField(choices=WORK_TYPE_CHOICES, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Configuration for 100s prefix work types
    applies_to_all_rooms = models.BooleanField(
        default=False,
        help_text="If true, this work type applies to all rooms by default (100s)"
    )

    class Meta:
        ordering = ['display_order', 'work_type_id']
        indexes = [
            models.Index(fields=['work_type_id']),
            models.Index(fields=['is_active', 'display_order']),
        ]

    def __str__(self):
        return f"{self.work_type_id} - {self.name}"

class Room(models.Model):
    """Model for individual rooms - replaces roomArea1-25 fields"""
    LOS_TRAVEL_CHOICES = [
        ('', 'No Value'),
        ('TBD', 'To Be Determined'),
        ('NA', 'Not Applicable'),
        ('LOS', 'Line of Sight'),
        ('TRAVEL', 'Travel Area'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='rooms')
    room_name = models.CharField(max_length=255)
    sequence = models.IntegerField(default=0)  # Maintains room order

    # Source tracking
    source_claim_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="If copied from another claim, store that claim number"
    )

    # Modification tracking (server-based)
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Last user to modify this room"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['client', 'sequence', 'room_name']
        unique_together = ['client', 'room_name']
        indexes = [
            models.Index(fields=['client', 'sequence']),
            models.Index(fields=['source_claim_number']),
        ]

    def __str__(self):
        return f"{self.room_name} ({self.client.pOwner})"


class RoomWorkTypeValue(models.Model):
    """LOS/TRAVEL values for each room and work type combination"""
    VALUE_CHOICES = [
        ('', 'No Value'),
        ('TBD', 'To Be Determined'),
        ('NA', 'Not Applicable'),
        ('LOS', 'Line Of Sight'),
        ('TRAVEL', 'Travel Area'),
    ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='work_type_values')
    work_type = models.ForeignKey(WorkType, on_delete=models.CASCADE)
    value_type = models.CharField(max_length=10, choices=VALUE_CHOICES, default='', blank=True)

    # Optional numeric value for calculations
    numeric_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['room', 'work_type']
        indexes = [
            models.Index(fields=['room', 'work_type']),
            models.Index(fields=['value_type']),
        ]

    def __str__(self):
        return f"{self.room.room_name} - WT{self.work_type.work_type_id}: {self.value_type}"




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

class ReadingImage(models.Model):
    filename = models.CharField(max_length=255)
    size = models.IntegerField()
    file = models.FileField(upload_to="readings/%Y/%m/%d/")
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Extracted values for sorting
    rh_value = models.FloatField(null=True, blank=True)
    t_value = models.FloatField(null=True, blank=True)
    gpp_value = models.FloatField(null=True, blank=True)
    mc_value = models.FloatField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.filename
    
    def save(self, *args, **kwargs):
        # Extract values from filename when saving
        if self.filename and not self.rh_value:
            self.extract_values_from_filename()
        super().save(*args, **kwargs)

    def extract_values_from_filename(self):
        """Extract RH, T, GPP, and MC values from filename"""
        # Try RH_T_GPP pattern first
        rh_t_gpp_patterns = [
            r'RH_([\d.]+|NA\d+)_T_([\d.]+|NA\d+)_GPP_([\d.]+|NA\d+)',
            r'RH_([\d.]+)_T_([\d.]+)_GPP_([\d.]+)'
        ]
        
        for pattern in rh_t_gpp_patterns:
            match = re.search(pattern, self.filename)
            if match:
                try:
                    # Handle RH value
                    rh_val = match.group(1)
                    if rh_val.startswith('NA'):
                        self.rh_value = None
                    else:
                        self.rh_value = float(rh_val)
                    
                    # Handle T value
                    t_val = match.group(2)
                    if t_val.startswith('NA'):
                        self.t_value = None
                    else:
                        self.t_value = float(t_val)
                    
                    # Handle GPP value
                    gpp_val = match.group(3)
                    if gpp_val.startswith('NA'):
                        self.gpp_value = None
                    else:
                        self.gpp_value = float(gpp_val)
                    
                    # Clear MC value for RH_T_GPP files
                    self.mc_value = None
                    return
                    
                except (ValueError, TypeError) as e:
                    print(f"Error parsing RH_T_GPP values from {self.filename}: {e}")
                    continue
        
        # Try MC pattern: "91. MC4.5" or "12. MC14.7" or "MC4.5"
        mc_patterns = [
            r'(\d+)\.\s*MC([\d.]+)',  # "91. MC4.5"
            r'MC([\d.]+)',            # "MC4.5"
            r'(\d+)\.\s*([\d.]+)\s*MC' # "91. 4.5 MC" (alternative format)
        ]
        
        for pattern in mc_patterns:
            match = re.search(pattern, self.filename, re.IGNORECASE)
            if match:
                try:
                    # If pattern has two groups, first is usually the number, second is MC value
                    if len(match.groups()) == 2:
                        mc_val = match.group(2)
                    else:
                        mc_val = match.group(1)
                    
                    self.mc_value = float(mc_val)
                    # Clear RH/T/GPP values for MC files
                    self.rh_value = None
                    self.t_value = None
                    self.gpp_value = None
                    return
                    
                except (ValueError, TypeError) as e:
                    print(f"Error parsing MC value from {self.filename}: {e}")
                    continue
        
        # If no pattern matched, it might be a room label or other format
        print(f"Could not parse filename (may be room label): {self.filename}")
        self.rh_value = None
        self.t_value = None
        self.gpp_value = None
        self.mc_value = None
        
    def delete(self, *args, **kwargs):
        if self.file:
            if os.path.isfile(self.file.path):
                os.remove(self.file.path)
        super().delete(*args, **kwargs)
    
    def get_file_extension(self):
        return os.path.splitext(self.filename)[1]
    
    def get_file_size_display(self):
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

    # Special Lease Instructions/Notes
    lease_special_notes = models.TextField(
        verbose_name="Special Lease Instructions/Notes",
        blank=True,
        null=True,
        help_text="Special instructions or notes to be included at the end of the Property section"
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

class EmailSchedule(models.Model):
    INTERVAL_CHOICES = [
        ('none', 'No Repeat'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('custom', 'Custom'),
    ]
    
    name = models.CharField(max_length=255)
    subject = models.TextField()
    body = models.TextField()
    recipients = models.JSONField()  # list of email addresses

    # Use your existing models:
    documents = models.ManyToManyField('Document', blank=True, related_name='scheduled_in_emails')
    attachments = models.ManyToManyField('File', blank=True, related_name='scheduled_in_emails')

    start_date = models.DateTimeField()
    interval = models.CharField(max_length=20, choices=INTERVAL_CHOICES, default='none')
    custom_interval_days = models.IntegerField(null=True, blank=True)
    repeat_count = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)

    # Use your configured auth user model
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    notify_on_open = models.BooleanField(default=True)
    admin_notification_email = models.EmailField()

    def __str__(self):
        return self.name

    def get_next_send_time(self, last_sent=None):
        if not last_sent:
            return self.start_date
        if self.interval == 'daily':
            return last_sent + timezone.timedelta(days=1)
        elif self.interval == 'weekly':
            return last_sent + timezone.timedelta(weeks=1)
        elif self.interval == 'monthly':
            # naive "next month" increment
            next_month = last_sent.month + 1
            next_year = last_sent.year
            if next_month > 12:
                next_month = 1
                next_year += 1
            return last_sent.replace(year=next_year, month=next_month)
        elif self.interval == 'custom' and self.custom_interval_days:
            return last_sent + timezone.timedelta(days=self.custom_interval_days)
        return None


class SentEmail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(EmailSchedule, on_delete=models.CASCADE, null=True, blank=True)
    subject = models.TextField()
    body = models.TextField()
    recipients = models.JSONField()

    # Use your existing models:
    documents = models.ManyToManyField('Document', blank=True, related_name='sent_in_emails')
    attachments = models.ManyToManyField('File', blank=True, related_name='sent_in_emails')

    sent_at = models.DateTimeField(auto_now_add=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    scheduled_send_time = models.DateTimeField(null=True, blank=True)
    tracking_pixel_id = models.UUIDField(default=uuid.uuid4, unique=True)
    is_opened = models.BooleanField(default=False)
    opened_at = models.DateTimeField(null=True, blank=True)
    notify_on_open = models.BooleanField(default=False)
    admin_notification_email = models.EmailField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.subject} - {self.sent_at}"


class EmailOpenEvent(models.Model):
    sent_email = models.ForeignKey(SentEmail, on_delete=models.CASCADE)
    opened_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-opened_at']


# ==================== Server-Based File Management Models ====================

class ClaimFile(models.Model):
    """Track files in claim folders on the server"""

    FILE_TYPES = [
        ('01-INFO', '01-INFO - General Information'),
        ('01-ROOMS', '01-ROOMS - Room Data'),
        ('02-INS-CO', '02-INS-CO - Insurance Company'),
        ('30-MASTER', '30-MASTER - Master Lists'),
        ('50-CONTRACT', '50-CONTRACT - Contracts'),
        ('60-SCOPE', '60-SCOPE - Scope Documents'),
        ('82-MIT', '82-MIT - Mitigation'),
        ('92-CPS', '92-CPS - Contents Processing'),
        ('94-INVOICE', '94-INVOICE - Invoices'),
        ('OTHER', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='claim_files')

    file_type = models.CharField(max_length=20, choices=FILE_TYPES)
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, help_text="Relative path from claim folder root")
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    file_hash = models.CharField(max_length=64, blank=True, help_text="MD5 hash for change detection")

    # File metadata
    mime_type = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_claim_files'
    )
    modified_at = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='modified_claim_files'
    )

    # Version control
    version = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True, help_text="False if file is deleted")

    class Meta:
        ordering = ['client', 'file_type', 'file_name']
        indexes = [
            models.Index(fields=['client', 'file_type']),
            models.Index(fields=['file_hash']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.get_file_type_display()})"

    def get_full_path(self):
        """Get absolute filesystem path to this file"""
        return os.path.join(self.client.get_server_folder_path(), self.file_path)

    def calculate_hash(self):
        """Calculate MD5 hash of file contents"""
        full_path = self.get_full_path()
        if os.path.exists(full_path):
            hash_md5 = hashlib.md5()
            with open(full_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        return ""


class FileChangeLog(models.Model):
    """Audit trail for file changes"""

    ACTIONS = [
        ('created', 'Created'),
        ('modified', 'Modified'),
        ('deleted', 'Deleted'),
        ('renamed', 'Renamed'),
        ('moved', 'Moved'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    claim_file = models.ForeignKey(ClaimFile, on_delete=models.CASCADE, related_name='change_logs')

    action = models.CharField(max_length=20, choices=ACTIONS)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    # Hash tracking for modifications
    old_hash = models.CharField(max_length=64, blank=True, help_text="File hash before change")
    new_hash = models.CharField(max_length=64, blank=True, help_text="File hash after change")

    # Additional metadata
    old_filename = models.CharField(max_length=255, blank=True)
    new_filename = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['claim_file', '-changed_at']),
            models.Index(fields=['changed_by']),
            models.Index(fields=['-changed_at']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.claim_file.file_name} - {self.changed_at}"


# ==================== ALE Lease Management Models ====================

class Lease(models.Model):
    """
    Represents a single ALE lease agreement for a claim.
    Contains all the data from the lease generation form.
    Multiple documents belong to one lease.
    """

    LEASE_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('review', 'Under Review'),  # Trevor reviews for accuracy
        ('sent_for_signature', 'Sent for Signature'),
        ('signed', 'Signed'),
        ('invoice_created', 'Invoice Created'),
        ('package_sent', 'Package Sent to Insurance'),
        ('payment_pending', 'Payment Pending'),
        ('payment_received', 'Payment Received'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Link to claim/client (property owner)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='leases')

    # ===== LESSOR INFORMATION (from form Tab 1) =====
    lessor_name = models.CharField(max_length=255, verbose_name="Lessor Full Name")
    lessor_address = models.CharField(max_length=500, blank=True)
    lessor_city = models.CharField(max_length=100, blank=True)
    lessor_state = models.CharField(max_length=50, blank=True)
    lessor_zip = models.CharField(max_length=20, blank=True)
    lessor_phone = models.CharField(max_length=50, blank=True)
    lessor_email = models.EmailField(blank=True)
    lessor_contact_person_1 = models.CharField(max_length=255, blank=True)
    lessor_contact_person_2 = models.CharField(max_length=255, blank=True)
    lessor_contact_phone = models.CharField(max_length=50, blank=True)
    lessor_contact_email = models.EmailField(blank=True)

    # ===== PROPERTY INFORMATION (from form Tab 2) =====
    property_address = models.CharField(max_length=500)
    property_city = models.CharField(max_length=100, blank=True)
    property_state = models.CharField(max_length=50, blank=True)
    property_zip = models.CharField(max_length=20, blank=True)
    bedrooms = models.PositiveIntegerField(default=1)

    # ===== RENTAL TERMS (from form Tab 3) =====
    lease_start_date = models.DateField(null=True, blank=True)
    lease_end_date = models.DateField(null=True, blank=True)
    lease_agreement_date = models.DateField(null=True, blank=True)
    rental_months = models.PositiveIntegerField(default=12)
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rent_due_day = models.PositiveIntegerField(default=1)
    late_fee = models.DecimalField(max_digits=10, decimal_places=2, default=50)
    late_fee_start_day = models.PositiveIntegerField(default=5)
    eviction_day = models.PositiveIntegerField(default=10)
    nsf_fee = models.DecimalField(max_digits=10, decimal_places=2, default=35)
    max_occupants = models.PositiveIntegerField(default=10)
    parking_spaces = models.PositiveIntegerField(default=2)
    parking_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    inspection_fee = models.DecimalField(max_digits=10, decimal_places=2, default=300)

    # ===== REAL ESTATE COMPANY INFO (from form Tab 4) =====
    real_estate_company = models.CharField(max_length=255, blank=True)
    company_mailing_address = models.CharField(max_length=500, blank=True)
    company_city = models.CharField(max_length=100, blank=True)
    company_state = models.CharField(max_length=50, blank=True)
    company_zip = models.CharField(max_length=20, blank=True)
    company_contact_person = models.CharField(max_length=255, blank=True)
    company_phone = models.CharField(max_length=50, blank=True)
    company_email = models.EmailField(blank=True)
    broker_name = models.CharField(max_length=255, blank=True)
    broker_phone = models.CharField(max_length=50, blank=True)
    broker_email = models.EmailField(blank=True)

    # ===== SPECIAL NOTES =====
    special_notes = models.TextField(blank=True)

    # ===== FLAGS =====
    is_renewal = models.BooleanField(default=False)
    exclude_security_deposit = models.BooleanField(default=False)
    exclude_inspection_fee = models.BooleanField(default=False)

    # ===== PIPELINE STATUS =====
    status = models.CharField(max_length=30, choices=LEASE_STATUS_CHOICES, default='draft')

    # Status timestamps
    generated_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    sent_for_signature_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    invoice_created_at = models.DateTimeField(null=True, blank=True)
    package_sent_at = models.DateTimeField(null=True, blank=True)
    payment_received_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # ===== USER TRACKING =====
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_leases'
    )
    last_modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='modified_leases'
    )

    # Notes/comments on the lease
    notes = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['lease_start_date', 'lease_end_date']),
        ]

    def __str__(self):
        return f"Lease: {self.client.pOwner} - {self.lessor_name} ({self.lease_start_date} to {self.lease_end_date})"

    @property
    def is_active(self):
        """Check if lease is currently active based on dates"""
        from datetime import date
        today = date.today()
        if self.status == 'cancelled':
            return False
        if not self.lease_start_date or not self.lease_end_date:
            return False
        return self.lease_start_date <= today <= self.lease_end_date

    @property
    def is_expired(self):
        """Check if lease has expired"""
        from datetime import date
        if not self.lease_end_date:
            return False
        return self.lease_end_date < date.today()

    @property
    def full_property_address(self):
        """Return full formatted property address"""
        parts = [self.property_address, self.property_city, self.property_state, self.property_zip]
        return ', '.join(p for p in parts if p)

    def get_status_color(self):
        """Return Bootstrap color class for status badge"""
        color_map = {
            'draft': 'secondary',
            'generated': 'info',
            'review': 'purple',  # Under review by Trevor
            'sent_for_signature': 'primary',
            'signed': 'success',
            'invoice_created': 'warning',
            'package_sent': 'info',
            'payment_pending': 'warning',
            'payment_received': 'success',
            'completed': 'success',
            'cancelled': 'danger',
        }
        return color_map.get(self.status, 'secondary')




class LeaseDocument(models.Model):
    """Individual documents that belong to a Lease"""

    DOCUMENT_TYPES = [
        ('engagement_agreement', 'Engagement Agreement'),
        ('term_sheet', 'Term Sheet'),
        ('month_to_month_rental', 'Month to Month Rental'),
        ('input_sheet', 'Input Sheet'),
        ('invoice', 'Invoice'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Link to parent lease
    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name='documents', null=True)

    # Document info
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    document_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, blank=True, help_text="Path to generated PDF on server")

    # Timestamps
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['document_type']

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.lease.client.pOwner}"


class LeaseActivity(models.Model):
    """Track all activity related to leases"""

    ACTIVITY_TYPES = [
        # Status-aligned activities (match LEASE_STATUS_CHOICES)
        ('draft', 'Draft Created'),
        ('generated', 'Documents Generated'),
        ('review', 'Documents Reviewed'),
        ('sent_for_signature', 'Sent for Signature'),
        ('signed', 'Lease Signed'),
        ('invoice_created', 'Invoice Created'),
        ('package_sent', 'Package Sent'),
        ('payment_pending', 'Payment Pending'),
        ('payment_received', 'Payment Received'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        # Additional activities
        ('note_added', 'Note Added'),
        ('document_downloaded', 'Document Downloaded'),
        ('document_viewed', 'Document Viewed'),
        ('email_parsed', 'Email Auto-Processed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lease = models.ForeignKey(
        Lease,
        on_delete=models.CASCADE,
        related_name='activities',
        null=True
    )

    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES)
    description = models.TextField()

    # Status change tracking
    old_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, blank=True)

    # User who performed the action
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Lease Activities'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['lease', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_activity_type_display()} - {self.lease.client.pOwner} - {self.created_at}"


# ==================== Pipeline Stage Management Models ====================

class PipelineStageAssignment(models.Model):
    """
    Defines which team member is responsible for each pipeline stage.
    This allows flexible assignment of stages to users.
    """

    STAGE_CHOICES = [
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('review', 'Review'),
        ('sent_for_signature', 'Sent for Signature'),
        ('signed', 'Signed'),
        ('invoice_created', 'Invoice Created'),
        ('package_sent', 'Package Sent'),
        ('payment_pending', 'Payment Pending'),
        ('payment_received', 'Payment Received'),
        ('completed', 'Completed'),
    ]

    stage = models.CharField(max_length=30, choices=STAGE_CHOICES, unique=True)
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_pipeline_stages'
    )
    description = models.TextField(blank=True, help_text="Description of what happens at this stage")
    order = models.PositiveIntegerField(default=0, help_text="Display order in pipeline")

    class Meta:
        ordering = ['order']
        verbose_name = 'Pipeline Stage Assignment'
        verbose_name_plural = 'Pipeline Stage Assignments'

    def __str__(self):
        user_email = self.assigned_user.email if self.assigned_user else 'Unassigned'
        return f"{self.get_stage_display()} - {user_email}"


class LeaseStageCompletion(models.Model):
    """
    Tracks the completion of each pipeline stage for a specific lease.
    Created when a lease is created, updated as the lease progresses.
    """

    lease = models.ForeignKey(
        Lease,
        on_delete=models.CASCADE,
        related_name='stage_completions'
    )
    stage = models.CharField(max_length=30, choices=PipelineStageAssignment.STAGE_CHOICES)
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_lease_stages',
        help_text="User assigned to complete this stage"
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_lease_stages',
        help_text="User who actually completed this stage"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['lease', 'stage']
        ordering = ['lease', 'stage']
        verbose_name = 'Lease Stage Completion'
        verbose_name_plural = 'Lease Stage Completions'

    def __str__(self):
        status = "Completed" if self.is_completed else "Pending"
        return f"{self.lease.client.pOwner} - {self.get_stage_display()}: {status}"


# ==================== Email Parsing Models ====================

class EmailParsingRule(models.Model):
    """
    Rules for parsing forwarded emails and automatically updating lease statuses.
    Team members forward emails to a dedicated inbox with specific subject formats.
    """

    name = models.CharField(max_length=100, help_text="Rule name for identification")
    is_active = models.BooleanField(default=True)

    # Keywords to match in email subject
    subject_keywords = models.CharField(
        max_length=255,
        help_text="Comma-separated keywords to match in subject (e.g., 'signed, executed')"
    )

    # Target status when rule matches
    target_status = models.CharField(
        max_length=30,
        choices=Lease.LEASE_STATUS_CHOICES,
        help_text="Status to set when this rule matches"
    )

    # Claim identifier pattern
    claim_identifier_pattern = models.CharField(
        max_length=255,
        default=r'CLAIM[#:\s]*(\w+)',
        help_text="Regex pattern to extract claim number from email"
    )

    # Priority for rule matching (lower = higher priority)
    priority = models.PositiveIntegerField(default=100)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'name']
        verbose_name = 'Email Parsing Rule'
        verbose_name_plural = 'Email Parsing Rules'

    def __str__(self):
        return f"{self.name} -> {self.get_target_status_display()}"

    def matches_subject(self, subject):
        """Check if email subject matches this rule's keywords"""
        if not self.subject_keywords:
            return False
        keywords = [kw.strip().lower() for kw in self.subject_keywords.split(',')]
        subject_lower = subject.lower()
        return any(kw in subject_lower for kw in keywords)


class ParsedEmail(models.Model):
    """
    Log of all parsed emails and the actions taken.
    Provides audit trail for email-based status updates.
    """

    STATUS_CHOICES = [
        ('success', 'Successfully Processed'),
        ('no_match', 'No Rule Matched'),
        ('no_lease', 'Lease Not Found'),
        ('error', 'Error Processing'),
    ]

    email_id = models.CharField(max_length=255, unique=True, help_text="Email message ID")
    sender = models.EmailField()
    subject = models.TextField()
    body_preview = models.TextField(max_length=500, blank=True)
    received_at = models.DateTimeField()
    processed_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    matched_rule = models.ForeignKey(
        EmailParsingRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='matched_emails'
    )

    # Resulting action
    lease = models.ForeignKey(
        Lease,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parsed_emails'
    )
    old_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, blank=True)

    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-processed_at']
        verbose_name = 'Parsed Email'
        verbose_name_plural = 'Parsed Emails'

    def __str__(self):
        return f"{self.subject[:50]} - {self.get_status_display()}"


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


class RoomScopeChecklist(models.Model):
    """Store scope checklist data for each room - Xactimate codes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='scope_checklists')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='scope_checklists')

    # CEILING (CLG)
    clg_material = models.CharField(max_length=20, blank=True)  # ACT, DRY, PLA, T&G, PNL, WPR, CNC, MAS
    clg_construction = models.CharField(max_length=20, blank=True)  # FLT, VLT, TRY, FRM
    clg_finish = models.CharField(max_length=20, blank=True)  # SMH, TEX, POP
    clg_activity = models.CharField(max_length=20, blank=True)  # ALL, MN, CLN, R&R, D&R, MSK, S++, PNT, STN, SND
    clg_sf = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # LIGHTS (LIT)
    lit_type = models.CharField(max_length=20, blank=True)  # LIT, LIT++, FNL, CHD, SEC, SMK, CHM, OS, SW, SW3
    lit_activity = models.CharField(max_length=20, blank=True)
    lit_qty = models.IntegerField(null=True, blank=True)

    # HVAC (HVC)
    hvc_type = models.CharField(max_length=20, blank=True)
    hvc_activity = models.CharField(max_length=20, blank=True)
    hvc_qty = models.IntegerField(null=True, blank=True)

    # WALLS (WAL)
    wal_material = models.CharField(max_length=20, blank=True)
    wal_finish = models.CharField(max_length=20, blank=True)
    wal_activity = models.CharField(max_length=20, blank=True)
    wal_sf = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # ELECTRICAL (ELE)
    ele_outlets = models.IntegerField(null=True, blank=True)
    ele_switches = models.IntegerField(null=True, blank=True)
    ele_sw3 = models.IntegerField(null=True, blank=True)
    ele_activity = models.CharField(max_length=20, blank=True)

    # FLOOR (FLR)
    flr_type = models.CharField(max_length=20, blank=True)  # FCC, FCS, FCV, FCW, LAM
    flr_activity = models.CharField(max_length=20, blank=True)
    flr_sf = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # BASEBOARD (BB)
    bb_height = models.CharField(max_length=20, blank=True)
    bb_activity = models.CharField(max_length=20, blank=True)
    bb_lf = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # TRIM
    trim_type = models.CharField(max_length=20, blank=True)
    trim_crown = models.CharField(max_length=10, blank=True)  # YES, NO
    trim_chairrail = models.CharField(max_length=10, blank=True)  # YES, NO
    trim_activity = models.CharField(max_length=20, blank=True)

    # DOOR (DOR)
    dor_type = models.CharField(max_length=20, blank=True)  # STD, BFD, BYD, BPM
    dor_activity = models.CharField(max_length=20, blank=True)
    dor_qty = models.IntegerField(null=True, blank=True)

    # OPENING (OPEN)
    open_activity = models.CharField(max_length=20, blank=True)
    open_qty = models.IntegerField(null=True, blank=True)

    # WINDOW (WDW)
    wdw_type = models.CharField(max_length=20, blank=True)  # WDW, WDV, WDA, BAY
    wdw_covers = models.CharField(max_length=20, blank=True)  # WDT, BLN, DRP
    wdw_activity = models.CharField(max_length=20, blank=True)
    wdw_qty = models.IntegerField(null=True, blank=True)

    # CLOSET
    closet_type = models.CharField(max_length=20, blank=True)  # WOOD, WIRE
    closet_rod = models.CharField(max_length=10, blank=True)  # YES, NO
    closet_lf = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # INSULATION (INS)
    ins_type = models.CharField(max_length=20, blank=True)  # BATT, LOOSE
    ins_rvalue = models.CharField(max_length=20, blank=True)
    ins_sf = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # FRAMING (FRM)
    frm_type = models.CharField(max_length=20, blank=True)
    frm_activity = models.CharField(max_length=20, blank=True)
    frm_lf = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Activity Notes
    activity_notes = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_scope_checklists'
    )

    class Meta:
        ordering = ['client', 'room']
        unique_together = ['room', 'client']
        indexes = [
            models.Index(fields=['client']),
            models.Index(fields=['room']),
        ]

    def __str__(self):
        return f"Scope Checklist - {self.room.room_name} ({self.client.pOwner})"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'clg_material': self.clg_material,
            'clg_construction': self.clg_construction,
            'clg_finish': self.clg_finish,
            'clg_activity': self.clg_activity,
            'clg_sf': str(self.clg_sf) if self.clg_sf else '',
            'lit_type': self.lit_type,
            'lit_activity': self.lit_activity,
            'lit_qty': self.lit_qty or '',
            'hvc_type': self.hvc_type,
            'hvc_activity': self.hvc_activity,
            'hvc_qty': self.hvc_qty or '',
            'wal_material': self.wal_material,
            'wal_finish': self.wal_finish,
            'wal_activity': self.wal_activity,
            'wal_sf': str(self.wal_sf) if self.wal_sf else '',
            'ele_outlets': self.ele_outlets or '',
            'ele_switches': self.ele_switches or '',
            'ele_sw3': self.ele_sw3 or '',
            'ele_activity': self.ele_activity,
            'flr_type': self.flr_type,
            'flr_activity': self.flr_activity,
            'flr_sf': str(self.flr_sf) if self.flr_sf else '',
            'bb_height': self.bb_height,
            'bb_activity': self.bb_activity,
            'bb_lf': str(self.bb_lf) if self.bb_lf else '',
            'trim_type': self.trim_type,
            'trim_crown': self.trim_crown,
            'trim_chairrail': self.trim_chairrail,
            'trim_activity': self.trim_activity,
            'dor_type': self.dor_type,
            'dor_activity': self.dor_activity,
            'dor_qty': self.dor_qty or '',
            'open_activity': self.open_activity,
            'open_qty': self.open_qty or '',
            'wdw_type': self.wdw_type,
            'wdw_covers': self.wdw_covers,
            'wdw_activity': self.wdw_activity,
            'wdw_qty': self.wdw_qty or '',
            'closet_type': self.closet_type,
            'closet_rod': self.closet_rod,
            'closet_lf': str(self.closet_lf) if self.closet_lf else '',
            'ins_type': self.ins_type,
            'ins_rvalue': self.ins_rvalue,
            'ins_sf': str(self.ins_sf) if self.ins_sf else '',
            'frm_type': self.frm_type,
            'frm_activity': self.frm_activity,
            'frm_lf': str(self.frm_lf) if self.frm_lf else '',
            'activity_notes': self.activity_notes,
        }
