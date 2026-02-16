#!/usr/bin/env python
"""
Test the complete email sending flow
Run this with: docker-compose exec web python test_full_email_flow.py
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mitigation_app.settings')
django.setup()

from django.conf import settings
from django.core.mail import EmailMessage
from django.contrib.auth import get_user_model
from docsAppR.models import SentEmail, Document
from docsAppR.forms import EmailForm

User = get_user_model()

def test_complete_flow():
    """Test the complete email sending flow as it happens in the view"""
    print("=" * 60)
    print("TESTING COMPLETE EMAIL FLOW")
    print("=" * 60)

    try:
        # Get or create a test user
        user, created = User.objects.get_or_create(
            username='testuser',
            defaults={'email': 'test@example.com'}
        )
        if created:
            user.set_password('testpass123')
            user.save()
            print(f"✅ Created test user: {user.username}")
        else:
            print(f"✅ Using existing test user: {user.username}")

        # Test form data (simulating what comes from the UI)
        form_data = {
            'recipients': 'co.allphaseconsulting@gmail.com',
            'subject': '🧪 Full Flow Test Email',
            'body': 'This is a test email sent through the complete flow simulation.',
            'send_now': True,
            'notify_on_open': True,
            'admin_notification_email': 'co.allphaseconsulting@gmail.com',
        }

        print(f"\n📝 Form data:")
        for key, value in form_data.items():
            print(f"  {key}: {value}")

        # Validate form
        form = EmailForm(data=form_data)
        if not form.is_valid():
            print(f"\n❌ Form validation FAILED:")
            print(f"Errors: {form.errors}")
            return False

        print(f"\n✅ Form validation PASSED")

        # Get cleaned data
        recipients = form.cleaned_data['recipients']
        print(f"\n📧 Recipients (after cleaning): {recipients}")
        print(f"   Type: {type(recipients)}")

        # Create email message (as in the view)
        email = EmailMessage(
            subject=form.cleaned_data['subject'],
            body=form.cleaned_data['body'],
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )

        print(f"\n✉️  Email object created:")
        print(f"   Subject: {email.subject}")
        print(f"   From: {email.from_email}")
        print(f"   To: {email.to}")
        print(f"   Body: {email.body[:50]}...")

        # Create SentEmail record (as in the view)
        sent_email = SentEmail.objects.create(
            subject=form.cleaned_data['subject'],
            body=form.cleaned_data['body'],
            recipients=recipients,
            sent_by=user,
            notify_on_open=form.cleaned_data['notify_on_open'],
            admin_notification_email=form.cleaned_data['admin_notification_email'] or user.email,
        )

        print(f"\n💾 SentEmail record created:")
        print(f"   ID: {sent_email.id}")
        print(f"   Tracking ID: {sent_email.tracking_pixel_id}")

        # Add tracking pixel (as in the view)
        tracking_url = f'http://localhost/emails/track/{sent_email.tracking_pixel_id}/'
        html_body = f'<div style="white-space: pre-wrap;">{form.cleaned_data["body"]}</div>'
        html_body += f'<img src="{tracking_url}" width="1" height="1" />'
        email.body = html_body
        email.content_subtype = "html"

        print(f"\n🔍 Tracking pixel added:")
        print(f"   URL: {tracking_url}")

        # Send email
        print(f"\n📤 Sending email...")
        result = email.send()
        print(f"✅ Email sent! Result: {result}")

        # Clean up test record
        sent_email.delete()
        print(f"\n🧹 Cleaned up test SentEmail record")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("\n🚀 Starting Complete Email Flow Test\n")

    success = test_complete_flow()

    print("\n" + "=" * 60)
    print("TEST RESULT")
    print("=" * 60)

    if success:
        print("🎉 COMPLETE FLOW TEST PASSED!")
        print("\nThe email system is working end-to-end.")
        print("If you're not seeing emails sent through the UI:")
        print("  1. Check browser console for JavaScript errors")
        print("  2. Check that documents are selected before clicking Send")
        print("  3. Check Django messages are displaying (now fixed)")
        print("  4. Check Docker logs: docker-compose logs web")
    else:
        print("❌ COMPLETE FLOW TEST FAILED")
        print("Check the error messages above.")

    print("=" * 60)
