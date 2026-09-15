from unittest import mock

from django.db import IntegrityError, transaction
from django.db.models.query import QuerySet
from django.test import TestCase
from rest_framework.test import APIClient
from users.models import User

from .models import Culture, DesignRecommendation


class RecommendationOrderingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='ordering-admin', email='ordering-admin@example.com', password='OrderTest123!', role=User.Role.ADMIN)
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.client.get('/backoffice/recommendations/')
        self.csrf = self.client.cookies['csrftoken'].value
        self.culture = Culture.objects.create(slug='ordering-a', name='A')
        self.other = Culture.objects.create(slug='ordering-b', name='B')
        self.items = [DesignRecommendation.objects.create(name=str(index), culture=self.culture, garment_type='tshirt', sort_order=1) for index in range(4)]
        self.other_item = DesignRecommendation.objects.create(name='Other', culture=self.other, garment_type='hoodie')

    def ids(self):
        return list(DesignRecommendation.objects.filter(culture=self.culture).order_by('sort_order').values_list('pk', flat=True))

    def reorder(self, ordered, expected=None, **kwargs):
        return self.client.post('/api/backoffice/recommendations/reorder/', {'culture': self.culture.id, 'ordered_ids': ordered, 'expected_order': self.ids() if expected is None else expected}, format='json', HTTP_X_CSRFTOKEN=self.csrf, **kwargs)

    def test_move_persists_dense_positions_and_other_culture_is_unchanged(self):
        desired = self.ids()[1:2] + self.ids()[:1] + self.ids()[2:]
        result = self.reorder(desired)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(self.ids(), desired)
        self.assertEqual(list(DesignRecommendation.objects.filter(culture=self.culture).order_by('sort_order').values_list('sort_order', flat=True)), [1, 2, 3, 4])
        self.other_item.refresh_from_db(); self.assertEqual(self.other_item.sort_order, 1)
        listed = self.client.get('/api/backoffice/recommendations/', {'culture': self.culture.id}).data['results']
        self.assertEqual([item['id'] for item in listed], desired)

    def test_cross_culture_missing_duplicate_and_stale_orders_are_rejected(self):
        current = self.ids()
        for ids in [current[:-1], [current[0]] * 4, current[:-1] + [self.other_item.id]]:
            self.assertEqual(self.reorder(ids).status_code, 400)
            self.assertEqual(self.ids(), current)
        self.assertEqual(self.reorder(current[::-1]).status_code, 200)
        self.assertEqual(self.reorder(current, expected=current).status_code, 409)

    def test_database_enforces_unique_positions(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DesignRecommendation.objects.filter(pk=self.items[1].pk).update(sort_order=self.items[0].sort_order)

    def test_reorder_rolls_back_even_after_temporary_positions_were_written(self):
        original, bulk_update, calls = self.ids(), QuerySet.bulk_update, []
        def fail_second(queryset, objects, fields, **kwargs):
            calls.append(True)
            if len(calls) == 2: raise RuntimeError('Simulated interrupted write')
            return bulk_update(queryset, objects, fields, **kwargs)
        with mock.patch.object(QuerySet, 'bulk_update', autospec=True, side_effect=fail_second), self.assertRaises(RuntimeError):
            self.reorder(original[::-1])
        self.assertEqual(self.ids(), original)
        self.assertEqual(list(DesignRecommendation.objects.filter(culture=self.culture).order_by('sort_order').values_list('sort_order', flat=True)), [1, 2, 3, 4])

    def test_new_delete_culture_move_and_stale_edit_keep_order_valid(self):
        stale = DesignRecommendation.objects.get(pk=self.items[0].pk)
        self.reorder(self.ids()[::-1])
        stale.name = 'Edited'; stale.save()
        stale.refresh_from_db(); self.assertEqual(stale.sort_order, 4)
        self.items[1].delete()
        self.assertEqual(list(DesignRecommendation.objects.filter(culture=self.culture).order_by('sort_order').values_list('sort_order', flat=True)), [1, 2, 3])
        stale.culture = self.other; stale.save()
        self.assertEqual(stale.sort_order, 2)
        self.assertEqual(list(DesignRecommendation.objects.filter(culture=self.culture).order_by('sort_order').values_list('sort_order', flat=True)), [1, 2])

    def test_customer_and_missing_csrf_cannot_reorder(self):
        self.assertEqual(self.client.post('/api/backoffice/recommendations/reorder/', {'culture': self.culture.pk, 'ordered_ids': self.ids(), 'expected_order': self.ids()}, format='json').status_code, 403)
        customer = User.objects.create_user(username='ordering-customer', email='ordering-customer@example.com')
        self.client.force_login(customer)
        self.assertEqual(self.reorder(self.ids()).status_code, 403)
