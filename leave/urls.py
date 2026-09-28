from django.urls import path

from . import employee_views, views

urlpatterns = [
    path("leave-types/", views.LeaveTypeListView.as_view(), name="leave-types"),
    path("me/balances/", employee_views.MyBalancesView.as_view(), name="my-balances"),
    path("leave-requests/", employee_views.LeaveRequestCollectionView.as_view(), name="leave-requests"),
    path(
        "leave-requests/preview/",
        employee_views.LeavePreviewView.as_view(),
        name="leave-request-preview",
    ),
    path(
        "leave-requests/<int:pk>/",
        employee_views.LeaveRequestDetailView.as_view(),
        name="leave-request",
    ),
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
