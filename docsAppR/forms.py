from typing import Any
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django import forms
from django.forms.widgets import PasswordInput, TextInput
from .models import CustomUser, Client

class CreateUserForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ['email', 'username']

class UploadFilesForm():
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
    lossOfUse = forms.CharField()
    breathingIssue = forms.CharField()
    hazardMaterialRemediation = forms.CharField()

    #Insurance
    insuranceCo_Name = forms.CharField()
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
    DAPhExt = forms.CharField()
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
    class Meta:
            model = Client
            fields = [
                'pOwner',
                'pAddress',
                'pCityStateZip',
                'cEmail',
                'cPhone',
                'coOwner2',
                'cPhone2',
                'cAddress2',
                'cCityStateZip2',
                'cEmail2',
                'causeOfLoss',
                'dateOfLoss',
                'rebuildType1',
                'rebuildType2',
                'rebuildType3',
                'demo',
                'mitigation',
                'otherStructures',
                'replacement',
                'CPSCLNCONCGN',
                'yearBuilt',
                'contractDate',
                'lossOfUse',
                'breathingIssue',
                'hazardMaterialRemediation',
                'insuranceCo_Name',
                'insAddressOvernightMail',
                'insCityStateZip',
                'insuranceCoPhone',
                'insWebsite',
                'insMailingAddress',
                'insMailCityStateZip',
                'claimNumber',
                'policyNumber',
                'emailInsCo',
                'deskAdjusterDA',
                'DAPhone',
                'DAPhExt',
                'DAEmail',
                'fieldAdjusterName',
                'phoneFieldAdj',
                'fieldAdjEmail',
                'adjContents',
                'adjCpsPhone',
                'adjCpsEmail',
                'emsAdj',
                'emsAdjPhone',
                'emsTmpEmail',
                'attLossDraftDept',
                'newCustomerID',
                'roomID',
                'roomArea1',
                'roomArea2',
                'roomArea3',
                'roomArea4',
                'roomArea5',
                'roomArea6',
                'roomArea7',
                'roomArea8',
                'roomArea9',
                'roomArea10',
                'roomArea11',
                'roomArea12',
                'roomArea13',
                'roomArea14',
                'roomArea15',
                'roomArea16',
                'roomArea17',
                'roomArea18',
                'roomArea19',
                'roomArea20',
                'roomArea21',
                'roomArea22',
                'roomArea23',
                'roomArea24',
                'roomArea25',
                'mortgageCo',
                'mortgageAccountCo',
                'mortgageContactPerson',
                'mortgagePhoneContact',
                'mortgagePhoneExtContact',
                'mortgageAttnLossDraftDept',
                'mortgageOverNightMail',
                'mortgageCityStZipOVN',
                'mortgageEmail',
                'mortgageWebsite',
                'mortgageWebsite',
                'mortgageCoFax',
                'mortgageMailingAddress',
            ]