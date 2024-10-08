import os
from django.test import SimpleTestCase
import simfile

from ..utils.charts import get_assets, get_song_lengths
from ..utils.analysis import SongAnalyzer
from ._common import TEST_BASE_DIR, open_test_simfile_dir


class GetAssetsTestClass(SimpleTestCase):
    maxDiff = None
    
    def _do_test(self, test_name, expected):
        test_dir_name = 'GetAssets_' + test_name
        sim_dir = open_test_simfile_dir(test_dir_name)
        actual = get_assets(sim_dir)

        # convert expected dict values from relative to absolute paths
        expected = {
            prop: os.path.normpath(os.path.join(
                TEST_BASE_DIR, 'simfile_dirs', test_dir_name, filename
            )) if filename else filename
            for prop, filename in expected.items()
        }
        self.assertEqual(expected, actual)

    def test_find_via_simfile(self):
        # test that assets are found when specified in the simfile
        # - video files are supported if specified explicitly
        # - files in subdirectories are supported
        self._do_test(
            'test_find_via_simfile',
            {
                'MUSIC': 'click.ogg',
                'BANNER': 'image1.avi',
                'BACKGROUND': 'image2.png',
                'CDTITLE': os.path.join('subdir', 'image3.png'),
                'JACKET': None,
                'CDIMAGE': None,
                'DISC': None
            }
        )

    def test_find_via_filename_hints(self):
        # test that assets can be found via filename hints
        self._do_test(
            'test_find_via_filename_hints',
            {
                'MUSIC': 'click.ogg',
                'BANNER': 'click bn.png',
                'BACKGROUND': 'click bg.png',
                'CDTITLE': 'click cdtitle.png',
                'JACKET': None,
                'CDIMAGE': None,
                'DISC': None
            }
        )

    def test_find_via_image_sizes(self):
        # test that assets can be found via image dimensions
        self._do_test(
            'test_find_via_image_sizes',
            {
                'MUSIC': 'click.ogg',
                'BANNER': 'image0.png',
                'BACKGROUND': 'image2.png',
                'CDTITLE': 'image1.png',
                'JACKET': None,
                'CDIMAGE': None,
                'DISC': None
            }
        )

    def test_simfile_spec_assets_can_be_reused(self):
        # test that if a file is found via simfile specification, it can still
        # be reused for other properties via filename hints
        self._do_test(
            'test_simfile_spec_assets_can_be_reused',
            {
                'MUSIC': 'click.ogg',
                'BANNER': 'img1 bkgd and bn.png',
                'BACKGROUND': 'img1 bkgd and bn.png',
                'CDTITLE': None,
                'JACKET': None,
                'CDIMAGE': None,
                'DISC': None
            }
        )
    
    def test_image_sizes_cannot_reuse(self):
        # test that if a file is found via simfile specification or filename
        # hints, it cannot be reused for other properties via image size hints.
        # Also tests that when selecting assets via filename hints, the first
        # eligible file alphabetically is used.
        self._do_test(
            'test_image_sizes_cannot_reuse',
            {
                'MUSIC': 'click.ogg',
                'BANNER': 'img2 bn.png',
                'BACKGROUND': 'img1.png',
                'CDTITLE': 'img3 not bn.png',
                'JACKET': None,
                'CDIMAGE': None,
                'DISC': None
            }
        )
    
    def test_case_insensitive(self):
        # test that simfile-specified filenames are case-insensitive.
        self._do_test(
            'test_case_insensitive',
            {
                'MUSIC': 'click.ogg',
                'BANNER': 'imaGe1.avi',
                'BACKGROUND': 'imAge2.png',
                'CDTITLE': os.path.join('subDir', 'image3.png'),
                'JACKET': None,
                'CDIMAGE': None,
                'DISC': None
            }
        )
    
    def test_outside_simfile_dir(self):
        # test that assets can be found outside the simfile directory
        # as long as it is still in the pack directory.
        # also ensures case-insensitivity is supported outside of the
        # simfile directory
        # here, 'simfile_dirs' will act as the pack directory
        self._do_test(
            'test_outside_simfile_dir',
            {
                'MUSIC': 'click.ogg',
                'BANNER': os.path.join(
                    '..', 'GetAssets_test_outside_simfile_dir_GFX', 'bn.png'
                ),
                'BACKGROUND': None,
                'CDTITLE': None,
                'JACKET': None,
                'CDIMAGE': None,
                'DISC': None
            }
        )

    def test_find_fail(self):
        # test that various failure cases are handled:
        # - file does not exist (bg)
        # - file path leads to a directory (banner)
        # - path leads outside the pack directory (cdtitle)
        # - if simfile-specified path fails, we can find the asset later using
        #   other methods (bg, cdtitle)
        # - malformed files with the right extension are still found and
        #   accepted (bg)
        self._do_test(
            'test_find_fail',
            {
                'MUSIC': 'click.ogg',
                'BANNER': None,
                'BACKGROUND': 'image2 malformed bg.png',
                'CDTITLE': 'image4.png',
                'JACKET': None,
                'CDIMAGE': None,
                'DISC': None
            }
        )


class GetSongLengthsTestClass(SimpleTestCase):
    def _do_test(self, test_name, expected):
        test_dir_path = os.path.join(
            TEST_BASE_DIR, 'simfile_dirs', 'GetSongLengths_' + test_name
        )
        music_path = os.path.join(test_dir_path, 'click16.ogg')
        sim_path = os.path.join(test_dir_path, 'click16.ssc')
        sim = simfile.open(sim_path)
        actual = get_song_lengths(music_path, SongAnalyzer(sim))
        self.assertEqual(expected, actual)

    def test_longer_song(self):
        # test that the correct values are returned when the song is longer
        # than the chart
        self._do_test('test_longer_song', (8, 4))
    
    def test_longer_chart(self):
        # test that the correct values are returned when a non-edit chart is
        # longer than the song (even if the chart's playstyle is not ITG-based)
        self._do_test('test_longer_chart', (30, 30))
    
    def test_only_edit(self):
        # test that the correct values are returned when an edit chart is
        # longer than the song and the edit chart is the only chart in the
        # simfile
        self._do_test('test_only_edit', (38, 38))
    
    def test_lastsecondhint(self):
        # test that the correct values are returned when the song length is
        # determined by LASTSECONDHINT
        self._do_test('test_lastsecondhint', (100, 100))
    
    def test_fail(self):
        # test that the function returns None if the music file cannot be
        # opened
        self._do_test('test_fail', None)