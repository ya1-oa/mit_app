from django.test import TestCase
from django.urls import reverse
from django.core import mail
from django.utils import timezone
from docsAppR.models import SentEmail, EmailOpenEvent
from .test_setup import TestSetup
import uuid

class EmailIntegrationTest(TestSetup):
    """Integration tests for the complete email flow"""
    
    def setUp(self):
        super().setUp()
        self.client.login(email='test@example.com', password='testpass123')
    
    def test_complete_email_flow(self):
        """Test complete email flow from composition to tracking"""
        # Step 1: Send email
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            post_data = {
                'documents': [self.document.id],
                'recipients': 'recipient@example.com',
                'subject': 'Integration Test Email',
                'body': 'This is an integration test',
                'send_now': True,
                'notify_on_open': True,
                'admin_notification_email': 'admin@example.com'
            }
            
            response = self.client.post(reverse('emails'), post_data)
            self.assertEqual(response.status_code, 302)
            
            # Step 2: Verify email was sent and recorded
            sent_email = SentEmail.objects.get(subject='Integration Test Email')
            self.assertIsNotNone(sent_email)
            self.assertFalse(sent_email.is_opened)
            self.assertIsNone(sent_email.opened_at)
            
            # Step 3: Simulate email opening
            tracking_url = reverse('track_email_open', args=[sent_email.tracking_pixel_id])
            response = self.client.get(tracking_url)
            self.assertEqual(response.status_code, 200)
            
            # Step 4: Verify tracking worked
            sent_email.refresh_from_db()
            self.assertTrue(sent_email.is_opened)
            self.assertIsNotNone(sent_email.opened_at)
            
            # Step 5: Verify open event was created
            self.assertTrue(EmailOpenEvent.objects.filter(sent_email=sent_email).exists())
            
            # Step 6: Check that notification email would be sent
            # (In a real test with Celery, you'd check the task queue)
    
    def test_email_with_multiple_recipients(self):
        """Test email sending to multiple recipients"""
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            post_data = {
                'recipients': 'user1@example.com, user2@example.com, user3@example.com',
                'subject': 'Multi-recipient Test',
                'body': 'Testing multiple recipients',
                'send_now': True,
                'notify_on_open': False
            }
            
            response = self.client.post(reverse('emails'), post_data)
            self.assertEqual(response.status_code, 302)
            
            sent_email = SentEmail.objects.get(subject='Multi-recipient Test')
            self.assertEqual(len(sent_email.recipients), 3)
            self.assertIn('user1@example.com', sent_email.recipients)
            self.assertIn('user2@example.com', sent_email.recipients)
            self.assertIn('user3@example.com', sent_email.recipients)
    
    def test_scheduled_email_creation(self):
        """Test creating a scheduled email with repeat settings"""
        future_date = timezone.now() + timezone.timedelta(days=7)
        
        post_data = {
            'name': 'Integration Test Schedule',
            'subject': 'Scheduled Integration Test',
            'body': 'This is a scheduled email for integration testing',
            'recipients': 'test@example.com',
            'start_date': future_date,
            'interval': 'monthly',
            'repeat_count': 6,
            'notify_on_open': True,
            'admin_notification_email': 'admin@example.com',
            'documents': [self.document.id]
        }
        
        response = self.client.post(reverse('create_schedule'), post_data)
        self.assertEqual(response.status_code, 302)
        
        schedule = EmailSchedule.objects.get(name='Integration Test Schedule')
        self.assertEqual(schedule.interval, 'monthly')
        self.assertEqual(schedule.repeat_count, 6)
        self.assertTrue(schedule.is_active)
        self.assertEqual(schedule.created_by, self.user)
        self.assertIn(self.document, schedule.documents.all())