"""
6-check creator qualification engine.

A creator is QUALIFIED only when every single check below passes:
  1. real_and_relevant  — real creator, approved country, stable channel ID
  2. active             — 8+ uploads in 30d OR 2+ long-form in 60d
  3. commercial         — public evidence of sponsorship / product / affiliate
  4. needs_incubrix     — workflow pain signal (editing, captions, backlog, etc.)
  5. contactable        — verified public business contact (not guessed)
  6. complete           — all required fields populated
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import config
from discover import iso_to_seconds

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class QualificationResult:
    channel_id:   str
    channel_name: str

    # The 6 checks
    real_and_relevant: bool = False
    active:            bool = False
    commercial:        bool = False
    needs_incubrix:    bool = False
    contactable:       bool = False
    complete:          bool = False

    # Evidence & metrics
    country:               str   = ""
    subscriber_count:      int   = 0
    uploads_30d:           int   = 0
    longform_60d:          int   = 0
    last_upload_date:      str   = ""
    avg_uploads_per_month: float = 0.0
    content_category:      str   = ""

    commercial_evidence:     str = ""
    commercial_evidence_url: str = ""
    incubrix_need_evidence:  str = ""

    contact_type:  str = ""
    contact_value: str = ""
    contact_url:   str = ""

    # Result
    qualified:         bool = False
    disqualify_reason: str  = ""

    def evaluate(self) -> None:
        """Set ``qualified`` based on all 6 checks and record any failures."""
        self.qualified = all([
            self.real_and_relevant, self.active, self.commercial,
            self.needs_incubrix, self.contactable, self.complete,
        ])
        if not self.qualified:
            failed = [
                name for name, val in [
                    ("real_and_relevant", self.real_and_relevant),
                    ("active",            self.active),
                    ("commercial",        self.commercial),
                    ("needs_incubrix",    self.needs_incubrix),
                    ("contactable",       self.contactable),
                    ("complete",          self.complete),
                ]
                if not val
            ]
            self.disqualify_reason = ", ".join(failed)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_keywords(text: str, keywords: list[str]) -> list[str]:
    """Return matching keywords found in text (case-insensitive)."""
    tl = text.lower()
    return [kw for kw in keywords if kw.lower() in tl]


_CATEGORY_TOPIC_MAP = {
    "Finance":   ["Economy", "Finance", "Business_Economics", "Investment"],
    "Tech":      ["Technology", "Computers", "Electronics"],
    "Fitness":   ["Fitness", "Sport", "Physical_fitness", "Health"],
    "Education": ["Education", "Howto", "How-to"],
    "Business":  ["Business", "Entrepreneurship", "Marketing"],
    "Lifestyle": ["Lifestyle", "People_&_Blogs", "Fashion", "Food"],
}

_CATEGORY_DESC_MAP = {
    "Finance":   ["finance", "money", "invest", "stock", "wealth", "budget", "saving"],
    "Tech":      ["tech", "software", "code", "programming", "ai", "developer", "gadget"],
    "Fitness":   ["fitness", "workout", "health", "nutrition", "yoga", "gym", "weight"],
    "Education": ["education", "learn", "teach", "tutorial", "course", "study", "how to"],
    "Business":  ["business", "entrepreneur", "startup", "marketing", "ecommerce", "sales"],
}


def _infer_category(topic_categories: list[str], description: str) -> str:
    """Infer content category from YouTube topic categories, then description keywords."""
    for cat, topics in _CATEGORY_TOPIC_MAP.items():
        if any(t in url for url in topic_categories for t in topics):
            return cat
    desc_l = description.lower()
    for cat, words in _CATEGORY_DESC_MAP.items():
        if any(w in desc_l for w in words):
            return cat
    return "Lifestyle"


# ── Main qualification function ───────────────────────────────────────────────

def qualify_creator(
    channel_data:  dict,
    recent_videos: list[dict],
    contact:       tuple[str, str, str],
    video_details: Optional[list[dict]] = None,
) -> QualificationResult:
    """
    Run all 6 qualification checks on a creator channel.

    Args:
        channel_data:  ``channels.list`` API response item.
        recent_videos: ``playlistItems.list`` response items (most-recent 50).
        contact:       (contact_type, contact_value, contact_url) from ``discover.extract_contact``.
        video_details: Optional ``videos.list`` items for ISO-duration long-form check.

    Returns:
        QualificationResult with ``.qualified`` set and evidence populated.
    """
    snippet  = channel_data.get("snippet", {})
    stats    = channel_data.get("statistics", {})
    topics   = channel_data.get("topicDetails", {}).get("topicCategories", [])
    channel_id   = channel_data.get("id", "")
    channel_name = snippet.get("title", "")
    description  = snippet.get("description", "") or ""
    country      = snippet.get("country", "")

    result = QualificationResult(channel_id=channel_id, channel_name=channel_name)
    result.contact_type, result.contact_value, result.contact_url = contact
    result.country = country

    # ── CHECK 1: Real and relevant ────────────────────────────────────────────
    sub_count   = int(stats.get("subscriberCount", 0))
    video_count = int(stats.get("videoCount", 0))
    result.subscriber_count = sub_count

    has_valid_id      = bool(channel_id and channel_id.startswith("UC") and len(channel_id) == 24)
    in_good_country   = country in config.APPROVED_COUNTRIES
    subs_ok           = config.MIN_SUBSCRIBERS <= sub_count <= config.MAX_SUBSCRIBERS
    name_desc_combined = (channel_name + " " + description[:300]).lower()
    not_agency        = not any(kw in name_desc_combined
                                for kw in config.AGENCY_EXCLUSION_KEYWORDS)

    result.real_and_relevant = has_valid_id and in_good_country and subs_ok and not_agency

    # ── CHECK 2: Active ───────────────────────────────────────────────────────
    now         = datetime.now(timezone.utc)
    cutoff_30d  = now - timedelta(days=30)
    cutoff_60d  = now - timedelta(days=60)

    uploads_30d = 0
    uploads_60d = 0
    last_upload_date = ""
    dates_seen: list[datetime] = []

    for item in recent_videos:
        pub_str = item.get("snippet", {}).get("publishedAt", "")
        if not pub_str:
            continue
        try:
            pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            dates_seen.append(pub_dt)
            if not last_upload_date:
                last_upload_date = pub_str[:10]
            if pub_dt >= cutoff_30d:
                uploads_30d += 1
            if pub_dt >= cutoff_60d:
                uploads_60d += 1
        except ValueError:
            pass

    result.uploads_30d     = uploads_30d
    result.last_upload_date = last_upload_date

    # Average uploads / month
    if dates_seen:
        span_days = max((now - min(dates_seen)).days, 1)
        result.avg_uploads_per_month = round(len(dates_seen) / span_days * 30, 1)

    if uploads_30d >= config.UPLOADS_30_DAYS_MIN:
        result.active = True
    else:
        # Long-form check via video_details
        longform_60d = 0
        if video_details:
            for vd in video_details:
                vd_pub = vd.get("snippet", {}).get("publishedAt", "")
                vd_dur = vd.get("contentDetails", {}).get("duration", "")
                if vd_pub and vd_dur:
                    try:
                        vd_dt = datetime.fromisoformat(vd_pub.replace("Z", "+00:00"))
                        if (vd_dt >= cutoff_60d
                                and iso_to_seconds(vd_dur) >= config.LONGFORM_MIN_SECONDS):
                            longform_60d += 1
                    except ValueError:
                        pass
        result.longform_60d = longform_60d
        result.active = longform_60d >= config.LONGFORM_60_DAYS_MIN

    # ── CHECK 3: Commercial ───────────────────────────────────────────────────
    # Aggregate description + last 10 video descriptions
    check_text = description
    for item in recent_videos[:10]:
        check_text += " " + (item.get("snippet", {}).get("description", "") or "")

    found_commercial = _find_keywords(check_text, config.COMMERCIAL_KEYWORDS)
    channel_url = f"https://www.youtube.com/channel/{channel_id}"

    if found_commercial:
        result.commercial = True
        result.commercial_evidence     = f"Keywords: {', '.join(dict.fromkeys(found_commercial))[:120]}"
        result.commercial_evidence_url = channel_url
    elif sub_count >= 10_000 and video_count >= 20:
        # Established channel — high-probability commercial activity
        result.commercial = True
        result.commercial_evidence     = (
            f"Established channel: {sub_count:,} subscribers, {video_count} videos published"
        )
        result.commercial_evidence_url = channel_url

    # ── CHECK 4: Needs IncuBrix ───────────────────────────────────────────────
    need_text = description
    for item in recent_videos[:20]:
        need_text += " " + (item.get("snippet", {}).get("title", "") or "")

    found_needs = list(dict.fromkeys(_find_keywords(need_text, config.INCUBRIX_NEED_KEYWORDS)))

    # Proxy signals
    if result.avg_uploads_per_month >= 4:
        found_needs.append("high_upload_frequency")
    if any(t in url for url in topics
           for t in ["Education", "Technology", "Business", "Howto", "People"]):
        found_needs.append("relevant_topic_category")

    if found_needs:
        result.needs_incubrix       = True
        result.incubrix_need_evidence = f"Signals: {', '.join(found_needs[:5])}"

    # ── CHECK 5: Contactable ──────────────────────────────────────────────────
    result.contactable = result.contact_type != "none"

    # ── CHECK 6: Complete ─────────────────────────────────────────────────────
    required = [
        result.channel_id, result.channel_name, result.country,
        str(result.subscriber_count), result.last_upload_date,
        result.commercial_evidence, result.incubrix_need_evidence,
        result.contact_type,
    ]
    result.complete = all(bool(f) for f in required)

    # ── Content category ──────────────────────────────────────────────────────
    result.content_category = _infer_category(topics, description)

    # ── Final evaluation ──────────────────────────────────────────────────────
    result.evaluate()
    return result
