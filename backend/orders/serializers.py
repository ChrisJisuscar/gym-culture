from django.core.files.storage import default_storage
from rest_framework import serializers

from .models import Order, OrderItem, OrderStatusHistory


class CheckoutSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    address = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=100)
    department = serializers.CharField(max_length=100)
    reference = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        for field in ("first_name", "last_name", "phone", "address", "city", "department"):
            attrs[field] = attrs[field].strip()
            if not attrs[field]:
                raise serializers.ValidationError({field: "Este campo es obligatorio."})
        attrs["email"] = attrs["email"].strip().lower()
        attrs["reference"] = attrs.get("reference", "").strip()
        return attrs


class OrderItemSerializer(serializers.ModelSerializer):
    is_customized = serializers.SerializerMethodField()
    customization = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id", "product", "product_name", "variant", "size", "color",
            "quantity", "unit_price", "subtotal", "is_customized", "customization",
        ]
        read_only_fields = fields

    def _media_url(self, path):
        if not path:
            return None
        url = default_storage.url(path)
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def get_is_customized(self, obj):
        return bool(obj.customization_snapshot)

    def get_customization(self, obj):
        snapshot = obj.customization_snapshot
        if not snapshot:
            return None
        configuration = snapshot.get("configuration") or {}
        designs = []
        for design in configuration.get("designs", []):
            designs.append({key: value for key, value in design.items() if key not in {"assetUrl", "source", "dataUrl"}})
        return {
            "id": snapshot.get("customizationId"),
            "preview_front_url": self._media_url(snapshot.get("previewFront")),
            "preview_back_url": self._media_url(snapshot.get("previewBack")),
            "designs": designs,
            "asset_count": len(snapshot.get("assets", [])),
        }


class OrderListSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = ["id", "order_number", "created_at", "status", "status_display", "item_count", "total"]
        read_only_fields = fields


class BackofficeOrderListSerializer(OrderListSerializer):
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.EmailField(source="contact_email", read_only=True)

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + ["customer_name", "customer_email"]

    def get_customer_name(self, obj):
        return f"{obj.contact_first_name} {obj.contact_last_name}".strip() or obj.user.username


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)
    shipping = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "status", "status_display", "payment_status",
            "payment_status_display", "delivery_method", "subtotal", "shipping_cost",
            "total", "created_at", "updated_at", "shipping", "item_count", "items",
        ]
        read_only_fields = fields

    def get_shipping(self, obj):
        return {
            "name": f"{obj.contact_first_name} {obj.contact_last_name}".strip(),
            "phone": obj.shipping_phone,
            "address": obj.shipping_address,
            "city": obj.shipping_city,
            "department": obj.shipping_department,
            "reference": obj.shipping_reference,
            "method": obj.delivery_method,
        }

    def get_item_count(self, obj):
        return getattr(obj, "item_count", obj.items.count())


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.CharField(source="changed_by.email", read_only=True)

    class Meta:
        model = OrderStatusHistory
        fields = ["old_status", "new_status", "changed_by", "created_at"]
        read_only_fields = fields


class AdminOrderSerializer(OrderSerializer):
    customer = serializers.SerializerMethodField()
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    allowed_transitions = serializers.SerializerMethodField()

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + ["customer", "status_history", "allowed_transitions"]

    def get_customer(self, obj):
        return {
            "id": obj.user_id,
            "first_name": obj.contact_first_name,
            "last_name": obj.contact_last_name,
            "email": obj.contact_email,
            "phone": obj.shipping_phone,
        }

    def get_shipping(self, obj):
        return {
            "address": obj.shipping_address,
            "city": obj.shipping_city,
            "department": obj.shipping_department,
            "reference": obj.shipping_reference,
            "method": obj.delivery_method,
        }

    def get_allowed_transitions(self, obj):
        from .services import ALLOWED_STATUS_TRANSITIONS

        return sorted(ALLOWED_STATUS_TRANSITIONS[obj.status])


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)
