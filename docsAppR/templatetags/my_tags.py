from django import template

register = template.Library()


@register.filter(name='multiply')
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter(name='get_item')
def get_item(mapping, key):
    """Dict/object attribute lookup: {{ my_dict|get_item:key }}"""
    if isinstance(mapping, dict):
        return mapping.get(key, '')
    return getattr(mapping, key, '')


@register.filter(name='attr')
def attr_filter(obj, key):
    """Object attribute lookup: {{ obj|attr:'field_name' }}"""
    return getattr(obj, key, '')