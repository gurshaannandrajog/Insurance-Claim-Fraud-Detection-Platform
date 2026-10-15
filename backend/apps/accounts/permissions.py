"""Role-based access control (REQ-AUTH-008/009, REQ-SEC-007..012). Object-level checks live in each app's selectors."""
from rest_framework.permissions import BasePermission

from .models import Role


class HasRole(BasePermission):
    roles: tuple = ()
    message = "Your role does not have access to this function."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.role in self.roles)


def role_permission(*roles):
    return type("Has" + "Or".join(r.title() for r in roles) + "Role", (HasRole,), {"roles": tuple(roles)})


IsCustomer = role_permission(Role.CUSTOMER)
IsAdjuster = role_permission(Role.ADJUSTER)
IsSIU = role_permission(Role.SIU)
IsAdmin = role_permission(Role.ADMIN)
IsStaff = role_permission(Role.ADJUSTER, Role.SIU, Role.ADMIN)
IsFraudAuthorised = role_permission(Role.ADJUSTER, Role.SIU, Role.ADMIN)  # REQ-FRD-008/009
IsAnyRole = role_permission(Role.CUSTOMER, Role.ADJUSTER, Role.SIU, Role.ADMIN)
