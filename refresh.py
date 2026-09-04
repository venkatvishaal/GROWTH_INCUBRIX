"""
Refresh engine — re-validates existing leads against live YouTube data.

On each refresh:
  - Re-fetches channel statistics (subscriber count, activity).
  - Re-runs all 6 qualification checks.
  - Updates contact information if changed.
  - Logs which leads were retained / dropped.
  - Overwrites leads.csv with the refreshed set.
"""

import logging
from datetime import date

import pandas as pd

import config
from discover import YouTubeDiscovery, QuotaTracker
from qualify import qualify_creator
from export import build_lead_record, export_to_csv, load_leads_df, LeadRecord
from score import score_creator, assign_priority

logger = logging.getLogger(__name__)


def refresh_leads(
    leads_df:    pd.DataFrame,
    discovery:   YouTubeDiscovery,
    output_path: str,
) -> tuple[pd.DataFrame, dict]:
    """
    Refresh all existing qualified leads.

    Args:
        leads_df:    DataFrame loaded from the current leads.csv.
        discovery:   Authenticated YouTubeDiscovery instance.
        output_path: Path to write the refreshed CSV.

    Returns:
        (refreshed_df, stats_dict)
    """
    if leads_df.empty:
        logger.warning("No leads to refresh — run normal mode first.")
        return leads_df, {}

    channel_ids = leads_df["creator_id"].dropna().tolist()
    total = len(channel_ids)
    logger.info(f"Refreshing {total} leads …")

    stats = {
        "total":              total,
        "refreshed":          0,
        "still_qualified":    0,
        "newly_disqualified": 0,
        "contact_updated":    0,
    }

    refreshed_records: list[LeadRecord] = []

    for i in range(0, total, 50):
        batch_ids     = channel_ids[i : i + 50]
        channel_batch = discovery.get_channel_details(batch_ids)

        for channel_data in channel_batch:
            channel_id = channel_data.get("id", "")

            # Find the original row
            orig_rows = leads_df[leads_df["creator_id"] == channel_id]
            if orig_rows.empty:
                continue
            orig = orig_rows.iloc[0].to_dict()

            # Get fresh uploads
            uploads_playlist = (
                channel_data.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads", "")
            )
            recent_videos = discovery.get_recent_uploads(uploads_playlist, max_results=50)
            contact       = discovery.extract_contact(channel_data)

            result = qualify_creator(channel_data, recent_videos, contact)
            stats["refreshed"] += 1

            if result.qualified:
                score    = score_creator(result, channel_data)
                priority = orig.get("priority", assign_priority(score))
                record   = build_lead_record(channel_data, result, score, priority)

                # Preserve original qualification date; update evidence date
                record.qualification_date    = orig.get("qualification_date",
                                                        date.today().isoformat())
                record.evidence_verified_date = date.today().isoformat()

                # Flag if contact info changed
                if record.contact_value != orig.get("contact_value", ""):
                    stats["contact_updated"] += 1
                    logger.info(f"Contact updated for {channel_id}: {record.contact_value}")

                refreshed_records.append(record)
                stats["still_qualified"] += 1
            else:
                stats["newly_disqualified"] += 1
                logger.info(
                    f"Lead dropped: {channel_id} | {result.channel_name} "
                    f"| reason: {result.disqualify_reason}"
                )

    if refreshed_records:
        export_to_csv(refreshed_records, output_path, append=False)
        refreshed_df = load_leads_df(output_path)
    else:
        refreshed_df = pd.DataFrame(columns=config.CSV_COLUMNS)

    logger.info(f"Refresh complete: {stats}")
    return refreshed_df, stats
