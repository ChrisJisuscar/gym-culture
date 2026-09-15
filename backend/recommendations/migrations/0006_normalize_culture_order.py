from django.db import migrations, models


def normalize_order(apps, schema_editor):
    Recommendation = apps.get_model('recommendations', 'DesignRecommendation')
    for culture in Recommendation.objects.order_by('culture_id').values_list('culture_id', flat=True).distinct():
        items = list(Recommendation.objects.filter(culture_id=culture).order_by('sort_order', '-featured', 'id'))
        for index, item in enumerate(items, 1):
            item.sort_order = index
        Recommendation.objects.bulk_update(items, ['sort_order'])


class Migration(migrations.Migration):
    dependencies = [('recommendations', '0005_designrecommendation_customization_state_and_more')]
    operations = [
        migrations.RunPython(normalize_order, migrations.RunPython.noop),
        migrations.AlterField(model_name='designrecommendation', name='sort_order', field=models.PositiveIntegerField(default=0, editable=False)),
    ]
