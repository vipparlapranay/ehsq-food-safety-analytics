"""
Step 1: Load OSHA Severe Injury Reports, run data quality checks, write a clean file.
Usage: python src/01_clean_and_validate.py data/raw/January2015toNovember2025.csv
"""
import sys
from pathlib import Path
import pandas as pd

RAW = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw/January2015toNovember2025.csv")
OUT = Path("data/processed"); OUT.mkdir(parents=True, exist_ok=True)
REP = Path("outputs"); REP.mkdir(exist_ok=True)

df = pd.read_csv(RAW, encoding="latin1", low_memory=False)
n_raw = len(df)
df["EventDate"] = pd.to_datetime(df["EventDate"], errors="coerce", format="mixed")
df["NAICS"] = df["Primary NAICS"].astype(str).str.extract(r"(\d+)")[0]

checks = []
def check(name, mask, action):
    checks.append({"check": name, "rows_flagged": int(mask.sum()), "action": action})
    return mask

# ---------- 12 data quality checks ----------
check("Duplicate ID", df.duplicated("ID", keep="first"), "drop duplicate")
check("Fully duplicated row", df.duplicated(keep="first"), "drop duplicate")
check("Unparseable event date", df["EventDate"].isna(), "drop")
check("Event date in the future", df["EventDate"] > pd.Timestamp("2025-11-30"), "drop")
check("Missing / non-numeric NAICS", df["NAICS"].isna(), "keep, industry = Unknown")
check("NAICS not 6 digits", df["NAICS"].notna() & (df["NAICS"].str.len() != 6), "keep, flag")
check("Missing state", df["State"].isna(), "keep, flag")
check("Latitude/longitude out of US range",
      df["Latitude"].notna() & ~df["Latitude"].between(13, 72) |
      df["Longitude"].notna() & ~df["Longitude"].between(-180, -60), "null coordinates")
check("Missing severity flags (Hospitalized/Amputation/Loss of Eye)",
      df[["Hospitalized", "Amputation", "Loss of Eye"]].isna().any(axis=1), "fill 0")
check("Negative severity counts",
      (df[["Hospitalized", "Amputation", "Loss of Eye"]] < 0).any(axis=1), "set 0")
check("No severity outcome recorded",
      df[["Hospitalized", "Amputation", "Loss of Eye"]].fillna(0).sum(axis=1) == 0, "keep, flag")
check("Missing or very short narrative (<20 chars)",
      df["Final Narrative"].fillna("").str.len() < 20, "keep, root cause = Unclassified")

pd.DataFrame(checks).to_csv(REP / "data_quality_report.csv", index=False)

# ---------- apply fixes ----------
df = df.drop_duplicates("ID").drop_duplicates()
df = df[df["EventDate"].notna() & (df["EventDate"] <= pd.Timestamp("2025-11-30"))]
bad_geo = ~df["Latitude"].between(13, 72) | ~df["Longitude"].between(-180, -60)
df.loc[bad_geo, ["Latitude", "Longitude"]] = None
for c in ["Hospitalized", "Amputation", "Loss of Eye"]:
    df[c] = df[c].fillna(0).clip(lower=0).astype(int)
df["State"] = df["State"].fillna("UNKNOWN").str.upper().str.strip()
df["Inspected"] = df["Inspection"].notna().astype(int)
df["Year"] = df["EventDate"].dt.year

def industry(n):
    if not isinstance(n, str): return "Unknown"
    if n.startswith("311") or n.startswith("3121"): return "Food & Beverage Manufacturing"
    if n[:2] in ("31", "32", "33"): return "Other Manufacturing"
    return "Other Industries"
df["IndustryGroup"] = df["NAICS"].map(industry)

df.to_csv(OUT / "sir_clean.csv", index=False)
print(f"raw rows {n_raw:,} -> clean rows {len(df):,}; checks: {len(checks)}")
print(pd.DataFrame(checks).to_string(index=False))
