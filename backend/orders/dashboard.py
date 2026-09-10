"""Commercial totals use paid orders, once per order, including archived history.

Sales are gross order totals (shipping included), excluding cancelled/refunded
orders. Periods group by order creation in Paraguay, not payment settlement.
Operational KPIs exclude archived orders; stock demand retains their commitments.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import Lower, Trim, TruncDay, TruncMonth
from django.utils import timezone

from products.constants import LOW_STOCK_THRESHOLD
from products.serializers import StockVariantSerializer
from products.services import stock_queryset
from users.models import User
from .models import Order, OrderItem
from .serializers import BackofficeOrderListSerializer


def dashboard_data(period):
    tz = ZoneInfo("America/Asuncion")
    today = timezone.localtime(timezone.now(), tz).date()
    monthly = period == "12m"
    if monthly:
        month_index = today.year * 12 + today.month - 1 - 11
        start = today.replace(year=month_index // 12, month=month_index % 12 + 1, day=1)
    else:
        start = today - timedelta(days=int(period) - 1)
    paid = Q(payment_status=Order.PaymentStatus.PAID) & ~Q(status=Order.Status.CANCELLED)
    all_orders = Order.objects.all()
    active = all_orders.filter(is_archived=False)
    financial = all_orders.aggregate(sales=Sum("total", filter=paid), average=Avg("total", filter=paid))
    counts = dict(active.order_by().values_list("status").annotate(total=Count("id")))
    shortages = OrderItem.objects.filter(allocated_quantity__lt=F("quantity")).values("order_id")
    critical = stock_queryset().filter(Q(stock__lte=LOW_STOCK_THRESHOLD) | Q(pending_demand__gt=0))
    buckets = all_orders.filter(
        created_at__gte=datetime.combine(start, time.min, tzinfo=tz),
        created_at__lt=datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz),
    ).order_by().annotate(bucket=(TruncMonth if monthly else TruncDay)("created_at", tzinfo=tz)).values("bucket").annotate(
        orders=Count("id"), sales=Sum("total", filter=paid),
    ).order_by("bucket")
    found = {row["bucket"].date(): row for row in buckets}
    series = []
    cursor = start
    while cursor <= today:
        row = found.get(cursor, {})
        series.append({"date": cursor.isoformat(), "orders": row.get("orders", 0), "sales": row.get("sales") or Decimal("0")})
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1) if monthly else cursor + timedelta(days=1)
    cities = list(all_orders.order_by().annotate(city=Lower(Trim("shipping_city"))).values("city").annotate(orders=Count("id")).order_by("-orders", "city"))
    for row in cities:
        row["city"] = row["city"].title() or "Sin ciudad registrada"
    top = list(OrderItem.objects.exclude(order__status=Order.Status.CANCELLED).order_by().values(
        "product_id", "product__name", "product__garment_type",
    ).annotate(quantity=Sum("quantity")).order_by("-quantity", "product_id")[:10])
    recent = active.select_related("user").prefetch_related("items__product", "items__variant__product").annotate(item_count=Count("items"))[:8]
    period_orders = sum(row["orders"] for row in series)
    period_sales = sum((row["sales"] for row in series), Decimal("0"))
    today_start = datetime.combine(today, time.min, tzinfo=tz)
    activity = all_orders.filter(created_at__lt=today_start + timedelta(days=1)).aggregate(
        sales_30_days=Sum("total", filter=paid & Q(created_at__gte=today_start - timedelta(days=29))),
        orders_today=Count("id", filter=Q(created_at__gte=today_start)),
        orders_this_week=Count("id", filter=Q(created_at__gte=today_start - timedelta(days=today.weekday()))),
    )
    return {
        "period": period,
        "period_summary": {"orders": period_orders, "sales": period_sales},
        "kpis": {
            "total_sales": financial["sales"] or Decimal("0"),
            "average_ticket": financial["average"] or Decimal("0"),
            "total_orders": all_orders.count(),
            "pending_orders": counts.get(Order.Status.PENDING, 0),
            "production_orders": counts.get(Order.Status.PREPARING, 0),
            "awaiting_stock": active.filter(pk__in=shortages, status__in=[Order.Status.PENDING, Order.Status.CONFIRMED]).count(),
            "customers": User.objects.filter(role=User.Role.CUSTOMER, is_staff=False, is_active=True).count(),
            "low_stock_variants": critical.count(),
            "sales_30_days": activity["sales_30_days"] or Decimal("0"),
            "orders_today": activity["orders_today"],
            "orders_this_week": activity["orders_this_week"],
        },
        "counts": {key.lower(): counts.get(key, 0) for key in Order.Status.values},
        "orders_by_city": cities,
        "sales_over_time": series,
        "orders_by_status": [{"status": key, "orders": counts.get(key, 0)} for key in Order.Status.values],
        "top_products": top,
        "low_stock": StockVariantSerializer(critical.order_by("-pending_demand", "stock", "product__name", "id")[:20], many=True).data,
        "recent_orders": BackofficeOrderListSerializer(recent, many=True).data,
    }
