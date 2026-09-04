from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .permissions import IsAdminRole
from .serializers import AdminCustomerDetailSerializer, AdminCustomerListSerializer, RegisterSerializer, UserSerializer


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == User.Role.ADMIN:
            return User.objects.all()
        return User.objects.filter(pk=self.request.user.pk)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomerPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def customer_queryset():
    return User.objects.filter(role=User.Role.CUSTOMER).annotate(
        order_count=Count("orders", distinct=True),
        total_spent=Coalesce(
            Sum("orders__total", filter=~Q(orders__status="CANCELLED")),
            Value(0),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        last_order_at=Max("orders__created_at"),
    )


class BackofficeCustomersAPI(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        queryset = customer_queryset().order_by("-date_joined")
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(username__icontains=search)
                | Q(email__icontains=search)
            )
        paginator = CustomerPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AdminCustomerListSerializer(page, many=True).data)


class BackofficeCustomerDetailAPI(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request, pk):
        customer = get_object_or_404(customer_queryset(), pk=pk)
        return Response(AdminCustomerDetailSerializer(customer).data)
