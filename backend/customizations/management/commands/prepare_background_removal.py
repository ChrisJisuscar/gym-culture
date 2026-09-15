import io
import urllib.request

from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageDraw

from customizations.background_removal import BackgroundRemovalService
from customizations.background_errors import SegmentationUnavailable
from customizations.segmentation import MODEL_BYTES, MODEL_URL, model_path, verify_model


class Command(BaseCommand):
    help = 'Verify local background removal; --download prepares the pinned semantic model.'

    def add_arguments(self, parser):
        parser.add_argument('--download', action='store_true', help='Download and verify the 224 MB BiRefNet Lite ONNX model.')

    def download(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix('.part')
        failures = 0
        while True:
            offset = partial.stat().st_size if partial.exists() else 0
            previous_size = offset
            if offset > MODEL_BYTES:
                raise CommandError('The partial model exceeds its expected size. Remove it before retrying.')
            if offset == MODEL_BYTES:
                break
            end = min(offset + 4 * 1024 * 1024, MODEL_BYTES) - 1
            request = urllib.request.Request(MODEL_URL, headers={'Range': f'bytes={offset}-{end}'})
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    if offset and response.status != 206:
                        offset = 0
                    if response.status == 206 and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                        raise CommandError('The model server returned an invalid byte range.')
                    with partial.open('ab' if offset else 'wb') as target:
                        while chunk := response.read(1024 * 1024):
                            target.write(chunk)
                            if target.tell() > MODEL_BYTES:
                                raise CommandError('The model exceeds its expected size.')
                self.stdout.write(f'Downloaded {partial.stat().st_size}/{MODEL_BYTES} bytes.')
                self.stdout.flush()
                if partial.stat().st_size <= previous_size:
                    raise OSError('The model download made no progress.')
                failures = 0
            except (OSError, TimeoutError) as error:
                failures += 1
                self.stderr.write(f'Download interrupted; retry {failures}/5.')
                if failures >= 5:
                    raise CommandError(f'Model download did not finish: {error}') from error
        try:
            verify_model(partial)
        except SegmentationUnavailable as error:
            raise CommandError('Model integrity verification failed. The incomplete file was not activated.') from error
        partial.replace(path)

    def handle(self, *args, **options):
        path = model_path()
        if options['download'] and not path.exists():
            self.download(path)
        try:
            verify_model(path)
        except Exception as error:
            raise CommandError(f'{error} Run prepare_background_removal --download.') from error
        image = Image.new('RGB', (128, 128), 'white')
        ImageDraw.Draw(image).rectangle((32, 32, 96, 96), fill='black')
        stream = io.BytesIO(); image.save(stream, 'PNG'); stream.seek(0)
        result = Image.open(io.BytesIO(BackgroundRemovalService().remove(stream)))
        if result.getpixel((0, 0))[3] != 0 or result.getpixel((64, 64))[3] != 255:
            raise CommandError('The flat-background self-check failed.')
        self.stdout.write(self.style.SUCCESS('Fast removal passed; semantic model checksum verified.'))
