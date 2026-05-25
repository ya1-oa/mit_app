from django.contrib import admin
from .models import Contractor, RateItem, GCEstimate, GCSection, GCLineItem


@admin.register(Contractor)
class ContractorAdmin(admin.ModelAdmin):
    list_display  = ['name', 'ein', 'role', 'city', 'state', 'contact_person', 'phone', 'is_active']
    list_filter   = ['role', 'state', 'is_active']
    search_fields = ['name', 'ein', 'contact_person']
    ordering      = ['name']


@admin.register(RateItem)
class RateItemAdmin(admin.ModelAdmin):
    list_display  = ['cat', 'sel', 'description', 'unit', 'remove_rate', 'replace_rate', 'taxable', 'is_bid_item', 'section_hint']
    list_filter   = ['cat', 'section_hint', 'taxable', 'is_bid_item']
    search_fields = ['cat', 'sel', 'description']
    ordering      = ['cat', 'sel']


class GCSectionInline(admin.TabularInline):
    model  = GCSection
    extra  = 0
    fields = ['section_type', 'order', 'subcontractor', 'bid_status']


class GCLineItemInline(admin.TabularInline):
    model  = GCLineItem
    extra  = 0
    fields = ['order', 'cat', 'sel', 'description', 'quantity', 'unit', 'remove_rate', 'replace_rate', 'taxable', 'is_bid_item']


@admin.register(GCEstimate)
class GCEstimateAdmin(admin.ModelAdmin):
    list_display  = ['estimate_number', 'client', 'gc_contractor', 'status', 'date_entered', 'created_at']
    list_filter   = ['status']
    search_fields = ['estimate_number', 'client__pOwner', 'gc_contractor__name']
    inlines       = [GCSectionInline]


@admin.register(GCSection)
class GCSectionAdmin(admin.ModelAdmin):
    list_display  = ['section_label', 'estimate', 'subcontractor', 'bid_status', 'section_subtotal']
    list_filter   = ['section_type', 'bid_status']
    inlines       = [GCLineItemInline]

    def section_label(self, obj):
        return obj.section_label
    section_label.short_description = 'Section'

    def section_subtotal(self, obj):
        return f'${obj.section_subtotal:,.2f}'
    section_subtotal.short_description = 'Subtotal'


@admin.register(GCLineItem)
class GCLineItemAdmin(admin.ModelAdmin):
    list_display  = ['cat', 'sel', 'description', 'quantity', 'unit', 'remove_rate', 'replace_rate', 'line_total', 'section']
    list_filter   = ['cat', 'taxable', 'is_bid_item', 'auto_calculated']
    search_fields = ['cat', 'sel', 'description']

    def line_total(self, obj):
        return f'${obj.line_total:,.2f}'
    line_total.short_description = 'Line Total'
