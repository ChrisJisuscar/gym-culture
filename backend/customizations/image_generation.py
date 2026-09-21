"""Provider boundary for optional server-side generation; disabled by default."""
import base64
import io
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from PIL import Image, UnidentifiedImageError


class GenerationError(Exception):
    code = 'generation_failed'


class GenerationUnavailable(GenerationError):
    code = 'generation_unavailable'


class GenerationTimeout(GenerationError):
    code = 'generation_timeout'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, *args, **kwargs):
        raise GenerationError('El servidor de generación no puede redirigir la solicitud.')


class HttpImageProvider:
    """Trusted operator-configured HTTP service returning base64, never a URL."""
    name = 'http'

    def generate_image(self, prompt, options):
        url = settings.IMAGE_GENERATION_URL
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}):
            raise GenerationUnavailable('El servidor de generación no está configurado correctamente.')
        timeout = min(60, max(1, settings.IMAGE_GENERATION_TIMEOUT))
        deadline = time.monotonic() + timeout
        headers = {'Content-Type': 'application/json'}
        if settings.IMAGE_GENERATION_API_KEY:
            headers['Authorization'] = f'Bearer {settings.IMAGE_GENERATION_API_KEY}'
        request = urllib.request.Request(url, data=json.dumps({'prompt': prompt, **options}).encode(), headers=headers, method='POST')
        limit = settings.IMAGE_GENERATION_MAX_BYTES * 4 // 3 + 4096
        payload = bytearray()
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
                while True:
                    if time.monotonic() >= deadline:
                        raise GenerationTimeout('La generación demoró demasiado. Intentá nuevamente.')
                    chunk = response.read1(min(65536, limit + 1 - len(payload)))
                    if not chunk:
                        break
                    payload.extend(chunk)
                    if len(payload) > limit:
                        raise GenerationError('El resultado supera el tamaño permitido.')
            data = json.loads(payload)
            return base64.b64decode(data['image_base64'], validate=True)
        except (TimeoutError, socket.timeout) as error:
            raise GenerationTimeout('La generación demoró demasiado. Intentá nuevamente.') from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise GenerationTimeout('La generación demoró demasiado. Intentá nuevamente.') from error
            raise GenerationError('No se pudo conectar con el generador.') from error
        except (ValueError, KeyError, TypeError) as error:
            raise GenerationError('El generador devolvió un resultado inválido.') from error


class ImageGenerationService:
    providers = {'http': HttpImageProvider}

    def __init__(self, provider=None):
        self.provider = provider

    @classmethod
    def available(cls):
        return settings.IMAGE_GENERATION_PROVIDER in cls.providers and bool(settings.IMAGE_GENERATION_URL)

    def generate_image(self, prompt, options):
        if self.provider is None:
            if not self.available():
                raise GenerationUnavailable('La generación con IA todavía no está habilitada. Podés subir tu propio diseño.')
            self.provider = self.providers[settings.IMAGE_GENERATION_PROVIDER]()
        try:
            payload = self.provider.generate_image(prompt, options)
        except GenerationError:
            raise
        except Exception as error:
            raise GenerationError('El generador no pudo completar la imagen. Intentá nuevamente.') from error
        if not isinstance(payload, bytes):
            raise GenerationError('El generador no devolvió una imagen válida.')
        if len(payload) > settings.IMAGE_GENERATION_MAX_BYTES:
            raise GenerationError('El resultado supera el tamaño permitido.')
        try:
            with Image.open(io.BytesIO(payload)) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP'} or min(image.size) < 64 or max(image.size) > 2048:
                    raise GenerationError('El generador devolvió dimensiones o formato inválidos.')
                image.load()
                output = io.BytesIO()
                image.convert('RGBA').save(output, 'PNG')
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise GenerationError('El generador no devolvió una imagen válida.') from error
        if output.tell() > settings.IMAGE_GENERATION_MAX_BYTES:
            raise GenerationError('La imagen generada supera el tamaño permitido.')
        return output.getvalue(), self.provider.name
