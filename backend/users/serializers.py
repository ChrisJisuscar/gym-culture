from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "date_joined",
        ]
        read_only_fields = fields


class AdminCustomerListSerializer(serializers.ModelSerializer):
    order_count = serializers.IntegerField(read_only=True)
    total_spent = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    last_order_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "date_joined", "is_active", "order_count", "total_spent", "last_order_at"]
        read_only_fields = fields


class AdminCustomerDetailSerializer(AdminCustomerListSerializer):
    orders = serializers.SerializerMethodField()

    class Meta(AdminCustomerListSerializer.Meta):
        fields = AdminCustomerListSerializer.Meta.fields + ["orders"]

    def get_orders(self, obj):
        from django.db.models import Count
        from orders.serializers import OrderListSerializer

        queryset = obj.orders.annotate(item_count=Count("items")).order_by("-created_at")
        return OrderListSerializer(queryset, many=True).data


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["username", "email", "password", "password_confirm"]

    def validate_email(self, value):
        return value.lower()

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Las contraseñas no coinciden."}
            )
        validate_password(
            attrs["password"],
            user=User(username=attrs["username"], email=attrs["email"]),
        )
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        return User.objects.create_user(
            password=password, role=User.Role.CUSTOMER, **validated_data
        )


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = "email"

    def validate(self, attrs):
        email = attrs.get("email", "").strip().lower()
        password = attrs.get("password")
        if not email or not password:
            raise serializers.ValidationError(
                "No se pudieron validar las credenciales."
            )

        user = authenticate(
            request=self.context.get("request"), username=email, password=password
        )
        if not user or not user.is_active:
            raise serializers.ValidationError(
                "No se pudieron validar las credenciales."
            )

        refresh = self.get_token(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": UserSerializer(user).data,
        }
