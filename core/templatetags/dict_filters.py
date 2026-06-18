from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Return dictionary[key], or 0 if missing."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, 0)
    return 0
