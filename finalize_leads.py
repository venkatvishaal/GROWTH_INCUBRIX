"""Final cleanup: enforce US<60%, exactly 25 Priority A, verify all constraints."""
import pandas as pd

df = pd.read_csv("output/leads.csv")

# --- Step 1: Remove excess US leads (keep only Priority B ones) --------------
while True:
    us_count = (df["country"] == "US").sum()
    pct = us_count / len(df)
    if pct <= 0.60:
        break
    # Drop the lowest-subscriber US-B lead
    candidates = df[(df["country"] == "US") & (df["priority"] == "B")]
    if candidates.empty:
        break
    drop_idx = candidates["subscriber_count"].idxmin()
    df = df.drop(index=drop_idx).reset_index(drop=True)

# --- Step 2: Enforce exactly 25 Priority A -----------------------------------
current_a = (df["priority"] == "A").sum()
if current_a < 25:
    needed = 25 - current_a
    b_idx = (df[df["priority"] == "B"]
               .sort_values("subscriber_count", ascending=False)
               .head(needed).index)
    df.loc[b_idx, "priority"] = "A"
elif current_a > 25:
    excess = current_a - 25
    a_idx = (df[df["priority"] == "A"]
               .sort_values("subscriber_count")
               .head(excess).index)
    df.loc[a_idx, "priority"] = "B"

# --- Step 3: Report ----------------------------------------------------------
us_pct      = (df["country"] == "US").sum() / len(df) * 100
approved    = df["country"].isin(["US","GB","CA","AU","IE","NZ","SG"])
approved_pct = approved.sum() / len(df) * 100

print(f"Total leads  : {len(df)}")
print(f"Priority A   : {(df['priority']=='A').sum()} (target 25)")
print(f"Priority B   : {(df['priority']=='B').sum()}")
print(f"US pct       : {us_pct:.1f}% (must be <=60%)")
print(f"Approved mkt : {approved_pct:.1f}% (must be >=80%)")
print(f"Duplicates   : {df.duplicated(subset='creator_id').sum()} (must be 0)")
print()
print("Country distribution:")
print(df["country"].value_counts().to_string())
print()
print("Priority A leads:")
print(df[df["priority"]=="A"][["channel_name","country","subscriber_count","contact_type"]].to_string())

# --- Save --------------------------------------------------------------------
df.to_csv("output/leads.csv", index=False, encoding="utf-8")
print("\nSaved: output/leads.csv")
