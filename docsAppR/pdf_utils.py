"""
PDF / document generation utilities.
Extracted from docsAppR/views.py to improve manageability.

Functions:
    convert_excel_to_pdf            - Convert an Excel file to PDF (Windows or Linux)
    generate_room_list_pdf          - Generate a room-list PDF (table or list format)
    generate_room_list_email_html   - Generate HTML email content for a room list
    _generate_table_format_email    - Internal: table-format HTML email
    _generate_list_format_email     - Internal: sequential-list HTML email
    _generate_list_pdf              - Internal: compact list-format PDF
    _generate_table_pdf             - Internal: table-format PDF
"""

import logging
import os
import platform
from io import BytesIO

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Excel → PDF conversion
# ---------------------------------------------------------------------------

def convert_excel_to_pdf(excel_path, pdf_path):
    """Convert a specific Excel sheet to PDF using the appropriate method for the OS."""
    if platform.system() == 'Windows':
        try:
            import win32com.client
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            wb = excel.Workbooks.Open(excel_path)
            wb.ExportAsFixedFormat(0, pdf_path)
            wb.Close()
            excel.Quit()
        except Exception as e:
            logger.error(f"Error converting with Excel: {str(e)}")
            raise
    else:
        try:
            import subprocess

            output_dir = os.path.dirname(pdf_path)
            os.makedirs(output_dir, exist_ok=True)

            try:
                subprocess.run(['which', 'unoconv'], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run([
                    'unoconv', '-f', 'pdf', '-o', pdf_path, excel_path
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            except (subprocess.SubprocessError, FileNotFoundError):
                subprocess.run([
                    'libreoffice', '--headless', '--convert-to', 'pdf',
                    '--outdir', output_dir, excel_path
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                libreoffice_output = os.path.splitext(os.path.basename(excel_path))[0] + '.pdf'
                libreoffice_output_path = os.path.join(output_dir, libreoffice_output)
                if os.path.exists(libreoffice_output_path) and libreoffice_output_path != pdf_path:
                    os.rename(libreoffice_output_path, pdf_path)

        except Exception as e:
            logger.error(f"Error converting with LibreOffice: {str(e)}")
            raise


# ---------------------------------------------------------------------------
# Room list PDF
# ---------------------------------------------------------------------------

def generate_room_list_pdf(claim_name, claim_address, room_data, format_type='list'):
    """
    Generate a PDF of the room list in either table or list format.

    Args:
        claim_name:    Name of the claim
        claim_address: Address of the claim
        room_data:     Dict with 'rooms' (list) and 'configs' (dict) keys
        format_type:   'list' (default) or 'table'

    Returns:
        BytesIO buffer containing the PDF
    """
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch

    rooms = room_data.get('rooms', [])
    configs = room_data.get('configs', {})

    buffer = BytesIO()

    if format_type == 'list':
        doc = SimpleDocTemplate(buffer, pagesize=letter,
                                rightMargin=0.3 * inch, leftMargin=0.3 * inch,
                                topMargin=0.3 * inch, bottomMargin=0.3 * inch)
    else:
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter),
                                rightMargin=0.3 * inch, leftMargin=0.3 * inch,
                                topMargin=0.3 * inch, bottomMargin=0.3 * inch)

    styles = getSampleStyleSheet()
    elements = []

    if format_type == 'list':
        return _generate_list_pdf(claim_name, claim_address, rooms, configs,
                                  doc, styles, elements, buffer)
    else:
        return _generate_table_pdf(claim_name, claim_address, rooms, configs,
                                   doc, styles, elements, buffer)


def _generate_list_pdf(claim_name, claim_address, rooms, configs, doc, styles, elements, buffer):
    """Generate compact list format PDF."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'],
        fontSize=12, textColor=colors.HexColor('#1e88e5'),
        spaceAfter=6, alignment=TA_CENTER, fontName='Helvetica-Bold'
    )
    subtitle_style = ParagraphStyle(
        'CustomSubtitle', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#555555'),
        spaceAfter=12, alignment=TA_CENTER
    )

    elements.append(Paragraph(f"{claim_name}", title_style))
    elements.append(Paragraph(f"{claim_address}", subtitle_style))
    elements.append(Spacer(1, 0.1 * inch))

    work_types = [
        (100, "JOB/ROOMS OVERVIEW PICS"),
        (200, "SOURCE of LOSS PICS"),
        (300, "C.P.S."),
        (400, "PPR"),
        (500, "DMO = DEMOLITION"),
        (600, "WTR MITIGATION EQUIPMENT & W.I.P"),
        (700, "HMR = HAZARDOUS MATERIALS"),
    ]

    all_data = []

    default_codes = [
        ("0.0001", "JOBSITE VERIFICATION"),
        ("0.0002", "MECHANICALS = WATER METER READING & PLUMBING REPORT/INVOICE"),
        ("0.0003", "MECHANICALS = ELECTRICAL HAZARDS"),
        ("0.0004", "EXT DAMAGE IF APPLICABLE ROOF TARPS"),
        ("1997", "LEAD & HMR TESTING LAB RESULTS"),
        ("1998", "KITCHEN CABINETS SIZES U & L =LF/ CT = SF; APPLIANCES"),
        ("1999", "BATHROOM FIXTURES CAB SIZE & FIXTURES & TYPE"),
    ]

    for code, desc in default_codes:
        all_data.append([code, desc])

    all_data.append([""] * 2)

    for work_type_num, work_type_desc in work_types:
        all_data.append([f"  {work_type_num}", f"= {work_type_desc}"])

        for idx, room in enumerate(rooms):
            base_num = idx + 1
            room_code = f"{work_type_num // 100}{base_num:02d}"
            room_config = configs.get(room, {})
            config_value = room_config.get(str(work_type_num), room_config.get(work_type_num, ''))
            display_value = config_value if config_value else ''
            room_info = f"{room}  [{display_value}]" if display_value else room
            all_data.append([f"    {room_code}", room_info])

        if work_type_num == 300:
            for code, desc in [
                ("3222", "CPS DAY2 WIP OVERVIEW WIP BOXES PACKOUT PICS"),
                ("3333", "CPS3 DAY3 STORAGE OVERVIEW STORAGE MOVE OUT PICS"),
                ("3444", "CPS4 DAY4 PACKBACK OVERVIEW PACK-BACK / RESET PICS"),
            ]:
                all_data.append([f"    {code}", desc])

        if work_type_num == 400:
            for code, desc in [
                ("4111.1", "REPLACEMENT 1 CON OVERVIEW DAY PICS"),
                ("4222.2", "REPLACEMENT 2 CON WIP"),
                ("4333.3", "REPLACEMENT 3 CON STORAGE"),
                ("4444.4", "REPLACEMENT 4 CON DISPOSAL"),
            ]:
                all_data.append([f"    {code}", desc])

    all_data.append([""] * 2)
    for code, desc in [
        ("9998.0", "REBUILD OVERVIEW WORK IN PROGRESS.......WIP"),
        ("9999.0", "REBUILD INTERIOR COMPLETED WORK"),
    ]:
        all_data.append([code, desc])

    col_widths = [1.2 * inch, 4.5 * inch]
    table = Table(all_data, colWidths=col_widths, hAlign='LEFT')

    table_style = TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Courier'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Courier-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, len(default_codes)), 'Courier-Bold'),
        ('TEXTCOLOR', (0, 0), (0, len(default_codes)), colors.HexColor('#1e88e5')),
    ])

    current_row = len(default_codes) + 2
    for work_type_num, _ in work_types:
        table_style.add('BACKGROUND', (0, current_row), (1, current_row), colors.HexColor('#f0f8ff'))
        table_style.add('FONTNAME', (0, current_row), (1, current_row), 'Helvetica-Bold')
        table_style.add('FONTSIZE', (0, current_row), (1, current_row), 8)
        current_row += 1

        for idx, room in enumerate(rooms):
            if idx % 2 == 0:
                table_style.add('BACKGROUND', (0, current_row), (1, current_row), colors.HexColor('#f9f9f9'))
            room_config = configs.get(room, {})
            config_value = room_config.get(str(work_type_num), room_config.get(work_type_num, ''))
            if config_value:
                table_style.add('FONTNAME', (1, current_row), (1, current_row), 'Helvetica-Bold')
                table_style.add('TEXTCOLOR', (1, current_row), (1, current_row), colors.HexColor('#d32f2f'))
            current_row += 1

        if work_type_num == 300 or work_type_num == 400:
            special_count = 3 if work_type_num == 300 else 4
            for i in range(special_count):
                table_style.add('FONTNAME', (0, current_row), (0, current_row), 'Courier-Bold')
                table_style.add('TEXTCOLOR', (0, current_row), (0, current_row), colors.HexColor('#1e88e5'))
                current_row += 1

    table.setStyle(table_style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _generate_table_pdf(claim_name, claim_address, rooms, configs, doc, styles, elements, buffer):
    """Generate table format PDF."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'],
        fontSize=10, textColor=colors.HexColor('#1e88e5'),
        spaceAfter=8, alignment=TA_CENTER, fontName='Helvetica-Bold'
    )
    subtitle_style = ParagraphStyle(
        'CustomSubtitle', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#555555'),
        spaceAfter=10, alignment=TA_CENTER
    )

    elements.append(Paragraph(claim_name, title_style))
    elements.append(Paragraph(claim_address, subtitle_style))
    elements.append(Spacer(1, 0.1 * inch))

    table_data = []
    header = ['Room', '100', 'L/T', '200', 'L/T', '300', 'L/T', '400', 'L/T',
              '500', 'L/T', '600', 'L/T', '700', 'L/T']
    table_data.append(header)

    for idx, room in enumerate(rooms):
        base_num = idx + 1
        room_config = configs.get(room, {})
        config_value = room_config.get('100', room_config.get(100, ''))
        los_value = config_value if config_value else ''
        display_room = room[:15] + '...' if len(room) > 18 else room

        row = [
            display_room,
            f'1{base_num:02d}', los_value, f'2{base_num:02d}', los_value,
            f'3{base_num:02d}', los_value, f'4{base_num:02d}', los_value,
            f'5{base_num:02d}', los_value, f'6{base_num:02d}', los_value,
            f'7{base_num:02d}', los_value
        ]
        table_data.append(row)

    col_widths = [1.0 * inch] + [0.35 * inch] * 14
    table = Table(table_data, colWidths=col_widths)

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e3f2fd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ('BACKGROUND', (1, 1), (1, -1), colors.HexColor('#fff8c6')),
        ('BACKGROUND', (3, 1), (3, -1), colors.HexColor('#f0f4f8')),
        ('BACKGROUND', (5, 1), (5, -1), colors.HexColor('#fff8c6')),
        ('BACKGROUND', (7, 1), (7, -1), colors.HexColor('#f0f4f8')),
        ('BACKGROUND', (9, 1), (9, -1), colors.HexColor('#fff8c6')),
        ('BACKGROUND', (11, 1), (11, -1), colors.HexColor('#f0f4f8')),
        ('BACKGROUND', (13, 1), (13, -1), colors.HexColor('#fff8c6')),
        ('BACKGROUND', (2, 1), (2, -1), colors.HexColor('#ffe6e6')),
        ('BACKGROUND', (4, 1), (4, -1), colors.HexColor('#ffe6e6')),
        ('BACKGROUND', (6, 1), (6, -1), colors.HexColor('#ffe6e6')),
        ('BACKGROUND', (8, 1), (8, -1), colors.HexColor('#ffe6e6')),
        ('BACKGROUND', (10, 1), (10, -1), colors.HexColor('#ffe6e6')),
        ('BACKGROUND', (12, 1), (12, -1), colors.HexColor('#ffe6e6')),
        ('BACKGROUND', (14, 1), (14, -1), colors.HexColor('#ffe6e6')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d0d0')),
    ])

    table.setStyle(table_style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ---------------------------------------------------------------------------
# Room list HTML email
# ---------------------------------------------------------------------------

def generate_room_list_email_html(claim_name, claim_address, room_data, version='table'):
    """
    Generate HTML email content for room list.

    Args:
        claim_name:    Name of the claim
        claim_address: Address of the claim
        room_data:     Dict with 'rooms' and 'configs' keys
        version:       'table' for table format, 'list' for sequential list format

    Returns:
        HTML string
    """
    rooms = room_data.get('rooms', [])
    configs = room_data.get('configs', {})

    if version == 'list':
        return _generate_list_format_email(claim_name, claim_address, rooms, configs)
    else:
        return _generate_table_format_email(claim_name, claim_address, rooms, configs)


def _generate_table_format_email(claim_name, claim_address, rooms, configs):
    """Generate the original table format email."""
    room_rows_html = ''
    for idx, room in enumerate(rooms):
        base_num = idx + 1
        room_config = configs.get(room, {})
        config_value = room_config.get('100', room_config.get(100, '.'))
        los_cell_value = '' if config_value == '.' else config_value

        room_rows_html += f'''
        <tr>
          <td>{room}</td>
          <td style="background:#fff8c6;">1{base_num:02d}</td>
          <td style="background:#ffe6e6; font-weight:bold;">{los_cell_value}</td>
          <td style="background:#f0f4f8;">2{base_num:02d}</td>
          <td style="background:#ffe6e6; font-weight:bold;">{los_cell_value}</td>
          <td style="background:#fff8c6;">3{base_num:02d}</td>
          <td style="background:#ffe6e6; font-weight:bold;">{los_cell_value}</td>
          <td style="background:#f0f4f8;">4{base_num:02d}</td>
          <td style="background:#ffe6e6; font-weight:bold;">{los_cell_value}</td>
          <td style="background:#fff8c6;">5{base_num:02d}</td>
          <td style="background:#ffe6e6; font-weight:bold;">{los_cell_value}</td>
          <td style="background:#f0f4f8;">6{base_num:02d}</td>
          <td style="background:#ffe6e6; font-weight:bold;">{los_cell_value}</td>
          <td style="background:#fff8c6;">7{base_num:02d}</td>
          <td style="background:#ffe6e6; font-weight:bold;">{los_cell_value}</td>
        </tr>
        '''

    html_content = f"""
<div style="font-family: Arial, sans-serif; background:#f5f7fa; padding:30px;">
  <div style="background: linear-gradient(90deg, #1e88e5, #42a5f5); color:white; padding:20px 25px;
      border-radius:8px; font-size:22px; font-weight:bold; margin-bottom:25px;
      box-shadow:0 4px 12px rgba(0,0,0,0.15);">
    {claim_name} — Worktype Documentation
  </div>

  <div style="background:white; border-radius:10px; padding:25px; margin-bottom:25px;
      box-shadow:0 3px 12px rgba(0,0,0,0.12); border-left: 5px solid #28a745;">
    <h2 style="margin-top:0; color:#28a745; font-size:20px;">How to Use This Email</h2>
    <p style="font-size:15px; color:#333; line-height:1.6;">
      This email contains the room list for <strong>{claim_name}</strong>.
      Scroll down to view the table, or open the attached PDF to print.
    </p>
  </div>

  <div style="background:white; border-radius:10px; padding:25px; margin-bottom:35px;
      box-shadow:0 3px 12px rgba(0,0,0,0.12);">
    <h2 style="margin-top:0; color:#1e88e5;">Reference Index — Worktype Codes</h2>
    <table cellspacing="0" cellpadding="8" border="1"
      style="border-collapse: collapse; width:100%; font-size:14px; border-color:#d0d0d0;">
      <tr><th style="background:#e3f2fd;">Code</th><th style="background:#e3f2fd;">Description</th></tr>
      <tr><td>0.0001</td><td>Jobsite Verification</td></tr>
      <tr><td>0.0002</td><td>Mechanicals – Water Meter Reading & Plumbing Report/Invoice</td></tr>
      <tr><td>0.0003</td><td>Mechanicals – Electrical Hazards</td></tr>
      <tr><td>0.0004</td><td>Exterior Damage If Applicable Roof Tarps</td></tr>
      <tr><td>1997</td><td>Lead & HMR Testing Lab Results</td></tr>
      <tr><td>1998</td><td>Kitchen Cabinets Sizes U & L =LF/ CT = SF; Appliances</td></tr>
      <tr><td>1999</td><td>Bathroom Fixtures Cab Size & Fixtures & Type</td></tr>
      <tr><td>100</td><td>Rooms Overview</td></tr>
      <tr><td>200</td><td>Source of Loss</td></tr>
      <tr><td>300</td><td>CPS</td></tr>
      <tr><td>400</td><td>PPR</td></tr>
      <tr><td>500</td><td>DMO Demo</td></tr>
      <tr><td>600</td><td>WTR Mitigation Equipment & W.I.P</td></tr>
      <tr><td>700</td><td>HMR</td></tr>
      <tr><td>9998.0</td><td>Rebuild overview work in progress.......WIP</td></tr>
      <tr><td>9999.0</td><td>Rebuild interior completed work</td></tr>
    </table>
  </div>

  <div style="background:white; border-radius:10px; padding:25px; margin-bottom:35px;
      box-shadow:0 3px 12px rgba(0,0,0,0.12);">
    <h2 style="color:#1e88e5; margin-top:0;">{claim_name} Worktype Room List</h2>
    <h3 style="color:#555; font-weight:normal; margin-top:5px;">@ {claim_address}</h3>

    <div style="width:100%; overflow-x:auto; -webkit-overflow-scrolling:touch;">
      <table cellspacing="0" cellpadding="8" border="1"
        style="border-collapse: collapse; width:100%; min-width:650px; font-size:14px; border-color:#d0d0d0;">
        <tr style="font-weight:bold;">
          <th style="background:#e3f2fd;">Room</th>
          <th style="background:#fff8c6;">100<br>Overview</th>
          <th style="background:#ffe6e6;">LOS/<br>Travel</th>
          <th style="background:#f0f4f8;">200<br>Source</th>
          <th style="background:#ffe6e6;">LOS/<br>Travel</th>
          <th style="background:#fff8c6;">300<br>CPS</th>
          <th style="background:#ffe6e6;">LOS/<br>Travel</th>
          <th style="background:#f0f4f8;">400<br>PPR</th>
          <th style="background:#ffe6e6;">LOS/<br>Travel</th>
          <th style="background:#fff8c6;">500<br>Demo</th>
          <th style="background:#ffe6e6;">LOS/<br>Travel</th>
          <th style="background:#f0f4f8;">600<br>WTR Equip</th>
          <th style="background:#ffe6e6;">LOS/<br>Travel</th>
          <th style="background:#fff8c6;">700<br>HMR</th>
          <th style="background:#ffe6e6;">LOS/<br>Travel</th>
        </tr>
        {room_rows_html}
      </table>
    </div>
  </div>

  <div style="text-align:center; padding:15px; color:#777; font-size:12px; margin-top:20px;">
    {claim_name} report | Powered by Claimet Email System
  </div>
</div>
    """
    return html_content


def _generate_list_format_email(claim_name, claim_address, rooms, configs):
    """Generate the sequential list format email."""
    work_types = [
        (100, "JOB/ROOMS OVERVIEW PICS", "...", "=========================="),
        (200, "SOURCE of LOSS PICS", ".....", "==========================="),
        (300, "C.P.S.", ".....", "======================================="),
        (400, "PPR", "", "============================================="),
        (500, "DMO = DEMOLITION", "......", "==========================="),
        (600, "WTR MITIGATION EQUIPMENT & W.I.P", "", "================================"),
        (700, "HMR = HAZARDOUS MATERIALS", "", "===================================="),
    ]

    list_items_html = ''

    default_codes = [
        ("0.0001", "JOBSITE VERIFICATION", "....."),
        ("0.0002", "MECHANICALS = WATER METER READING & PLUMBING REPORT/INVOICE", "."),
        ("0.0003", "MECHANICALS = ELECTRICAL HAZARDS", "."),
        ("0.0004", "EXT DAMAGE IF APPLICABLE ROOF TARPS", "."),
        ("1997", "LEAD & HMR TESTING LAB RESULTS", "."),
        ("1998", "KITCHEN CABINETS SIZES U & L =LF/ CT = SF; APPLIANCES", "."),
        ("1999", "BATHROOM FIXTURES CAB SIZE & FIXTURES & TYPE", "."),
    ]

    for code, description, dots in default_codes:
        list_items_html += f'''
        <div style="padding:8px 0; border-bottom:1px solid #e0e0e0; font-family:monospace; font-size:14px;">
          <span style="display:inline-block; width:80px; font-weight:bold; color:#1e88e5;">{code}</span>
          <span style="color:#555;">{dots} {description}</span>
        </div>
        '''

    for work_type_num, work_type_desc, dots, separator in work_types:
        list_items_html += f'''
        <div style="padding:10px 0; border-bottom:2px solid #1e88e5; font-family:monospace; font-size:14px;
            background:#e3f2fd; margin-top:10px;">
          <span style="display:inline-block; width:80px; font-weight:bold; color:#1e88e5;">{work_type_num}</span>
          <span style="font-weight:bold; color:#1e88e5;">{dots} = {work_type_desc} {separator}</span>
        </div>
        '''

        for idx, room in enumerate(rooms):
            base_num = idx + 1
            room_code = f"{work_type_num // 100}{base_num:02d}"
            room_config = configs.get(room, {})
            config_value = room_config.get(str(work_type_num), room_config.get(work_type_num, '.'))
            display_value = config_value if config_value and config_value != '.' else '............'

            list_items_html += f'''
            <div style="padding:8px 0; border-bottom:1px solid #e0e0e0; font-family:monospace; font-size:14px;">
              <span style="display:inline-block; width:80px; font-weight:bold; color:#1e88e5;">{room_code}</span>
              <span style="display:inline-block; width:150px; color:#333;">{room}</span>
              <span style="color:#555;">{dots} {work_type_desc} {dots}</span>
              <span style="font-weight:bold; color:#d32f2f; margin-left:10px;">{display_value}</span>
            </div>
            '''

        if work_type_num == 300:
            for code, description, d in [
                ("3222", "CPS DAY2 WIP OVERVIEW WIP BOXES PACKOUT PICS", "."),
                ("3333", "CPS3 DAY3 STORAGE OVERVIEW STORAGE MOVE OUT PICS", "."),
                ("3444", "CPS4 DAY4 PACKBACK OVERVIEW PACK-BACK / RESET PICS", "."),
            ]:
                list_items_html += f'''
                <div style="padding:8px 0; border-bottom:1px solid #e0e0e0; font-family:monospace; font-size:14px;">
                  <span style="display:inline-block; width:80px; font-weight:bold; color:#1e88e5;">{code}</span>
                  <span style="color:#555;">{d} {description}</span>
                </div>
                '''

        if work_type_num == 400:
            for code, description, d in [
                ("4111.1", "REPLACEMENT 1 CON OVERVIEW DAY PICS", "."),
                ("4222.2", "REPLACEMENT 2 CON WIP", "."),
                ("4333.3", "REPLACEMENT 3 CON STORAGE", "."),
                ("4444.4", "REPLACEMENT 4 CON DISPOSAL", "."),
            ]:
                list_items_html += f'''
                <div style="padding:8px 0; border-bottom:1px solid #e0e0e0; font-family:monospace; font-size:14px;">
                  <span style="display:inline-block; width:80px; font-weight:bold; color:#1e88e5;">{code}</span>
                  <span style="color:#555;">{d} {description}</span>
                </div>
                '''

    for code, description, suffix in [
        ("9998.0", "REBUILD OVERVIEW WORK IN PROGRESS.......", "WIP"),
        ("9999.0", "REBUILD INTERIOR COMPLETED WORK", ""),
    ]:
        list_items_html += f'''
        <div style="padding:8px 0; border-bottom:1px solid #e0e0e0; font-family:monospace; font-size:14px;">
          <span style="display:inline-block; width:80px; font-weight:bold; color:#1e88e5;">{code}</span>
          <span style="color:#555;">. {description} {suffix}</span>
        </div>
        '''

    html_content = f"""
<div style="font-family: Arial, sans-serif; background:#f5f7fa; padding:30px;">
  <div style="background: linear-gradient(90deg, #1e88e5, #42a5f5); color:white; padding:20px 25px;
      border-radius:8px; font-size:22px; font-weight:bold; margin-bottom:25px;
      box-shadow:0 4px 12px rgba(0,0,0,0.15);">
    {claim_name} — Worktype Documentation
  </div>

  <div style="background:white; border-radius:10px; padding:25px; margin-bottom:25px;
      box-shadow:0 3px 12px rgba(0,0,0,0.12); border-left: 5px solid #28a745;">
    <h2 style="margin-top:0; color:#28a745; font-size:20px;">How to Use This Email</h2>
    <p style="font-size:15px; color:#333; line-height:1.6;">
      This email contains the room list for <strong>{claim_name}</strong>.
      Scroll down to view the list, or open the attached PDF to print.
    </p>
  </div>

  <div style="background:white; border-radius:10px; padding:25px; margin-bottom:35px;
      box-shadow:0 3px 12px rgba(0,0,0,0.12);">
    <h2 style="color:#1e88e5; margin-top:0;">{claim_name} Worktype Room List</h2>
    <h3 style="color:#555; font-weight:normal; margin-top:5px;">@ {claim_address}</h3>
    <div style="margin-top:20px;">
      {list_items_html}
    </div>
  </div>

  <div style="text-align:center; padding:15px; color:#777; font-size:12px; margin-top:20px;">
    {claim_name} report | Powered by Claimet Email System
  </div>
</div>
    """
    return html_content
