from rest_framework.permissions import BasePermission

from .models import User


class IsAdminRole(BasePermission):
    """Allows access only to accounts explicitly assigned the application ADMIN role."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.ADMIN)
