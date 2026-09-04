"""Priority scoring and A/B/C assignment for qualified creator leads."""

import logging
import pandas as pd

from qualify import QualificationResult
import config

logger = logging.getLogger(__name__)


def score_creator(result: QualificationResult, channel_data: dict) -> int:
    """
    Score a *qualified* creator on a 0–10 scale.

    Higher score → better Priority A candidate.
    Scores are based on contact quality, commercial strength, workflow
    pain signals, subscriber sweet-spot, and market priority.
    """
    if not result.qualified:
        return 0

    score = 0
    w = config.PRIORITY_WEIGHTS

    # Verified direct email (stronger than a form / website link)
    if result.contact_type == "email":
        score += w["verified_email"]

    # Strong direct-sponsorship commercial evidence
    strong_signals = ["sponsored by", "brand deal", "partnered with", "collab", "partnership"]
    if any(s in result.commercial_evidence.lower() for s in strong_signals):
        score += w["direct_sponsorship"]
    elif result.commercial_evidence:
        score += 1  # Weaker commercial evidence still gets partial credit

    # Workflow pain signals (3+ = full credit, 1–2 = partial)
    need_ev = result.incubrix_need_evidence
    if need_ev and "Signals:" in need_ev:
        signal_count = need_ev.count(",") + 1
        if signal_count >= 3:
            score += w["workflow_pain_signals"]
        elif signal_count >= 1:
            score += 1

    # Subscriber sweet-spot: 10K–500K (engaged but not mega)
    subs = result.subscriber_count
    if config.SWEET_SPOT_MIN <= subs <= config.SWEET_SPOT_MAX:
        score += w["sweet_spot_subs"]

    # Top-3 markets: US, UK, CA
    if result.country in ("US", "GB", "CA"):
        score += w["approved_market"]

    # High upload frequency (> 4/month)
    if result.avg_uploads_per_month >= 4:
        score += w["recent_upload_frequency"]

    # Has separate website / booking page / contact form
    if result.contact_type in ("website", "contact_form", "booking_page"):
        score += w["has_website"]

    return min(score, 10)


def assign_priority(score: int) -> str:
    """Map a numeric score to a Priority label (A / B / C)."""
    if score >= 7:
        return "A"
    elif score >= 4:
        return "B"
    return "C"


def finalize_priority_a(df: pd.DataFrame, n: int = 25) -> pd.DataFrame:
    """
    Ensure exactly *n* Priority A leads in the dataframe.

    Algorithm:
      1. Sort by 'score' descending (highest quality first).
      2. Assign A/B/C labels by score threshold.
      3. Promote or demote to reach exactly n Priority A leads.

    Args:
        df: DataFrame that must contain a 'score' column.
        n:  Target number of Priority A leads (default 25).

    Returns:
        DataFrame with 'priority' column updated in-place.
    """
    if "score" not in df.columns:
        df["score"] = 5

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["priority"] = df["score"].apply(assign_priority)

    a_idx = df[df["priority"] == "A"].index.tolist()
    b_idx = df[df["priority"] == "B"].index.tolist()

    if len(a_idx) > n:
        # Demote lowest-scored A → B
        demote = a_idx[n:]
        df.loc[demote, "priority"] = "B"
    elif len(a_idx) < n:
        # Promote top-B → A
        needed = n - len(a_idx)
        promote = b_idx[:needed]
        df.loc[promote, "priority"] = "A"

    counts = df["priority"].value_counts().to_dict()
    logger.info(
        f"Priority distribution — A:{counts.get('A',0)} "
        f"B:{counts.get('B',0)} C:{counts.get('C',0)}"
    )
    return df
