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


@register.filter(name='ordinal_suffix')
def ordinal_suffix(value):
    """
    Return ONLY the English ordinal suffix for a day/number: 1->st, 2->nd,
    3->rd, 4->th, 11->th, 21->st ... Works whether the value is an int or a
    string (the lease templates pass an int, which broke the old
    `== "1"` string comparisons and always rendered "th", e.g. "1th").
    Use as:  {{ day }}<sup>{{ day|ordinal_suffix }}</sup>
    """
    try:
        n = int(value)
    except (ValueError, TypeError):
        return ''
    if 10 <= (n % 100) <= 20:
        return 'th'
    return {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')