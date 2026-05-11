import unittest

from input import total_positive


class TotalPositiveTests(unittest.TestCase):
    def test_total_positive_filters_negative_values(self):
        self.assertEqual(total_positive([1, -2, 3, 0, 5]), 9)

    def test_total_positive_empty_input(self):
        self.assertEqual(total_positive([]), 0)


if __name__ == "__main__":
    unittest.main()
