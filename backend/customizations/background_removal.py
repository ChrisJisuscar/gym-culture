"""Hybrid background-removal service; originals never leave the local backend."""
import io
import threading

from PIL import Image, ImageOps

from .background_assessment import assess_image
from .background_errors import BackgroundRemovalBusy, BackgroundRemovalRejected, SAFE_MESSAGE, SegmentationUnavailable
from .foreground_mask import refine_mask, validate_mask
from .segmentation import LocalSegmentationEngine
from .solid_background import SolidBackgroundRemover


class BackgroundRemovalService:
    _slot = threading.Lock()
    max_dimension = 3072

    def __init__(self, segmentation_engine=None):
        self.segmentation_engine = segmentation_engine or LocalSegmentationEngine()
        self.background_confidence = 0
        self.confidence_level = 'UNSAFE'
        self.strategy = 'unsafe'

    def remove(self, upload):
        if not self._slot.acquire(blocking=False):
            raise BackgroundRemovalBusy()
        try:
            with Image.open(upload) as source:
                compressed = source.format in {'JPEG', 'WEBP'}
                if source.format == 'JPEG':
                    source.draft('RGB', (self.max_dimension, self.max_dimension))
                image = ImageOps.exif_transpose(source).convert('RGBA')
            if image.getchannel('A').getextrema()[0] < 255:
                self.strategy = 'transparent'
                raise BackgroundRemovalRejected('already_transparent', message='Esta imagen ya tiene transparencia. Se conservó sin cambios.')
            image.thumbnail((self.max_dimension, self.max_dimension), Image.Resampling.LANCZOS)
            solid = SolidBackgroundRemover()
            assessment = assess_image(image, solid, compressed)
            self.strategy = assessment.strategy
            if assessment.strategy == 'unsafe':
                raise BackgroundRemovalRejected(assessment.reason)
            if assessment.strategy == 'solid':
                result = solid.remove_image(image, compressed)
                self.background_confidence = solid.background_confidence
                self.confidence_level = solid.confidence_level
                return result
            mask = self.segmentation_engine.predict(image)
            self.background_confidence = validate_mask(mask)
            self.confidence_level = 'HIGH' if self.background_confidence >= .92 else 'MEDIUM'
            output = io.BytesIO()
            refine_mask(image, mask).save(output, 'PNG', optimize=True)
            return output.getvalue()
        finally:
            self._slot.release()
