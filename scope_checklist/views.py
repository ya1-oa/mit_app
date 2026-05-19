"""
Scope Checklist app views.
"""
import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from allauth.account.decorators import login_required

from docsAppR.models import Client, Room, SentEmail

logger = logging.getLogger(__name__)


@login_required
def scope_checklist(request):
    """
    Main Scope Checklist page - Interior Inspection Work Scope
    Displays claim selection, room tabs, and detailed checklist with Xactimate codes
    """
    claims = Client.objects.all().order_by('-created_at')

    return render(request, 'account/scope_checklist.html', {
        'claims': claims
    })


@login_required
def scope_checklist_get_rooms(request, claim_id):
    """
    API endpoint to get rooms for a selected claim
    Returns room list with any saved scope checklist data
    """
    try:
        client = get_object_or_404(Client, id=claim_id)
        rooms = Room.objects.filter(client=client).order_by('sequence', 'room_name')

        rooms_data = []
        for room in rooms:
            room_info = {
                'id': str(room.id),
                'room_name': room.room_name,
                'sequence': room.sequence,
            }

            # Get saved scope checklist data if it exists
            try:
                from docsAppR.models import RoomScopeChecklist
                scope_data = RoomScopeChecklist.objects.get(room=room, client=client)
                room_info['scope_data'] = scope_data.to_dict()
            except:
                room_info['scope_data'] = {}

            rooms_data.append(room_info)

        return JsonResponse({
            'success': True,
            'rooms': rooms_data,
            'client': {
                'id': client.id,
                'name': client.pOwner,
                'address': client.pAddress,
                'phone': client.cPhone,
                'insurance': client.insuranceCo_Name,
                'cause': client.causeOfLoss
            }
        })

    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Claim not found'}, status=404)
    except Exception as e:
        logger.error(f"Error getting rooms for scope checklist: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
def scope_checklist_save(request):
    """
    API endpoint to save scope checklist data for all rooms
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        claim_id = data.get('claim_id')
        rooms_data = data.get('rooms_data', {})

        if not claim_id:
            return JsonResponse({'error': 'Missing claim_id'}, status=400)

        client = get_object_or_404(Client, id=claim_id)
        from docsAppR.models import RoomScopeChecklist

        saved_count = 0
        for room_id, room_fields in rooms_data.items():
            try:
                room = Room.objects.get(id=room_id)

                # Update or create scope checklist
                scope_data, created = RoomScopeChecklist.objects.update_or_create(
                    room=room,
                    client=client,
                    defaults={
                        'clg_material': room_fields.get('clg_material', ''),
                        'clg_construction': room_fields.get('clg_construction', ''),
                        'clg_finish': room_fields.get('clg_finish', ''),
                        'clg_activity': room_fields.get('clg_activity', ''),
                        'clg_sf': room_fields.get('clg_sf') or None,
                        'lit_type': room_fields.get('lit_type', ''),
                        'lit_activity': room_fields.get('lit_activity', ''),
                        'lit_qty': room_fields.get('lit_qty') or None,
                        'hvc_type': room_fields.get('hvc_type', ''),
                        'hvc_activity': room_fields.get('hvc_activity', ''),
                        'hvc_qty': room_fields.get('hvc_qty') or None,
                        'wal_material': room_fields.get('wal_material', ''),
                        'wal_finish': room_fields.get('wal_finish', ''),
                        'wal_activity': room_fields.get('wal_activity', ''),
                        'wal_sf': room_fields.get('wal_sf') or None,
                        'ele_outlets': room_fields.get('ele_outlets') or None,
                        'ele_switches': room_fields.get('ele_switches') or None,
                        'ele_sw3': room_fields.get('ele_sw3') or None,
                        'ele_activity': room_fields.get('ele_activity', ''),
                        'flr_type': room_fields.get('flr_type', ''),
                        'flr_activity': room_fields.get('flr_activity', ''),
                        'flr_sf': room_fields.get('flr_sf') or None,
                        'bb_height': room_fields.get('bb_height', ''),
                        'bb_activity': room_fields.get('bb_activity', ''),
                        'bb_lf': room_fields.get('bb_lf') or None,
                        'trim_type': room_fields.get('trim_type', ''),
                        'trim_crown': room_fields.get('trim_crown', ''),
                        'trim_chairrail': room_fields.get('trim_chairrail', ''),
                        'trim_activity': room_fields.get('trim_activity', ''),
                        'dor_type': room_fields.get('dor_type', ''),
                        'dor_activity': room_fields.get('dor_activity', ''),
                        'dor_qty': room_fields.get('dor_qty') or None,
                        'open_activity': room_fields.get('open_activity', ''),
                        'open_qty': room_fields.get('open_qty') or None,
                        'wdw_type': room_fields.get('wdw_type', ''),
                        'wdw_covers': room_fields.get('wdw_covers', ''),
                        'wdw_activity': room_fields.get('wdw_activity', ''),
                        'wdw_qty': room_fields.get('wdw_qty') or None,
                        'closet_type': room_fields.get('closet_type', ''),
                        'closet_rod': room_fields.get('closet_rod', ''),
                        'closet_lf': room_fields.get('closet_lf') or None,
                        'ins_type': room_fields.get('ins_type', ''),
                        'ins_rvalue': room_fields.get('ins_rvalue', ''),
                        'ins_sf': room_fields.get('ins_sf') or None,
                        'frm_type': room_fields.get('frm_type', ''),
                        'frm_activity': room_fields.get('frm_activity', ''),
                        'frm_lf': room_fields.get('frm_lf') or None,
                        'activity_notes': room_fields.get('activity_notes', ''),
                        'created_by': request.user,
                    }
                )
                saved_count += 1
            except Room.DoesNotExist:
                logger.warning(f"Room not found: {room_id}")
                continue
            except Exception as e:
                logger.error(f"Error saving room {room_id}: {str(e)}")
                continue

        return JsonResponse({
            'success': True,
            'saved_count': saved_count,
            'message': f'Saved data for {saved_count} rooms'
        })

    except Exception as e:
        logger.error(f"Error saving scope checklist: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
def scope_checklist_generate_pdf(request):
    """
    Generate PDF for scope checklist
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        claim_id = data.get('claim_id')
        rooms_data = data.get('rooms_data', {})

        if not claim_id:
            return JsonResponse({'error': 'Missing claim_id'}, status=400)

        client = get_object_or_404(Client, id=claim_id)

        # Generate PDF using ReportLab
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from io import BytesIO

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter),
                               rightMargin=30, leftMargin=30,
                               topMargin=30, bottomMargin=30)

        elements = []
        styles = getSampleStyleSheet()

        # Header style
        header_style = ParagraphStyle(
            'Header',
            parent=styles['Heading1'],
            fontSize=14,
            spaceAfter=12
        )

        # Title
        elements.append(Paragraph(f"Interior Inspection Work Scope", header_style))
        elements.append(Paragraph(f"<b>Client:</b> {client.pOwner}", styles['Normal']))
        elements.append(Paragraph(f"<b>Address:</b> {client.pAddress} {client.pCityStateZip}", styles['Normal']))
        elements.append(Paragraph(f"<b>Phone:</b> {client.cPhone}", styles['Normal']))
        elements.append(Paragraph(f"<b>Insurance:</b> {client.insuranceCo_Name}", styles['Normal']))
        elements.append(Paragraph(f"<b>Cause of Loss:</b> {client.causeOfLoss}", styles['Normal']))
        elements.append(Spacer(1, 20))

        # Get rooms
        rooms = Room.objects.filter(client=client).order_by('sequence', 'room_name')

        # Summary table headers
        headers = ['#', 'Room', 'CLG', 'LIT', 'HVC', 'WAL', 'ELE', 'FLR', 'BB', 'DOR', 'WDW', 'NOTES']

        # Build summary table data
        table_data = [headers]

        for idx, room in enumerate(rooms, 1):
            room_id = str(room.id)
            room_fields = rooms_data.get(room_id, {})

            row = [
                str(idx),
                room.room_name[:15],  # Truncate long names
                room_fields.get('clg_material', '') + '/' + room_fields.get('clg_activity', ''),
                room_fields.get('lit_type', ''),
                room_fields.get('hvc_type', ''),
                room_fields.get('wal_material', '') + '/' + room_fields.get('wal_activity', ''),
                f"OS:{room_fields.get('ele_outlets', '')} SW:{room_fields.get('ele_switches', '')}",
                room_fields.get('flr_type', '') + '/' + room_fields.get('flr_activity', ''),
                room_fields.get('bb_height', ''),
                room_fields.get('dor_type', ''),
                room_fields.get('wdw_type', ''),
                room_fields.get('activity_notes', '')[:30] if room_fields.get('activity_notes') else ''
            ]
            table_data.append(row)

        # Create summary table
        col_widths = [25, 80, 60, 40, 40, 60, 70, 60, 40, 40, 40, 120]
        summary_table = Table(table_data, colWidths=col_widths)
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0066cc')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(summary_table)

        # Add detailed room pages
        elements.append(PageBreak())

        for idx, room in enumerate(rooms, 1):
            room_id = str(room.id)
            room_fields = rooms_data.get(room_id, {})

            elements.append(Paragraph(f"Room {idx}: {room.room_name}", header_style))
            elements.append(Spacer(1, 10))

            # Room details table
            detail_data = [
                ['SECTION', 'TYPE/MATERIAL', 'ACTIVITY', 'QTY/SF/LF', 'NOTES'],
                ['CEILING', room_fields.get('clg_material', ''), room_fields.get('clg_activity', ''), room_fields.get('clg_sf', ''), room_fields.get('clg_finish', '')],
                ['LIGHTS', room_fields.get('lit_type', ''), room_fields.get('lit_activity', ''), room_fields.get('lit_qty', ''), ''],
                ['HVAC', room_fields.get('hvc_type', ''), room_fields.get('hvc_activity', ''), room_fields.get('hvc_qty', ''), ''],
                ['WALLS', room_fields.get('wal_material', ''), room_fields.get('wal_activity', ''), room_fields.get('wal_sf', ''), room_fields.get('wal_finish', '')],
                ['ELECTRICAL', f"OS:{room_fields.get('ele_outlets', '')} SW:{room_fields.get('ele_switches', '')}", room_fields.get('ele_activity', ''), '', ''],
                ['FLOOR', room_fields.get('flr_type', ''), room_fields.get('flr_activity', ''), room_fields.get('flr_sf', ''), ''],
                ['BASEBOARD', room_fields.get('bb_height', ''), room_fields.get('bb_activity', ''), room_fields.get('bb_lf', ''), ''],
                ['TRIM', room_fields.get('trim_type', ''), room_fields.get('trim_activity', ''), '', f"CRN:{room_fields.get('trim_crown', '')} CHR:{room_fields.get('trim_chairrail', '')}"],
                ['DOORS', room_fields.get('dor_type', ''), room_fields.get('dor_activity', ''), room_fields.get('dor_qty', ''), ''],
                ['OPENINGS', '', room_fields.get('open_activity', ''), room_fields.get('open_qty', ''), ''],
                ['WINDOWS', room_fields.get('wdw_type', ''), room_fields.get('wdw_activity', ''), room_fields.get('wdw_qty', ''), room_fields.get('wdw_covers', '')],
                ['CLOSET', room_fields.get('closet_type', ''), '', room_fields.get('closet_lf', ''), f"ROD:{room_fields.get('closet_rod', '')}"],
                ['INSULATION', room_fields.get('ins_type', ''), '', room_fields.get('ins_sf', ''), room_fields.get('ins_rvalue', '')],
                ['FRAMING', room_fields.get('frm_type', ''), room_fields.get('frm_activity', ''), room_fields.get('frm_lf', ''), ''],
            ]

            detail_table = Table(detail_data, colWidths=[80, 120, 80, 80, 150])
            detail_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f0f0f0')),
            ]))
            elements.append(detail_table)

            # Activity notes
            if room_fields.get('activity_notes'):
                elements.append(Spacer(1, 10))
                elements.append(Paragraph(f"<b>Activity Notes:</b> {room_fields.get('activity_notes', '')}", styles['Normal']))

            elements.append(PageBreak())

        # Add scope codes reference page
        elements.append(Paragraph("XACTIMATE SCOPE CODES REFERENCE", header_style))
        elements.append(Spacer(1, 10))

        codes_data = [
            ['BUILDING MATERIALS', '', 'CONSTRUCTION TYPE', '', 'FINISH', ''],
            ['ACT', 'CLG TILES', 'FLT', 'FLAT', 'SMH', 'SMOOTH'],
            ['DRY', 'DRYWALL', 'VLT', 'VAULTED', 'TEX', 'TEXTURE'],
            ['PLA', 'PLASTER', 'TRY', 'TRAY', 'POP', 'POPCORN'],
            ['T&G', 'TONGUE&GROOVE', 'FRM', 'OPEN', '', ''],
            ['PNL', 'PANELING', '', '', '', ''],
            ['WPR', 'WALLPAPER', '', '', '', ''],
            ['CNC', 'CONCRETE', '', '', '', ''],
            ['MAS', 'BRICK/MASONRY', '', '', '', ''],
            ['', '', '', '', '', ''],
            ['FLOOR TYPES', '', 'DOOR TYPES', '', 'WINDOW TYPES', ''],
            ['FCC', 'CARPET', 'STD', 'STANDARD', 'WDW', 'WOOD'],
            ['FCS', 'STONE', 'BFD', 'BIFOLD', 'WDV', 'VINYL'],
            ['FCV', 'VINYL TILE', 'BYD', 'BYPASS/SLIDER', 'WDA', 'ALUMINUM'],
            ['FCW', 'HARDWOOD', 'BPM', 'MIRROR', 'BAY', 'BAY/BOW'],
            ['LAM', 'LAMINATE', '', '', '', ''],
            ['', '', '', '', '', ''],
            ['ACTIVITY CODES', '', '', '', '', ''],
            ['ALL', 'REPAIR ALL', 'CLN', 'CLEAN', 'R&R', 'REPLACE'],
            ['D&R', 'DETACH & RESET', 'MSK', 'MASK', 'S++', 'PRIME/SEAL'],
            ['PNT', 'PAINT', 'STN', 'STAIN & SEAL', 'SND', 'SAND'],
        ]

        codes_table = Table(codes_data, colWidths=[50, 100, 50, 100, 50, 100])
        codes_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0066cc')),
            ('BACKGROUND', (0, 10), (-1, 10), colors.HexColor('#0066cc')),
            ('BACKGROUND', (0, 17), (-1, 17), colors.HexColor('#0066cc')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 10), (-1, 10), colors.white),
            ('TEXTCOLOR', (0, 17), (-1, 17), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 10), (-1, 10), 'Helvetica-Bold'),
            ('FONTNAME', (0, 17), (-1, 17), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(codes_table)

        # Build PDF
        doc.build(elements)

        # Return PDF response
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="scope_checklist_{client.pOwner}.pdf"'
        return response

    except Exception as e:
        logger.error(f"Error generating scope checklist PDF: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
def scope_checklist_send_email(request):
    """
    Send scope checklist PDF via email
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        claim_id = data.get('claim_id')
        rooms_data = data.get('rooms_data', {})
        recipients = data.get('recipients', '')
        subject = data.get('subject', '')
        notes = data.get('notes', '')

        if not claim_id:
            return JsonResponse({'error': 'Missing claim_id'}, status=400)

        if not recipients:
            return JsonResponse({'error': 'Missing recipients'}, status=400)

        client = get_object_or_404(Client, id=claim_id)

        # Parse recipients
        recipient_list = [email.strip() for email in recipients.split(',') if email.strip()]

        if not recipient_list:
            return JsonResponse({'error': 'No valid recipients'}, status=400)

        # Generate PDF
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from io import BytesIO

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter),
                               rightMargin=30, leftMargin=30,
                               topMargin=30, bottomMargin=30)

        elements = []
        styles = getSampleStyleSheet()

        header_style = ParagraphStyle(
            'Header',
            parent=styles['Heading1'],
            fontSize=14,
            spaceAfter=12
        )

        # Build PDF content (same as generate_pdf)
        elements.append(Paragraph(f"Interior Inspection Work Scope", header_style))
        elements.append(Paragraph(f"<b>Client:</b> {client.pOwner}", styles['Normal']))
        elements.append(Paragraph(f"<b>Address:</b> {client.pAddress} {client.pCityStateZip}", styles['Normal']))
        elements.append(Paragraph(f"<b>Phone:</b> {client.cPhone}", styles['Normal']))
        elements.append(Paragraph(f"<b>Insurance:</b> {client.insuranceCo_Name}", styles['Normal']))
        elements.append(Paragraph(f"<b>Cause of Loss:</b> {client.causeOfLoss}", styles['Normal']))
        elements.append(Spacer(1, 20))

        rooms = Room.objects.filter(client=client).order_by('sequence', 'room_name')

        # Summary table
        headers = ['#', 'Room', 'CLG', 'LIT', 'HVC', 'WAL', 'ELE', 'FLR', 'BB', 'DOR', 'WDW', 'NOTES']
        table_data = [headers]

        for idx, room in enumerate(rooms, 1):
            room_id = str(room.id)
            room_fields = rooms_data.get(room_id, {})

            row = [
                str(idx),
                room.room_name[:15],
                room_fields.get('clg_material', '') + '/' + room_fields.get('clg_activity', ''),
                room_fields.get('lit_type', ''),
                room_fields.get('hvc_type', ''),
                room_fields.get('wal_material', '') + '/' + room_fields.get('wal_activity', ''),
                f"OS:{room_fields.get('ele_outlets', '')} SW:{room_fields.get('ele_switches', '')}",
                room_fields.get('flr_type', '') + '/' + room_fields.get('flr_activity', ''),
                room_fields.get('bb_height', ''),
                room_fields.get('dor_type', ''),
                room_fields.get('wdw_type', ''),
                room_fields.get('activity_notes', '')[:30] if room_fields.get('activity_notes') else ''
            ]
            table_data.append(row)

        col_widths = [25, 80, 60, 40, 40, 60, 70, 60, 40, 40, 40, 120]
        summary_table = Table(table_data, colWidths=col_widths)
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0066cc')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(summary_table)

        doc.build(elements)
        buffer.seek(0)

        # Create and send email
        email_subject = subject or f"Interior Inspection Scope - {client.pOwner}"

        email_body = f"""
<html>
<body style="font-family: Arial, sans-serif;">
<h2>Interior Inspection Work Scope</h2>
<p><strong>Client:</strong> {client.pOwner}</p>
<p><strong>Address:</strong> {client.pAddress}</p>
<p><strong>Insurance:</strong> {client.insuranceCo_Name}</p>
<p><strong>Cause of Loss:</strong> {client.causeOfLoss}</p>
{f'<p><strong>Notes:</strong> {notes}</p>' if notes else ''}
<p>Please find the attached scope checklist PDF.</p>
<hr>
<p style="color: #666; font-size: 12px;">Generated by Claimet App</p>
</body>
</html>
"""

        email = EmailMessage(
            subject=email_subject,
            body=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipient_list
        )
        email.content_subtype = 'html'

        # Attach PDF
        pdf_filename = f"Scope_Checklist_{client.pOwner.replace(' ', '_')}.pdf"
        email.attach(pdf_filename, buffer.getvalue(), 'application/pdf')

        # Send email
        email.send()

        # Log sent email
        SentEmail.objects.create(
            subject=email_subject,
            recipients=recipient_list,
            body=email_body,
            sent_by=request.user,
            sent_at=timezone.now()
        )

        return JsonResponse({
            'success': True,
            'message': f'Email sent successfully to {len(recipient_list)} recipient(s)',
            'recipients_count': len(recipient_list)
        })

    except Exception as e:
        logger.error(f"Error sending scope checklist email: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
