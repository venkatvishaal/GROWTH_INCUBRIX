"""Unit tests for deduplicate.py."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from deduplicate import ChannelDeduplicator, _normalise_name


class TestNormaliseName(unittest.TestCase):
    def test_strips_suffix(self):
        self.assertEqual(_normalise_name("TechTalks Official"), "techtalks")
        self.assertEqual(_normalise_name("Finance YouTube"), "finance")

    def test_removes_special_chars(self):
        self.assertEqual(_normalise_name("John's Podcast!"), "johns podcast")

    def test_lowercases(self):
        self.assertEqual(_normalise_name("GREAT CREATOR"), "great creator")


class TestChannelDeduplicator(unittest.TestCase):
    def setUp(self):
        self.dedup = ChannelDeduplicator(fuzzy_threshold=88)

    def test_exact_id_duplicate(self):
        self.dedup.add("UCabc123", "Creator One")
        self.assertTrue(self.dedup.is_duplicate("UCabc123", "Anything"))

    def test_new_id_not_duplicate(self):
        self.dedup.add("UCabc123", "Creator One")
        self.assertFalse(self.dedup.is_duplicate("UCxyz789", "Creator Two"))

    def test_fuzzy_name_duplicate(self):
        self.dedup.add("UCabc123", "Finance With John")
        # Very similar name — should be caught by fuzzy match
        self.assertTrue(self.dedup.is_duplicate("UCnew999", "Finance with John Official"))

    def test_different_name_not_duplicate(self):
        self.dedup.add("UCabc123", "Cooking Channel")
        self.assertFalse(self.dedup.is_duplicate("UCnew999", "Tech Reviews Daily"))

    def test_url_duplicate(self):
        self.dedup.add("UCabc123", "Creator A", "https://youtube.com/channel/UCabc123")
        self.assertTrue(self.dedup.is_duplicate("UCdiff", "Creator A",
                                                "https://youtube.com/channel/UCabc123/"))

    def test_add_and_check_increments_count(self):
        self.dedup.add("UCabc123", "Creator X")
        result = self.dedup.add_and_check("UCabc123", "Creator X")
        self.assertTrue(result)
        self.assertEqual(self.dedup.duplicate_count, 1)

    def test_load_existing(self):
        dedup = ChannelDeduplicator()
        dedup.load_existing(["UCold1", "UCold2"], ["Old Creator", "Another"], ["", ""])
        self.assertTrue(dedup.is_duplicate("UCold1", "Irrelevant"))
        self.assertFalse(dedup.is_duplicate("UCnew9", "Brand New Creator"))


if __name__ == "__main__":
    unittest.main()
