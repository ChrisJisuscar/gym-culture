from django.db.models.signals import post_delete
from django.dispatch import receiver

from customizations.models import Customization

from .models import CartItem


@receiver(post_delete, sender=CartItem)
def return_unordered_customization_to_draft(sender, instance, **kwargs):
    if not instance.customization_id:
        return
    Customization.objects.filter(
        pk=instance.customization_id,
        state=Customization.State.IN_CART,
        cart_items__isnull=True,
    ).update(state=Customization.State.DRAFT)
