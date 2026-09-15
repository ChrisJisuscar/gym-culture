"""Validate semantic masks without eroding hair, fine strokes or accessories."""
import numpy as np
from PIL import Image
from scipy import ndimage

from .background_errors import BackgroundRemovalRejected

FOREGROUND_PROBABILITY = .8
BACKGROUND_PROBABILITY = .08
MINIMUM_SUBJECT_FRACTION = .008
MAXIMUM_SUBJECT_FRACTION = .97


def validate_mask(mask):
    sample = np.asarray(Image.fromarray(mask.astype(np.float32)).resize((384, 384), Image.Resampling.BILINEAR))
    subject = sample >= .5
    fraction = float(subject.mean())
    if not MINIMUM_SUBJECT_FRACTION <= fraction <= MAXIMUM_SUBJECT_FRACTION:
        raise BackgroundRemovalRejected('invalid_subject_extent')
    foreground = sample >= FOREGROUND_PROBABILITY
    background = sample <= BACKGROUND_PROBABILITY
    if foreground.mean() < MINIMUM_SUBJECT_FRACTION or background.mean() < .025:
        raise BackgroundRemovalRejected('uncertain_separation')
    labels, count = ndimage.label(subject)
    sizes = np.bincount(labels.ravel())[1:]
    significant = sizes[sizes > subject.size * .001]
    if count and len(significant) > 12 and sizes.max() / sizes.sum() < .7:
        raise BackgroundRemovalRejected('fragmented_foreground')
    # Strongly predicted holes may be genuine gaps between arms or strands.
    # Large uncertain holes inside a subject are a failed segmentation.
    holes = ndimage.binary_fill_holes(subject) & ~subject
    uncertain_holes = holes & (sample > BACKGROUND_PROBABILITY)
    if uncertain_holes.sum() > subject.sum() * .04:
        raise BackgroundRemovalRejected('uncertain_internal_holes')
    interior = ndimage.distance_transform_edt(subject) >= 3
    if interior.any() and float((sample[interior] < .7).mean()) > .2:
        raise BackgroundRemovalRejected('transparent_subject_interior')
    uncertainty = float(((sample > BACKGROUND_PROBABILITY) & (sample < FOREGROUND_PROBABILITY)).mean())
    confidence = float(np.clip(1 - uncertainty * 2, 0, 1))
    if confidence < .6:
        raise BackgroundRemovalRejected('uncertain_mask', confidence)
    return confidence


def refine_mask(image, mask):
    alpha = mask.copy()
    # Make the confidently enclosed core opaque; keep the model's soft boundary
    # exactly where thin hair, antialiasing and fabric edges need partial alpha.
    core = ndimage.distance_transform_edt(alpha >= .7) > 2
    alpha[core] = 1
    alpha[alpha < .01] = 0
    alpha[alpha > .99] = 1
    rgb = np.array(image.convert('RGB'), dtype=np.float32)
    soft_edge = (alpha > .1) & (alpha < .9)
    if soft_edge.any():
        background = alpha < .01
        weights = ndimage.uniform_filter(background.astype(np.float32), size=7)
        local_background = np.stack([ndimage.uniform_filter(rgb[..., channel] * background, size=7) / np.maximum(weights, 1e-6) for channel in range(3)], axis=-1)
        # Only unmix a known nearby exterior; do not recolor ambiguous hair.
        eligible = soft_edge & (weights > .25)
        rgb[eligible] = np.clip((rgb[eligible] - (1 - alpha[eligible, None]) * local_background[eligible]) / alpha[eligible, None], 0, 255)
    result = Image.fromarray(rgb.astype(np.uint8)).convert('RGBA')
    result.putalpha(Image.fromarray(np.round(alpha * 255).astype(np.uint8)))
    return result
