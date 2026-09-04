from django.apps import AppConfig


class CustomizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "customizations"

    def ready(self):
        from . import signals  # noqa: F401
