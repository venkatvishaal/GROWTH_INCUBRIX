"""UTF-8 CSV export for qualified creator leads."""

import logging
from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional

import pandas as pd

import config
from qualify import QualificationResult

logger = logging.getLogger(__name__)


# ── Lead record ───────────────────────────────────────────────────────────────

@dataclass
class LeadRecord:
    """One row in leads.csv — mirrors the workbook column schema exactly."""
    creator_id:              str
    platform:                str
    channel_name:            str
    channel_url:             str
    country:                 str
    subscriber_count:        int
    avg_uploads_per_month:   float
    last_upload_date:        str
    content_category:        str
    commercial_evidence:     str
    commercial_evidence_url: str
    incubrix_need_evidence:  str
    contact_type:            str
    contact_value:           str
    contact_url:             str
    priority:                str
    qualification_date:      str
    evidence_verified_date:  str
    notes:                   str
    # Internal — stripped from CSV output
    score: int = 0


# ── Builder ───────────────────────────────────────────────────────────────────

def build_lead_record(
    channel_data: dict,
    result:       QualificationResult,
    score:        int,
    priority:     str,
) -> LeadRecord:
    """Construct a LeadRecord from raw API data and a QualificationResult."""
    channel_id = channel_data.get("id", "")
    branding   = channel_data.get("brandingSettings", {}).get("channel", {})
    today      = date.today().isoformat()

    # Prefer the YouTube @handle URL
    custom = branding.get("customUrl", "")
    if custom.startswith("@"):
        channel_url = f"https://www.youtube.com/{custom}"
    elif custom.startswith("http"):
        channel_url = custom
    else:
        channel_url = f"https://www.youtube.com/channel/{channel_id}"

    return LeadRecord(
        creator_id              = channel_id,
        platform                = "YouTube",
        channel_name            = result.channel_name,
        channel_url             = channel_url,
        country                 = result.country,
        subscriber_count        = result.subscriber_count,
        avg_uploads_per_month   = result.avg_uploads_per_month,
        last_upload_date        = result.last_upload_date,
        content_category        = result.content_category,
        commercial_evidence     = result.commercial_evidence,
        commercial_evidence_url = result.commercial_evidence_url,
        incubrix_need_evidence  = result.incubrix_need_evidence,
        contact_type            = result.contact_type,
        contact_value           = result.contact_value,
        contact_url             = result.contact_url,
        priority                = priority,
        qualification_date      = today,
        evidence_verified_date  = today,
        notes                   = "",
        score                   = score,
    )


# ── Export ────────────────────────────────────────────────────────────────────

def export_to_csv(
    records:   list[LeadRecord],
    filepath:  str,
    append:    bool = False,
) -> int:
    """
    Write lead records to a UTF-8 CSV file.

    Args:
        records:  List of LeadRecord objects.
        filepath: Output CSV path.
        append:   Merge with existing file if True (deduplicating by creator_id).

    Returns:
        Total number of rows written.
    """
    if not records:
        logger.warning("export_to_csv called with 0 records — nothing written.")
        return 0

    rows = []
    for r in records:
        row = asdict(r)
        row.pop("score", None)      # strip internal field
        rows.append(row)

    new_df = pd.DataFrame(rows, columns=config.CSV_COLUMNS)

    if append:
        existing_df = load_leads_df(filepath)
        if not existing_df.empty:
            # Remove any rows that are being superseded by new data
            existing_df = existing_df[
                ~existing_df["creator_id"].isin(new_df["creator_id"])
            ]
            new_df = pd.concat([existing_df, new_df], ignore_index=True)

    new_df.to_csv(filepath, index=False, encoding="utf-8")
    logger.info(f"Exported {len(new_df)} leads -> {filepath}")
    return len(new_df)


# -- Loader --------------------------------------------------------------------

def load_leads_df(filepath: str) -> pd.DataFrame:
    """Load existing leads CSV as a DataFrame (returns empty DF if not found)."""
    try:
        df = pd.read_csv(filepath, encoding="utf-8")
        logger.info(f"Loaded {len(df)} existing leads from {filepath}")
        return df
    except FileNotFoundError:
        return pd.DataFrame(columns=config.CSV_COLUMNS)
