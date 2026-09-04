"""IncuBrix Lead Engine — Configuration & Constants."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── API ───────────────────────────────────────────────────────────────────────
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR   = BASE_DIR / "logs"
CACHE_DIR  = BASE_DIR / ".cache"

for _d in [OUTPUT_DIR, LOGS_DIR, CACHE_DIR]:
    _d.mkdir(exist_ok=True)

LEADS_CSV    = str(OUTPUT_DIR / "leads.csv")
STATE_FILE   = str(CACHE_DIR  / "state.json")
RUN_LOG_FILE = str(LOGS_DIR   / "runs.json")

# ── Lead targets ──────────────────────────────────────────────────────────────
TARGET_TOTAL       = 1200
MIN_TOTAL          = 1000
PRIORITY_A_COUNT   = 25
QUOTA_BUDGET_DEFAULT = 8000

# ── Country quotas (no country > 60%, 80%+ from approved markets) ─────────────
COUNTRY_QUOTAS = {
    "US": 0.55,   # ~660
    "GB": 0.15,   # ~180
    "CA": 0.10,   # ~120
    "AU": 0.08,   # ~96
    "IE": 0.05,   # ~60
    "NZ": 0.04,   # ~48
    "SG": 0.03,   # ~36
}
APPROVED_COUNTRIES     = set(COUNTRY_QUOTAS.keys())
COUNTRY_TARGETS        = {k: int(v * TARGET_TOTAL) for k, v in COUNTRY_QUOTAS.items()}
MAX_SINGLE_COUNTRY_PCT = 0.60
MIN_APPROVED_MARKET_PCT = 0.80

# ── Creator thresholds ────────────────────────────────────────────────────────
MIN_SUBSCRIBERS  = 1_000
MAX_SUBSCRIBERS  = 5_000_000
SWEET_SPOT_MIN   = 10_000
SWEET_SPOT_MAX   = 500_000

# ── Activity thresholds ───────────────────────────────────────────────────────
UPLOADS_30_DAYS_MIN  = 8       # OR
LONGFORM_60_DAYS_MIN = 2       # long-form = >= 20 min
LONGFORM_MIN_SECONDS = 1200    # 20 minutes

# ── Priority scoring weights (max 10 pts total) ───────────────────────────────
PRIORITY_WEIGHTS = {
    "verified_email":          2,
    "direct_sponsorship":      2,
    "workflow_pain_signals":   2,
    "sweet_spot_subs":         1,
    "approved_market":         1,
    "recent_upload_frequency": 1,
    "has_website":             1,
}

# ── Commercial signal keywords ────────────────────────────────────────────────
COMMERCIAL_KEYWORDS = [
    "sponsored by", "sponsor", "affiliate", "discount code", "promo code",
    "check out my course", "my membership", "my product", "shop now",
    "link in bio", "use code", "partnered with", "brand deal",
    "merch", "patreon", "buy my", "free trial", "gumroad", "teachable",
    "udemy", "skillshare", "amazon associate", "consulting", "coaching program",
    "use my link", "#ad", "#sponsored", "collab", "brand partnership",
]

# ── IncuBrix need signal keywords ─────────────────────────────────────────────
INCUBRIX_NEED_KEYWORDS = [
    "repurpose", "content backlog", "editing", "captions", "subtitles",
    "workflow", "consistency", "publishing schedule", "video editing",
    "content team", "editor", "burnout", "upload more", "post more",
    "batch content", "content calendar", "automate", "transcription",
    "short form", "clips", "reels", "shorts", "newsletter", "show notes",
    "podcast workflow", "content strategy", "content production",
    "need to be more consistent", "struggling to keep up", "behind on content",
    "repurposing", "content creation process", "content workflow",
]

# ── Agency / non-creator exclusion keywords ───────────────────────────────────
AGENCY_EXCLUSION_KEYWORDS = [
    "talent agency", "management firm", "media group", "official fan",
    "fan page", "fanpage", "directory", "publication", "magazine",
    "news channel", "record label", "distribution",
]

# ── CSV column schema (order matters — matches workbook) ─────────────────────
CSV_COLUMNS = [
    "creator_id", "platform", "channel_name", "channel_url", "country",
    "subscriber_count", "avg_uploads_per_month", "last_upload_date",
    "content_category", "commercial_evidence", "commercial_evidence_url",
    "incubrix_need_evidence", "contact_type", "contact_value", "contact_url",
    "priority", "qualification_date", "evidence_verified_date", "notes",
]

# ── Search queries by country ─────────────────────────────────────────────────
SEARCH_QUERIES: dict[str, list[str]] = {
    "US": [
        # Round 1
        "personal finance tips", "business growth strategy",
        "productivity creator youtube", "fitness coach youtube",
        "tech reviewer creator", "entrepreneur vlog",
        "online course creator", "digital marketing tips",
        "investing for beginners", "side hustle ideas creator",
        "self improvement youtube", "coding tutorial creator",
        "small business owner youtube", "content creator tips",
        "life coach youtube", "health wellness creator",
        "real estate investing youtube", "e-commerce seller youtube",
        "freelancer tips creator", "mindset motivation creator",
        # Round 2 — new niches
        "podcast host youtube", "video podcaster creator",
        "expert led content creator", "niche education youtube",
        "diy youtube creator", "travel vlogger youtube",
        "food recipe youtuber", "personal brand youtube",
        "nutrition coach youtube", "parenting content creator",
        "legal tips youtube creator", "accounting tips youtube",
        "mental health creator youtube", "resume tips youtube",
        "saas founder youtube", "startup tips youtube",
        "creator economy youtube", "ghostwriting tips youtube",
        "newsletter creator youtube", "solopreneur youtube",
    ],
    "GB": [
        # Round 1
        "uk personal finance youtube", "british business creator",
        "uk productivity youtube", "uk tech youtuber",
        "uk fitness creator", "british entrepreneur vlog",
        "uk online business", "uk education youtube",
        "uk money saving creator", "uk self improvement",
        # Round 2
        "uk podcast creator youtube", "british life coach",
        "uk nutrition creator", "uk career tips youtube",
        "uk creator economy", "uk freelancer tips",
    ],
    "CA": [
        # Round 1
        "canada business creator", "canadian finance youtube",
        "canadian entrepreneur", "canada productivity creator",
        "canadian tech youtube", "canada education creator",
        # Round 2
        "canada podcast creator", "canadian life coach youtube",
        "canada wellness creator", "canadian solopreneur",
    ],
    "AU": [
        # Round 1
        "australia business youtube", "australian finance creator",
        "australia fitness creator", "australian entrepreneur",
        "australia education youtube",
        # Round 2
        "australia podcast creator", "australian life coach",
        "australia wellness youtube", "australia freelancer",
    ],
    "IE": [
        "ireland business creator", "irish entrepreneur youtube",
        "ireland finance creator", "ireland podcast creator",
        "irish life coach youtube",
    ],
    "NZ": [
        "new zealand youtube creator", "nz entrepreneur",
        "new zealand business creator", "nz podcast creator",
        "new zealand finance youtube",
    ],
    "SG": [
        "singapore creator youtube", "singapore business youtube",
        "singapore finance creator", "singapore startup youtube",
        "singapore entrepreneur vlog",
    ],
}
