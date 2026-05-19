from django.test import TestCase
from django.contrib.auth import get_user_model
from docsAppR.models import DocumentCategory, GeneratedDocument, EmailSchedule, SentEmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
import uuid

User = get_user_model()

class TestSetup(TestCase):
    """Base test class with common setup methods"""
    
    def setUp(self):
        """Set up test data for all tests"""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        self.admin_user = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123'
        )
        
        self.category = DocumentCategory.objects.create(
            name='Test Category'
        )
        
        # Create a test file
        self.test_file = SimpleUploadedFile(
            "test_document.pdf",
            b"file_content",
            content_type="application/pdf"
        )
        
        self.document = GeneratedDocument.objects.create(
            filename='Test Document',
            file=self.test_file,
            category=self.category,
            client_name='Test Client',
            created_by=self.user,
            description='Test description'
        )
        
        self.email_schedule = EmailSchedule.objects.create(
            name='Test Schedule',
            subject='Test Subject',
            body='Test Body',
            recipients=['recipient1@example.com', 'recipient2@example.com'],
            start_date=timezone.now() + timezone.timedelta(hours=1),
            interval='daily',
            repeat_count=5,
            created_by=self.user,
            notify_on_open=True,
            admin_notification_email='admin@example.com'
        )
        self.email_schedule.documents.add(self.document)

class ModelTestSetup(TestSetup):
    """Base class for model tests with additional setup"""
    
    def create_sent_email(self, **kwargs):
        """Helper method to create sent email instances"""
        defaults = {
            'subject': 'Test Email',
            'body': 'Test email body',
            'recipients': ['test@example.com'],
            'sent_by': self.user,
            'notify_on_open': True,
            'admin_notification_email': 'admin@example.com'
        }
        defaults.update(kwargs)
        
        sent_email = SentEmail.objects.create(**defaults)
        if 'documents' in kwargs:
            sent_email.documents.set(kwargs['documents'])
        else:
            sent_email.documents.add(self.document)
        return sent_email