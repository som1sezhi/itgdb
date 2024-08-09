import os
import logging
from datetime import datetime, timezone
from unittest.mock import patch
from django.conf import settings
from django.test import TestCase
from django.test.testcases import SerializeMixin

from ..tasks import process_pack_from_web
from ._common import TEST_BASE_DIR


@patch('itgdb_site.tasks.ProgressTracker')
@patch('itgdb_site.tasks.upload_pack')
class ProcessPackFromWebTestClass(SerializeMixin, TestCase):
    # run these tests sequentially so we can reliably test for the
    # nonexistence of downloaded/extracted archives after the task is done
    lockfile = __file__

    def setUp(self):
        # disable celery error logs + patool info logs polluting stdout
        logging.disable(logging.CRITICAL)
    
    def tearDown(self):
        # restore previous log level
        logging.disable(logging.NOTSET)

    def _get_archive_url(self, file_suffix):
        path = os.path.join(
            TEST_BASE_DIR, 'pack_archives', 'ProcessPackFromWeb_' + file_suffix
        )
        return 'file://' + path
    
    def _fill_pack_data_list(self, pack_data_list):
        base = {
            'name': '',
            'author': '',
            'release_date': None,
            'category': None,
            'tags': [],
            'links': ''
        }
        new_pack_data_list = [base.copy() for _ in pack_data_list]
        for data, new_data in zip(pack_data_list, new_pack_data_list):
            new_data.update(data)
        return new_pack_data_list
    
    def _assert_upload_pack_calls(self, mock_upload_pack, expected_calls):
        self.assertEqual(mock_upload_pack.call_count, len(expected_calls))
        for actual_call, expected_call in zip(
            mock_upload_pack.call_args_list, expected_calls
        ):
            actual_sim_pack = actual_call.args[0]
            actual_pack_dir_name = actual_sim_pack.name
            actual_pack_data = actual_call.args[1]
            expected_pack_dir_name, expected_pack_data = expected_call
            if expected_pack_dir_name is not None:
                self.assertEqual(actual_pack_dir_name, expected_pack_dir_name)
            self.assertEqual(actual_pack_data, expected_pack_data)
    
    def _assert_cleaned_up(self):
        self.assertFalse(os.listdir(settings.MEDIA_ROOT / 'packs'))
        self.assertFalse(os.listdir(settings.MEDIA_ROOT / 'extracted'))
    
    def _do_test(
        self, mock_upload_pack,
        file_suffix, pack_data_list, expected_pack_dir_names,
        expected_status='SUCCESS'
    ):
        archive_url = self._get_archive_url(file_suffix)
        pack_data_list = self._fill_pack_data_list(pack_data_list)
        task = process_pack_from_web.s(pack_data_list, archive_url).apply()
        self.assertEqual(task.status, expected_status)
        self._assert_upload_pack_calls(
            mock_upload_pack, list(zip(expected_pack_dir_names, pack_data_list))
        )
        self._assert_cleaned_up()

    def test_one_pack(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, '1_pack.zip',
            [{
                'name': 'pack1',
                'author': 'Author 1, Author 2',
                'release_date': datetime(2022, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
                'category': 1,
                'tags': [1, 2],
                'links': 'https://example.com\nLink 2\nhttps://example.com/2'
            }],
            ['pack1']
        )
    
    def test_one_pack_no_matching_name(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, '1_pack.zip',
            [{'name': 'asdf'}],
            ['pack1']
        )

    def test_extracted_root_is_pack_dir(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, '1_pack_songs_in_root.zip',
            [{'name': 'asdf'}],
            [None] # extracted dir name is random, don't bother checking
        )
        # instead, just check where the dir is located
        sim_pack = mock_upload_pack.call_args.args[0]
        path = sim_pack.pack_dir
        self.assertEqual(
            str(settings.MEDIA_ROOT / 'extracted'),
            os.path.dirname(path)
        )

    def test_two_packs(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, '2_packs.zip',
            [{'name': 'pack2'}, {'name': 'pack1'}],
            ['pack2', 'pack1']
        )

    def test_two_packs_fail(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, '2_packs.zip',
            [{'name': 'pack2'}, {'name': 'asdf'}],
            [], 'FAILURE'
        )

    def test_not_enough_packs_fail(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, '2_packs.zip',
            [{'name': 'pack2'}, {'name': 'pack1'}, {'name': 'extraneous_dir'}],
            [], 'FAILURE'
        )

    def test_more_packs_than_requested(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, '2_packs.zip',
            [{'name': 'pack2'}],
            ['pack2'],
        )

    def test_invalid_url_fail(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, 'asdfasdfasdf',
            [{'name': 'pack1'}],
            [], 'FAILURE'
        )

    def test_invalid_file_fail(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, 'not_an_archive.txt',
            [{'name': 'pack1'}],
            [], 'FAILURE'
        )

    def test_no_packs_in_archive(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, '0_packs.zip',
            [{'name': 'pack1'}],
            [], 'FAILURE'
        )

    def test_rar_format(self, mock_upload_pack, mock_prog):
        self._do_test(
            mock_upload_pack, '1_pack.rar',
            [{'name': 'pack1'}],
            ['pack1']
        )