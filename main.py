"""
IncuBrix Creator Lead Engine — main entry point
================================================

Usage:
    python main.py --mode normal          # Discovery + qualification run
    python main.py --mode refresh         # Re-validate existing leads
    python main.py --mode test-input --file sample.csv   # Test on provided CSV

Options:
    --mode          Run mode: normal | refresh | test-input  (default: normal)
    --budget        YouTube API quota budget in units         (default: 8000)
    --output        Output CSV path                          (default: output/leads.csv)
    --file          Input CSV for test-input mode
    --country       Restrict discovery to one country code   (e.g. US, GB)
    --max-leads     Stop after collecting this many leads    (default: 1200)
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import config
from logger import setup_logging
from discover import YouTubeDiscovery, QuotaTracker
from qualify import qualify_creator
from deduplicate import ChannelDeduplicator
from score import score_creator, assign_priority, finalize_priority_a
from export import build_lead_record, export_to_csv, load_leads_df, LeadRecord
from refresh import refresh_leads

logger = logging.getLogger(__name__)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _within_days(date_str: str, days: int) -> bool:
    if not date_str:
        return False
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt >= datetime.now(timezone.utc) - timedelta(days=days)
    except ValueError:
        return False


def _save_run_log(stats: dict) -> None:
    log_path = Path(config.RUN_LOG_FILE)
    runs = []
    if log_path.exists():
        try:
            runs = json.loads(log_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            runs = []
    runs.append(stats)
    log_path.write_text(json.dumps(runs, indent=2, default=str), encoding="utf-8")
    logger.info(f"Run log -> {log_path}")


def _save_combined(records: list[LeadRecord], existing_df: pd.DataFrame,
                   output_path: str) -> int:
    """Merge new records with existing DF, finalise Priority A, save CSV."""
    if not records:
        return len(existing_df)

    new_rows = []
    for r in records:
        row = {c: getattr(r, c, "") for c in config.CSV_COLUMNS}
        row["score"] = r.score
        new_rows.append(row)

    new_df = pd.DataFrame(new_rows)

    if not existing_df.empty:
        if "score" not in existing_df.columns:
            existing_df["score"] = 5
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined = new_df

    combined = combined.drop_duplicates(subset=["creator_id"], keep="last")
    combined = finalize_priority_a(combined, n=config.PRIORITY_A_COUNT)
    combined.drop(columns=["score"], errors="ignore").to_csv(
        output_path, index=False, encoding="utf-8"
    )
    logger.info(f"Saved {len(combined)} total leads -> {output_path}")
    return len(combined)


# -- Run modes -----------------------------------------------------------------

def run_normal(
    api_key:        str,
    budget:         int,
    output_path:    str,
    max_leads:      int,
    country_filter: str = None,
) -> dict:
    """Discover and qualify creator channels from YouTube."""

    quota     = QuotaTracker(budget)
    discovery = YouTubeDiscovery(api_key, quota)
    dedup     = ChannelDeduplicator()

    existing_df = load_leads_df(output_path)
    if not existing_df.empty:
        dedup.load_existing(
            existing_df["creator_id"].tolist(),
            existing_df["channel_name"].tolist(),
            existing_df["channel_url"].tolist(),
        )
        logger.info(f"Pre-seeded deduplicator with {len(existing_df)} existing leads")

    qualified:      list[LeadRecord] = []
    seen_ids:       set[str]         = set()

    stats = {
        "mode":             "normal",
        "run_start":        datetime.now().isoformat(),
        "channels_found":   0,
        "channels_checked": 0,
        "qualified":        0,
        "rejected":         0,
        "duplicates_removed": 0,
        "by_country":       {},
    }

    # Build ordered list of (query, country_code)
    queries_map = (
        {country_filter: config.SEARCH_QUERIES.get(country_filter, [])}
        if country_filter
        else config.SEARCH_QUERIES
    )
    query_list = [(q, cc) for cc, qs in queries_map.items() for q in qs]
    logger.info(f"Discovery: {len(query_list)} queries | budget={budget} | target={max_leads}")

    for query, country_code in query_list:
        # Stop conditions
        if quota.remaining < 150:
            logger.info(f"Quota low ({quota.remaining} units). Stopping search phase.")
            break
        total_so_far = len(qualified) + len(existing_df)
        if total_so_far >= max_leads:
            logger.info(f"Target of {max_leads} leads reached.")
            break

        # ── Search ────────────────────────────────────────────────────────────
        channel_ids = discovery.search_channels(query, region_code=country_code)
        new_ids = [cid for cid in channel_ids if cid not in seen_ids]
        seen_ids.update(new_ids)
        stats["channels_found"] += len(new_ids)

        if not new_ids:
            continue

        # ── Channel details ───────────────────────────────────────────────────
        channel_details = discovery.get_channel_details(new_ids)

        for ch in channel_details:
            ch_id   = ch.get("id", "")
            ch_name = ch.get("snippet", {}).get("title", "")
            ch_url  = f"https://www.youtube.com/channel/{ch_id}"
            ch_country = ch.get("snippet", {}).get("country", "")
            subs       = int(ch.get("statistics", {}).get("subscriberCount", 0))

            stats["channels_checked"] += 1

            # Fast pre-filters before quota-heavy upload checks
            if ch_country not in config.APPROVED_COUNTRIES:
                continue
            if not (config.MIN_SUBSCRIBERS <= subs <= config.MAX_SUBSCRIBERS):
                continue

            # Duplicate check
            if dedup.add_and_check(ch_id, ch_name, ch_url):
                stats["duplicates_removed"] += 1
                continue

            # ── Recent uploads ────────────────────────────────────────────────
            uploads_pl = (
                ch.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads", "")
            )
            recent_videos = discovery.get_recent_uploads(uploads_pl, max_results=50)

            # Long-form duration check only when needed
            video_details = None
            uploads_30d = sum(
                1 for v in recent_videos
                if _within_days(v.get("snippet", {}).get("publishedAt", ""), 30)
            )
            if uploads_30d < config.UPLOADS_30_DAYS_MIN and recent_videos and quota.remaining >= 5:
                vid_ids = [
                    v.get("contentDetails", {}).get("videoId", "")
                    for v in recent_videos
                    if v.get("contentDetails", {}).get("videoId", "")
                ][:20]
                if vid_ids:
                    video_details = discovery.get_video_details(vid_ids)

            # ── Contact ───────────────────────────────────────────────────────
            contact = discovery.extract_contact(ch)

            # ── Full qualification ────────────────────────────────────────────
            result = qualify_creator(ch, recent_videos, contact, video_details)

            if result.qualified:
                score    = score_creator(result, ch)
                priority = assign_priority(score)
                record   = build_lead_record(ch, result, score, priority)
                record.score = score

                qualified.append(record)
                ctry = result.country
                stats["by_country"][ctry] = stats["by_country"].get(ctry, 0) + 1
                stats["qualified"] += 1

                logger.info(
                    f"[OK] [{len(qualified)+len(existing_df)}] {ch_name} "
                    f"({ctry}, {subs:,} subs, score={score}, P={priority})"
                )
            else:
                stats["rejected"] += 1
                logger.debug(f"✗ {ch_name} | {result.disqualify_reason}")

            time.sleep(0.05)   # polite delay

    # ── Save ──────────────────────────────────────────────────────────────────
    total_saved = _save_combined(qualified, existing_df, output_path)

    stats["run_end"]          = datetime.now().isoformat()
    stats["quota_used"]       = quota.used
    stats["quota_summary"]    = quota.summary()
    stats["total_leads_saved"] = total_saved
    _save_run_log(stats)
    return stats


def run_refresh(api_key: str, budget: int, output_path: str) -> dict:
    """Re-validate all existing leads against live YouTube data."""
    quota     = QuotaTracker(budget)
    discovery = YouTubeDiscovery(api_key, quota)

    existing_df = load_leads_df(output_path)
    if existing_df.empty:
        logger.error("No leads to refresh. Run normal mode first.")
        return {}

    updated_df, stats = refresh_leads(existing_df, discovery, output_path)
    stats["quota_used"] = quota.used
    stats["run_end"]    = datetime.now().isoformat()
    stats["mode"]       = "refresh"
    _save_run_log(stats)
    return stats


def run_test_input(api_key: str, budget: int, input_file: str, output_path: str) -> dict:
    """Qualify a provided CSV of channel IDs (for live demo / reviewer testing)."""
    try:
        test_df = pd.read_csv(input_file, encoding="utf-8")
    except FileNotFoundError:
        logger.error(f"Test input file not found: {input_file}")
        return {}

    logger.info(f"test-input: processing {len(test_df)} rows from {input_file}")

    id_col = next((c for c in ["creator_id", "channel_id", "id"] if c in test_df.columns), None)
    if not id_col:
        logger.error("Input CSV must contain a 'creator_id' column.")
        return {}

    channel_ids = test_df[id_col].dropna().astype(str).tolist()

    quota     = QuotaTracker(budget)
    discovery = YouTubeDiscovery(api_key, quota)
    dedup     = ChannelDeduplicator()

    qualified: list[LeadRecord] = []
    stats = {
        "mode": "test-input",
        "input_file": input_file,
        "input_rows": len(channel_ids),
    }

    channel_details = discovery.get_channel_details(channel_ids)
    for ch in channel_details:
        ch_id   = ch.get("id", "")
        ch_name = ch.get("snippet", {}).get("title", "")
        ch_url  = f"https://www.youtube.com/channel/{ch_id}"

        if dedup.add_and_check(ch_id, ch_name, ch_url):
            continue

        uploads_pl    = (ch.get("contentDetails", {})
                          .get("relatedPlaylists", {})
                          .get("uploads", ""))
        recent_videos = discovery.get_recent_uploads(uploads_pl)
        contact       = discovery.extract_contact(ch)
        result        = qualify_creator(ch, recent_videos, contact)

        if result.qualified:
            score  = score_creator(result, ch)
            record = build_lead_record(ch, result, score, assign_priority(score))
            qualified.append(record)

    if qualified:
        export_to_csv(qualified, output_path, append=False)

    stats.update({
        "qualified":         len(qualified),
        "rejected":          len(channel_ids) - len(qualified),
        "duplicates_removed": dedup.duplicate_count,
        "quota_used":        quota.used,
        "run_end":           datetime.now().isoformat(),
    })
    _save_run_log(stats)
    return stats


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="IncuBrix Creator Lead Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--mode", choices=["normal", "refresh", "test-input"],
                        default="normal")
    parser.add_argument("--budget", type=int, default=config.QUOTA_BUDGET_DEFAULT)
    parser.add_argument("--output", default=config.LEADS_CSV)
    parser.add_argument("--file",   help="Input CSV for test-input mode")
    parser.add_argument("--country", help="Restrict to one country code (e.g. US)")
    parser.add_argument("--max-leads", type=int, default=config.TARGET_TOTAL)

    args = parser.parse_args()
    setup_logging(run_mode=args.mode)

    api_key = config.YOUTUBE_API_KEY
    if not api_key:
        logger.error("YOUTUBE_API_KEY not set. Add it to .env and retry.")
        sys.exit(1)

    logger.info(f"IncuBrix Lead Engine | mode={args.mode} | budget={args.budget}")
    t0 = time.time()

    try:
        if args.mode == "normal":
            stats = run_normal(
                api_key=api_key, budget=args.budget,
                output_path=args.output, max_leads=args.max_leads,
                country_filter=args.country,
            )
        elif args.mode == "refresh":
            stats = run_refresh(
                api_key=api_key, budget=args.budget, output_path=args.output,
            )
        else:  # test-input
            if not args.file:
                logger.error("--file is required for test-input mode.")
                sys.exit(1)
            stats = run_test_input(
                api_key=api_key, budget=args.budget,
                input_file=args.file, output_path=args.output,
            )
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Partial results may have been saved.")
        sys.exit(0)

    elapsed = time.time() - t0
    sep = "=" * 60
    logger.info(f"\n{sep}")
    logger.info(f"Done in {elapsed:.1f}s | mode={args.mode}")
    for key in ("qualified", "total_leads_saved", "quota_used"):
        if key in stats:
            logger.info(f"  {key}: {stats[key]}")
    logger.info(f"  output: {args.output}")
    logger.info(sep)


if __name__ == "__main__":
    main()
