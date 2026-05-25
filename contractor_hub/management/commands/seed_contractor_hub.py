"""
Management command: seed_contractor_hub

Seeds the Contractor registry and RateItem library from the standardized
data extracted from the HAYNES CPS estimate PDFs.

Usage:
    python manage.py seed_contractor_hub
    python manage.py seed_contractor_hub --rates-only
    python manage.py seed_contractor_hub --contractors-only
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from contractor_hub.models import Contractor, ContractorRole, RateItem


# ---------------------------------------------------------------------------
# Contractor data — extracted from all 6 PDFs
# ---------------------------------------------------------------------------

CONTRACTORS = [
    {
        'name': 'Platinum One Properties, LLC',
        'ein': '270-62-7387',
        'role': ContractorRole.GC,
        'address': '3239 E128 St. Lee Rd',
        'city': 'Cleveland',
        'state': 'OH',
        'zip_code': '44128',
        'phone': '(216) 214-6747',
        'email': 'properties.platinum@gmail.com',
        'contact_person': 'Quinton Durham Jr',
    },
    {
        'name': 'All Phase Consulting, LLC',
        'ein': '83-2260563',
        'role': ContractorRole.ESTIMATOR,
        'address': '375 Rockbridge NW 172-343',
        'city': 'Lilburn',
        'state': 'GA',
        'zip_code': '30047',
        'phone': '(216) 450-7228',
        'phone2': '(404) 446-9060',
        'email': 'wsbjoe9@gmail.com',
        'email2': 'info@myapcllc.com',
        'website': 'https://www.myapcllc.com',
        'contact_person': 'Joe Jones',
        'notes': 'Also performs CPS Packing & Evaluation as sub.',
    },
    {
        'name': 'Adens Perfection, LLC',
        'ein': '92-0685-963',
        'role': ContractorRole.ADMINISTRATIVE,
        'address': '1244 Rte138 #1201',
        'city': 'Riverdale',
        'state': 'GA',
        'zip_code': '30296',
        'phone': '(404) 454-9745',
        'website': 'https://www.instagram.com/adensperfections',
        'contact_person': 'Marilyn Owens',
    },
    {
        'name': 'BAL Construction & Restoration, LLC',
        'ein': '83-131-5114',
        'role': ContractorRole.STORAGE,
        'address': '20810 Aurora Rd',
        'city': 'Bedford Heights',
        'state': 'OH',
        'zip_code': '44146',
        'phone': '(216) 990-3533',
        'email': 'alhoust523@gmail.com',
        'contact_person': 'Al Houston',
    },
    {
        'name': 'Ian His Hands, LLC',
        'ein': '92-1783835',
        'role': ContractorRole.CLEANING,
        'address': '11645 Cheyenne Trail Suite #301',
        'city': 'Parma Heights',
        'state': 'OH',
        'zip_code': '44130',
        'phone': '(216) 538-6964',
        'contact_person': 'Ian Birks',
        'certification': 'Lead Based Paint Renovation, Repair & Painting Cert#R-I-18350-25-05967',
    },
    {
        'name': 'CAL Construction & Landscaping, LLC',
        'ein': '84-460-8968',
        'role': ContractorRole.DEMO,
        'address': '15728 Lorain #153',
        'city': 'Cleveland',
        'state': 'OH',
        'zip_code': '44111',
        'phone': '(216) 389-2335',
        'email': 'calcompany.cle@gmail.com',
        'contact_person': 'Nehemiah Stanley',
    },
]


# ---------------------------------------------------------------------------
# Rate Library — all standard line item codes and rates
# Source: OHCL8X_MAR26 / OHCL8X_02MAY26 price lists
# ---------------------------------------------------------------------------

RATE_ITEMS = [
    # ── EXHAUST PER LEVEL ────────────────────────────────────────────────────
    {
        'cat': 'WTR', 'sel': 'DRY',
        'description': 'Air mover (per 24 hour period) - No monitoring',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '26.00',
        'taxable': True, 'section_hint': 'exhaust',
    },
    {
        'cat': 'WTR', 'sel': 'DUCTLF',
        'description': 'Ducting - lay-flat',
        'unit': 'LF', 'remove_rate': '0.00', 'replace_rate': '0.38',
        'taxable': True, 'section_hint': 'exhaust',
    },
    {
        'cat': 'WTR', 'sel': 'EQ',
        'description': 'Equipment setup, take down, and monitoring (hourly charge)',
        'unit': 'HR', 'remove_rate': '0.00', 'replace_rate': '69.50',
        'taxable': True, 'section_hint': 'exhaust',
    },
    {
        'cat': 'WTR', 'sel': 'EQD',
        'description': 'Equipment decontamination charge - per piece of equipment',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '41.28',
        'taxable': True, 'section_hint': 'exhaust',
    },
    {
        'cat': 'WTR', 'sel': 'FHEPA',
        'description': 'Add for HEPA filter (for negative air exhaust fan)',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '219.79',
        'taxable': True, 'section_hint': 'exhaust',
    },
    {
        'cat': 'HMR', 'sel': 'LABH',
        'description': 'Hazardous Waste/Mold Cleaning Technician - per hour',
        'unit': 'HR', 'remove_rate': '0.00', 'replace_rate': '73.49',
        'taxable': True, 'section_hint': 'exhaust',
    },
    {
        'cat': 'HMR', 'sel': 'HBAG',
        'description': 'Plastic bag - used for hazardous waste cleanup - Medium',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '1.93',
        'taxable': True, 'section_hint': 'exhaust',
    },
    {
        'cat': 'HMR', 'sel': 'HEPAVAC',
        'description': 'HEPA Vacuuming - hourly charge',
        'unit': 'HR', 'remove_rate': '0.00', 'replace_rate': '76.78',
        'taxable': True, 'section_hint': 'exhaust',
    },

    # ── ADMINISTRATIVE (Adens Perfection) ────────────────────────────────────
    {
        'cat': 'LAB', 'sel': 'ADMIN',
        'description': 'Administrative/supervisor labor charge (Bid Item)',
        'unit': 'HR', 'remove_rate': '0.00', 'replace_rate': '0.00',
        'taxable': False, 'is_bid_item': True, 'section_hint': 'admin',
    },
    {
        'cat': 'CPS', 'sel': 'LABS',
        'description': 'Contents Evaluation and/or Supervisor/Admin - per hour',
        'unit': 'HR', 'remove_rate': '0.00', 'replace_rate': '72.28',
        'taxable': True, 'section_hint': 'admin',
    },
    {
        'cat': 'CPS', 'sel': 'LAB',
        'description': 'Inventory, Packing, Boxing, and Moving charge - per hour',
        'unit': 'HR', 'remove_rate': '0.00', 'replace_rate': '56.29',
        'taxable': True, 'section_hint': 'admin',
    },
    {
        'cat': 'CLN', 'sel': 'AV',
        'description': 'Clean the floor',
        'unit': 'SF', 'remove_rate': '0.00', 'replace_rate': '0.50',
        'taxable': True, 'section_hint': 'admin',
    },

    # ── PACKING / CPS (All Phase Consulting) ─────────────────────────────────
    {
        'cat': 'CPS', 'sel': 'BIDITM',
        'description': 'Packaging, Handling (Bid Item)',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '0.00',
        'taxable': True, 'is_bid_item': True, 'section_hint': 'packing',
    },
    {
        'cat': 'HMR', 'sel': 'PPE+',
        'description': 'Add for personal protective equipment - Heavy duty',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '50.05',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BX',
        'description': 'Provide box, packing paper & tape - medium size',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '3.91',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BX>',
        'description': 'Provide box, packing paper & tape - large size',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '5.28',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'CVCH',
        'description': 'Provide plastic chair cover & packing tape',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '5.31',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'CVCH>',
        'description': 'Provide plastic couch/sofa cover & packing tape',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '8.57',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'PAD+',
        'description': 'Provide furniture heavyweight blanket/pad',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '18.26',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXMSE',
        'description': 'Evaluate pack & inventory misc items - per Sml box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '14.15',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXMME',
        'description': 'Evaluate pack & inventory misc items - per Med box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '17.36',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXMLE',
        'description': 'Evaluate pack & inventory misc items - per Lg box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '22.09',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXMXE',
        'description': 'Evaluate pack & inventory misc items - per Xlg box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '29.87',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXMIR',
        'description': 'Provide mirror/picture box, packing paper & tape',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '10.29',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXLMP',
        'description': 'Provide lamp box set, packing paper & tape',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '8.91',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXWDR>',
        'description': 'Provide wardrobe box & tape - large size',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '27.89',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXDISH',
        'description': 'Provide dishpack box, packing paper & tape',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '9.98',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXDPE',
        'description': 'Evaluate pack & inventory dishpack - per box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '21.02',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXGL',
        'description': 'Provide glasspack box, packing paper & tape',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '19.34',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXGLE',
        'description': 'Evaluate pack & inventory glasspack - per box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '28.11',
        'taxable': True, 'section_hint': 'packing',
    },
    {
        'cat': 'CPS', 'sel': 'BXPPE',
        'description': 'Evaluate pack & inventory pots and pans - per Med box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '9.48',
        'taxable': True, 'section_hint': 'packing',
    },

    # ── CONTENT MANIPULATION (transport, packing labor) ──────────────────────
    {
        'cat': 'CON', 'sel': 'LAB',
        'description': 'Content Manipulation charge - per hour',
        'unit': 'HR', 'remove_rate': '0.00', 'replace_rate': '54.90',
        'taxable': True, 'section_hint': 'transport',
    },

    # ── STORAGE (BAL Construction) ───────────────────────────────────────────
    {
        'cat': 'CPS', 'sel': 'STOPM',
        'description': 'Job-site moving/storage container - 20\' long - per month',
        'unit': 'MO', 'remove_rate': '0.00', 'replace_rate': '0.00',
        'taxable': True, 'section_hint': 'storage',
    },
    {
        'cat': 'CPS', 'sel': 'STOPCD',
        'description': 'Job-site cargo container - pick up/delivery (each way) 16\'-40\'',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '0.00',
        'taxable': True, 'section_hint': 'storage',
    },
    {
        'cat': 'CPS', 'sel': 'STOPP',
        'description': 'Padlock/disc lock',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '0.00',
        'taxable': True, 'section_hint': 'storage',
    },

    # ── CLEANING (Ian His Hands) ─────────────────────────────────────────────
    {
        'cat': 'CGN', 'sel': 'BIDITM',
        'description': 'Clean - General Items (Bid Item)',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '0.00',
        'taxable': True, 'is_bid_item': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'CGN', 'sel': 'BXMS',
        'description': 'Clean misc items - per Sml box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '54.06',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'CGN', 'sel': 'BXMM',
        'description': 'Clean misc items - per Med box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '64.83',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'CGN', 'sel': 'BXML',
        'description': 'Clean misc items - per Lg box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '81.05',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'CGN', 'sel': 'BXMX',
        'description': 'Clean misc items - per Xlg box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '107.82',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'CGN', 'sel': 'BXDP-',
        'description': 'Clean dishpack - per box - Light clean',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '33.95',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'CGN', 'sel': 'BXGL-',
        'description': 'Clean glasspack - per box - Light clean',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '28.76',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'CGN', 'sel': 'BXPP',
        'description': 'Clean pots and pans - per medium box',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '29.64',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'CLM', 'sel': 'FLF-',
        'description': 'Clean floor lamp - flat finish (no shade) - Light clean',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '26.02',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'CGN', 'sel': 'DODROZ',
        'description': 'Deodorization chamber - Ozone treatment',
        'unit': 'CF', 'remove_rate': '0.00', 'replace_rate': '0.11',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'HMR', 'sel': 'PROTX',
        'description': 'Protect - Cover with plastic',
        'unit': 'SF', 'remove_rate': '0.00', 'replace_rate': '0.31',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'HMR', 'sel': 'CLNJST',
        'description': 'Clean floor or roof joist system',
        'unit': 'SF', 'remove_rate': '0.00', 'replace_rate': '1.69',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'HMR', 'sel': 'HEPAVAS',
        'description': 'HEPA Vacuuming - Detailed - per SF',
        'unit': 'SF', 'remove_rate': '0.00', 'replace_rate': '0.93',
        'taxable': True, 'section_hint': 'cleaning',
    },
    {
        'cat': 'CLN', 'sel': 'BIDITM',
        'description': 'Cleaning (Bid Item)',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '0.00',
        'taxable': True, 'is_bid_item': True, 'section_hint': 'cleaning',
    },

    # ── DEMO / RUBBISH (CAL Construction) ────────────────────────────────────
    {
        'cat': 'DMO', 'sel': 'DD',
        'description': 'Debris disposal - (Bid Item)',
        'unit': 'EA', 'remove_rate': '693.24', 'replace_rate': '0.00',
        'taxable': False, 'is_bid_item': True, 'section_hint': 'demo',
    },
    {
        'cat': 'DMO', 'sel': 'PU',
        'description': 'Haul debris - per pickup truck load - including dump fees',
        'unit': 'EA', 'remove_rate': '199.44', 'replace_rate': '0.00',
        'taxable': True, 'section_hint': 'demo',
    },
    {
        'cat': 'DMO', 'sel': 'LAB',
        'description': 'General Demolition - per hour',
        'unit': 'HR', 'remove_rate': '62.58', 'replace_rate': '0.00',
        'taxable': True, 'section_hint': 'demo',
    },

    # ── MISC / SEPARATOR lines ────────────────────────────────────────────────
    {
        'cat': 'USR', 'sel': 'MISC',
        'description': 'Miscellaneous / Separator / Note line',
        'unit': 'EA', 'remove_rate': '0.00', 'replace_rate': '0.00',
        'taxable': False, 'section_hint': '',
    },
]


class Command(BaseCommand):
    help = 'Seed the contractor registry and rate library from standardized CPS data'

    def add_arguments(self, parser):
        parser.add_argument('--rates-only', action='store_true')
        parser.add_argument('--contractors-only', action='store_true')

    def handle(self, *args, **options):
        rates_only = options['rates_only']
        contractors_only = options['contractors_only']

        if not rates_only:
            self._seed_contractors()

        if not contractors_only:
            self._seed_rates()

    def _seed_contractors(self):
        created = updated = 0
        for data in CONTRACTORS:
            obj, is_new = Contractor.objects.update_or_create(
                ein=data['ein'],
                defaults=data,
            )
            if is_new:
                created += 1
            else:
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(f'Contractors: {created} created, {updated} updated')
        )

    def _seed_rates(self):
        created = updated = 0
        for data in RATE_ITEMS:
            obj, is_new = RateItem.objects.update_or_create(
                cat=data['cat'],
                sel=data['sel'],
                defaults={
                    'description': data['description'],
                    'unit': data['unit'],
                    'remove_rate': Decimal(data['remove_rate']),
                    'replace_rate': Decimal(data['replace_rate']),
                    'taxable': data.get('taxable', True),
                    'is_bid_item': data.get('is_bid_item', False),
                    'section_hint': data.get('section_hint', ''),
                },
            )
            if is_new:
                created += 1
            else:
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(f'Rate items: {created} created, {updated} updated')
        )
