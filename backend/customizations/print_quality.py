"""Advisory PPI using approximate garment heights, never a production guarantee."""
from django.conf import settings

DEFAULT_PRINT_PROFILE = {
    'highDpi': 300, 'mediumDpi': 150,
    # Model heights measured from the shipped GLBs; garment cm are estimates.
    'garments': {
        'tshirt': {'modelHeight': 28.06645584, 'heightCm': 70},
        'oversized': {'modelHeight': 1, 'heightCm': 76},
        'hoodie': {'modelHeight': 1, 'heightCm': 72},
    },
}


def print_profile():
    return getattr(settings, 'CUSTOM_LAB_PRINT_PROFILE', DEFAULT_PRINT_PROFILE)


def estimate_print_quality(design, garment_type):
    profile = print_profile()
    garment = profile['garments'].get(garment_type)
    pixels = (design.get('imageWidth'), design.get('imageHeight'))
    if design.get('type') != 'image' or not garment or not all(pixels):
        return None
    cm_per_unit = garment['heightCm'] / garment['modelHeight']
    width_cm = design['width'] * design['scale'] * cm_per_unit
    height_cm = design['height'] * design['scale'] * cm_per_unit
    dpi = min(pixels[0] / (width_cm / 2.54), pixels[1] / (height_cm / 2.54))
    level = 'high' if dpi >= profile['highDpi'] else 'medium' if dpi >= profile['mediumDpi'] else 'low'
    return {'level': level, 'dpi': round(dpi), 'widthCm': round(width_cm, 1), 'heightCm': round(height_cm, 1), 'estimated': True}


def enrich_print_quality(configuration):
    for design in configuration['designs']:
        quality = estimate_print_quality(design, configuration['garment']['type'])
        if quality:
            design['printQuality'] = quality
