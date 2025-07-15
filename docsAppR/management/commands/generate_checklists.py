from django.core.management.base import BaseCommand
from docsAppR.models import Client
from docsAppR.signals import create_checklist_items_for_client

class Command(BaseCommand):
    help = 'Generate checklist items for all existing clients'

    def handle(self, *args, **options):
        for client in Client.objects.all():
            create_checklist_items_for_client(client)
            self.stdout.write(f'Created checklist items for {client.pOwner}')