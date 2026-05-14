"""
Tests for the scoring and brief logic. Run with: python tests/test_pipeline.py
"""

import json
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

from icp_filter import score_filing, stage_from_raise, rank_filings
from brief_generator import generate_brief, generate_outreach_email


class TestStageMapping(unittest.TestCase):
    def test_friends_and_family(self):
        self.assertEqual(stage_from_raise(100_000), "friends_and_family")

    def test_pre_seed(self):
        self.assertEqual(stage_from_raise(1_000_000), "pre_seed")

    def test_seed(self):
        self.assertEqual(stage_from_raise(3_500_000), "seed")

    def test_series_a(self):
        self.assertEqual(stage_from_raise(12_000_000), "series_a")

    def test_growth(self):
        self.assertEqual(stage_from_raise(50_000_000), "growth")

    def test_missing(self):
        self.assertIsNone(stage_from_raise(None))


class TestScoring(unittest.TestCase):
    def test_investment_fund_disqualified(self):
        f = {
            "industry": "Pooled Investment Fund Interests",
            "total_offering": "5000000",
            "total_sold": "3000000",
            "issuer_state": "CA",
        }
        result = score_filing(f)
        self.assertEqual(result["score"], 0)
        self.assertTrue(any("Investment fund" in d or "Industry" in d for d in result["disqualifiers"]))

    def test_too_small_disqualified(self):
        f = {
            "industry": "Technology",
            "total_offering": "50000",
            "total_sold": "50000",
            "issuer_state": "CA",
        }
        result = score_filing(f)
        self.assertEqual(result["score"], 0)

    def test_too_large_disqualified(self):
        f = {
            "industry": "Technology",
            "total_offering": "100000000",
            "total_sold": "60000000",
            "issuer_state": "CA",
        }
        result = score_filing(f)
        self.assertEqual(result["score"], 0)

    def test_high_fit_seed_scores_high(self):
        f = {
            "industry": "Technology",
            "total_offering": "3500000",
            "total_sold": "2800000",
            "issuer_state": "CA",
            "year_of_inc": "2024",
            "related_persons": [{"name": "A", "relationships": ["Executive Officer"]}],
        }
        result = score_filing(f)
        self.assertGreaterEqual(result["score"], 80)
        self.assertEqual(result["stage"], "seed")

    def test_non_us_disqualified(self):
        f = {
            "industry": "Technology",
            "total_offering": "3000000",
            "total_sold": "2000000",
            "issuer_state": "UNITED KINGDOM",
        }
        result = score_filing(f)
        self.assertEqual(result["score"], 0)

    def test_doubt_window_signal(self):
        """Round still open (low % closed) should add the doubt-window points."""
        open_round = {
            "industry": "Technology",
            "total_offering": "3000000",
            "total_sold": "1000000",  # only 33% closed
            "issuer_state": "CA",
        }
        closed_round = {
            "industry": "Technology",
            "total_offering": "3000000",
            "total_sold": "3000000",  # fully closed
            "issuer_state": "CA",
        }
        open_score = score_filing(open_round)["score"]
        closed_score = score_filing(closed_round)["score"]
        self.assertGreater(open_score, closed_score)


class TestRanking(unittest.TestCase):
    def test_rank_descending(self):
        filings = [
            {"industry": "Technology", "total_offering": "3500000",
             "total_sold": "2800000", "issuer_state": "CA"},
            {"industry": "Pooled Investment Fund Interests",
             "total_offering": "50000000", "total_sold": "30000000",
             "issuer_state": "DE"},
        ]
        ranked = rank_filings(filings)
        self.assertGreater(ranked[0]["_zeutara"]["score"], ranked[1]["_zeutara"]["score"])


class TestBrief(unittest.TestCase):
    def test_brief_contains_key_sections(self):
        filing = {
            "issuer_name": "Test Co",
            "issuer_state": "CA",
            "issuer_city": "SF",
            "industry": "Technology",
            "total_offering": "3500000",
            "total_sold": "2800000",
            "year_of_inc": "2024",
            "related_persons": [{"name": "Jane Doe", "relationships": ["Executive Officer"]}],
        }
        filing["_zeutara"] = score_filing(filing)
        brief = generate_brief(filing)
        self.assertIn("Test Co", brief)
        self.assertIn("Seed", brief)
        self.assertIn("90 days", brief)
        self.assertIn("Jane Doe", brief)

    def test_email_generated(self):
        filing = {
            "issuer_name": "Test Co",
            "issuer_state": "CA",
            "industry": "Technology",
            "total_offering": "3500000",
            "total_sold": "2800000",
            "year_of_inc": "2024",
            "related_persons": [{"name": "Jane Doe", "relationships": ["Executive Officer"]}],
        }
        filing["_zeutara"] = score_filing(filing)
        email = generate_outreach_email(filing)
        self.assertIn("Subject:", email)
        self.assertIn("Jane", email)
        self.assertIn("Zeutara", email)


if __name__ == "__main__":
    unittest.main(verbosity=2)
