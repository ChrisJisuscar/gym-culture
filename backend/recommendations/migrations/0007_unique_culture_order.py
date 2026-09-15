from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('recommendations', '0006_normalize_culture_order')]
    operations = [migrations.AddConstraint(model_name='designrecommendation', constraint=models.UniqueConstraint(fields=('culture', 'sort_order'), name='unique_recommendation_position_in_culture'))]
