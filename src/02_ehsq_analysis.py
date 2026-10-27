"""
Step 2: EHSQ analysis of food & beverage manufacturing severe injuries.
- Industry benchmark (amputation, hospitalisation, inspection rates)
- Hazard (root cause) classification from incident narratives, rule-based NLP
- Sub-sector, equipment, body part, trend and state breakdowns
Writes outputs/*.csv and outputs/metrics.json
"""
import json
import re
from pathlib import Path
import pandas as pd

OUT = Path("outputs"); OUT.mkdir(exist_ok=True)
df = pd.read_csv("data/processed/sir_clean.csv", low_memory=False)
for c in ["EventTitle", "SourceTitle", "NatureTitle", "Part of Body Title"]:
    df[c] = df[c].fillna("Unknown").str.strip()

food = df[df["IndustryGroup"] == "Food & Beverage Manufacturing"].copy()

# ---------- 1. Industry benchmark ----------
bench = (df[df["IndustryGroup"] != "Unknown"].groupby("IndustryGroup")
         .agg(reports=("ID", "size"),
              amputation_rate=("Amputation", lambda s: (s > 0).mean()),
              hospitalisation_rate=("Hospitalized", lambda s: (s > 0).mean()),
              inspection_rate=("Inspected", "mean"))
         .round(3).reset_index())
bench.to_csv(OUT / "industry_benchmark.csv", index=False)

# ---------- 2. Hazard classification from narratives (first match wins) ----------
RULES = [
    ("Maintenance & cleaning (LOTO risk)",
     r"lock ?out|tag ?out|loto|clean|sanit|maintenan|unjam|jam|clear(ing)? (a|the)? ?(blockage|product)|repair"),
    ("Moving machinery: caught-in / guarding",
     r"guard|conveyor|roller|sprocket|chain|belt|auger|mixer|grinder|slicer|saw|blade|press|die|nip point|caught"),
    ("Powered industrial vehicles",
     r"forklift|fork lift|pallet jack|order picker|truck|tow motor"),
    ("Slips, trips and falls",
     r"slip|trip|fell|fall|ladder|wet floor"),
    ("Burns: steam, hot liquids, oil",
     r"burn|steam|hot (water|oil|liquid|grease)|fryer|scald|boil"),
    ("Chemical / ammonia exposure",
     r"ammonia|chlorine|chemical|caustic|acid|sanitizer"),
    ("Knives and hand tools",
     r"knife|knives|hook|cutter|scissor|hand tool"),
]
def classify(text):
    t = str(text).lower()
    if len(t) < 20:
        return "Unclassified"
    for label, pat in RULES:
        if re.search(pat, t):
            return label
    return "Other"
food["Hazard"] = food["Final Narrative"].map(classify)
hazard = (food.groupby("Hazard")
          .agg(reports=("ID", "size"),
               amputations=("Amputation", lambda s: int((s > 0).sum())))
          .sort_values("reports", ascending=False).reset_index())
hazard["share"] = (hazard["reports"] / len(food)).round(3)
hazard.to_csv(OUT / "hazard_classification.csv", index=False)

# ---------- 3. Breakdowns ----------
SUBSECTOR = {"3111": "Animal food", "3112": "Grain & oilseed milling",
             "3113": "Sugar & confectionery", "3114": "Fruit & vegetable preserving",
             "3115": "Dairy", "3116": "Meat & poultry processing", "3117": "Seafood",
             "3118": "Bakeries & tortillas", "3119": "Other food (snacks, coffee, sauces)",
             "3121": "Beverages"}
food["Subsector"] = food["NAICS"].astype(str).str[:4].map(SUBSECTOR).fillna("Other")
sub = (food.groupby("Subsector")
       .agg(reports=("ID", "size"), amputation_rate=("Amputation", lambda s: (s > 0).mean()))
       .round(3).sort_values("reports", ascending=False).reset_index())
sub.to_csv(OUT / "subsector.csv", index=False)

trend = food.groupby("Year").agg(reports=("ID", "size"),
                                 amputations=("Amputation", lambda s: int((s > 0).sum()))).reset_index()
trend.to_csv(OUT / "trend_by_year.csv", index=False)
food["SourceTitle"].value_counts().head(10).rename_axis("equipment").reset_index(name="reports") \
    .to_csv(OUT / "top_equipment.csv", index=False)
food["State"].value_counts().head(10).rename_axis("state").reset_index(name="reports") \
    .to_csv(OUT / "top_states.csv", index=False)

# ---------- 4. Headline metrics ----------
fingers = food["Part of Body Title"].str.contains("finger|thumb", case=False).mean()
maint_events = food["EventTitle"].str.contains("maintenance, cleaning", case=False).mean()
amp_food = (food["Amputation"] > 0).mean()
amp_nonmfg = (df.loc[df["IndustryGroup"] == "Other Industries", "Amputation"] > 0).mean()
pre = trend[trend.Year.between(2015, 2019)]["reports"].mean()
post = trend[trend.Year.between(2021, 2024)]["reports"].mean()
dq = pd.read_csv(OUT / "data_quality_report.csv")

m = {
    "total_reports_all_industries": int(len(df)),
    "raw_rows": 105996,
    "data_quality_checks": int(len(dq)),
    "rows_flagged_total": int(dq["rows_flagged"].sum()),
    "food_reports": int(len(food)),
    "food_share_of_all": round(len(food) / len(df), 3),
    "food_amputation_rate": round(amp_food, 3),
    "non_manufacturing_amputation_rate": round(amp_nonmfg, 3),
    "amputation_rate_multiple": round(amp_food / amp_nonmfg, 1),
    "food_inspection_rate": round(food["Inspected"].mean(), 3),
    "finger_hand_share": round(fingers, 3),
    "maintenance_cleaning_event_share": round(maint_events, 3),
    "top_hazard": hazard.iloc[0]["Hazard"],
    "top_hazard_share": float(hazard.iloc[0]["share"]),
    "top2_hazards_share": float(hazard.iloc[:2]["share"].sum().round(3)),
    "classified_share": round((food["Hazard"].isin(["Other", "Unclassified"]) == False).mean(), 3),
    "meat_poultry_share": round((food["Subsector"] == "Meat & poultry processing").mean(), 3),
    "avg_reports_2015_2019": round(pre, 1),
    "avg_reports_2021_2024": round(post, 1),
    "trend_change": round(post / pre - 1, 3),
}
json.dump(m, open(OUT / "metrics.json", "w"), indent=2)
food[["ID", "EventDate", "Year", "State", "NAICS", "Subsector", "Hazard", "EventTitle", "SourceTitle",
      "NatureTitle", "Part of Body Title", "Hospitalized", "Amputation", "Loss of Eye", "Inspected"]] \
    .to_csv("data/processed/food_incidents.csv", index=False)
print(json.dumps(m, indent=2)); print(hazard.to_string(index=False)); print(sub.to_string(index=False))
