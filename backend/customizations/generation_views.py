from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from .image_generation import ImageGenerationService, GenerationError, GenerationUnavailable, GenerationTimeout
from .models import GeneratedImage
from .print_quality import print_profile
from .storage import private_image_response


class GenerationInput(serializers.Serializer):
    prompt = serializers.CharField(max_length=1000, min_length=3)
    culture = serializers.ChoiceField(choices=['', 'gymrat', 'anime', 'memes', 'urban'], default='')
    format = serializers.ChoiceField(choices=['square', 'vertical'], default='square')
    transparent = serializers.BooleanField(default=False)


class GenerationThrottle(UserRateThrottle):
    scope = 'image-generation'
    rate = '3/hour'


class ImageGenerationAPI(APIView):
    throttle_classes = [GenerationThrottle]

    def post(self, request):
        serializer = GenerationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        options = dict(serializer.validated_data)
        prompt = options.pop('prompt')
        try:
            payload, provider = ImageGenerationService().generate_image(prompt, options)
        except GenerationError as error:
            code = 503 if isinstance(error, GenerationUnavailable) else 504 if isinstance(error, GenerationTimeout) else 502
            return Response({'detail': str(error), 'code': error.code}, status=code)
        image = GeneratedImage(user=request.user, prompt=prompt, provider=provider, options=options)
        try:
            image.file.save('generated.png', ContentFile(payload), save=False)
            image.save()
        except Exception:
            if image.file:
                image.file.delete(save=False)
            raise
        return Response({'id': image.pk, 'url': reverse('generated-image', args=[image.pk]), 'provider': provider, 'created_at': image.created_at}, status=201, headers={'Cache-Control': 'no-store'})


class GeneratedImageAPI(APIView):
    def get(self, request, pk):
        image = get_object_or_404(GeneratedImage, pk=pk, user=request.user)
        return private_image_response(image.file, 'image/png')


class EditorConfigAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'printQuality': print_profile(), 'generation': {'enabled': ImageGenerationService.available(), 'formats': ['square', 'vertical']}})
