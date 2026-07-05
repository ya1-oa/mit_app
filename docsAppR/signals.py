# signals.py
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from .models import Client, ChecklistItem, Room

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# ALLAUTH: Email-verified confirmation
# Fires once when the user clicks the allauth verification link and
# their email address is marked verified in the database.
# ──────────────────────────────────────────────────────────────────────────────
try:
    from allauth.account.signals import email_confirmed

    @receiver(email_confirmed)
    def send_email_verified_confirmation(sender, request, email_address, **kwargs):
        """
        Send a branded confirmation email telling the user their email is
        verified and their account is fully active.
        """
        user = email_address.user

        # Build the login URL — fall back to a plain path if Sites aren't set up
        try:
            from django.contrib.sites.shortcuts import get_current_site
            site = get_current_site(request)
            login_url = f"https://{site.domain}/accounts/login/"
        except Exception:
            login_url = "/accounts/login/"

        context = {
            'username': user.get_full_name() or user.username or user.email.split('@')[0],
            'email': email_address.email,
            'login_url': login_url,
        }

        subject = "Your email has been verified — Welcome to Claimet!"
        html_body = render_to_string(
            'account/email/email_verified_confirmation.html',
            context,
            request=request,
        )
        # Plain-text fallback for email clients that don't render HTML
        text_body = (
            f"Hi {context['username']},\n\n"
            f"Your email address ({email_address.email}) has been successfully verified.\n"
            f"Your Claimet account is now fully active.\n\n"
            f"Log in here: {login_url}\n\n"
            f"— The Claimet Team"
        )

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email_address.email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)
            logger.info("Sent email-verified confirmation to %s", email_address.email)
        except Exception as exc:
            # Never crash the verification flow if the confirmation email fails
            logger.error("Failed to send email-verified confirmation to %s: %s",
                         email_address.email, exc)

except ImportError:
    # allauth not installed — skip gracefully
    logger.warning("allauth not available; email_confirmed signal not registered")

@receiver(post_save, sender=Client)
def create_client_checklist(sender, instance, created, **kwargs):
    if created:
        create_checklist_items_for_client(instance)


@receiver(post_save, sender=Client)
def create_client_folder_and_templates(sender, instance, created, **kwargs):
    """Create folder structure and copy templates when a client is created."""
    if created:
        try:
            from .tasks import create_server_folder_structure_task, copy_templates_to_server_task
            # Trigger async tasks to create folder structure and copy templates
            # Chain them so templates are copied after folder is created
            create_server_folder_structure_task.apply_async(
                args=[instance.id],
                link=copy_templates_to_server_task.si(instance.id)
            )
            logger.info(f"Triggered folder and template creation for client {instance.id}")
        except Exception as e:
            logger.error(f"Failed to trigger folder/template creation: {e}")


@receiver(post_save, sender=Client)
def regenerate_excel_files_on_update(sender, instance, created, **kwargs):
    """Regenerate Excel files when client data is updated (not on create)."""
    if not created and instance.server_folder_path:
        from .tasks import regenerate_client_excel_files
        from django.core.cache import cache
        try:
            # Debounce: only queue one task per client per 10 seconds.
            # Rapid saves (e.g. multiple API calls in a batch) would otherwise
            # spawn N concurrent workers all writing the same files, causing
            # LibreOffice lock-violation errors (0x11b) and file corruption.
            debounce_key = f'excel_regen_debounce:{instance.id}'
            if not cache.add(debounce_key, '1', timeout=10):
                logger.debug(f"Excel regen debounced for client {instance.id}")
                return
            regenerate_client_excel_files.apply_async(
                args=[instance.id],
                countdown=3,  # small delay so any in-flight saves commit first
            )
            logger.info(f"Triggered Excel regeneration for client {instance.id}")
        except Exception as e:
            logger.error(f"Failed to trigger Excel regeneration: {e}")


@receiver(post_save, sender=Room)
def generate_labels_on_room_creation(sender, instance, created, **kwargs):
    """
    Generate and email wall/box labels when rooms are created for a claim.

    This is triggered when rooms are saved. We use a flag on the client to avoid
    sending duplicate emails when multiple rooms are created in batch.

    The labels are emailed to the Georgia and Ohio team groups configured in settings.
    """
    if created:
        client = instance.client

        # Use a simple cache key to prevent duplicate emails within a short time window
        # This handles the case where multiple rooms are created in rapid succession
        cache_key = f'labels_email_sent_{client.id}'

        try:
            from django.core.cache import cache
            from .tasks import generate_and_email_labels_task

            # Check if we've already queued a labels email for this client recently (5 min window)
            if cache.get(cache_key):
                logger.debug(f"Labels email already queued for client {client.id}, skipping")
                return

            # Set cache flag for 5 minutes to batch room creations
            cache.set(cache_key, True, timeout=300)

            # Delay the task slightly to allow all rooms to be created in a batch
            # This ensures we generate labels for ALL rooms, not just the first one
            generate_and_email_labels_task.apply_async(
                args=[client.id],
                countdown=10  # Wait 10 seconds before running to allow batch completion
            )
            logger.info(f"Queued labels email generation for client {client.id} (room: {instance.room_name})")

        except Exception as e:
            logger.error(f"Failed to queue labels email for client {client.id}: {e}")

def create_checklist_items_for_client(client):
    """Create all required checklist items for a client based on their claim type"""
    # MIT Documents
    if client.mitigation:
        mit_docs = [
            'MIT_AUTH', 'MIT_AGREE', 'MIT_W9', 'MIT_VERIFY',
            'MIT_EQUIP', 'MIT_INVOICE', 'MIT_OVERVIEW',
            'MIT_DRYLOG', 'MIT_EMAIL'
        ]
        for doc_type in mit_docs:
            ChecklistItem.objects.get_or_create(
                client=client,
                document_type=doc_type,
                defaults={'required': True}
            )
    
    # CPS Documents
    if client.CPSCLNCONCGN:
        cps_docs = [
            'CPS_AUTH', 'CPS_AGREE', 'CPS_W9', 'CPS_VERIFY',
            'CPS_BOXCOUNT', 'CPS_BOXPHOTO', 'CPS_CUSTPICS',
            'CPS_CUSTLIST', 'CPS_INVOICE', 'CPS_ESX',
            'CPS_OVERVIEW', 'CPS_DAY1', 'CPS_DAY2',
            'CPS_DAY3', 'CPS_DAY4', 'CPS_EMAIL'
        ]
        for doc_type in cps_docs:
            ChecklistItem.objects.get_or_create(
                client=client,
                document_type=doc_type,
                defaults={'required': True}
            )
    
    # PPR Documents
    if client.replacement:
        ppr_docs = [
            'PPR_SCHEDULE', 'PPR_PHOTOREP', 'PPR_CUSTPICS',
            'PPR_CUSTLIST', 'PPR_EMAIL'
        ]
        for doc_type in ppr_docs:
            ChecklistItem.objects.get_or_create(
                client=client,
                document_type=doc_type,
                defaults={'required': True}
            )