from django.http import JsonResponse
from django.shortcuts import render
from products.models import Product


def home(request):
    return render(request, "home.html")


def login(request):
    return render(request, "auth/login.html")


def register(request):
    return render(request, "auth/register.html")


def cart(request):
    return render(request, "cart.html")


def api_home(request):
    return JsonResponse(
        {"message": "GYM CULTURE API funcionando correctamente", "status": "ok"}
    )


def create_tshirt(request):
    """Customizer UI. Persistence/cart integration is intentionally deferred."""
    # Cargamos las variantes junto al producto para evitar consultas adicionales en la plantilla.
    product = Product.objects.filter(active=True).prefetch_related("variants").first()
    variants = []
    if product:
        variants = [
            {"size": variant.size, "color": variant.color, "stock": variant.stock}
            for variant in product.variants.all()
        ]
    return render(
        request,
        "create_tshirt.html",
        {
            "product": product,
            "variants": variants,
        },
    )
