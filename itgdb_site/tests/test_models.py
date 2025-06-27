from django.test import SimpleTestCase

from ..models import Chart

class ChartTestClass(SimpleTestCase):
    def test_difficulty_str_to_int_normal(self):
        # test that difficulty can be determined via the difficulty field.
        # ensure it is case insensitive and that whitespace is stripped.
        self.assertEqual(
            Chart.DIFFICULTY_MAPPING['challenge'],
            Chart.difficulty_str_to_int('challenge', 'easy', 1)
        )
        self.assertEqual(
            Chart.DIFFICULTY_MAPPING['medium'],
            Chart.difficulty_str_to_int('   Medium   ', 'easy', 1)
        )
    
    def test_difficulty_str_to_int_via_desc(self):
        # test that difficulty can be determined via the description
        # if the difficulty field is invalid.
        # ensure it is case insensitive.
        # (we don't have to strip whitespace from the description, since
        # it should already be stripped by the time it is passed in.)
        self.assertEqual(
            Chart.DIFFICULTY_MAPPING['easy'],
            Chart.difficulty_str_to_int('', 'easy', 1)
        )
        self.assertEqual(
            Chart.DIFFICULTY_MAPPING['medium'],
            Chart.difficulty_str_to_int('invalid', 'MediuM', 1)
        )
    
    def test_difficulty_str_to_int_via_meter(self):
        # test that difficulty can be determined via the meter
        # if the difficulty and description fields are invalid.
        mappings = [
            # note: due to how the logic works, an invalid meter
            # puts the chart in the easy slot. this indeed seems to match
            # SM's behavior.
            (-1, 'easy'),
            (1, 'beginner'),
            (2, 'easy'),
            (3, 'easy'),
            (4, 'medium'),
            (6, 'medium'),
            (7, 'hard')
        ]
        for meter, expected in mappings:
            self.assertEqual(
                Chart.DIFFICULTY_MAPPING[expected],
                Chart.difficulty_str_to_int('asdf', 'asdf', meter)
            )
