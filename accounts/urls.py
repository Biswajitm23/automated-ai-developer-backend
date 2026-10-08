from django.urls import path

from . import employees, views

urlpatterns = [
    path("auth/csrf/", views.CsrfView.as_view(), name="auth-csrf"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path(
        "auth/password-reset/request/",
        views.PasswordResetRequestView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "auth/password-reset/verify/",
        views.PasswordResetVerifyView.as_view(),
        name="auth-password-reset-verify",
    ),
    path(
        "auth/password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path("auth/session/", views.SessionView.as_view(), name="auth-session"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("admin/ping/", views.AdminPingView.as_view(), name="admin-ping"),
    path("admin/employees/", employees.EmployeeListView.as_view(), name="admin-employees"),
    path("admin/employees/<int:pk>/", employees.EmployeeDetailView.as_view(), name="admin-employee"),
    path(
        "admin/employees/<int:pk>/deactivate/",
        employees.EmployeeDeactivateView.as_view(),
        name="admin-employee-deactivate",
    ),
    path(
        "admin/employees/<int:pk>/reactivate/",
        employees.EmployeeReactivateView.as_view(),
        name="admin-employee-reactivate",
    ),
]
