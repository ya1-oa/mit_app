"""
Management command: seed_line_item_templates
============================================
Populates LineItemTemplate with all static line items for each section type
and box type combination.  Run once after migration 0004.

Usage:
    python manage.py seed_line_item_templates
    python manage.py seed_line_item_templates --clear   # wipe and reseed
"""

from django.core.management.base import BaseCommand
from contractor_hub.models import LineItemTemplate


# ---------------------------------------------------------------------------
# Master template list
# Each row: (group_code, section_type, box_type, cat, sel, description,
#            unit, qty_factor_str, order, notes)
# ---------------------------------------------------------------------------
TEMPLATES = [
    # ══════════════════════════════════════════════════════════════════════
    # PACKING  — CPS PACKING HANDLING & EVALUATION
    # ══════════════════════════════════════════════════════════════════════

    # SMALL BOX CPS
    ('SMALL_TOTAL2', 'packing', 'small', 'CPS', 'BX<',
     'Provide packing box - small', 'EA', '1.0000', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('SMALL_TOTAL2', 'packing', 'small', 'CPS', 'BXMSE',
     'Evaluate pack & inventory misc items - per Sml box', 'EA', '1.0000', 20,
     'B) Allowance for evaluation & packing only'),
    ('SMALL_TOTAL2', 'packing', 'small', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.2000', 30,
     'F) Include RESET to original place, UNPACKING'),
    ('SMALL_TOTAL2', 'packing', 'small', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.0500', 40, ''),
    ('SMALL_TOTAL2', 'packing', 'small', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.0100', 50,
     'I) Lead Technician'),

    # MEDIUM BOX CPS
    ('MEDIUM_TOTAL', 'packing', 'medium', 'CPS', 'BX',
     'Provide packing box - medium', 'EA', '1.0000', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('MEDIUM_TOTAL', 'packing', 'medium', 'CPS', 'BXMME',
     'Evaluate pack & inventory misc items - per Med box', 'EA', '1.0000', 20,
     'B) Allowance for evaluation & packing only'),
    ('MEDIUM_TOTAL', 'packing', 'medium', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.3000', 30,
     'F) Include RESET to original place, UNPACKING'),
    ('MEDIUM_TOTAL', 'packing', 'medium', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.0500', 40, ''),
    ('MEDIUM_TOTAL', 'packing', 'medium', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.0100', 50,
     'I) Lead Technician'),

    # LRG BOX CPS
    ('LRG_TOTAL_BO', 'packing', 'large', 'CPS', 'BX>',
     'Provide packing box - large', 'EA', '1.0000', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('LRG_TOTAL_BO', 'packing', 'large', 'CPS', 'BXMLE',
     'Evaluate pack & inventory misc items - per Lg box', 'EA', '1.0000', 20,
     'B) Allowance for evaluation & packing only'),
    ('LRG_TOTAL_BO', 'packing', 'large', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.5000', 30,
     'F) Include RESET to original place, UNPACKING'),
    ('LRG_TOTAL_BO', 'packing', 'large', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.1000', 40,
     'I) Lead Technician'),

    # XL BOX CPS
    ('XL_TOTAL_ITE', 'packing', 'xl', 'CPS', 'CVCH',
     'Provide plastic chair cover & packing tape', 'EA', '0.3333', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('XL_TOTAL_ITE', 'packing', 'xl', 'CPS', 'BXMXE',
     'Evaluate pack & inventory misc items - per Xlg box', 'EA', '1.0000', 20,
     'B) Allowance for evaluation & packing only'),
    ('XL_TOTAL_ITE', 'packing', 'xl', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.2000', 30,
     'D) Allowance for moving labor INTO storage'),
    ('XL_TOTAL_ITE', 'packing', 'xl', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.2000', 40,
     'E) Allowance for moving labor BACK FROM storage'),
    ('XL_TOTAL_ITE', 'packing', 'xl', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.2000', 50,
     'F) Include RESET to original place, UNPACKING'),
    ('XL_TOTAL_ITE', 'packing', 'xl', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.1000', 60,
     'I) Lead Technician'),

    # MIRROR PIC BOX CPS
    ('MIRROR_PIC_B', 'packing', 'mirror', 'CPS', 'BXMIR',
     'Provide mirror/picture box, packing paper & tape', 'EA', '1.0000', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('MIRROR_PIC_B', 'packing', 'mirror', 'CPS', 'BXMME',
     'Evaluate pack & inventory misc items - per Med box', 'EA', '1.0000', 20,
     'B) Allowance for evaluation & packing only'),
    ('MIRROR_PIC_B', 'packing', 'mirror', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.3000', 30,
     'F) Include RESET to original place, UNPACKING'),
    ('MIRROR_PIC_B', 'packing', 'mirror', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.0100', 40,
     'I) Lead Technician'),

    # LAMP/PLANT/VASE BOX CPS
    ('LAMP__PLANT_', 'packing', 'lamp', 'CPS', 'BXLMP',
     'Provide lamp/vase/plant box', 'EA', '1.0000', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('LAMP__PLANT_', 'packing', 'lamp', 'CPS', 'BXMME',
     'Evaluate pack & inventory misc items - per Med box', 'EA', '1.0000', 20,
     'B) Allowance for evaluation & packing only'),
    ('LAMP__PLANT_', 'packing', 'lamp', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.3000', 30,
     'F) Include RESET to original place, UNPACKING'),
    ('LAMP__PLANT_', 'packing', 'lamp', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.0100', 40,
     'I) Lead Technician'),

    # TV BOX CPS
    ('TV_BOX_COUNT', 'packing', 'tv', 'CPS', 'BXTV',
     'Provide TV box', 'EA', '1.3300', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('TV_BOX_COUNT', 'packing', 'tv', 'CPS', 'BXMME',
     'Evaluate pack & inventory misc items - per Med box', 'EA', '1.3300', 20,
     'B) Allowance for evaluation & packing only'),
    ('TV_BOX_COUNT', 'packing', 'tv', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.4000', 30,
     'F) Include RESET to original place, UNPACKING'),
    ('TV_BOX_COUNT', 'packing', 'tv', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.0100', 40,
     'I) Lead Technician'),

    # WARDROBE BOX CPS
    ('WARDROBE_BOX', 'packing', 'wardrobe', 'CPS', 'BXWDR>',
     'Provide wardrobe box', 'EA', '1.7500', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('WARDROBE_BOX', 'packing', 'wardrobe', 'CPS', 'BXMLE',
     'Evaluate pack & inventory misc items - per Lg box', 'EA', '1.7500', 20,
     'B) Allowance for evaluation & packing only'),
    ('WARDROBE_BOX', 'packing', 'wardrobe', 'CDC', 'LABC',
     'Wardrobe bar clothing removal/reset - per box', 'EA', '0.8800', 30,
     'C) Wardrobe bar labor'),
    ('WARDROBE_BOX', 'packing', 'wardrobe', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.8800', 40,
     'D) Allowance for moving labor INTO storage'),
    ('WARDROBE_BOX', 'packing', 'wardrobe', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.8800', 50,
     'E) Allowance for moving labor BACK FROM storage'),
    ('WARDROBE_BOX', 'packing', 'wardrobe', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.8800', 60,
     'F) Include RESET to original place, UNPACKING'),
    ('WARDROBE_BOX', 'packing', 'wardrobe', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.1800', 70,
     'I) Lead Technician'),

    # MATTRESS BOX CPS
    ('BEDROOM_MAT2', 'packing', 'mattress', 'CPS', 'BXMATQ',
     'Provide mattress bag - queen', 'EA', '1.0000', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('BEDROOM_MAT2', 'packing', 'mattress', 'CPS', 'BXMXE',
     'Evaluate pack & inventory misc items - per Xlg box', 'EA', '1.0000', 20,
     'B) Allowance for evaluation & packing only'),
    ('BEDROOM_MAT2', 'packing', 'mattress', 'CUP', 'MATF-',
     'Cover mattress/box spring - full/queen', 'EA', '1.0000', 30,
     'C) Mattress protection cover'),
    ('BEDROOM_MAT2', 'packing', 'mattress', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '1.2000', 40,
     'F) Include RESET to original place, UNPACKING'),
    ('BEDROOM_MAT2', 'packing', 'mattress', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.1000', 50,
     'I) Lead Technician'),

    # DISH PACK BOX CPS
    ('DISH_PACK_BO', 'packing', 'dishpack', 'CPS', 'BXDISH',
     'Provide dish pack box', 'EA', '1.0000', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('DISH_PACK_BO', 'packing', 'dishpack', 'CPS', 'BXDPE',
     'Evaluate pack & inventory dishes/pack - per box', 'EA', '1.0000', 20,
     'B) Allowance for evaluation & packing only'),
    ('DISH_PACK_BO', 'packing', 'dishpack', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.3000', 30,
     'F) Include RESET to original place, UNPACKING'),
    ('DISH_PACK_BO', 'packing', 'dishpack', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.1000', 40, ''),
    ('DISH_PACK_BO', 'packing', 'dishpack', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.0100', 50,
     'I) Lead Technician'),

    # GLASSPACK BOX CPS
    ('GLASSPACK_BO', 'packing', 'glasspack', 'CPS', 'BXGL',
     'Provide glasspack box, packing paper & tape', 'EA', '1.0000', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('GLASSPACK_BO', 'packing', 'glasspack', 'CPS', 'BXGLE',
     'Evaluate pack & inventory glasspack - per box', 'EA', '1.0000', 20,
     'B) Allowance for evaluation & packing only'),
    ('GLASSPACK_BO', 'packing', 'glasspack', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.3000', 30,
     'F) Include RESET to original place, UNPACKING'),
    ('GLASSPACK_BO', 'packing', 'glasspack', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.1000', 40,
     'I) Lead Technician'),

    # POTS & PANS BOX CPS
    ('POTS_PANS_BO', 'packing', 'pots', 'CPS', 'BX',
     'Provide packing box - small', 'EA', '1.0000', 10,
     'A] SUPPLIES ;BOXES, TAPE, LABELS, ETC.'),
    ('POTS_PANS_BO', 'packing', 'pots', 'CPS', 'BXPPE',
     'Evaluate pack & inventory pots and pans - per Med box', 'EA', '1.0000', 20,
     'B) Allowance for evaluation & packing only'),
    ('POTS_PANS_BO', 'packing', 'pots', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.3000', 30,
     'F) Include RESET to original place, UNPACKING'),
    ('POTS_PANS_BO', 'packing', 'pots', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.0100', 40,
     'I) Lead Technician'),

    # ══════════════════════════════════════════════════════════════════════
    # CLEANING  — CONTENTS CLEANING
    # ══════════════════════════════════════════════════════════════════════
    ('SMALL_TOTAL2', 'cleaning', 'small',    'CGN', 'BXMS',
     'Clean misc items - per Sml box', 'EA', '1.0000', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('MEDIUM_TOTAL', 'cleaning', 'medium',   'CGN', 'BXMM',
     'Clean misc items - per Med box', 'EA', '1.0000', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('LRG_TOTAL_BO', 'cleaning', 'large',    'CGN', 'BXML',
     'Clean misc items - per Lg box', 'EA', '1.0000', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('XL_TOTAL_ITE', 'cleaning', 'xl',       'CGN', 'BXMX',
     'Clean misc items - per Xlg box', 'EA', '1.0000', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('MIRROR_PIC_B', 'cleaning', 'mirror',   'CGN', 'BXMM',
     'Clean misc items - per Med box', 'EA', '1.0000', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('LAMP__PLANT_', 'cleaning', 'lamp',     'CLM', 'FLF-',
     'Clean floor/lamp/plant - light clean', 'EA', '1.0000', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('TV_BOX_COUNT', 'cleaning', 'tv',       'CGN', 'BXMM',
     'Clean misc items - per Med box', 'EA', '1.3300', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('WARDROBE_BOX', 'cleaning', 'wardrobe', 'CGN', 'BXML',
     'Clean misc items - per Lg box', 'EA', '1.7500', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('BEDROOM_MAT2', 'cleaning', 'mattress', 'CGN', 'BXMX',
     'Clean misc items - per Xlg box', 'EA', '1.0000', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('DISH_PACK_BO', 'cleaning', 'dishpack', 'CGN', 'BXDP-',
     'Clean dish pack - per box - Light clean', 'EA', '1.0000', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('GLASSPACK_BO', 'cleaning', 'glasspack','CGN', 'BXGL-',
     'Clean glasspack - per box - Light clean', 'EA', '1.0000', 10,
     'C) Allowance to wipe down, vacuum, air dust'),
    ('POTS_PANS_BO', 'cleaning', 'pots',     'CGN', 'BXPP',
     'Clean pots & pans boxes', 'EA', '1.0000', 10,
     'C) Allowance to wipe down, vacuum, air dust'),

    # ══════════════════════════════════════════════════════════════════════
    # TRANSPORT  — TRANSPORTING CONTENTS
    # qty = box_count × factor (round-trip labor hours)
    # ══════════════════════════════════════════════════════════════════════
    ('SMALL_TOTAL2', 'transport', 'small',    'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.4000', 10,
     'Transport round trip (LL*.2*2)'),
    ('MEDIUM_TOTAL', 'transport', 'medium',   'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.6000', 10,
     'Transport round trip (LL*.3*2)'),
    ('LRG_TOTAL_BO', 'transport', 'large',    'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '2.0000', 10,
     'Transport round trip (LL*1.0*2)'),
    ('XL_TOTAL_ITE', 'transport', 'xl',       'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.4000', 10,
     'Transport round trip (LL*.2*2)'),
    ('MIRROR_PIC_B', 'transport', 'mirror',   'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.6000', 10,
     'Transport round trip (LL*.3*2)'),
    ('LAMP__PLANT_', 'transport', 'lamp',     'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.6000', 10,
     'Transport round trip (LL*.3*2)'),
    ('TV_BOX_COUNT', 'transport', 'tv',       'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.8000', 10,
     'Transport round trip (LL*.4*2)'),
    ('WARDROBE_BOX', 'transport', 'wardrobe', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '1.7600', 10,
     'Transport round trip (LL*.88*2)'),
    ('BEDROOM_MAT2', 'transport', 'mattress', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '2.4000', 10,
     'Transport round trip (LL*1.2*2)'),
    ('DISH_PACK_BO', 'transport', 'dishpack', 'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.6000', 10,
     'Transport round trip (LL*.3*2)'),
    ('GLASSPACK_BO', 'transport', 'glasspack','CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.6000', 10,
     'Transport round trip (LL*.3*2)'),
    ('POTS_PANS_BO', 'transport', 'pots',     'CON', 'LAB',
     'Content Manipulation charge - per hour', 'HR', '0.6000', 10,
     'Transport round trip (LL*.3*2)'),

    # ══════════════════════════════════════════════════════════════════════
    # ADMIN  — ADMINISTRATIVE EXPENSES (bid items — rates are placeholders)
    # ══════════════════════════════════════════════════════════════════════
    ('ADMIN_BID', 'admin', 'fixed', 'CPS', 'BIDITM',
     'Packaging, Handling (bid Item)', 'EA', '1.0000', 10, ''),
    ('ADMIN_BID', 'admin', 'fixed', 'CPS', 'LABS',
     'Contents Evaluation and/or Supervisor/Admin - per hour', 'HR', '0.0000', 20,
     'Supervisory Hours: initial site visit, work monitoring, final closeout'),
    ('ADMIN_BID', 'admin', 'fixed', 'CLN', 'AV',
     'Clean the floor', 'SF', '0.0000', 30,
     'Floor area cleaning allowance'),

    # ══════════════════════════════════════════════════════════════════════
    # DMO  — DMO & RUBBISH REMOVAL (bid items)
    # ══════════════════════════════════════════════════════════════════════
    ('CPS_DMO_RUBB', 'demo', 'fixed', 'DMO', 'DD',
     'Debris disposal - (Bid Item)', 'EA', '1.0000', 10,
     'G) Allowance for DMO remove packing materials & bag, haul to dump'),
    ('CPS_DMO_RUBB', 'demo', 'fixed', 'DMO', 'PU',
     'Haul debris - per pickup truck load - including dump fees', 'EA', '0.0000', 20, ''),
]


class Command(BaseCommand):
    help = 'Seed LineItemTemplate with all static Xactimate line items per section/box type'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete all existing templates before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            count = LineItemTemplate.objects.count()
            LineItemTemplate.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Deleted {count} existing templates.'))

        created = 0
        for row in TEMPLATES:
            (group_code, section_type, box_type, cat, sel,
             description, unit, qty_factor, order, notes) = row

            obj, was_created = LineItemTemplate.objects.get_or_create(
                group_code=group_code,
                section_type=section_type,
                box_type=box_type,
                cat=cat,
                sel=sel,
                order=order,
                defaults={
                    'description': description,
                    'unit': unit,
                    'qty_factor': qty_factor,
                    'notes': notes,
                    'taxable': True,
                },
            )
            if was_created:
                created += 1
            else:
                # Update in case description/factor changed
                obj.description = description
                obj.unit = unit
                obj.qty_factor = qty_factor
                obj.notes = notes
                obj.save()

        total = LineItemTemplate.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f'Done — {created} templates created, {total} total in database.'
            )
        )
