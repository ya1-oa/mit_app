from django.core.management.base import BaseCommand
from django.utils import timezone
from docsAppR.models import EmailSchedule, SentEmail
from django.core.mail import EmailMessage
from django.conf import settings

class Command(BaseCommand):
    help = 'Send scheduled emails'
    
    def handle(self, *args, **options):
        now = timezone.now()
        schedules = EmailSchedule.objects.filter(
            is_active=True,
            start_date__lte=now
        )
        
        for schedule in schedules:
            self.send_scheduled_email(schedule)
    
    def send_scheduled_email(self, schedule):
        # Implementation for sending scheduled emails
        # This would create SentEmail records and send the emails
        pass