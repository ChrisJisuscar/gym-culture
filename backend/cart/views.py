from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cart, CartItem
from .serializers import AddCartItemSerializer, CartSerializer, CartItemSerializer


class CartViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        serializer = CartSerializer(cart, context={"request": request})
        return Response(serializer.data)

    def destroy(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart.items.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        cart, _ = Cart.objects.get_or_create(user=self.request.user)
        return cart.items.select_related("product", "variant").prefetch_related("product__images")

    def create(self, request, *args, **kwargs):
        serializer = AddCartItemSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(CartItemSerializer(item, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        item = self.get_object()
        if "customization_data" in request.data:
            payload = {
                "product": item.product_id,
                "variant": request.data.get("variant", item.variant_id),
                "quantity": request.data.get("quantity", item.quantity),
                "customization_data": request.data.get("customization_data"),
                "preview_front": request.data.get("preview_front"),
                "preview_back": request.data.get("preview_back"),
            }
            serializer = AddCartItemSerializer(data=payload, context={"request": request})
            serializer.is_valid(raise_exception=True)
            updated_item = serializer.save(existing_item=item)
            return Response(CartItemSerializer(updated_item, context={"request": request}).data)
        quantity = request.data.get("quantity")
        if quantity is None:
            return Response({"quantity": ["Este campo es obligatorio."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response({"quantity": ["La cantidad debe ser un número entero."]}, status=status.HTTP_400_BAD_REQUEST)
        if quantity < 1:
            return Response({"quantity": ["La cantidad debe ser mayor que 0."]}, status=status.HTTP_400_BAD_REQUEST)
        if item.variant and quantity > item.variant.stock:
            return Response({"quantity": f"Stock insuficiente. Disponible: {item.variant.stock}"}, status=status.HTTP_400_BAD_REQUEST)
        item.quantity = quantity
        item.save(update_fields=["quantity", "updated_at"])
        return Response(CartItemSerializer(item, context={"request": request}).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return Response(CartSerializer(cart, context={"request": request}).data)

    def delete(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart.items.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
