"""Unit tests for qualify.py — the 6-check qualification engine."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from datetime import datetime, timedelta, timezone
from qualify import qualify_creator, QualificationResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_channel(
    channel_id="UC" + "A" * 22,
    title="Test Creator",
    country="US",
    subscribers=50_000,
    video_count=200,
    description="",
    topic_cats=None,
):
    return {
        "id": channel_id,
        "snippet": {
            "title": title,
            "country": country,
            "description": description,
        },
        "statistics": {
            "subscriberCount": str(subscribers),
            "videoCount": str(video_count),
        },
        "brandingSettings": {"channel": {}},
        "contentDetails": {"relatedPlaylists": {"uploads": "PL" + "A" * 32}},
        "topicDetails": {"topicCategories": topic_cats or []},
    }


def _make_video(days_ago: int, description: str = "") -> dict:
    return {
        "snippet": {
            "publishedAt": _days_ago(days_ago),
            "description": description,
            "title": "Test video",
        },
        "contentDetails": {"videoId": "ABC123"},
    }


CONTACT_EMAIL = ("email", "creator@example.com", "https://youtube.com/channel/UCtest")
CONTACT_NONE  = ("none", "", "")


class TestRealAndRelevant(unittest.TestCase):
    def test_passes_valid_us_channel(self):
        ch = _make_channel()
        r  = qualify_creator(ch, [_make_video(1)]*8, CONTACT_EMAIL)
        self.assertTrue(r.real_and_relevant)

    def test_fails_unknown_country(self):
        ch = _make_channel(country="IN")
        r  = qualify_creator(ch, [_make_video(1)]*8, CONTACT_EMAIL)
        self.assertFalse(r.real_and_relevant)

    def test_fails_too_few_subs(self):
        ch = _make_channel(subscribers=500)
        r  = qualify_creator(ch, [_make_video(1)]*8, CONTACT_EMAIL)
        self.assertFalse(r.real_and_relevant)

    def test_fails_agency_keyword_in_name(self):
        ch = _make_channel(title="XYZ Talent Agency")
        r  = qualify_creator(ch, [_make_video(1)]*8, CONTACT_EMAIL)
        self.assertFalse(r.real_and_relevant)


class TestActive(unittest.TestCase):
    def test_passes_8_uploads_in_30_days(self):
        ch = _make_channel()
        videos = [_make_video(i) for i in range(1, 9)]
        r = qualify_creator(ch, videos, CONTACT_EMAIL)
        self.assertTrue(r.active)
        self.assertEqual(r.uploads_30d, 8)

    def test_fails_only_old_uploads(self):
        ch = _make_channel()
        videos = [_make_video(40), _make_video(50)]
        r = qualify_creator(ch, videos, CONTACT_EMAIL)
        self.assertFalse(r.active)

    def test_passes_longform_in_60_days(self):
        from qualify import qualify_creator
        ch = _make_channel()
        videos = [_make_video(35), _make_video(45)]  # 2 videos in 60d, not 30d
        video_details = [
            {
                "snippet": {"publishedAt": _days_ago(35)},
                "contentDetails": {"duration": "PT1H30M"},   # 90 min
            },
            {
                "snippet": {"publishedAt": _days_ago(45)},
                "contentDetails": {"duration": "PT45M"},     # 45 min
            },
        ]
        r = qualify_creator(ch, videos, CONTACT_EMAIL, video_details=video_details)
        self.assertTrue(r.active)


class TestCommercial(unittest.TestCase):
    def test_passes_sponsor_keyword(self):
        ch = _make_channel(description="This video is sponsored by Acme Corp. Use code CREATOR for 20% off.")
        videos = [_make_video(i) for i in range(1, 9)]
        r = qualify_creator(ch, videos, CONTACT_EMAIL)
        self.assertTrue(r.commercial)

    def test_passes_established_channel_heuristic(self):
        ch = _make_channel(subscribers=15_000, video_count=100, description="Welcome to my channel!")
        videos = [_make_video(i) for i in range(1, 9)]
        r = qualify_creator(ch, videos, CONTACT_EMAIL)
        self.assertTrue(r.commercial)


class TestNeedsIncubrix(unittest.TestCase):
    def test_passes_workflow_keyword(self):
        ch = _make_channel(description="I struggle with my content workflow and repurposing videos.")
        videos = [_make_video(i) for i in range(1, 9)]
        r = qualify_creator(ch, videos, CONTACT_EMAIL)
        self.assertTrue(r.needs_incubrix)

    def test_passes_high_upload_frequency(self):
        ch = _make_channel(description="")
        # 8 uploads in 7 days = ~34/month → triggers high_upload_frequency proxy
        videos = [_make_video(i) for i in range(1, 9)]
        r = qualify_creator(ch, videos, CONTACT_EMAIL)
        self.assertTrue(r.needs_incubrix)


class TestContactable(unittest.TestCase):
    def test_passes_email_contact(self):
        ch = _make_channel()
        videos = [_make_video(i) for i in range(1, 9)]
        r = qualify_creator(ch, videos, CONTACT_EMAIL)
        self.assertTrue(r.contactable)

    def test_fails_no_contact(self):
        ch = _make_channel()
        videos = [_make_video(i) for i in range(1, 9)]
        r = qualify_creator(ch, videos, CONTACT_NONE)
        self.assertFalse(r.contactable)


class TestFullQualification(unittest.TestCase):
    def test_fully_qualified_creator(self):
        ch = _make_channel(
            description=(
                "Sponsored by Acme. Use code CREATOR10. "
                "I repurpose all my videos into newsletters and shorts. "
                "Business: creator@domain.com"
            )
        )
        videos = [_make_video(i) for i in range(1, 9)]
        r = qualify_creator(ch, videos, CONTACT_EMAIL)
        self.assertTrue(r.qualified, f"Expected qualified but got: {r.disqualify_reason}")

    def test_disqualified_no_contact(self):
        ch = _make_channel(description="Sponsored by Acme.")
        videos = [_make_video(i) for i in range(1, 9)]
        r = qualify_creator(ch, videos, CONTACT_NONE)
        self.assertFalse(r.qualified)
        self.assertIn("contactable", r.disqualify_reason)


if __name__ == "__main__":
    unittest.main()
