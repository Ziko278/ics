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

@register.filter
def slice_after(value, delimiter):
    """Returns the text after the first occurrence of delimiter"""
    if not value or not delimiter:
        return value
    parts = value.split(delimiter, 1)
    if len(parts) > 1:
        return parts[1].split('\n')[0].strip()
    return ''


@register.filter
def split(value, delimiter):
    return value.split(delimiter)