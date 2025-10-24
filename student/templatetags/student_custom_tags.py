# student/templatetags/custom_tags.py
from django import template

from admin_site.models import ClassSectionInfoModel

register = template.Library()


@register.filter
def is_form_teacher(user):
    """Returns True if this user is assigned as a form teacher."""
    try:
        staff = user.staff_profile.staff
        return ClassSectionInfoModel.objects.filter(form_teacher=staff).exists()
    except Exception:
        return False
