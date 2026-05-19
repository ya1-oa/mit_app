from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from docsAppR.models import DocumentCategory, GeneratedDocument, EmailSchedule, SentEmail, EmailOpenEvent
from .test_setup import ModelTestSetup
import uuid

class DocumentCategoryModelTest(ModelTestSetup):
    """Test DocumentCategory model"""
    
    def test_category_creation(self):
        """Test category creation and string representation"""
        self.assertEqual(str(self.category), 'Test Category')
    
    def test_category_parent_relationship(self):
        """Test parent-child relationship for categories"""
        child_category = DocumentCategory.objects.create(
            name='Child Category',
            parent=self.category
        )
        self.assertEqual(child_category.parent, self.category)
        self.assertEqual(list(self.category.documentcategory_set.all()), [child_category])

class GeneratedDocumentModelTest(ModelTestSetup):
    """Test GeneratedDocument model"""
    
    def test_document_creation(self):
        """Test document creation and basic properties"""
        self.assertEqual(str(self.document), 'Test Document')
        self.assertEqual(self.document.client_name, 'Test Client')
        self.assertEqual(self.document.category, self.category)
        self.assertEqual(self.document.created_by, self.user)
        self.assertIsNotNone(self.document.created_at)
    
    def test_document_ordering(self):
        """Test that documents are ordered by creation date descending"""
        # Create another document
        doc2 = GeneratedDocument.objects.create(
            filename='Newer Document',
            file=self.test_file,
            created_by=self.user
        )
        
        documents = GeneratedDocument.objects.all()
        self.assertEqual(documents[0], doc2)  # Newest first
        self.assertEqual(documents[1], self.document)
    
    def test_document_optional_fields(self):
        """Test document with optional fields omitted"""
        doc = GeneratedDocument.objects.create(
            filename='Minimal Document',
            file=self.test_file,
            created_by=self.user
        )
        self.assertIsNone(doc.category)
        self.assertEqual(doc.client_name, '')
        self.assertEqual(doc.description, '')

class EmailScheduleModelTest(ModelTestSetup):
    """Test EmailSchedule model"""
    
    def test_schedule_creation(self):
        """Test email schedule creation"""
        self.assertEqual(str(self.email_schedule), 'Test Schedule')
        self.assertEqual(self.email_schedule.subject, 'Test Subject')
        self.assertEqual(self.email_schedule.recipients, ['recipient1@example.com', 'recipient2@example.com'])
        self.assertTrue(self.email_schedule.is_active)
        self.assertEqual(self.email_schedule.created_by, self.user)
    
    def test_interval_choices(self):
        """Test interval choices are correctly set"""
        valid_intervals = ['none', 'daily', 'weekly', 'monthly', 'custom']
        for interval in valid_intervals:
            schedule = EmailSchedule.objects.create(
                name=f'Schedule {interval}',
                subject='Test',
                body='Test',
                recipients=['test@example.com'],
                start_date=timezone.now(),
                interval=interval,
                created_by=self.user,
                admin_notification_email='admin@example.com'
            )
            self.assertEqual(schedule.interval, interval)
    
    def test_get_next_send_time(self):
        """Test next send time calculation for different intervals"""
        base_time = timezone.now()
        
        # Test daily interval
        self.email_schedule.interval = 'daily'
        next_time = self.email_schedule.get_next_send_time(base_time)
        expected_time = base_time + timezone.timedelta(days=1)
        self.assertEqual(next_time.date(), expected_time.date())
        
        # Test weekly interval
        self.email_schedule.interval = 'weekly'
        next_time = self.email_schedule.get_next_send_time(base_time)
        expected_time = base_time + timezone.timedelta(weeks=1)
        self.assertEqual(next_time.date(), expected_time.date())
        
        # Test custom interval
        self.email_schedule.interval = 'custom'
        self.email_schedule.custom_interval_days = 3
        next_time = self.email_schedule.get_next_send_time(base_time)
        expected_time = base_time + timezone.timedelta(days=3)
        self.assertEqual(next_time.date(), expected_time.date())
        
        # Test no interval
        self.email_schedule.interval = 'none'
        next_time = self.email_schedule.get_next_send_time(base_time)
        self.assertIsNone(next_time)
    
    def test_get_next_send_time_no_last_sent(self):
        """Test next send time when no previous send"""
        next_time = self.email_schedule.get_next_send_time()
        self.assertEqual(next_time, self.email_schedule.start_date)

class SentEmailModelTest(ModelTestSetup):
    """Test SentEmail model"""
    
    def test_sent_email_creation(self):
        """Test sent email creation"""
        sent_email = self.create_sent_email()
        
        self.assertEqual(sent_email.subject, 'Test Email')
        self.assertEqual(sent_email.recipients, ['test@example.com'])
        self.assertEqual(sent_email.sent_by, self.user)
        self.assertFalse(sent_email.is_opened)
        self.assertIsNone(sent_email.opened_at)
        self.assertIsNotNone(sent_email.tracking_pixel_id)
        self.assertIsInstance(sent_email.tracking_pixel_id, uuid.UUID)
    
    def test_sent_email_ordering(self):
        """Test that sent emails are ordered by sent date descending"""
        sent_email1 = self.create_sent_email(subject='First Email')
        sent_email2 = self.create_sent_email(subject='Second Email')
        
        sent_emails = SentEmail.objects.all()
        self.assertEqual(sent_emails[0], sent_email2)  # Newest first
        self.assertEqual(sent_emails[1], sent_email1)
    
    def test_sent_email_string_representation(self):
        """Test sent email string representation"""
        sent_email = self.create_sent_email(subject='Important Email')
        expected_str = f"Important Email - {sent_email.sent_at}"
        self.assertEqual(str(sent_email), expected_str)

class EmailOpenEventModelTest(ModelTestSetup):
    """Test EmailOpenEvent model"""
    
    def test_open_event_creation(self):
        """Test email open event creation"""
        sent_email = self.create_sent_email()
        open_event = EmailOpenEvent.objects.create(
            sent_email=sent_email,
            ip_address='192.168.1.1',
            user_agent='Test Browser'
        )
        
        self.assertEqual(open_event.sent_email, sent_email)
        self.assertEqual(open_event.ip_address, '192.168.1.1')
        self.assertEqual(open_event.user_agent, 'Test Browser')
        self.assertIsNotNone(open_event.opened_at)
    
    def test_open_event_ordering(self):
        """Test that open events are ordered by opened date descending"""
        sent_email = self.create_sent_email()
        event1 = EmailOpenEvent.objects.create(sent_email=sent_email)
        event2 = EmailOpenEvent.objects.create(sent_email=sent_email)
        
        events = EmailOpenEvent.objects.all()
        self.assertEqual(events[0], event2)  # Newest first
        self.assertEqual(events[1], event1)