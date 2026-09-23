from django.conf import settings
from django.db import migrations


def backfill_profiles(apps, schema_editor):
    """Give every existing user a profile: ADMIN for superusers, EMPLOYEE otherwise."""
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Profile = apps.get_model("accounts", "Profile")
    for user in User.objects.filter(profile__isnull=True).iterator():
        Profile.objects.get_or_create(
            user=user, defaults={"role": "ADMIN" if user.is_superuser else "EMPLOYEE"}
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill_profiles, migrations.RunPython.noop),
    ]
