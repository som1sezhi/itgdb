import logging
from datetime import datetime, timezone
from unittest.mock import patch
from django.test import TestCase
from django.utils.timezone import now
from django.core.files.storage.memory import InMemoryStorage
from simfile.dir import SimfilePack
from storages.backends.s3 import S3Storage

from ..models import Tag, PackCategory, Pack, ImageFile, Song
from ..utils.uploads import upload_pack
from ._common import open_test_pack

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
        # - check that images are uploaded correctly
        #   - pack and song2 banner image should be the same object
        #   - pack/song2 banner is 100x70, song1 banner is 100x100
        simfile_pack = open_test_pack('UploadPack_test_upload')
        pack_data = {
            'name': 'Test Pack',
            'author': 'Author 1, Author 2',
            'release_date': datetime(2022, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
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
            'tags': set(self.tags)
        })
        pack = Pack.objects.first()
        self._check_pack(pack, pack_data)
        # check songs and charts
        self.assertEqual(2, len(pack.song_set.all()))
        song1 = pack.song_set.get(title='song1')
        song2 = pack.song_set.get(title='song2')
        self.assertEqual(1, len(song1.chart_set.all()))
        self.assertEqual(1, len(song2.chart_set.all()))
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
        # - other fields should be empty/null
        simfile_pack = open_test_pack('UploadPack_test_minimal_data')
        pack_data = {
            'name': '',
            'author': '',
            'release_date': None,
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
            'banner': None
        })
        pack = Pack.objects.first()
        self._check_pack(pack, pack_data)