"""Local subject segmentation; no uploaded image leaves this server."""
import io
import os
import threading
from functools import lru_cache

from django.conf import settings
from PIL import Image, ImageChops, ImageOps


class BackgroundRemovalUnavailable(Exception):
    pass


class BackgroundRemovalBusy(Exception):
    pass


class BackgroundRemovalService:
    # Bound CPU and working memory per worker. Requests never queue indefinitely.
    _slot = threading.Lock()

    @staticmethod
    @lru_cache(maxsize=1)
    def session():
        directory = settings.BASE_DIR / "var" / "background-removal"
        if not (directory / "u2netp.onnx").is_file():
            raise BackgroundRemovalUnavailable("Run prepare_background_removal before serving requests")
        os.environ["U2NET_HOME"] = str(directory)
        os.environ.setdefault("OMP_NUM_THREADS", "2")
        from rembg import new_session
        return new_session("u2netp", providers=["CPUExecutionProvider"])

    def remove(self, upload):
        if not self._slot.acquire(blocking=False):
            raise BackgroundRemovalBusy()
        try:
            session = self.session()
            from rembg import remove
            with Image.open(upload) as source:
                original = ImageOps.exif_transpose(source).convert("RGBA")
            # Segmentation runs on a bounded image; keep output dimensions/transforms.
            working = original.convert("RGB")
            working.thumbnail((1024, 1024))
            mask = remove(working, session=session, only_mask=True)
            mask = mask.convert("L").resize(original.size, Image.Resampling.LANCZOS)
            original.putalpha(ImageChops.multiply(original.getchannel("A"), mask))
            output = io.BytesIO()
            original.save(output, "PNG")
            return output.getvalue()
        finally:
            self._slot.release()
