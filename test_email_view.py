#!/usr/bin/env python
"""
Test the email view functionality
Run this with: docker-compose exec web python test_email_view.py
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mitigation_app.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from docsAppR.forms import EmailForm

User = get_user_model()

def test_email_form():
    """Test the EmailForm validation"""
    print("=" * 60)
    print("TESTING EMAIL FORM")
    print("=" * 60)

    # Test valid form data
    form_data = {
        'recipients': 'co.allphaseconsulting@gmail.com',
        'subject': 'Test Email from Form',
        'body': 'This is a test email body.',
        'send_now': True,
        'notify_on_open': False,
    }

    form = EmailForm(data=form_data)

    if form.is_valid():
        print("✅ Form is VALID")
        print(f"Recipients (cleaned): {form.cleaned_data['recipients']}")
        print(f"Subject: {form.cleaned_data['subject']}")
        print(f"Send now: {form.cleaned_data['send_now']}")
        return True
    else:
        print("❌ Form is INVALID")
        print(f"Errors: {form.errors}")
        return False


def test_multiple_recipients():
    """Test multiple recipients"""
    print("\n" + "=" * 60)
    print("TESTING MULTIPLE RECIPIENTS")
    print("=" * 60)

    form_data = {
        'recipients': 'co.allphaseconsulting@gmail.com, test@example.com',
        'subject': 'Test Email',
        'body': 'Test body',
        'send_now': True,
        'notify_on_open': False,
    }

    form = EmailForm(data=form_data)

    if form.is_valid():
        recipients = form.cleaned_data['recipients']
        print(f"✅ Form is VALID")
        print(f"Recipients count: {len(recipients)}")
        print(f"Recipients: {recipients}")
        return True
    else:
        print("❌ Form is INVALID")
        print(f"Errors: {form.errors}")
        return False


def test_invalid_email():
    """Test invalid email validation"""
    print("\n" + "=" * 60)
    print("TESTING INVALID EMAIL VALIDATION")
    print("=" * 60)

    form_data = {
        'recipients': 'invalid-email',
        'subject': 'Test Email',
        'body': 'Test body',
        'send_now': True,
        'notify_on_open': False,
    }

    form = EmailForm(data=form_data)

    if not form.is_valid():
        print("✅ Form correctly REJECTED invalid email")
        print(f"Errors: {form.errors}")
        return True
    else:
        print("❌ Form incorrectly ACCEPTED invalid email")
        return False


if __name__ == '__main__':
    print("\n🚀 Starting Email Form Tests\n")

    # Run tests
    test1 = test_email_form()
    test2 = test_multiple_recipients()
    test3 = test_invalid_email()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Basic Form Test: {'✅ PASSED' if test1 else '❌ FAILED'}")
    print(f"Multiple Recipients: {'✅ PASSED' if test2 else '❌ FAILED'}")
    print(f"Invalid Email Validation: {'✅ PASSED' if test3 else '❌ FAILED'}")
    print("=" * 60)

    if all([test1, test2, test3]):
        print("\n🎉 ALL TESTS PASSED! Email form is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Check the error messages above.")
