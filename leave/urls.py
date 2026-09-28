from django.urls import path

from . import views

urlpatterns = [
    path("leave-types/", views.LeaveTypeListView.as_view(), name="leave-types"),
    path(
        "admin/employees/<int:pk>/allowances/",
        views.EmployeeAllowancesView.as_view(),
        name="admin-employee-allowances",
    ),
    path(
        "admin/employees/<int:pk>/allowances/<int:year>/<str:leave_type>/",
        views.AllowanceDetailView.as_view(),
        name="admin-employee-allowance",
    ),
]
