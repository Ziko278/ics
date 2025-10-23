from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """Splits a string by the given argument."""
    if not value:
        return []
    return value.split(arg)

@register.filter
def strip(value):
    """Removes leading and trailing whitespace."""
    if not isinstance(value, str):
        return value
    return value.strip()
