from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.forms import ModelForm
import os

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
    dateOfLoss = models.DateField(null=True)
    rebuildType1 = models.CharField(max_length=255, blank=True)
    rebuildType2 = models.CharField(max_length=255, blank=True)
    rebuildType3 = models.CharField(max_length=255, blank=True)
    demo = models.BooleanField(default=False)
    mitigation = models.BooleanField(default=False)
    otherStructures = models.BooleanField(default=False)
    replacement = models.BooleanField(default=False)
    CPSCLNCONCGN = models.BooleanField(default=False)
    yearBuilt = models.CharField(max_length=255, blank=True)
    contractDate = models.DateField(null=True)
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
    claimReportDate = models.DateField(null=True)
    insuranceCustomerServiceRep = models.CharField(max_length=255, blank=True)
    timeOfClaimReport = models.CharField(max_length=255, blank=True)
    phoneExt = models.CharField(max_length=255, blank=True)
    tarpExtTMPOk = models.BooleanField(default=False)
    IntTMPOk = models.BooleanField(default=False)
    DRYPLACUTOUTMOLDSPRAYOK = models.BooleanField(default=False)
    
    #ALE
    lossOfUseALE = models.CharField(max_length=255, blank=True)
    tenantLesee = models.CharField(max_length=255, blank=True)
    propertyAddressStreet = models.CharField(max_length=255, blank=True)
    propertyCityStateZip = models.CharField(max_length=255, blank=True)
    customerEmail = models.CharField(max_length=255, blank=True)
    cstOwnerPhoneNumber = models.CharField(max_length=255, blank=True)
    causeOfLoss = models.CharField(max_length=255, blank=True)
    dateOfLoss = models.DateField(null=True)
    contractDate = models.DateField(null=True)
    insuranceCoName = models.CharField(max_length=255, blank=True)
    claimNumber = models.CharField(max_length=255, blank=True)
    policyClaimNumber = models.CharField(max_length=255, blank=True)
    emailInsCo = models.CharField(max_length=255, blank=True)
    deskAdjusterDA = models.CharField(max_length=255, blank=True)
    DAPhone = models.CharField(max_length=255, blank=True)
    DAPhExtNumber = models.CharField(max_length=255, blank=True)
    DAEmail = models.CharField(max_length=255, blank=True)
    startDate = models.DateField(null=True)
    endDate = models.DateField(null=True)
    lessor = models.CharField(max_length=255, blank=True)
    propertyAddressStreet = models.CharField(max_length=255, blank=True)
    propertyCityStateZip = models.CharField(max_length=255, blank=True)
    customerEmail = models.CharField(max_length=255, blank=True)
    cstOwnerPhoneNumber = models.CharField(max_length=255, blank=True)
    bedrooms = models.CharField(max_length=255, blank=True)
    termsAmount = models.CharField(max_length=255, blank=True)
    endDate = models.DateField(null=True)

# each file is linked to a customer ID, adn it provides a path to the file on the server
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