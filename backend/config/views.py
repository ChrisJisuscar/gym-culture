from django.http import JsonResponse
from django.db.models import Prefetch
from django.shortcuts import render

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
    return render(request, "orders/checkout.html")


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


def api_home(request):
    return JsonResponse(
        {"message": "GYM CULTURE API funcionando correctamente", "status": "ok"}
    )


def create_tshirt(request):
    """Muestra el Custom Lab 3D con persistencia e integración con el carrito."""
    # Cargamos las variantes junto al producto para evitar consultas adicionales en la plantilla.
    active_variants = ProductVariant.objects.filter(active=True)
    product = (
        Product.objects.filter(active=True)
        .prefetch_related(Prefetch("variants", queryset=active_variants))
        .first()
    )
    variants = []
    if product:
        variants = [
            {
                "id": variant.id,
                "size": variant.size,
                "color": variant.color,
                "stock": variant.stock,
            }
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
