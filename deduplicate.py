"""
Deduplication of creator leads.

Strategy (in order):
  1. Exact YouTube channel ID match (``UC…`` 24-char string) — definitive.
  2. Normalised channel URL match.
  3. Fuzzy creator name match (RapidFuzz token_sort_ratio ≥ threshold).
"""

import re
import logging
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

_STRIP_SUFFIX_RE = re.compile(
    r'\s*(official|channel|yt|youtube|media|tv|podcast|show|vlog)\s*$',
    re.IGNORECASE,
)
_NON_ALNUM_RE = re.compile(r'[^a-z0-9 ]')


def _normalise_name(name: str) -> str:
    """Return a lowercase, stripped, suffix-removed version of a creator name."""
    name = _STRIP_SUFFIX_RE.sub("", name.strip())
    name = _NON_ALNUM_RE.sub("", name.lower())
    return name.strip()


def _normalise_url(url: str) -> str:
    return url.lower().rstrip("/")


class ChannelDeduplicator:
    """
    Tracks seen creator channels and detects duplicates.

    Usage:
        dedup = ChannelDeduplicator()
        dedup.load_existing(ids, names, urls)  # pre-seed from existing CSV
        is_dup = dedup.add_and_check(channel_id, name, url)
    """

    def __init__(self, fuzzy_threshold: int = 88):
        self._ids:   set[str]  = set()
        self._names: list[str] = []   # normalised names
        self._urls:  set[str]  = set()
        self.threshold     = fuzzy_threshold
        self.duplicate_count = 0

    # ── Seeding ───────────────────────────────────────────────────────────────

    def load_existing(
        self,
        channel_ids:  list[str],
        channel_names: list[str],
        channel_urls:  list[str],
    ) -> None:
        """Pre-load already-known channels so they register as duplicates."""
        for cid in channel_ids:
            if cid:
                self._ids.add(cid)
        for name in channel_names:
            if name:
                self._names.append(_normalise_name(name))
        for url in channel_urls:
            if url:
                self._urls.add(_normalise_url(url))

    # ── Checks ────────────────────────────────────────────────────────────────

    def is_duplicate(
        self,
        channel_id:  str,
        channel_name: str,
        channel_url:  str = "",
    ) -> bool:
        """Return True if this channel has already been seen."""

        # 1. Exact ID
        if channel_id and channel_id in self._ids:
            logger.debug(f"Dup (ID): {channel_id}")
            return True

        # 2. Exact URL
        norm_url = _normalise_url(channel_url)
        if norm_url and norm_url in self._urls:
            logger.debug(f"Dup (URL): {channel_url}")
            return True

        # 3. Fuzzy name
        norm_name = _normalise_name(channel_name)
        for seen in self._names:
            if fuzz.token_sort_ratio(norm_name, seen) >= self.threshold:
                logger.debug(f"Dup (fuzzy): '{channel_name}' ≈ '{seen}'")
                return True

        return False

    def add(
        self,
        channel_id:  str,
        channel_name: str,
        channel_url:  str = "",
    ) -> None:
        """Register a channel as seen (does NOT check for duplicates first)."""
        if channel_id:
            self._ids.add(channel_id)
        norm = _normalise_name(channel_name)
        if norm and norm not in self._names:
            self._names.append(norm)
        norm_url = _normalise_url(channel_url)
        if norm_url:
            self._urls.add(norm_url)

    def add_and_check(
        self,
        channel_id:  str,
        channel_name: str,
        channel_url:  str = "",
    ) -> bool:
        """
        Check for duplicate and, if not a duplicate, register the channel.

        Returns True if it IS a duplicate (and the caller should skip it).
        """
        if self.is_duplicate(channel_id, channel_name, channel_url):
            self.duplicate_count += 1
            return True
        self.add(channel_id, channel_name, channel_url)
        return False

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def seen_count(self) -> int:
        return len(self._ids)
