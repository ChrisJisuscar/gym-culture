from django.http import JsonResponse
from django.conf import settings
from django.db.models import Prefetch
from django.shortcuts import redirect, render

from products.models import Product, ProductVariant


def home(request):
    return render(request, "home.html")


def login(request):
    return render(request, "auth/login.html")


def register(request):
    return render(request, "auth/register.html")


def cart(request):
    return render(request, "cart.html")


def checkout(request):
    return render(
        request,
        "orders/checkout.html",
        {
            "payment_provider": settings.PAYMENT_PROVIDER,
            "payment_mock_enabled": settings.DEBUG
            and settings.PAYMENT_PROVIDER == "mock",
            "debug": settings.DEBUG,
        },
    )


def order_confirmation(request, order_number):
    return render(request, "orders/confirmation.html", {"order_number": order_number})


def my_orders(request):
    return render(request, "orders/list.html")


def my_order_detail(request, pk):
    return render(request, "orders/detail.html", {"order_id": pk})


def backoffice_dashboard(request):
    return render(request, "backoffice/dashboard.html")


def backoffice_orders(request):
    return render(request, "backoffice/orders.html")


def backoffice_order_detail(request, pk):
    return render(request, "backoffice/order_detail.html", {"order_id": pk})


def backoffice_production(request):
    return render(request, "backoffice/production.html")


def backoffice_products(request):
    return render(request, "backoffice/products.html")


def backoffice_product_detail(request, pk):
    return render(request, "backoffice/product_detail.html", {"product_id": pk})


def backoffice_product_create(request):
    return render(request, "backoffice/product_detail.html", {"product_id": ""})


def backoffice_stock(request):
    return render(request, "backoffice/stock.html")


def backoffice_customers(request):
    return render(request, "backoffice/customers.html")


def backoffice_customer_detail(request, pk):
    return render(request, "backoffice/customer_detail.html", {"customer_id": pk})


def backoffice_recommendations(request):
    if request.method == "POST":
        return redirect("backoffice-recommendations-page")
    return render(request, "backoffice/recommendations.html")


def api_home(request):
    return JsonResponse(
        {"message": "GYM CULTURE API funcionando correctamente", "status": "ok"}
    )


def create_tshirt(request, recommendation_admin=False, recommendation_id=None):
    """Muestra el Custom Lab 3D con persistencia e integración con el carrito."""
    from recommendations.models import Culture
    from products.serializers import ProductSerializer

    products = list(Product.objects.filter(active=True).prefetch_related(
        Prefetch("variants", queryset=ProductVariant.objects.filter(active=True)), "images"
    ).order_by("id"))
    product = next((item for item in products if item.garment_type == "tshirt"), None)
    cultures = list((Culture.objects.all() if recommendation_admin else Culture.objects.filter(active=True)).order_by("sort_order", "id"))
    requested_culture = (request.GET.get("culture") or "").strip().lower()
    selected_culture = next((culture for culture in cultures if culture.slug == requested_culture), None) \
        or (cultures[0] if cultures else None)
    return render(request, "create_tshirt.html", {
        "product": product,
        "customizer_mode": "recommendation-admin" if recommendation_admin else "customer",
        "recommendation_id": recommendation_id or "",
        "customizer_products": ProductSerializer(products, many=True).data,
        "cultures": [
            {"id": culture.id, "slug": culture.slug, "name": culture.name, "tagline": culture.tagline}
            for culture in cultures
        ],
        "selected_culture": selected_culture.slug if selected_culture else "",
    })
