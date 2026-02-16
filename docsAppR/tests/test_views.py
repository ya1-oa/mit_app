from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from docsAppR.models import GeneratedDocument, SentEmail, DocumentCategory, EmailOpenEvent
from .test_setup import TestSetup
import uuid
import base64

User = get_user_model()

class EmailViewTest(TestSetup):
    """Test email-related views"""
    
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')
        self.emails_url = reverse('emails')
    
    def test_emails_view_get(self):
        """Test GET request to emails view"""
        response = self.client.get(self.emails_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account/emails.html')
        self.assertIn('documents', response.context)
        self.assertIn('categories', response.context)
        self.assertIn('sent_emails', response.context)
        self.assertIn('schedules', response.context)
        self.assertIn('form', response.context)
    
    def test_emails_view_post_valid(self):
        """Test POST request with valid email data"""
        # Mock the email sending to avoid actual SMTP calls
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            post_data = {
                'documents': [self.document.id],
                'recipients': 'test1@example.com, test2@example.com',
                'subject': 'Test Email Subject',
                'body': 'Test email body content',
                'send_now': True,
                'notify_on_open': True,
                'admin_notification_email': 'admin@example.com'
            }
            
            response = self.client.post(self.emails_url, post_data)
            
            # Check redirect
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, self.emails_url)
            
            # Check that SentEmail was created
            self.assertTrue(SentEmail.objects.filter(subject='Test Email Subject').exists())
            
            # Check success message (would need to follow redirect to see it)
    
    def test_emails_view_post_invalid(self):
        """Test POST request with invalid email data"""
        post_data = {
            'recipients': 'test@example.com',
            # Missing subject and body
        }
        
        response = self.client.post(self.emails_url, post_data)
        
        # Should re-render the form with errors
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)
        self.assertTrue(response.context['form'].errors)
    
    def test_emails_view_filtering(self):
        """Test document filtering functionality"""
        # Create documents with different categories and clients
        category2 = DocumentCategory.objects.create(name='Category 2')
        doc2 = GeneratedDocument.objects.create(
            filename='Doc 2',
            file=self.test_file,
            category=category2,
            client_name='Client B',
            created_by=self.user
        )
        
        # Test category filter
        response = self.client.get(self.emails_url, {'category': self.category.id})
        self.assertEqual(response.status_code, 200)
        documents = response.context['documents']
        self.assertTrue(all(doc.category == self.category for doc in documents))
        
        # Test client filter
        response = self.client.get(self.emails_url, {'client': 'Client B'})
        self.assertEqual(response.status_code, 200)
        documents = response.context['documents']
        self.assertTrue(all('Client B' in doc.client_name for doc in documents))
        
        # Test date range filter
        response = self.client.get(self.emails_url, {'date_range': 'today'})
        self.assertEqual(response.status_code, 200)
    
    def test_emails_view_authentication_required(self):
        """Test that email view requires authentication"""
        self.client.logout()
        response = self.client.get(self.emails_url)
        # Should redirect to login
        self.assertEqual(response.status_code, 302)

