from django.urls import path

from . import views

auth_urlpatterns = [
    path("csrf/", views.CsrfView.as_view()),
    path("register/", views.RegisterView.as_view()),
    path("verify-email/", views.VerifyEmailView.as_view()),
    path("resend-verification/", views.ResendVerificationView.as_view()),
    path("login/", views.LoginView.as_view()),
    path("logout/", views.LogoutView.as_view()),
    path("me/", views.MeView.as_view()),
    path("password-reset/", views.PasswordResetRequestView.as_view()),
    path("password-reset/confirm/", views.PasswordResetConfirmView.as_view()),
    path("change-password/", views.ChangePasswordView.as_view()),
]

profile_urlpatterns = [
    path("", views.ProfileView.as_view()),
    path("delete/", views.DeleteAccountView.as_view()),
]

admin_urlpatterns = [
    path("users/", views.AdminUserListCreateView.as_view()),
    path("users/<int:pk>/", views.AdminUserDetailView.as_view()),
    path("users/<int:pk>/<str:action>/", views.AdminUserActionView.as_view()),
    path("customers/", views.AdminCustomerListView.as_view()),
]
