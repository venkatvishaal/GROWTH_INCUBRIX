"""YouTube Data API v3 channel discovery with quota tracking and retry logic."""

import re
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config

logger = logging.getLogger(__name__)

# ── Regex helpers ─────────────────────────────────────────────────────────────
EMAIL_RE   = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
URL_RE     = re.compile(r'https?://[^\s<>"\')]+')
ISO_DUR_RE = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')

BOOKING_DOMAINS    = ['calendly.com', 'cal.com', 'tidycal.com', 'savvycal.com',
                      'acuityscheduling.com', 'bookme.name', 'hubspot.com/meetings']
CONTACT_FORM_KWORDS = ['contact', 'work-with-me', 'hire-me', 'collab',
                       'business-inquiry', 'partnerships']


def iso_to_seconds(duration: str) -> int:
    """Convert ISO 8601 duration (e.g. PT1H23M45S) to seconds."""
    m = ISO_DUR_RE.match(duration or "")
    if not m:
        return 0
    h, mins, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mins * 60 + s


# ── Quota tracker ─────────────────────────────────────────────────────────────

class QuotaTracker:
    """Tracks YouTube API quota consumption per session."""

    # Official quota costs per method
    COSTS: dict[str, int] = {
        "search.list":         100,
        "channels.list":         1,
        "playlistItems.list":    1,
        "videos.list":           1,
    }

    def __init__(self, budget: int = config.QUOTA_BUDGET_DEFAULT):
        self.budget = budget
        self.used   = 0
        self.calls: dict[str, int] = {}

    def charge(self, method: str, n: int = 1) -> bool:
        """Deduct quota for n API calls. Returns False if budget would be exceeded."""
        cost = self.COSTS.get(method, 1) * n
        if self.used + cost > self.budget:
            logger.warning(f"Quota budget reached ({self.used}/{self.budget}). Halting {method}.")
            return False
        self.used += cost
        self.calls[method] = self.calls.get(method, 0) + n
        logger.debug(f"Quota [{method}x{n}] +{cost} -> {self.used}/{self.budget}")
        return True

    @property
    def remaining(self) -> int:
        return self.budget - self.used

    def summary(self) -> dict:
        return {
            "budget": self.budget,
            "used":   self.used,
            "remaining": self.remaining,
            "calls": self.calls,
        }


# ── Discovery client ──────────────────────────────────────────────────────────

