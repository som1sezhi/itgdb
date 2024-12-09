import os
from datetime import datetime, timezone
from django.test import TestCase
from django.utils.timezone import make_aware

from ..admin import PackAdmin
from ..tasks import process_pack_from_web
from ..models import Tag, PackCategory
from ._common import TEST_BASE_DIR


class ParseBatchCsvIntoTasksTestClass(TestCase):
    maxDiff = None

    def setUp(self):
        self.tag1 = Tag.objects.create(name='tag1')
        self.technical_cat = PackCategory.objects.create(name='Technical')
    
    def _get_task_sigs(self, test_name):
        with open(os.path.join(
            TEST_BASE_DIR, 'csv', f'ParseBatchCsvIntoTasks_{test_name}.csv'
        ), 'rb') as f:
            task_sigs = PackAdmin.parse_batch_csv_into_tasks(f)
        return task_sigs
    
    def _assert_model_counts(self, expected_cat_count, expected_tag_count):
        self.assertEqual(PackCategory.objects.count(), expected_cat_count)
        self.assertEqual(Tag.objects.count(), expected_tag_count)
    
    def _assert_matching_sigs(self, actual_sigs, expected_args):
        expected_sigs = [
            process_pack_from_web.signature(args) for args in expected_args
        ]
        self.assertEqual(expected_sigs, actual_sigs)
    
    def _fill_pack_data(self, **kwargs):
        ret = {
            'name': '',
            'author': '',
            'release_date': None,
            'release_date_year_only': False,
            'category': None,
            'tags': [],
            'links': ''
        }.copy()
        ret.update(kwargs)
        return ret
    
    def test_normal(self):
        sigs = self._get_task_sigs('test_normal')
        self._assert_model_counts(2, 2)
        stamina_cat = PackCategory.objects.get(name='Stamina')
        tag2 = Tag.objects.get(name='TAG 2')
        self._assert_matching_sigs(sigs, [
            ([{
                'name': 'Test Pack',
                'author': 'Test Author',
                'release_date': make_aware(datetime(2023, 1, 1, 9, 0, 0)),
                'release_date_year_only': False,
                'category': self.technical_cat.id,
                'tags': [self.tag1.id, tag2.id],
                'links': 'https://example.com/1\nLink 2\nhttps://example.com/2'
            }], 'https://example.com'),
            ([{
                'name': 'Pack 2',
                'author': 'Author 2',
                'release_date': datetime(
                    2024, 7, 7, 12, 0, 0, tzinfo=timezone.utc
                ),
                'release_date_year_only': False,
                'category': stamina_cat.id,
                'tags': [tag2.id],
                'links': 'Link 1\nhttps://test.com/1'
            }], 'https://test.com'),
        ])

    def test_minimal_data(self):
        sigs = self._get_task_sigs('test_minimal_data')
        self._assert_model_counts(1, 1)
        self._assert_matching_sigs(sigs, [
            ([self._fill_pack_data()], 'https://example.com')
        ])

    def test_see_below(self):
        sigs = self._get_task_sigs('test_see_below')
        self._assert_model_counts(1, 1)
        self._assert_matching_sigs(sigs, [
            ([
                self._fill_pack_data(name='p1'),
            ], 'https://example.com'),
            ([
                self._fill_pack_data(name='p2'),
                self._fill_pack_data(name='p3'),
                self._fill_pack_data(name='p4'),
            ], 'https://example2.com'),
            ([
                self._fill_pack_data(name='p5'),
                self._fill_pack_data(name='p6'),
            ], 'https://example3.com'),
        ])

    def test_release_date(self):
        sigs = self._get_task_sigs('test_release_date')
        self._assert_model_counts(1, 1)
        self._assert_matching_sigs(sigs, [
            ([self._fill_pack_data(
                release_date=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
            )], 'https://p1.com'),
            ([self._fill_pack_data(
                release_date=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
            )], 'https://p2.com'),
            ([self._fill_pack_data(
                release_date=make_aware(datetime(2023, 1, 1, 6, 0))
            )], 'https://p3.com'),
            ([self._fill_pack_data(
                release_date=make_aware(datetime(2023, 1, 1, 6, 0, 59))
            )], 'https://p4.com'),
            ([self._fill_pack_data(
                release_date=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
                release_date_year_only=True
            )], 'https://p5.com'),
        ])

    def test_links(self):
        sigs = self._get_task_sigs('test_links')
        self._assert_model_counts(1, 1)
        self._assert_matching_sigs(sigs, [
            ([self._fill_pack_data(
                links='https://link1.com'
            )], 'https://p1.com'),
            ([self._fill_pack_data(
                links='Link 1\nhttps://link1.com'
            )], 'https://p2.com'),
            ([self._fill_pack_data(
                links='https://link1.com\nLink 2\nhttps://link2.com\nLink 3\nhttps://link3.com'
            )], 'https://p3.com'),
            ([self._fill_pack_data(
                links='Link 1\nhttps://link1.com\nLink 2\nhttps://link2.com'
            )], 'https://p4.com'),
        ])
