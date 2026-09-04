# IncuBrix Creator Lead Engine

## One-line run command

```bash
python main.py --mode normal
```

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your YouTube Data API v3 key
cp .env.example .env
# Edit .env and paste your key as: YOUTUBE_API_KEY=your_key_here
```

---

## Run modes

| Command | What it does |
|---------|-------------|
| `python main.py --mode normal` | Discover, qualify, deduplicate, score, and export leads |
| `python main.py --mode refresh` | Re-validate all existing leads against live YouTube data |
| `python main.py --mode test-input --file sample.csv` | Qualify a provided list of channel IDs |

### Optional flags

| Flag | Default | Description |
|------|---------|-------------|
| `--budget INT` | 8000 | YouTube API quota units to use per run |
| `--output PATH` | output/leads.csv | Output CSV location |
| `--country CODE` | all | Restrict to one country (US, GB, CA, AU, IE, NZ, SG) |
| `--max-leads INT` | 1200 | Stop after collecting this many leads |

### Examples

```bash
# Run with full budget targeting 1,200 leads
python main.py --mode normal --budget 8000 --max-leads 1200

# Refresh existing leads
python main.py --mode refresh

# Test on a provided CSV of 10 channel IDs (live demo)
python main.py --mode test-input --file sample.csv --output output/test_leads.csv

# Restrict to US only
python main.py --mode normal --country US --max-leads 600
```

---

## Output files

```
output/leads.csv          ← Full lead list (UTF-8, matches workbook columns)
logs/run_normal_*.log     ← Detailed per-run log
logs/runs.json            ← Machine-readable run history (quota, counts, timing)
.cache/state.json         ← Processed channel IDs (prevents re-checking)
```

---

## What the engine does

1. **Discover** — Searches YouTube Data API v3 by niche keyword + country (60 queries across 7 countries)
2. **Qualify** — Applies all 6 IncuBrix checks: real & relevant, active, commercial, needs IncuBrix, contactable, complete
3. **Deduplicate** — SHA-style exact channel ID match + fuzzy creator-name match (RapidFuzz ≥ 88%)
4. **Score** — Scores each qualified lead 0–10 across contact quality, commercial strength, workflow pain signals, subscriber sweet-spot, and market priority
5. **Export** — Writes UTF-8 `leads.csv` with all required columns matching the IncuBrix workbook schema
6. **Refresh** — On rerun, re-validates existing leads and updates any changed contact info or activity status

---

## Running tests

```bash
python -m pytest tests/ -v
```

---

## API quota usage

| Phase | Units per run |
|-------|--------------|
| Search (30–60 queries) | 3,000–6,000 |
| Channel details (batched) | ~60 |
| Upload checks | ~1,500 |
| Video duration checks | ~300 |
| **Total** | **~5,000–8,000** |

Default budget is 8,000 units/run. YouTube's free quota is 10,000 units/day.

---

## Notes

- **No passwords or secret keys are committed.** API key lives in `.env` (git-ignored).
- **No creators are contacted.** The engine only reads public YouTube data.
- **All data sources are public and consented.** YouTube API Terms of Service compliant.
- AI tools used: Google Gemini (Antigravity IDE) for code generation. All code reviewed and tested.