class YouTubeDiscovery:
    """Discovers and fetches creator channel data from YouTube Data API v3."""

    def __init__(self, api_key: str, quota: QuotaTracker):
        self.api   = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
        self.quota = quota

    # ── Internal ──────────────────────────────────────────────────────────────

    def _exec(self, request, max_retries: int = 4):
        """Execute an API request with exponential backoff on transient errors."""
        for attempt in range(max_retries):
            try:
                return request.execute()
            except HttpError as e:
                if e.resp.status in (429, 500, 502, 503):
                    wait = 2 ** attempt
                    logger.warning(f"HTTP {e.resp.status} (attempt {attempt+1}), retrying in {wait}s")
                    time.sleep(wait)
                elif e.resp.status == 403:
                    logger.error("API quota exceeded (403). Stopping calls.")
                    raise
                else:
                    logger.error(f"API error {e.resp.status}: {e}")
                    raise
        raise RuntimeError("Max API retries exceeded")

    # ── Public methods ────────────────────────────────────────────────────────

    def search_channels(
        self,
        query: str,
        region_code: str = "US",
        max_results: int = 50,
    ) -> list[str]:
        """
        Search YouTube for creator channels matching query + region.

        Returns a list of channel IDs.
        Costs: 100 quota units per call.
        """
        if not self.quota.charge("search.list"):
            return []
        try:
            resp = self._exec(
                self.api.search().list(
                    q=query,
                    type="channel",
                    regionCode=region_code,
                    relevanceLanguage="en",
                    maxResults=min(max_results, 50),
                    part="snippet",
                    safeSearch="none",
                )
            )
            ids = [item["snippet"]["channelId"] for item in resp.get("items", [])]
            logger.info(f"  search '{query}' [{region_code}] -> {len(ids)} channels")
            return ids
        except HttpError as e:
            logger.error(f"search_channels failed: {e}")
            return []

    def get_channel_details(self, channel_ids: list[str]) -> list[dict]:
        """
        Batch-fetch full channel metadata (50 IDs per API call).

        Parts: snippet, statistics, brandingSettings, contentDetails, topicDetails.
        Costs: 1 quota unit per batch call.
        """
        if not channel_ids:
            return []
        results = []
        for i in range(0, len(channel_ids), 50):
            batch = channel_ids[i : i + 50]
            if not self.quota.charge("channels.list"):
                break
            try:
                resp = self._exec(
                    self.api.channels().list(
                        id=",".join(batch),
                        part="snippet,statistics,brandingSettings,contentDetails,topicDetails",
                        maxResults=50,
                    )
                )
                results.extend(resp.get("items", []))
            except HttpError as e:
                logger.error(f"get_channel_details batch failed: {e}")
        logger.debug(f"Channel details fetched: {len(results)}")
        return results

    def get_recent_uploads(
        self,
        uploads_playlist_id: str,
        max_results: int = 50,
    ) -> list[dict]:
        """
        Fetch the most-recent uploads from a channel's uploads playlist.

        Costs: 1 quota unit per call.
        """
        if not uploads_playlist_id:
            return []
        if not self.quota.charge("playlistItems.list"):
            return []
        try:
            resp = self._exec(
                self.api.playlistItems().list(
                    playlistId=uploads_playlist_id,
                    maxResults=min(max_results, 50),
                    part="snippet,contentDetails",
                )
            )
            return resp.get("items", [])
        except HttpError as e:
            logger.error(f"get_recent_uploads failed [{uploads_playlist_id}]: {e}")
            return []

    def get_video_details(self, video_ids: list[str]) -> list[dict]:
        """
        Batch-fetch video metadata including ISO 8601 duration.

        Costs: 1 quota unit per batch call.
        """
        if not video_ids:
            return []
        results = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i : i + 50]
            if not self.quota.charge("videos.list"):
                break
            try:
                resp = self._exec(
                    self.api.videos().list(
                        id=",".join(batch),
                        part="contentDetails,snippet,statistics",
                        maxResults=50,
                    )
                )
                results.extend(resp.get("items", []))
            except HttpError as e:
                logger.error(f"get_video_details batch failed: {e}")
        return results

    def extract_contact(self, channel_data: dict) -> tuple[str, str, str]:
        """
        Derive the best verified public business contact for a channel.

        Priority order:
          1. API-provided contactEmail (set by creator in YouTube Studio)
          2. Email address in channel description
          3. Booking page URL (Calendly, Cal.com, etc.)
          4. Contact-form URL keyword match
          5. Non-YouTube website link in description
          6. 'none' — no verifiable contact found

        Returns: (contact_type, contact_value, contact_url)
          contact_type: 'email' | 'booking_page' | 'contact_form' | 'website' | 'none'
        """
        snippet     = channel_data.get("snippet", {})
        branding    = channel_data.get("brandingSettings", {}).get("channel", {})
        description = snippet.get("description", "") or ""
        channel_id  = channel_data.get("id", "")
        channel_url = f"https://www.youtube.com/channel/{channel_id}"

        # 1. API email
        api_email = branding.get("contactEmail", "").strip()
        if api_email and "@" in api_email:
            return "email", api_email, channel_url

        # 2. Email in description
        emails = EMAIL_RE.findall(description)
        if emails:
            # Prefer custom-domain over free providers
            custom = [e for e in emails
                      if not any(p in e.lower()
                                 for p in ("@gmail", "@hotmail", "@yahoo", "@outlook", "@icloud"))]
            chosen = custom[0] if custom else emails[0]
            return "email", chosen, channel_url

        # 3. URLs in description
        urls = URL_RE.findall(description)
        for url in urls:
            u = url.lower().rstrip("/.,)")
            if any(bd in u for bd in BOOKING_DOMAINS):
                return "booking_page", "", url
            if any(kw in u for kw in CONTACT_FORM_KWORDS):
                return "contact_form", "", url

        # 4. Any non-YouTube external link
        for url in urls:
            if "youtube.com" not in url.lower() and url.startswith("http"):
                return "website", "", url

        return "none", "", ""
