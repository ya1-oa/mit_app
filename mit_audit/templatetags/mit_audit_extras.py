from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Return dictionary[key], or None if key is absent.
    Usage: {{ my_dict|get_item:variable_key }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
