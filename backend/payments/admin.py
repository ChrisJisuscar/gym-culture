from django.contrib import admin

from .models import Payment, PaymentEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "provider", "amount", "currency", "status", "created_at")
    list_filter = ("provider", "status", "currency")
    search_fields = ("external_id", "order__order_number", "order__contact_email")
    readonly_fields = (
        "id",
        "order",
        "provider",
        "external_id",
        "amount",
        "currency",
        "status",
        "payment_method",
        "metadata",
        "paid_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("provider_event_id", "provider", "payment", "event_type", "processed", "created_at")
    list_filter = ("provider", "processed", "event_type")
    search_fields = ("provider_event_id", "payment__external_id")
    readonly_fields = ("payment", "provider_event_id", "event_type", "processed", "error", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
