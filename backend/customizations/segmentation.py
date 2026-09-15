"""Local ONNX inference. No network or remote Python code runs in a request."""
import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np
from django.conf import settings
from PIL import Image
from scipy.special import expit

from .background_errors import SegmentationUnavailable

MODEL_FILENAME = 'birefnet-general-lite.onnx'
MODEL_URL = 'https://huggingface.co/onnx-community/BiRefNet_lite-ONNX/resolve/f82954f/onnx/model.onnx'
MODEL_SHA256 = '5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333'
MODEL_BYTES = 224005088
INPUT_SIZE = 1024
IMAGE_MEAN = np.array([.485, .456, .406], dtype=np.float32)
IMAGE_STD = np.array([.229, .224, .225], dtype=np.float32)


def model_path():
    default = Path(__file__).resolve().parents[1] / 'var' / 'models' / MODEL_FILENAME
    return Path(getattr(settings, 'BACKGROUND_REMOVAL_MODEL_PATH', default)) if settings.configured else default


def verify_model(path):
    if not path.is_file() or path.stat().st_size != MODEL_BYTES:
        raise SegmentationUnavailable('El modelo de segmentación no está preparado.')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != MODEL_SHA256:
        raise SegmentationUnavailable('El modelo de segmentación no superó la verificación de integridad.')


@lru_cache(maxsize=1)
def inference_session(path):
    verify_model(Path(path))
    try:
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # The arena otherwise retains large intermediate tensors after inference,
        # competing with Django and the 3D browser on machines with limited RAM.
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        return ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
    except (ImportError, RuntimeError) as error:
        raise SegmentationUnavailable('No se pudo iniciar la segmentación local.') from error


class LocalSegmentationEngine:
    name = 'birefnet-lite'

    def predict(self, image):
        session = inference_session(str(model_path()))
        resized = image.convert('RGB').resize((INPUT_SIZE, INPUT_SIZE), Image.Resampling.LANCZOS)
        pixels = np.asarray(resized, dtype=np.float32) / 255
        tensor = ((pixels - IMAGE_MEAN) / IMAGE_STD).transpose(2, 0, 1)[None]
        logits = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        # Keep calibrated soft probabilities; stretching min/max can turn an
        # uncertain, nearly empty prediction into an apparently confident cut.
        probabilities = expit(np.asarray(logits, dtype=np.float32).squeeze())
        if probabilities.ndim != 2 or not np.isfinite(probabilities).all():
            raise SegmentationUnavailable('El modelo devolvió una máscara inválida.')
        mask = Image.fromarray(probabilities).resize(image.size, Image.Resampling.BILINEAR)
        return np.asarray(mask).clip(0, 1)
