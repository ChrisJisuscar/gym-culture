from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customization
from .serializers import CustomizationSerializer, CustomizationWriteSerializer


class BackgroundRemovalAPI(APIView):
    # Designing is also available before login. This endpoint stores no files.
    from rest_framework.permissions import AllowAny
    from rest_framework.throttling import AnonRateThrottle

    class ProcessingThrottle(AnonRateThrottle):
        rate = "10/min"

        def get_cache_key(self, request, view):
            return self.cache_format % {"scope": "background-removal", "ident": self.get_ident(request)}

    permission_classes = [AllowAny]
    throttle_classes = [ProcessingThrottle]

    def post(self, request):
        import logging
        from django.http import HttpResponse
        from .background_removal import BackgroundRemovalService, BackgroundRemovalBusy
        from .validators import validate_uploaded_image

        upload = request.FILES.get("image")
        if upload is None:
            return Response({"detail": "Seleccioná una imagen PNG, JPG o WebP."}, status=400)
        validate_uploaded_image(upload)
        try:
            result = BackgroundRemovalService().remove(upload)
        except BackgroundRemovalBusy:
            return Response({"detail": "Estamos procesando otra imagen. Intentá de nuevo en unos segundos."}, status=429)
        except Exception:
            logging.getLogger(__name__).exception("image_processing_error: background removal")
            return Response({"detail": "No pudimos quitar el fondo de esta imagen. Intentá nuevamente en unos momentos."}, status=503)
        return HttpResponse(result, content_type="image/png", headers={"Cache-Control": "no-store"})


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
