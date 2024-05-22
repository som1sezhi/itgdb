from typing import Tuple
import os
from django.test import TestCase
import simfile
from simfile.types import Simfile, Chart

from ..utils.charts import get_counts

SIMS_BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sims')

def _open_test_simfile(name: str) -> Simfile:
    path = os.path.join(SIMS_BASE_DIR, name)
    return simfile.open(path)
    
def _open_test_chart(name: str) -> Tuple[Simfile, Chart]:
    sim = _open_test_simfile(name)
    return sim, sim.charts[0]


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
            'objects': 19,
            'steps': 7,
            'combo': 7,
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