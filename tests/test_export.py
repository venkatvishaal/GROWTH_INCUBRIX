"""Unit tests for export.py — LeadRecord and CSV export."""

import sys
import os
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
import pandas as pd

from export import LeadRecord, build_lead_record, export_to_csv, load_leads_df
from qualify import QualificationResult
import config


def _make_result(country="US", subs=50_000) -> QualificationResult:
    r = QualificationResult(channel_id="UC" + "A" * 22, channel_name="Test Creator")
    r.real_and_relevant = r.active = r.commercial = True
    r.needs_incubrix = r.contactable = r.complete = True
    r.country = country
    r.subscriber_count = subs
    r.avg_uploads_per_month = 8.0
    r.last_upload_date = "2026-08-30"
    r.content_category = "Education"
    r.commercial_evidence = "Sponsored by Acme"
    r.commercial_evidence_url = "https://youtube.com/test"
    r.incubrix_need_evidence = "Signals: workflow, captions"
    r.contact_type = "email"
    r.contact_value = "creator@example.com"
    r.contact_url = "https://youtube.com/test"
    r.qualified = True
    return r


def _make_channel(channel_id="UC" + "A" * 22) -> dict:
    return {
        "id": channel_id,
        "snippet": {"title": "Test Creator"},
        "brandingSettings": {"channel": {"customUrl": "@testcreator"}},
    }


class TestBuildLeadRecord(unittest.TestCase):
    def test_builds_correctly(self):
        result  = _make_result()
        channel = _make_channel()
        record  = build_lead_record(channel, result, score=8, priority="A")
        self.assertEqual(record.priority, "A")
        self.assertEqual(record.country, "US")
        self.assertEqual(record.contact_type, "email")
        self.assertIn("youtube.com/@testcreator", record.channel_url)

    def test_score_set(self):
        result  = _make_result()
        channel = _make_channel()
        record  = build_lead_record(channel, result, score=7, priority="A")
        self.assertEqual(record.score, 7)


class TestExportToCSV(unittest.TestCase):
    def test_exports_valid_utf8_csv(self):
        result  = _make_result()
        channel = _make_channel()
        record  = build_lead_record(channel, result, score=8, priority="A")

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            count = export_to_csv([record], path, append=False)
            self.assertEqual(count, 1)

            df = pd.read_csv(path, encoding="utf-8")
            self.assertEqual(len(df), 1)
            # 'score' column must NOT be in the CSV
            self.assertNotIn("score", df.columns)
            # All expected columns must be present
            for col in config.CSV_COLUMNS:
                self.assertIn(col, df.columns, f"Missing column: {col}")
        finally:
            os.unlink(path)

    def test_append_deduplicates(self):
        result1 = _make_result(country="US")
        result2 = _make_result(country="GB")
        ch1     = _make_channel("UC" + "A" * 22)
        ch2     = _make_channel("UC" + "B" * 22)
        rec1    = build_lead_record(ch1, result1, score=8, priority="A")
        rec2    = build_lead_record(ch2, result2, score=7, priority="B")

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            export_to_csv([rec1], path, append=False)
            # Append rec1 again (should be deduplicated) + rec2
            export_to_csv([rec1, rec2], path, append=True)
            df = pd.read_csv(path)
            self.assertEqual(len(df), 2)   # rec1 deduplicated; rec2 added
        finally:
            os.unlink(path)


class TestLoadLeadsDF(unittest.TestCase):
    def test_returns_empty_df_when_missing(self):
        df = load_leads_df("/nonexistent/path.csv")
        self.assertTrue(df.empty)
        for col in config.CSV_COLUMNS:
            self.assertIn(col, df.columns)


if __name__ == "__main__":
    unittest.main()
