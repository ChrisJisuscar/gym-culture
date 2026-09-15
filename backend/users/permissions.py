from rest_framework.permissions import BasePermission

from .models import User


def is_administrator(user):
    return bool(user and user.is_authenticated and user.is_active and (user.role == User.Role.ADMIN or user.is_staff))


class IsAdminRole(BasePermission):
    """Permite el acceso solo a cuentas con el rol ADMIN de la aplicación."""

    def has_permission(self, request, view):
        return is_administrator(request.user)
