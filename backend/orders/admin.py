from django.contrib import admin

from .models import Order, OrderItem, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("subtotal",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user", "status", "payment_status", "total", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order_number", "user__username", "user__email", "contact_email")
    inlines = (OrderItemInline,)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "product_name",
        "size",
        "color",
        "quantity",
        "unit_price",
        "subtotal",
    )
    search_fields = ("product__name", "order__user__email")


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "old_status", "new_status", "changed_by", "created_at")
    list_filter = ("new_status", "created_at")
    readonly_fields = ("order", "old_status", "new_status", "changed_by", "created_at")
