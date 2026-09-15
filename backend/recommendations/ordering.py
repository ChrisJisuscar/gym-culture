from django.db.models import Max

from .models import Culture


def lock_cultures(ids):
    # Consistent parent-before-child lock order for edits, creates and reorders.
    return list(Culture.objects.select_for_update().filter(pk__in=ids).order_by('pk'))


def next_position(model, culture_id):
    return (model.objects.filter(culture_id=culture_id).aggregate(value=Max('sort_order'))['value'] or 0) + 1


def write_positions(model, items):
    if not items:
        return
    offset = max(item.sort_order for item in items) + len(items) + 1
    for index, item in enumerate(items):
        item.sort_order = offset + index
    model.objects.bulk_update(items, ['sort_order'])
    for index, item in enumerate(items, 1):
        item.sort_order = index
    model.objects.bulk_update(items, ['sort_order'])
