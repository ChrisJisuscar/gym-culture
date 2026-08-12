from django.http import JsonResponse
from django.shortcuts import render


def home(request):
    return render(request, 'home.html')


def api_home(request):
    return JsonResponse({
        "message": "GYM CULTURE API funcionando correctamente",
        "status": "ok"
    })
