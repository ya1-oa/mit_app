# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Client, ChecklistItem

@receiver(post_save, sender=Client)
def create_client_checklist(sender, instance, created, **kwargs):
    if created:
        create_checklist_items_for_client(instance)

def create_checklist_items_for_client(client):
    """Create all required checklist items for a client based on their claim type"""
    # MIT Documents
    if client.mitigation:
        mit_docs = [
            'MIT_AUTH', 'MIT_AGREE', 'MIT_W9', 'MIT_VERIFY',
            'MIT_EQUIP', 'MIT_INVOICE', 'MIT_OVERVIEW',
            'MIT_DRYLOG', 'MIT_EMAIL'
        ]
        for doc_type in mit_docs:
            ChecklistItem.objects.get_or_create(
                client=client,
                document_type=doc_type,
                defaults={'required': True}
            )
    
    # CPS Documents
    if client.CPSCLNCONCGN:
        cps_docs = [
            'CPS_AUTH', 'CPS_AGREE', 'CPS_W9', 'CPS_VERIFY',
            'CPS_BOXCOUNT', 'CPS_BOXPHOTO', 'CPS_CUSTPICS',
            'CPS_CUSTLIST', 'CPS_INVOICE', 'CPS_ESX',
            'CPS_OVERVIEW', 'CPS_DAY1', 'CPS_DAY2',
            'CPS_DAY3', 'CPS_DAY4', 'CPS_EMAIL'
        ]
        for doc_type in cps_docs:
            ChecklistItem.objects.get_or_create(
                client=client,
                document_type=doc_type,
                defaults={'required': True}
            )
    
    # PPR Documents
    if client.replacement:
        ppr_docs = [
            'PPR_SCHEDULE', 'PPR_PHOTOREP', 'PPR_CUSTPICS',
            'PPR_CUSTLIST', 'PPR_EMAIL'
        ]
        for doc_type in ppr_docs:
            ChecklistItem.objects.get_or_create(
                client=client,
                document_type=doc_type,
                defaults={'required': True}
            )