"""
Step 4: Build the interactive EHSQ Safety Command Centre (dashboard/index.html).
Packs the 6,862 food & beverage incidents into compact columnar JSON and injects it
into src/dashboard_template.html. All filtering and aggregation then runs in the browser.
"""
import json
import re
from pathlib import Path
import pandas as pd

df = pd.read_csv("data/processed/sir_clean.csv", low_memory=False)
food = df[df["IndustryGroup"] == "Food & Beverage Manufacturing"].copy()
inc = pd.read_csv("data/processed/food_incidents.csv")            # carries Hazard + Subsector
food = food.merge(inc[["ID", "Hazard", "Subsector"]], on="ID", how="left")
m = json.load(open("outputs/metrics.json"))
dq = pd.read_csv("outputs/data_quality_report.csv")

def body_group(t):
    t = str(t).lower()
    for label, pat in [("Fingers & thumbs", r"finger|thumb"), ("Hands & wrists", r"hand|wrist"),
                       ("Arms & shoulders", r"arm|elbow|shoulder"),
                       ("Legs & feet", r"leg|knee|ankle|foot|feet|toe|hip|thigh"),
                       ("Head, face & eyes", r"head|face|eye|skull|brain|scalp|ear|nose|mouth|jaw"),
                       ("Trunk & back", r"trunk|back|chest|abdomen|pelvi|lumbar|spine|rib|buttock|groin")]:
        if re.search(pat, t):
            return label
    return "Multiple / other"

food["Body"] = food["Part of Body Title"].map(body_group)
food["Equip"] = food["SourceTitle"].fillna("Unknown").str.strip()
top_eq = food.loc[food["Amputation"] > 0, "Equip"].value_counts().head(24).index
food["Equip"] = food["Equip"].where(food["Equip"].isin(top_eq), "All other sources")

def codes(col):
    cats = sorted(food[col].fillna("Unknown").unique().tolist())
    idx = {c: i for i, c in enumerate(cats)}
    return cats, food[col].fillna("Unknown").map(idx).astype(int).tolist()

dims, cols = {}, {}
for key, col in [("sub", "Subsector"), ("haz", "Hazard"), ("st", "State"), ("eq", "Equip"), ("body", "Body")]:
    dims[key], cols[key] = codes(col)
cols["y"] = food["Year"].astype(int).tolist()
cols["amp"] = (food["Amputation"] > 0).astype(int).tolist()
cols["hosp"] = (food["Hospitalized"] > 0).astype(int).tolist()
cols["insp"] = food["Inspected"].astype(int).tolist()
cols["lat"] = food["Latitude"].round(2).where(food["Latitude"].notna(), None).tolist()
cols["lon"] = food["Longitude"].round(2).where(food["Longitude"].notna(), None).tolist()

# Case explorer: 30 random narratives per hazard
cases = []
for h, g in food.groupby("Hazard"):
    for _, r in g.sample(min(30, len(g)), random_state=7).iterrows():
        cases.append({"h": h, "s": r["Subsector"], "y": int(r["Year"]), "a": int(r["Amputation"] > 0),
                      "st": str(r["State"]).title(), "eq": str(r["SourceTitle"]).strip(),
                      "t": re.sub(r"\s+", " ", str(r["Final Narrative"]))[:420]})

# Phase 2 (recipe / allergen specifications), produced by src/05_recipe_allergen_spec.py
p2 = None
if Path("outputs/phase2_metrics.json").exists():
    qq = pd.read_csv("outputs/phase2_spec_review_queue.csv", dtype=str).fillna("")
    p2 = {"meta": json.load(open("outputs/phase2_metrics.json")),
          "allergens": pd.read_csv("outputs/phase2_allergen_specs.csv").to_dict("records"),
          "cats": pd.read_csv("outputs/phase2_category_specs.csv").to_dict("records"),
          "where": pd.read_csv("outputs/phase2_where_used.csv").to_dict("records"),
          "queue": qq.to_dict("records"),
          "fda": json.load(open("data/raw/phase2/fda_recall_summary.json"))}

payload = {"dims": dims, "cols": cols, "cases": cases, "p2": p2,
           "meta": {**m, "nonmfg_amp": m["non_manufacturing_amputation_rate"]},
           "dq": dq.to_dict("records")}
tpl = Path("src/dashboard_template.html").read_text(encoding="utf-8")
out = tpl.replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":")))
Path("dashboard/index.html").write_text(out, encoding="utf-8")
print(f"dashboard/index.html written ({len(out)/1024:.0f} KB), {len(food):,} incidents, {len(cases)} cases")