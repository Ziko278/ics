# student/utils.py

import re
from admin_site.models import ClassesModel, ClassSectionModel
# utils/fingerprint_match.py
import base64
import cv2
import numpy as np
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

def normalize_base64_input(b64: str) -> bytes:
    """
    Accepts:
      - base64url (URL-safe)
      - standard base64
      - data URLs like "data:image/png;base64,...."
    Returns raw bytes.
    """
    if not isinstance(b64, str):
        raise ValueError("Expected base64 string")

    # strip data URL prefix if present
    if b64.startswith("data:"):
        _, b64 = b64.split(",", 1)

    # remove whitespace/newlines
    b64 = "".join(b64.split())

    # convert base64url to standard base64
    b64 = b64.replace("-", "+").replace("_", "/")

    # fix padding
    padding = len(b64) % 4
    if padding:
        b64 += "=" * (4 - padding)

    try:
        return base64.b64decode(b64)
    except Exception as e:
        logger.exception("Failed to decode base64 fingerprint data")
        raise


def _read_image_from_bytes(b: bytes):
    arr = np.frombuffer(b, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)  # grayscale
    return img


def simple_template_match(probe_b64: str, gallery_b64: str, threshold: float = 0.12) -> Tuple[bool, float]:
    """
    Image-based matching using ORB features and BFMatcher (Hamming).
    Returns (is_match, score) where score is ratio of good matches to max(keypoints).
    NOTE: threshold tuning required per dataset; default 0.12 is conservative.
    """
    try:
        probe_bytes = normalize_base64_input(probe_b64)
        gallery_bytes = normalize_base64_input(gallery_b64)
    except Exception as e:
        logger.exception("Base64 normalization failed")
        return False, 0.0

    probe_img = _read_image_from_bytes(probe_bytes)
    gallery_img = _read_image_from_bytes(gallery_bytes)

    if probe_img is None or gallery_img is None:
        logger.warning("One of the images could not be decoded to OpenCV image")
        return False, 0.0

    # resize to the same scale (helps ORB)
    # choose small side scale to keep speed; preserve aspect ratio
    h1, w1 = probe_img.shape
    h2, w2 = gallery_img.shape
    target_w = min(w1, w2)
    target_h = int(target_w * max(h1/w1, h2/w2))
    # optional: skip resizing if already similar size
    # create ORB detector
    orb = cv2.ORB_create(nfeatures=1200)

    kp1, des1 = orb.detectAndCompute(probe_img, None)
    kp2, des2 = orb.detectAndCompute(gallery_img, None)

    if des1 is None or des2 is None:
        logger.debug("No descriptors found: kp1=%s kp2=%s", len(kp1) if kp1 else 0, len(kp2) if kp2 else 0)
        return False, 0.0

    # BFMatcher with Hamming (binary descriptors)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    try:
        matches = bf.match(des1, des2)
    except Exception as e:
        logger.exception("Matcher failed")
        return False, 0.0

    if not matches:
        return False, 0.0

    # good matches are those with small distance
    matches = sorted(matches, key=lambda m: m.distance)
    # use a dynamic distance threshold: e.g. <= 60 or median*1.2
    # compute median distance
    dists = [m.distance for m in matches]
    median_dist = np.median(dists)
    # threshold_dist chosen conservatively
    threshold_dist = max(50, int(median_dist * 1.2))

    good = [m for m in matches if m.distance <= threshold_dist]
    # normalized score: good matches / max(keypoints)
    denom = max(1, max(len(kp1), len(kp2)))
    score = len(good) / denom

    is_match = score >= threshold

    # Debug info
    logger.debug("Match results: kp1=%d kp2=%d matches=%d good=%d median_dist=%.2f thr=%d score=%.4f is_match=%s",
                 len(kp1), len(kp2), len(matches), len(good), float(median_dist), threshold_dist, score, is_match)

    return bool(is_match), float(score)


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
