from django.contrib.auth.backends import ModelBackend

from .models import User


class EmailBackend(ModelBackend):
    """Authenticate the existing custom user model by its unique email."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (kwargs.get("email") or username or "").strip().lower()
        if not email or not password:
            return None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Keep Django's password-hash timing behavior for unknown users.
            User().set_password(password)
            return None
        return user if user.check_password(password) and self.user_can_authenticate(user) else None
