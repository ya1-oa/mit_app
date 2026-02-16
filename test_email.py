#!/usr/bin/env python
"""
Test email configuration
Run this with: docker-compose exec web python test_email.py
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mitigation_app.settings')
django.setup()

from django.core.mail import send_mail, EmailMessage
from django.conf import settings

def test_basic_email():
    """Test basic text email"""
    print("=" * 60)
    print("TESTING EMAIL CONFIGURATION")
    print("=" * 60)
    print(f"EMAIL_HOST: {settings.EMAIL_HOST}")
    print(f"EMAIL_PORT: {settings.EMAIL_PORT}")
    print(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
    print(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
    print("=" * 60)

    try:
        result = send_mail(
            subject='✅ Test Email from Claimet App',
            message='This is a test email to verify the email system is working correctly.\n\nIf you receive this, your email configuration is set up properly!',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['galaxielsaga@gmail.com'],
            fail_silently=False,
        )
        print(f"✅ SUCCESS! Email sent. Result: {result}")
        return True
    except Exception as e:
        print(f"❌ ERROR sending email: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False


def test_html_email():
    """Test HTML email with styling"""
    print("\n" + "=" * 60)
    print("TESTING HTML EMAIL")
    print("=" * 60)

    html_content = """
<div style="font-family: Arial, sans-serif; background:#f5f7fa; padding:30px;">

  <!-- ========================= -->
  <!-- HEADER / BRANDING BAR -->
  <!-- ========================= -->
  <div style="
      background: linear-gradient(90deg, #1e88e5, #42a5f5);
      color:white;
      padding:20px 25px;
      border-radius:8px;
      font-size:22px;
      font-weight:bold;
      margin-bottom:25px;
      box-shadow:0 4px 12px rgba(0,0,0,0.15);
  ">
    OH25 BROWNLEE — Worktype Documentation  
  </div>


  <!-- ========================= -->
  <!-- CARD: REFERENCE INDEX -->
  <!-- ========================= -->
  <div style="
      background:white;
      border-radius:10px;
      padding:25px;
      margin-bottom:35px;
      box-shadow:0 3px 12px rgba(0,0,0,0.12);
  ">
    <h2 style="margin-top:0; color:#1e88e5;">Reference Index — Worktype Codes</h2>

    <table cellspacing="0" cellpadding="8" border="1"
      style="border-collapse: collapse; width:100%; font-size:14px; border-color:#d0d0d0;">

      <tr>
        <th style="background:#e3f2fd; font-weight:bold;">Code</th>
        <th style="background:#e3f2fd; font-weight:bold;">Description</th>
      </tr>

      <tr><td>0.01</td><td>Jobsite Verification</td></tr>
      <tr><td>0.02</td><td>Exterior Damages (If Applicable)</td></tr>
      <tr><td>0.03</td><td>Mechanicals – Water Meter Reading & Plumbing Report/Invoice</td></tr>
      <tr><td>0.04</td><td>Mechanicals – Electrical Hazards (If Applicable)</td></tr>
      <tr><td>0.05</td><td>Kitchen Cabinet Sizes (If Applicable)</td></tr>
      <tr><td>0.06</td><td>Bathroom Fixtures (If Applicable)</td></tr>

      <tr><td>100</td><td>Rooms Overview</td></tr>
      <tr><td>200</td><td>Source of Loss</td></tr>
      <tr><td>300</td><td>CPS</td></tr>
      <tr><td>3222</td><td>CPS Day 2 WIP</td></tr>
      <tr><td>3322</td><td>CPS Day 3 Storage</td></tr>
      <tr><td>3444</td><td>CPS Day 4 Packback</td></tr>

      <tr><td>400</td><td>PPR</td></tr>
      <tr><td>411.1</td><td>Replacement 1 – Contractor Overview Day Pics</td></tr>
      <tr><td>422.2</td><td>Replacement 2 – WIP</td></tr>
      <tr><td>433.3</td><td>Replacement 3 – Storage</td></tr>
      <tr><td>444.4</td><td>Replacement 4 – Disposal</td></tr>

      <tr><td>500</td><td>DMO Demo</td></tr>
      <tr><td>600</td><td>WTR Mitigation Equipment & W.I.P</td></tr>

      <tr><td>7000</td><td>HMR</td></tr>
      <tr><td>7999</td><td>Lead & HMR Testing</td></tr>

      <tr><td>8000</td><td>Day 0 – MC Readings Stabilization</td></tr>
      <tr><td>8100.0</td><td>MC Readings</td></tr>
      <tr><td>8100.1</td><td>Day 1 MC Readings</td></tr>
      <tr><td>8200.2</td><td>Day 2 MC Readings</td></tr>
      <tr><td>8300.3</td><td>Day 3 MC Readings</td></tr>
      <tr><td>8400.4</td><td>Day 4 MC Readings</td></tr>

      <tr><td>9000</td><td>RH/T/GPP Dry Chambers</td></tr>
      <tr><td>9100–9405</td><td>Dry Chamber Readings (Days 1–4)</td></tr>

      <tr><td>9998</td><td>Rebuild Overview WIP</td></tr>
      <tr><td>9999</td><td>Rebuild Interior Completed Work</td></tr>
    </table>
  </div>



  <!-- ========================= -->
  <!-- CARD: ROOM LIST -->
  <!-- ========================= -->
  <div style="
      background:white;
      border-radius:10px;
      padding:25px;
      margin-bottom:35px;
      box-shadow:0 3px 12px rgba(0,0,0,0.12);
  ">
    <h2 style="color:#1e88e5; margin-top:0;">OH25 BROWNLEE Worktype Room List</h2>
    <h3 style="color:#555; font-weight:normal; margin-top:5px;">
      @ E189 – 3922 E 189 St, Cleveland, OH 44128
    </h3>

    <!-- MOBILE SAFE SCROLL WRAPPER -->
    <div style="width:100%; overflow-x:auto; -webkit-overflow-scrolling:touch;">

      <table cellspacing="0" cellpadding="8" border="1"
        style="border-collapse: collapse; width:100%; min-width:650px; table-layout:auto; font-size:14px; border-color:#d0d0d0;">

        <tr style="font-weight:bold;">
          <th style="background:#e3f2fd;">Room</th>
          <th style="background:#fff8c6;">100<br>Overview</th>
          <th style="background:#f0f4f8;">200<br>Source</th>
          <th style="background:#fff8c6;">300<br>CPS</th>
          <th style="background:#f0f4f8;">400<br>PPR</th>
          <th style="background:#fff8c6;">500<br>Demo</th>
          <th style="background:#f0f4f8;">600<br>WTR Equip</th>
          <th style="background:#fff8c6;">700<br>HMR</th>
        </tr>

        <!-- ROWS -->
        <tr>
          <td>Living Room</td>
          <td style="background:#fff8c6;">101</td>
          <td style="background:#f0f4f8;">201</td>
          <td style="background:#fff8c6;">301</td>
          <td style="background:#f0f4f8;">401</td>
          <td style="background:#fff8c6;">501</td>
          <td style="background:#f0f4f8;">601</td>
          <td style="background:#fff8c6;">701</td>
        </tr>

        <tr>
          <td>Hallway</td>
          <td style="background:#fff8c6;">102</td>
          <td style="background:#f0f4f8;">202</td>
          <td style="background:#fff8c6;">302</td>
          <td style="background:#f0f4f8;">402</td>
          <td style="background:#fff8c6;">502</td>
          <td style="background:#f0f4f8;">602</td>
          <td style="background:#fff8c6;">702</td>
        </tr>

        <tr>
          <td>Kitchen</td>
          <td style="background:#fff8c6;">103</td>
          <td style="background:#f0f4f8;">203</td>
          <td style="background:#fff8c6;">303</td>
          <td style="background:#f0f4f8;">403</td>
          <td style="background:#fff8c6;">503</td>
          <td style="background:#f0f4f8;">603</td>
          <td style="background:#fff8c6;">703</td>
        </tr>

        <tr>
          <td>Den</td>
          <td style="background:#fff8c6;">104</td>
          <td style="background:#f0f4f8;">204</td>
          <td style="background:#fff8c6;">304</td>
          <td style="background:#f0f4f8;">404</td>
          <td style="background:#fff8c6;">504</td>
          <td style="background:#f0f4f8;">604</td>
          <td style="background:#fff8c6;">704</td>
        </tr>

        <tr>
          <td>Stairs Up</td>
          <td style="background:#fff8c6;">105</td>
          <td style="background:#f0f4f8;">205</td>
          <td style="background:#fff8c6;">305</td>
          <td style="background:#f0f4f8;">405</td>
          <td style="background:#fff8c6;">505</td>
          <td style="background:#f0f4f8;">605</td>
          <td style="background:#fff8c6;">705</td>
        </tr>

        <tr>
          <td>Hall Up</td>
          <td style="background:#fff8c6;">106</td>
          <td style="background:#f0f4f8;">206</td>
          <td style="background:#fff8c6;">306</td>
          <td style="background:#f0f4f8;">406</td>
          <td style="background:#fff8c6;">506</td>
          <td style="background:#f0f4f8;">606</td>
          <td style="background:#fff8c6;">706</td>
        </tr>

        <tr>
          <td>Primary Bedroom Up</td>
          <td style="background:#fff8c6;">107</td>
          <td style="background:#f0f4f8;">207</td>
          <td style="background:#fff8c6;">307</td>
          <td style="background:#f0f4f8;">407</td>
          <td style="background:#fff8c6;">507</td>
          <td style="background:#f0f4f8;">607</td>
          <td style="background:#fff8c6;">707</td>
        </tr>

        <tr>
          <td>Bathroom Up</td>
          <td style="background:#fff8c6;">108</td>
          <td style="background:#f0f4f8;">208</td>
          <td style="background:#fff8c6;">308</td>
          <td style="background:#f0f4f8;">408</td>
          <td style="background:#fff8c6;">508</td>
          <td style="background:#f0f4f8;">608</td>
          <td style="background:#fff8c6;">708</td>
        </tr>

      </table>
    </div>
  </div>



  <!-- ========================= -->
  <!-- FOOTER -->
  <!-- ========================= -->
  <div style="
      text-align:center;
      padding:15px;
      color:#777;
      font-size:12px;
      margin-top:20px;
  ">
    OH25 BROWNLEE report | Powered by Claimet Email System
  </div>

</div>
    """

    try:
        email = EmailMessage(
            subject='[✨SCHEDULED] ROOM LIST EMAIL V3',
            body=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=['galaxielsaga@gmail.com', 'wsbjoe9@gmail.com'],
        )
        email.content_subtype = 'html'
        email.send()
        print("✅ SUCCESS! HTML email sent.")
        return True
    except Exception as e:
        print(f"❌ ERROR sending HTML email: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_multiple_recipients():
    """Test sending to multiple recipients"""
    print("\n" + "=" * 60)
    print("TESTING MULTIPLE RECIPIENTS")
    print("=" * 60)

    recipients = [
        'someuserdotcom@gmail.com',
        'galaxielsaga@gmail.com',
        'wsbjoe9@gmail.com'
        # Add more test recipients here if needed
    ]

    try:
        result = send_mail(
            subject='📧 Multi-Recipient Test',
            message='This email was sent to multiple recipients at once.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
        print(f"✅ SUCCESS! Email sent to {len(recipients)} recipient(s)")
        return True
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False


if __name__ == '__main__':
    print("\n🚀 Starting Email System Tests\n")

    # Run tests
    #test1 = test_basic_email()
    test2 = test_html_email()
    #test3 = test_multiple_recipients()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    #print(f"Basic Email Test: {'✅ PASSED' if test1 else '❌ FAILED'}")
    print(f"HTML Email Test: {'✅ PASSED' if test2 else '❌ FAILED'}")
    #print(f"Multiple Recipients: {'✅ PASSED' if test3 else '❌ FAILED'}")
    print("=" * 60)

    if all([ test2]): # add test1, and test3 for those tests
        print("\n🎉 ALL TESTS PASSED! Email system is ready to use.")
    else:
        print("\n⚠️  Some tests failed. Check the error messages above.")