class EmailTrackingTest(TestSetup):
    """Test email tracking functionality"""
    
    def setUp(self):
        super().setUp()
        self.client = Client()
    
    def test_track_email_open(self):
        """Test email open tracking with pixel"""
        sent_email = SentEmail.objects.create(
            subject='Tracked Email',
            body='Test body',
            recipients=['test@example.com'],
            sent_by=self.user,
            tracking_pixel_id=uuid.uuid4(),
            notify_on_open=True,
            admin_notification_email='admin@example.com'
        )
        
        tracking_url = reverse('track_email_open', args=[sent_email.tracking_pixel_id])
        response = self.client.get(tracking_url)
        
        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/gif')
        
        # Check that email was marked as opened
        sent_email.refresh_from_db()
        self.assertTrue(sent_email.is_opened)
        self.assertIsNotNone(sent_email.opened_at)
        
        # Check that open event was created
        self.assertTrue(EmailOpenEvent.objects.filter(sent_email=sent_email).exists())
    
    def test_track_nonexistent_email(self):
        """Test tracking for non-existent email ID"""
        fake_uuid = uuid.uuid4()
        tracking_url = reverse('track_email_open', args=[fake_uuid])
        response = self.client.get(tracking_url)
        
        # Should still return the tracking pixel without error
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/gif')
    
    def test_tracking_pixel_content(self):
        """Test that tracking pixel returns correct image data"""
        sent_email = SentEmail.objects.create(
            subject='Test',
            body='Test',
            recipients=['test@example.com'],
            sent_by=self.user,
            tracking_pixel_id=uuid.uuid4()
        )
        
        tracking_url = reverse('track_email_open', args=[sent_email.tracking_pixel_id])
        response = self.client.get(tracking_url)
        
        # Check that it returns a 1x1 transparent GIF
        expected_gif = base64.b64decode(b'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
        self.assertEqual(response.content, expected_gif)
        
        # Check cache headers
        self.assertEqual(response['Cache-Control'], 'no-cache, no-store, must-revalidate')
        self.assertEqual(response['Pragma'], 'no-cache')
        self.assertEqual(response['Expires'], '0')

class DocumentListAPITest(TestSetup):
    """Test document list API endpoint"""
    
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')
        self.api_url = reverse('document_list_api')
    
    def test_document_list_api(self):
        """Test basic API functionality"""
        response = self.client.get(self.api_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        data = response.json()
        self.assertIn('documents', data)
        self.assertEqual(len(data['documents']), 1)
        self.assertEqual(data['documents'][0]['filename'], 'Test Document')
    
    def test_document_list_api_filtering(self):
        """Test API filtering parameters"""
        # Create another document with different category
        category2 = DocumentCategory.objects.create(name='Category 2')
        doc2 = GeneratedDocument.objects.create(
            filename='Filtered Doc',
            file=self.test_file,
            category=category2,
            client_name='Special Client',
            created_by=self.user
        )
        
        # Test category filter
        response = self.client.get(self.api_url, {'category': category2.id})
        data = response.json()
        self.assertEqual(len(data['documents']), 1)
        self.assertEqual(data['documents'][0]['filename'], 'Filtered Doc')
        
        # Test client filter
        response = self.client.get(self.api_url, {'client': 'Special Client'})
        data = response.json()
        self.assertEqual(len(data['documents']), 1)
        self.assertEqual(data['documents'][0]['client_name'], 'Special Client')
        
        # Test search
        response = self.client.get(self.api_url, {'search': 'Filtered'})
        data = response.json()
        self.assertEqual(len(data['documents']), 1)
        self.assertEqual(data['documents'][0]['filename'], 'Filtered Doc')
    
    def test_document_list_api_authentication(self):
        """Test that API requires authentication"""
        self.client.logout()
        response = self.client.get(self.api_url)
        # Should redirect to login
        self.assertEqual(response.status_code, 302)

class EmailScheduleViewTest(TestSetup):
    """Test email schedule creation view"""
    
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')
        self.schedule_url = reverse('create_schedule')
    
    def test_schedule_view_get(self):
        """Test GET request to schedule creation view"""
        response = self.client.get(self.schedule_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account/email_schedule_form.html')
        self.assertIn('form', response.context)
    
    def test_schedule_view_post_valid(self):
        """Test POST request with valid schedule data"""
        post_data = {
            'name': 'New Test Schedule',
            'subject': 'Scheduled Email',
            'body': 'This is a scheduled email',
            'recipients': 'schedule1@example.com, schedule2@example.com',
            'start_date': timezone.now() + timezone.timedelta(days=1),
            'interval': 'weekly',
            'repeat_count': 3,
            'notify_on_open': True,
            'admin_notification_email': 'admin@example.com',
            'documents': [self.document.id]
        }
        
        response = self.client.post(self.schedule_url, post_data)
        
        # Check redirect
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('emails'))
        
        # Check that schedule was created
        self.assertTrue(EmailSchedule.objects.filter(name='New Test Schedule').exists())
        schedule = EmailSchedule.objects.get(name='New Test Schedule')
        self.assertEqual(schedule.recipients, ['schedule1@example.com', 'schedule2@example.com'])
        self.assertEqual(schedule.interval, 'weekly')
        self.assertEqual(schedule.created_by, self.user)
    
    def test_schedule_view_post_invalid(self):
        """Test POST request with invalid schedule data"""
        post_data = {
            'name': '',  # Missing required field
            'subject': 'Test',
            'body': 'Test',
            'recipients': 'invalid-email',  # Invalid email
            'start_date': timezone.now(),
            'interval': 'none',
            'admin_notification_email': 'admin@example.com'
        }
        
        response = self.client.post(self.schedule_url, post_data)
        
        # Should re-render form with errors
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)
        self.assertTrue(response.context['form'].errors)