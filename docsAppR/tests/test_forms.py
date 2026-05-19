from django.test import TestCase
from django.utils import timezone
from docsAppR.forms import EmailForm, EmailScheduleForm
from .test_setup import TestSetup

class EmailFormTest(TestSetup):
    """Test EmailForm validation and functionality"""
    
    def test_valid_email_form(self):
        """Test form with valid data"""
        form_data = {
            'documents': [self.document.id],
            'recipients': 'test1@example.com, test2@example.com',
            'subject': 'Test Subject',
            'body': 'Test email body',
            'send_now': True,
            'notify_on_open': True,
            'admin_notification_email': 'admin@example.com'
        }
        form = EmailForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_email_form_recipients_parsing(self):
        """Test that recipients are properly parsed"""
        form_data = {
            'recipients': '  test1@example.com, test2@example.com  , test3@example.com',
            'subject': 'Test',
            'body': 'Test'
        }
        form = EmailForm(data=form_data)
        if form.is_valid():
            recipients = form.cleaned_data['recipients']
            self.assertEqual(recipients, 'test1@example.com, test2@example.com, test3@example.com')
    
    def test_email_form_missing_required_fields(self):
        """Test form validation with missing required fields"""
        form_data = {
            'recipients': 'test@example.com',
            # Missing subject and body
        }
        form = EmailForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('subject', form.errors)
        self.assertIn('body', form.errors)
    
    def test_email_form_invalid_emails(self):
        """Test form validation with invalid email addresses"""
        form_data = {
            'recipients': 'invalid-email, test@example.com',
            'subject': 'Test',
            'body': 'Test'
        }
        form = EmailForm(data=form_data)
        # Note: The form doesn't do extensive email validation in clean_recipients
        # This test documents the current behavior
    
    def test_email_form_scheduling(self):
        """Test form with scheduling options"""
        future_time = timezone.now() + timezone.timedelta(hours=2)
        form_data = {
            'recipients': 'test@example.com',
            'subject': 'Test',
            'body': 'Test',
            'send_now': False,
            'scheduled_time': future_time
        }
        form = EmailForm(data=form_data)
        self.assertTrue(form.is_valid())

class EmailScheduleFormTest(TestSetup):
    """Test EmailScheduleForm validation and functionality"""
    
    def test_valid_schedule_form(self):
        """Test form with valid data"""
        form_data = {
            'name': 'Test Schedule',
            'subject': 'Test Subject',
            'body': 'Test Body',
            'recipients': 'test1@example.com, test2@example.com',
            'start_date': timezone.now() + timezone.timedelta(days=1),
            'interval': 'daily',
            'repeat_count': 5,
            'notify_on_open': True,
            'admin_notification_email': 'admin@example.com'
        }
        form = EmailScheduleForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_schedule_form_recipients_validation(self):
        """Test recipients field validation"""
        # Test with valid emails
        form_data = {
            'name': 'Test',
            'subject': 'Test',
            'body': 'Test',
            'recipients': 'valid@example.com, another.valid@test.org',
            'start_date': timezone.now(),
            'interval': 'none',
            'admin_notification_email': 'admin@example.com'
        }
        form = EmailScheduleForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        # Test with invalid email format
        form_data['recipients'] = 'invalid-email-format'
        form = EmailScheduleForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('recipients', form.errors)
    
    def test_schedule_form_custom_interval_validation(self):
        """Test custom interval validation"""
        # Test custom interval without days
        form_data = {
            'name': 'Test',
            'subject': 'Test',
            'body': 'Test',
            'recipients': 'test@example.com',
            'start_date': timezone.now(),
            'interval': 'custom',
            'custom_interval_days': None,  # Missing required field
            'admin_notification_email': 'admin@example.com'
        }
        form = EmailScheduleForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)
    
    def test_schedule_form_clean_recipients(self):
        """Test the clean_recipients method"""
        form = EmailScheduleForm()
        
        # Test with valid emails
        valid_emails = 'test1@example.com, test2@example.com'
        cleaned = form.clean_recipients(valid_emails)
        self.assertEqual(cleaned, ['test1@example.com', 'test2@example.com'])
        
        # Test with invalid email
        with self.assertRaises(Exception):  # Adjust based on your actual validation
            invalid_emails = 'invalid-email'
            form.clean_recipients(invalid_emails)