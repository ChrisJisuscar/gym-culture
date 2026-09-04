from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customization
from .serializers import CustomizationSerializer, CustomizationWriteSerializer


class CustomizationCollectionAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CustomizationWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        customization = serializer.save()
        return Response(CustomizationSerializer(customization, context={"request": request}).data, status=status.HTTP_201_CREATED)


class CustomizationDetailAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        return Customization.objects.prefetch_related("assets").get(pk=pk, user=request.user)

    def get(self, request, pk):
        try:
            customization = self.get_object(request, pk)
        except Customization.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(CustomizationSerializer(customization, context={"request": request}).data)

    def patch(self, request, pk):
        try:
            customization = self.get_object(request, pk)
        except Customization.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if customization.is_frozen:
            return Response({"detail": "Una personalización comprada ya no puede editarse."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = CustomizationWriteSerializer(customization, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        customization = serializer.save()
        return Response(CustomizationSerializer(customization, context={"request": request}).data)

    def delete(self, request, pk):
        try:
            customization = self.get_object(request, pk)
        except Customization.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if customization.is_frozen or customization.order_items.exists():
            return Response({"detail": "Una personalización comprada no puede eliminarse."}, status=status.HTTP_400_BAD_REQUEST)
        if customization.cart_items.exists():
            return Response({"detail": "Quitá primero esta personalización del carrito."}, status=status.HTTP_400_BAD_REQUEST)
        customization.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
