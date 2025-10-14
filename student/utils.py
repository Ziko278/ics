# student/utils.py

import re
from admin_site.models import ClassesModel, ClassSectionModel


def clean_email(email_str):
    """
    Extracts the first valid email from a string that might contain multiple
    emails separated by commas, semicolons, or spaces.
    Returns None if no valid email is found.
    """
    if not email_str:
        return None

    email_str = str(email_str).strip()
    # Split by common delimiters: comma, semicolon, space, or newline
    emails = re.split(r'[,;\s\n]+', email_str)

    for email in emails:
        email = email.strip().lower()
        # A simple but effective regex for basic email validation
        if email and re.match(r'[^@]+@[^@]+\.[^@]+', email):
            return email
    return None


def clean_phone(phone_str):
    """
    Extracts the first valid phone number from a string, cleaning common
    formatting characters. Returns a cleaned number or None.
    """
    if not phone_str:
        return None

    phone_str = str(phone_str).strip()
    # Split by common delimiters in case multiple numbers are provided
    phones = re.split(r'[,;/]+', phone_str)

    for phone in phones:
        phone = phone.strip()
        # Remove non-digit characters, but keep a leading '+' if it exists
        cleaned_phone = re.sub(r'[^\d+]', '', phone)
        if cleaned_phone and len(cleaned_phone) >= 10:
            return cleaned_phone[:20]  # Limit to a reasonable max length (e.g., 20)
    return None


def normalize_gender(gender_str):
    """
    Normalizes various gender inputs (e.g., 'M', 'male', 'F', 'Female')
    to the standard choices 'MALE' or 'FEMALE'.
    """
    if not gender_str:
        return None

    gender_str = str(gender_str).strip().upper()

    if gender_str in ['M', 'MALE']:
        return 'MALE'
    elif gender_str in ['F', 'FEMALE']:
        return 'FEMALE'
    return None


def find_class_by_name(class_name):
    """
    Finds a ClassesModel instance by its name, performing a case-insensitive search.
    Returns the first match or None if not found.
    """
    if not class_name:
        return None

    class_name = str(class_name).strip()
    try:
        # Use .first() to safely get one object or None
        return ClassesModel.objects.filter(name__iexact=class_name).first()
    except ClassesModel.DoesNotExist:
        return None


def find_section_by_name(section_name):
    """
    Finds a ClassSectionModel instance by its name, performing a case-insensitive search.
    Returns the first match or None if not found.
    """
    if not section_name:
        return None

    section_name = str(section_name).strip()
    try:
        # Use .first() to safely get one object or None
        return ClassSectionModel.objects.filter(name__iexact=section_name).first()
    except ClassSectionModel.DoesNotExist:
        return None