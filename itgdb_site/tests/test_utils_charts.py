from typing import Tuple
import os
from django.test import TestCase
import simfile
from simfile.types import Simfile, Chart
from simfile.dir import SimfileDirectory

from ..utils.charts import get_counts, get_assets

TEST_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _open_test_simfile(name: str) -> Simfile:
    path = os.path.join(TEST_BASE_DIR, 'sims', name)
    return simfile.open(path)
    
def _open_test_chart(name: str) -> Tuple[Simfile, Chart]:
    sim = _open_test_simfile(name)
    return sim, sim.charts[0]

def _open_test_simfile_dir(name: str) -> SimfileDirectory:
    path = os.path.join(TEST_BASE_DIR, 'simfile_dirs', name)
    return SimfileDirectory(path)


class GetCountsTestClass(TestCase):
    def test_counts(self):
        # desired behaviors:
        # - any simultaneous note chord is a step/jump/hand
        #   - note types can be mixed, e.g. lift+tap chord
        # - 2+ arrows during a hold/roll is a hand and jump
        # - 1 arrow during 2+ holds/rolls is a hand, but not a jump
        # - simultaneous holds/rolls are counted separately
        # - mines/lifts/fakes are counted separately
        # - fakes are not included in any counts besides the fakes count
        sim, chart = _open_test_chart('GetCounts_test_counts.ssc')
        expected = {
            'objects': 84,
            'steps': 45,
            'combo': 73,
            'jumps': 22,
            'mines': 8,
            'hands': 13,
            'holds': 14,
            'rolls': 10,
            'lifts': 7,
            'fakes': 3
        }
        actual = get_counts(sim, chart)
        self.assertEqual(expected, actual)
    
    def test_unhittable_notes(self):
        # test that fake regions and warps are skipped over when counting
        # notes (except for 'objects'/'fakes')
        sim, chart = _open_test_chart('GetCounts_test_unhittable_notes.ssc')
        expected = {
            'objects': 26,
            'steps': 11,
            'combo': 11,
            'jumps': 0,
            'mines': 0,
            'hands': 0,
            'holds': 4,
            'rolls': 2,
            'lifts': 0,
            'fakes': 2
        }
        actual = get_counts(sim, chart)
        self.assertEqual(expected, actual)


class GetAssetsTestClass(TestCase):
    @staticmethod
    def _convert_assets_dict_to_abs_path(test_dir_name, assets):
        return {
            prop: os.path.join(
                TEST_BASE_DIR, 'simfile_dirs', test_dir_name, filename
            ) if filename else filename
            for prop, filename in assets.items()
        }

    def test_find_via_simfile(self):
        # test that assets are found when specified in the simfile
        # - video files are supported if specified explicitly
        # - files in subdirectories are supported
        test_dir_name = 'GetAssets_test_find_via_simfile'
        sim_dir = _open_test_simfile_dir(test_dir_name)
        actual = get_assets(sim_dir)
        expected = GetAssetsTestClass._convert_assets_dict_to_abs_path(
            test_dir_name,
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
        self.assertEqual(expected, actual)

    def test_find_via_filename_hints(self):
        # test that assets can be found via filename hints
        test_dir_name = 'GetAssets_test_find_via_filename_hints'
        sim_dir = _open_test_simfile_dir(test_dir_name)
        actual = get_assets(sim_dir)
        expected = GetAssetsTestClass._convert_assets_dict_to_abs_path(
            test_dir_name,
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
        self.assertEqual(expected, actual)

    def test_find_via_image_sizes(self):
        # test that assets can be found via image dimensions
        test_dir_name = 'GetAssets_test_find_via_image_sizes'
        sim_dir = _open_test_simfile_dir(test_dir_name)
        actual = get_assets(sim_dir)
        expected = GetAssetsTestClass._convert_assets_dict_to_abs_path(
            test_dir_name,
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
        self.assertEqual(expected, actual)

    def test_find_via_multiple_methods(self):
        # test how different asset-finding methods interact:
        # - if a file is found via simfile specification, it can still found
        #   later on by other methods for other properties
        # - if a file is found via filename hints, it cannot be reused later
        #   on when finding via image sizes
        #
        # - banner is found via filename hints
        # - background is found via simfile specification
        # - cdtitle is found via image size hints
        test_dir_name = 'GetAssets_test_find_via_multiple_methods'
        sim_dir = _open_test_simfile_dir(test_dir_name)
        actual = get_assets(sim_dir)
        expected = GetAssetsTestClass._convert_assets_dict_to_abs_path(
            test_dir_name,
            {
                'MUSIC': 'click.ogg',
                'BANNER': 'img1 bkgd and bn.png',
                'BACKGROUND': 'img1 bkgd and bn.png',
                'CDTITLE': 'img2 not actually bn.png',
                'JACKET': None,
                'CDIMAGE': None,
                'DISC': None
            }
        )
        self.assertEqual(expected, actual)

    def test_find_fail(self):
        # test that various failure cases are handled:
        # - file does not exist (bg)
        # - file path leads to a directory (banner)
        # - path leads outside the pack directory (cdtitle)
        # - if simfile-specified path fails, we can find the asset later using
        #   other methods (bg, cdtitle)
        # - malformed files with the right extension are still found and
        #   accepted (bg)
        test_dir_name = 'GetAssets_test_find_fail'
        sim_dir = _open_test_simfile_dir(test_dir_name)
        actual = get_assets(sim_dir)
        expected = GetAssetsTestClass._convert_assets_dict_to_abs_path(
            test_dir_name,
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
        self.assertEqual(expected, actual)