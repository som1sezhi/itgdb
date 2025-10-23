import logging
from datetime import datetime, timezone
import shutil
import os
from unittest.mock import patch
from django.test import TestCase
from django.utils.timezone import now
from django.core.files.storage.memory import InMemoryStorage
from simfile.dir import SimfilePack
from storages.backends.s3 import S3Storage

from ..models import Tag, PackCategory, Pack, ImageFile, Song, Chart
from ..utils.uploads import upload_pack, patch_pack
from ._common import TEST_BASE_DIR, open_test_pack
from ..tasks import ProcessPatchResults

in_mem_storage = InMemoryStorage()

# essentially replace s3 with mock/temporary storage during tests
@patch.object(S3Storage, '_save', in_mem_storage._save)
@patch.object(S3Storage, '_open', in_mem_storage._open)
class UploadPackTestClass(TestCase):

    def setUp(self):
        self.tags = [
            Tag.objects.create(name='tag1'), Tag.objects.create(name='tag2')
        ]
        self.pack_category = PackCategory.objects.create(name='Technical')

        # disable info logs for processing songs
        logging.disable(logging.INFO)
    
    def tearDown(self):
        # restore previous log level
        logging.disable(logging.NOTSET)

    def _check_pack(self, actual_pack, expected_data):
        for attr, expected_attr in expected_data.items():
            actual_attr = getattr(actual_pack, attr)
            if attr == 'tags':
                # convert django queryset to set
                actual_attr = set(actual_attr.all())

            if attr == 'upload_date':
                # special case for upload_date: check if sufficiently close
                # to the present (expected_attr)
                delta = expected_attr - actual_attr
                self.assertTrue(0 <= delta.total_seconds() <= 30)
            else:
                self.assertEqual(expected_attr, actual_attr)

    def test_upload(self):
        # test a regular upload of a pack with 2 songs
        # - check that the pack contains the correct data
        # - check that songs and charts are also uploaded
        #   - check that release_date and release_date_year_only are propagated
        #     from pack to songs/charts correctly
        # - check that images are uploaded correctly
        #   - pack and song2 banner image should be the same object
        #   - pack/song2 banner is 100x70, song1 banner is 100x100
        simfile_pack = open_test_pack('UploadPack_test_upload')
        expected_release_date = datetime(2022, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        pack_data = {
            'name': 'Test Pack',
            'author': 'Author 1, Author 2',
            'release_date': expected_release_date,
            'release_date_year_only': True,
            'category': self.pack_category.id,
            'tags': [tag.id for tag in self.tags],
            'links': 'https://example.com\nLink 2\nhttps://example.com/2'
        }

        upload_pack(simfile_pack, pack_data)

        # check pack
        self.assertEqual(1, len(Pack.objects.all()))
        pack_data.update({
            'upload_date': now(),
            'category': self.pack_category,
            'tags': set(self.tags),
            'pack_ini': ''
        })
        pack = Pack.objects.first()
        self._check_pack(pack, pack_data)
        # check songs and charts
        self.assertEqual(2, len(pack.song_set.all()))
        song1 = pack.song_set.get(title='song1')
        song2 = pack.song_set.get(title='song2')
        self.assertEqual(1, len(song1.chart_set.all()))
        self.assertEqual(1, len(song2.chart_set.all()))
        # check release dates
        for song in pack.song_set.all():
            self.assertEqual(expected_release_date, song.release_date)
            self.assertTrue(song.release_date_year_only)
        for chart in Chart.objects.filter(song__pack=pack):
            self.assertEqual(expected_release_date, chart.release_date)
            self.assertTrue(chart.release_date_year_only)
        # check images
        song1_bn = song1.banner
        song2_bn = song2.banner
        self.assertEqual({song1_bn, song2_bn}, set(pack.imagefile_set.all()))
        self.assertEqual(song2_bn, pack.banner)
        for dims, bn in (((100, 100), song1_bn), ((100, 70), song2_bn)):
            self.assertEqual(dims, (bn.image.width, bn.image.height))

    def test_minimal_data(self):
        # test an upload with minimal supplied data (most fields are empty).
        # - name should be autofilled with name of pack directory
        # - upload_date should be filled
        # - release_date_year_only is required (we set to False)
        # - other fields should be empty/null
        simfile_pack = open_test_pack('UploadPack_test_minimal_data')
        pack_data = {
            'name': '',
            'author': '',
            'release_date': None,
            'release_date_year_only': False,
            'category': None,
            'tags': [],
            'links': ''
        }

        upload_pack(simfile_pack, pack_data)

        self.assertEqual(1, len(Pack.objects.all()))
        pack_data.update({
            'name': 'UploadPack_test_minimal_data',
            'upload_date': now(),
            'tags': set(),
            'banner': None,
            'pack_ini': ''
        })
        pack = Pack.objects.first()
        self._check_pack(pack, pack_data)

    def test_dupe_sims(self):
        # test that duplicate simfiles are handled appropriately.
        # the file that is first alphabetically (case-insensitive) should be
        # kept, and the others should be deleted.
        # in this test case, the correct simfiles should have titles containing
        # the word "REAL" in them.

        # clone the test data, since we will be deleting files in it
        pack_copy_path = os.path.join(
            TEST_BASE_DIR, 'packs', 'UploadPack_test_dupe_sims_COPY'
        )
        shutil.copytree(
            os.path.join(TEST_BASE_DIR, 'packs', 'UploadPack_test_dupe_sims'),
            pack_copy_path
        )

        try:
            simfile_pack = open_test_pack('UploadPack_test_dupe_sims_COPY')
            pack_data = {
                'name': '',
                'author': '',
                'release_date': None,
                'release_date_year_only': False,
                'category': None,
                'tags': [],
                'links': ''
            }

            upload_pack(simfile_pack, pack_data)

            self.assertEqual(1, len(Pack.objects.all()))
            pack = Pack.objects.first()
            songs = pack.song_set.all()
            titles = set(song.title for song in songs)
            self.assertEqual(
                {
                    'dupetest REAL',
                    'dupetest2 REAL',
                    'dupetest_sm REAL',
                    'dupetest_uppercase_ext REAL'
                },
                titles
            )
        finally:
            # clean up the cloned test data
            shutil.rmtree(pack_copy_path)
    
    def test_pack_ini(self):
        # test that Pack.ini is handled correctly for the standard use case.
        # - Pack.ini display title overrides other specified names if present
        # - Pack.ini banner path is used
        # - Pack.ini data is stored in pack_ini column
        simfile_pack = open_test_pack('UploadPack_test_pack_ini')
        pack_data = {
            'name': 'ignore this title',
            'author': '',
            'release_date': None,
            'release_date_year_only': False,
            'category': None,
            'tags': [],
            'links': ''
        }

        upload_pack(simfile_pack, pack_data)

        self.assertEqual(1, len(Pack.objects.all()))
        pack_data.update({
            'name': 'test title',
            'upload_date': now(),
            'tags': set(),
            'pack_ini': '''[Group]
Version=1
DisplayTitle=test title
TranslitTitle=test title translit
SortTitle=test title
Series=test
Year=2025
Banner=pack_banner.png
SyncOffset=ITG
'''
        })
        pack = Pack.objects.first()
        self._check_pack(pack, pack_data)
        # correct banner has dimensions 100x70
        # incorrect banner has dimensions 200x200
        self.assertEqual(100, pack.banner.image.width)
    
    def test_pack_ini_do_fallback(self):
        # test that if Pack.ini is present but has missing/broken info
        # (missing displaytitle, broken banner path), we fall back
        # on the default methods for finding this info.
        simfile_pack = open_test_pack('UploadPack_test_pack_ini_do_fallback')
        pack_data = {
            'name': '',
            'author': '',
            'release_date': None,
            'release_date_year_only': False,
            'category': None,
            'tags': [],
            'links': ''
        }

        upload_pack(simfile_pack, pack_data)

        self.assertEqual(1, len(Pack.objects.all()))
        pack_data.update({
            'name': 'UploadPack_test_pack_ini_do_fallback',
            'upload_date': now(),
            'tags': set(),
            'pack_ini': '''[Group]
Version=1
TranslitTitle=test title translit
SortTitle=test title
Series=test
Year=2025
Banner=fake_pack_banner.png
SyncOffset=ITG
'''
        })
        pack = Pack.objects.first()
        self._check_pack(pack, pack_data)
        # correct banner has dimensions 100x70
        self.assertEqual(100, pack.banner.image.width)
    

@patch.object(S3Storage, '_save', in_mem_storage._save)
@patch.object(S3Storage, '_open', in_mem_storage._open)
class PatchPackTestClass(TestCase):
    maxDiff = None

    def setUp(self):
        # disable info logs for processing songs
        logging.disable(logging.INFO)

        # the base pack has:
        # - song1
        #     - hard chart (4 steps)
        #     - challenge chart (8 steps)
        # - song2
        #     - challenge chart (8 steps)
        base_pack = open_test_pack('PatchPack_base')
        self.old_release_date = datetime(2022, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        base_pack_data = {
            'name': 'Test Pack',
            'author': '',
            'release_date': self.old_release_date,
            'release_date_year_only': False,
            'category': None,
            'tags': [],
            'links': ''
        }
        upload_pack(base_pack, base_pack_data)
        self.pack = Pack.objects.get()
        self.pack_id = self.pack.id
        self.song1 = Song.objects.get(title='song1')
        self.song2 = Song.objects.get(title='song2')
        self.song1_chall = self.song1.chart_set.get(difficulty=4)
        self.song2_chall = self.song2.chart_set.get(difficulty=4)
    
    def tearDown(self):
        # restore previous log level
        logging.disable(logging.NOTSET)
    
    def _assert_fields_equal(self, expected, actual, ignore=[]):
        def get_field_values(instance):
            vals = {}
            for field in instance._meta.get_fields():
                if field.one_to_many or field.name in ignore:
                    continue
                vals[field.name] = getattr(instance, field.name)
            return vals
        
        expected_vals = get_field_values(expected)
        actual_vals = get_field_values(actual)
        self.assertEqual(expected_vals, actual_vals)
    
    def _assert_test_patch(self, expected_release_date):
        self.assertEqual(1, Pack.objects.count())
        self.assertEqual(3, Song.objects.count())
        self.assertEqual(4, Chart.objects.count())

        pack = Pack.objects.get()
        song1 = Song.objects.get(title='song1')
        song1_chall = song1.chart_set.get(difficulty=4)
        song2 = Song.objects.get(title='song2')
        song2_chall = song2.chart_set.get(difficulty=4)
        song3 = Song.objects.get(title='song3')
        # assert objs stayed the same
        self._assert_fields_equal(self.pack, pack)
        self._assert_fields_equal(self.song1, song1, ['artist', 'simfile'])
        self._assert_fields_equal(self.song2, song2)
        self._assert_fields_equal(
            self.song1_chall, song1_chall,
            [
                'description', 'analysis', 'objects_count',
                'steps_count', 'combo_count', 'chart_hash'
            ]
        )
        self._assert_fields_equal(self.song2_chall, song2_chall)
        # ensure pack.ini
        self.assertEqual(
            '''[Group]
Version=1
SyncOffset=ITG
''',
            pack.pack_ini
        )
        # ensure song1 and its chart are as we expect
        self.assertEqual('new artist', song1.artist)
        self.assertEqual(2, song1.chart_set.count())
        song1_med = song1.chart_set.get(difficulty=2)
        self.assertEqual(2, song1_med.steps_count)
        self.assertEqual(expected_release_date, song1_med.release_date)
        self.assertEqual(7, song1_chall.steps_count)
        self.assertEqual('new desc', song1_chall.description)
        # ensure song3 is as we expect
        song3_chall = song3.chart_set.get(difficulty=4)
        self.assertEqual(5, song3_chall.steps_count)
        self.assertEqual(expected_release_date, song3.release_date)
        self.assertEqual(expected_release_date, song3_chall.release_date)

    def test_patch(self):
        # test a regular patch
        # - pack.ini added
        # - song1
        #     - updated artist metadata
        #     - medium chart (new) (2 steps)
        #     - no hard chart
        #     - challenge chart (updated) (7 steps)
        #         - new description
        # - song3 (new)
        #     - challenge chart (5 steps)

        # check that:
        # - pack id stays the same
        # - pack.ini is recorded
        # - song1 and song2's fields stay the same (including id)
        #     - excluding song1 artist and simfile
        # - song1's and song2's challenge chart fields stays the same
        #     - excluding song1 challenge chart desc and note counts
        # - song1 artist is updated
        # - song1 has 2 charts, a medium and a challenge
        # - song1 new medium chart inherits release date from song
        # - song1's challenge chart has a new description and no. of steps
        # - song3 is uploaded, with a challenge chart, and with a
        #   release date that is the same as the pack

        patch_sim_pack = open_test_pack('PatchPack_test_patch')
        patch_params = {
            'patch_date': None,
            'results': ProcessPatchResults()
        }
        patch_pack(patch_sim_pack, self.pack, patch_params)
        # print(patch_params['results'].results)

        self._assert_test_patch(self.old_release_date)
    
    def test_patch_with_date(self):
        # test a patch with a release date.
        # - use same patch as test_patch
        # - check that all newly-created songs/charts have the new release date
        patch_sim_pack = open_test_pack('PatchPack_test_patch')
        expected_date = datetime(2023, 7, 7, 12, 0, 0, tzinfo=timezone.utc)
        patch_params = {
            'patch_date': expected_date,
            'results': ProcessPatchResults()
        }
        patch_pack(patch_sim_pack, self.pack, patch_params)
        # print(patch_params['results'].results)

        self._assert_test_patch(expected_date)