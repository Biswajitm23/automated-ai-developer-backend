from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Profile

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fields = ("role", "department", "employee_code")
    verbose_name_plural = "Profile"


admin.site.unregister(User)


@admin.register(User)
class UserWithProfileAdmin(UserAdmin):
    inlines = [ProfileInline]
    list_display = (*UserAdmin.list_display, "role", "is_active")

    def get_inline_instances(self, request, obj=None):
        # On "Add user" the post_save signal creates the profile; a second one from the
        # inline would violate the one-to-one constraint. The role is set on the change page.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def save_related(self, request, form, formsets, change) -> None:
        super().save_related(request, form, formsets, change)
        # The role is the source of truth: re-apply it over the staff/superuser checkboxes.
        profile = Profile.objects.filter(user=form.instance).first()
        if profile is not None:
            profile.sync_user_flags()

    @admin.display(description="Role", ordering="profile__role")
    def role(self, obj) -> str:
        return getattr(getattr(obj, "profile", None), "role", "-")
