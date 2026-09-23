from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile, Role


@receiver(post_save, sender=get_user_model(), dispatch_uid="accounts_create_profile")
def create_profile(sender, instance, created: bool, raw: bool = False, **kwargs) -> None:
    if created and not raw:
        Profile.objects.get_or_create(
            user=instance,
            defaults={"role": Role.ADMIN if instance.is_superuser else Role.EMPLOYEE},
        )
