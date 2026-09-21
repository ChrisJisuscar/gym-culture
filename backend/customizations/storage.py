"""Keep private drafts outside MEDIA_ROOT without moving existing cart assets."""
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils._os import safe_join


class CustomizationStorage(FileSystemStorage):
    def _save(self, name, content):
        if name.startswith('private/'):
            private = FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)
            return 'private/' + private.save(name.removeprefix('private/'), content)
        return super()._save(name, content)

    def path(self, name):
        if name.startswith('private/'):
            return safe_join(settings.PRIVATE_MEDIA_ROOT, name.removeprefix('private/'))
        return super().path(name)

    def url(self, name):
        if name.startswith('private/'):
            raise ValueError('Private images require an authenticated download endpoint.')
        return super().url(name)


customization_storage = CustomizationStorage()


def private_image_response(field, mime_type):
    try:
        stream = field.open('rb')
    except FileNotFoundError as error:
        raise Http404('La imagen ya no está disponible.') from error
    response = FileResponse(stream, content_type=mime_type)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def image_url(customization, field, asset_id=None, side=None):
    if customization.private_assets:
        if asset_id:
            return reverse('customization-asset', args=[customization.pk, asset_id])
        return reverse('customization-preview', args=[customization.pk, side])
    return field.url
