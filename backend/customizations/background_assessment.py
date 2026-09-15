"""Select the fast path only for flat graphics with a measurable exterior."""
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .background_errors import BackgroundRemovalRejected
from .solid_background import rgb_to_lab


@dataclass(frozen=True)
class ImageAssessment:
    strategy: str
    reason: str


def assess_image(image, solid_engine, compressed):
    sample = image.convert('RGB')
    sample.thumbnail((256, 256), Image.Resampling.BOX)
    pixels = np.asarray(sample)
    differences = np.concatenate((np.abs(np.diff(pixels.astype(float), axis=0)).ravel(), np.abs(np.diff(pixels.astype(float), axis=1)).ravel()))
    if float((differences > 8).mean()) < .0005:
        return ImageAssessment('unsafe', 'no_subject_structure')
    try:
        colors, tolerances, *_ = solid_engine.estimate_background(image, compressed)
    except BackgroundRemovalRejected as error:
        if error.reason == 'unstructured_noise':
            return ImageAssessment('unsafe', error.reason)
        return ImageAssessment('semantic', error.reason)
    distances = np.linalg.norm(rgb_to_lab(pixels)[:, :, None] - rgb_to_lab(colors), axis=-1)
    ink = pixels[~np.any(distances <= tolerances, axis=-1)]
    if len(ink) < 8:
        return ImageAssessment('unsafe', 'no_clear_foreground')
    _, counts = np.unique(ink // 24, axis=0, return_counts=True)
    flat_palette_coverage = np.sort(counts)[-8:].sum() / counts.sum()
    # JPEG ringing around a flat logo remains on the fast path. Character
    # shading/skin/clothes introduce structure beyond its dominant ink colors.
    if flat_palette_coverage >= .94:
        return ImageAssessment('solid', 'flat_graphic')
    return ImageAssessment('semantic', 'structured_subject')
