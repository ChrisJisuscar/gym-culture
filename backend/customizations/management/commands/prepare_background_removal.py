import os

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Download and verify the small local U2NetP segmentation model before deployment."

    def handle(self, *args, **options):
        directory = settings.BASE_DIR / "var" / "background-removal"
        directory.mkdir(parents=True, exist_ok=True)
        os.environ["U2NET_HOME"] = str(directory)
        os.environ.setdefault("OMP_NUM_THREADS", "2")
        from rembg import new_session
        new_session("u2netp", providers=["CPUExecutionProvider"])
        self.stdout.write(self.style.SUCCESS("Local background removal model ready."))
