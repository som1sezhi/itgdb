from django.test import SimpleTestCase

from ..utils.analysis import SongAnalyzer
from ._common import open_test_chart

class GetCountsTestClass(SimpleTestCase):
    def _do_test(self, test_name, expected):
        sim, chart = open_test_chart(f'GetCounts_{test_name}.ssc')
        chart_analyzer = SongAnalyzer(sim).get_chart_analyzer(chart)
        actual = chart_analyzer.get_counts()
        self.assertEqual(expected, actual)

    def test_counts(self):
        # desired behaviors:
        # - any simultaneous note chord is a step/jump/hand
        #   - note types can be mixed, e.g. lift+tap chord
        # - 2+ arrows during a hold/roll is a hand and jump
        # - 1 arrow during 2+ holds/rolls is a hand, but not a jump
        # - simultaneous holds/rolls are counted separately
        # - mines/lifts/fakes are counted separately
        # - fakes are not included in any counts besides the fakes count
        self._do_test(
            'test_counts',
            {
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
        )
    
    def test_unhittable_notes(self):
        # test that fake regions and warps are skipped over when counting
        # notes (except for 'objects'/'fakes')
        self._do_test(
            'test_unhittable_notes',
            {
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
        )
    
    def test_weird_fake_regions(self):
        # test for correct handling of fake region edge cases:
        # - out-of-order fake regions in file should act the same as in-order
        # - fake regions with negative beat should work properly
        # - overlapping fake region should "cut off" a previous fake region
        # - regions with too-small/zero/negative length should act nonexistent
        self._do_test(
            'test_weird_fake_regions',
            {
                'objects': 11,
                'steps': 6,
                'combo': 6,
                'jumps': 0,
                'mines': 0,
                'hands': 0,
                'holds': 0,
                'rolls': 0,
                'lifts': 0,
                'fakes': 0
            }
        )