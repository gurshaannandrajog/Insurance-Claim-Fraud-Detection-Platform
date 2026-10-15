from django.contrib.auth import login, logout
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.models import AuditAction
from apps.audit.services import log_event

from . import services
from .models import Role, User
from .permissions import IsAdmin, IsCustomer
from .serializers import (AdminUserSerializer, ChangePasswordSerializer, DeleteAccountSerializer,
                          EmailSerializer, EmployeeCreateSerializer, LoginSerializer,
                          PasswordResetConfirmSerializer, ProfileUpdateSerializer, RegisterSerializer,
                          TokenSerializer, UserSerializer)


class PublicAuthView(APIView):
    """Unauthenticated endpoints: CSRF still enforced (prevents login-CSRF), throttled."""
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]

    @method_decorator(csrf_protect)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "CSRF cookie set"})


class RegisterView(PublicAuthView):
    throttle_scope = "register"

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.register_customer(**s.validated_data, request=request)
        return Response({"detail": "Registration successful. Check your email to verify your account."},
                        status=status.HTTP_201_CREATED)


class VerifyEmailView(PublicAuthView):
    throttle_scope = "verification"

    def post(self, request):
        s = TokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.verify_email(s.validated_data["token"], request=request)
        return Response({"detail": "Email verified. You can now sign in."})


class ResendVerificationView(PublicAuthView):
    throttle_scope = "verification"

    def post(self, request):
        s = EmailSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.resend_verification(s.validated_data["email"])
        return Response({"detail": "If that account exists and is unverified, a new link has been sent."})


class LoginView(PublicAuthView):
    throttle_scope = "login"

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = services.authenticate_user(s.validated_data["email"], s.validated_data["password"], request=request)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")  # rotates session id
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    def post(self, request):
        log_event(AuditAction.LOGOUT, request.user, request=request)
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class PasswordResetRequestView(PublicAuthView):
    throttle_scope = "password_reset"

    def post(self, request):
        s = EmailSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.request_password_reset(s.validated_data["email"], request=request)
        return Response({"detail": "If an account exists for that email, a reset link has been sent."})


class PasswordResetConfirmView(PublicAuthView):
    throttle_scope = "password_reset"

    def post(self, request):
        s = PasswordResetConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.reset_password(**s.validated_data, request=request)
        return Response({"detail": "Password updated. You can now sign in."})


class ChangePasswordView(APIView):
    def post(self, request):
        s = ChangePasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.change_password(request.user, **s.validated_data, request=request)
        # keep the user signed in after changing password
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)
        return Response({"detail": "Password changed."})


class ProfileView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        s = ProfileUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        user = services.update_customer_profile(request.user, s.validated_data, request=request)
        return Response(UserSerializer(user).data)


class DeleteAccountView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        s = DeleteAccountSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.delete_customer_account(request.user, s.validated_data["password"], request=request)
        logout(request)
        return Response({"detail": "Your account has been deleted."})


# ----------------------------------------------------------------------------- administrator: users
class AdminUserListCreateView(generics.ListAPIView):
    permission_classes = [IsAdmin]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.select_related("customer_profile", "employee_profile").filter(deleted_at__isnull=True)
        role = self.request.query_params.get("role")
        if role == "STAFF":
            qs = qs.exclude(role=Role.CUSTOMER)
        elif role:
            qs = qs.filter(role=role)
        q = self.request.query_params.get("search")
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(full_name__icontains=q))
        return qs

    def post(self, request):
        s = EmployeeCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = services.create_employee(admin=request.user, request=request, **s.validated_data)
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdmin]
    serializer_class = AdminUserSerializer
    queryset = User.objects.all()


class AdminUserActionView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk, action):
        user = get_object_or_404(User, pk=pk)
        if action == "activate":
            services.set_user_active(request.user, user, True, request)
        elif action == "deactivate":
            services.set_user_active(request.user, user, False, request)
        elif action == "unlock":
            services.unlock_user(request.user, user, request)
        else:
            return Response({"error": {"code": "unknown_action", "message": "Unknown action."}}, status=404)
        return Response(AdminUserSerializer(user).data)


class AdminCustomerListView(generics.ListAPIView):
    """REQ-REP-008 / customer management: customers with their vehicle/policy/claim counts."""
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = (User.objects.filter(role=Role.CUSTOMER).select_related("customer_profile")
              .annotate(vehicle_count=Count("customer_profile__vehicles", distinct=True),
                        policy_count=Count("customer_profile__policies", distinct=True),
                        claim_count=Count("customer_profile__policies__claims", distinct=True)))
        q = self.request.query_params.get("search")
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(full_name__icontains=q) | Q(customer_profile__phone__icontains=q))
        return qs.order_by("-date_joined")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        data = [{**AdminUserSerializer(u).data, "vehicle_count": u.vehicle_count, "policy_count": u.policy_count,
                 "claim_count": u.claim_count} for u in page]
        return self.get_paginated_response(data)
