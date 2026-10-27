"""
Phase 2 (PLM / recipe side): recipe and allergen specification analysis.

Inputs
  data/raw/phase2/off_au_products.txt   2,724 Australian products from Open Food Facts
                                        (fetched with src/fetch_phase2_data.py)
  data/raw/phase2/fda_recall_summary.json  openFDA food recall counts (29,512 records)

What it does, the way a recipe / PLM system would:
  1. Builds a product-ingredient bill of materials (BOM): one row per product x ingredient.
  2. Derives each product's allergens from its ingredient list (allergen roll-up).
  3. Compares derived allergens against the declared "Contains" statement and flags
     specification gaps for review.
  4. Runs a where-used analysis: how many product specs each ingredient touches,
     which is the impact of one supplier or formulation change.
  5. Benchmarks against FDA recall causes to prioritise allergens.
Writes outputs/phase2_*.csv and outputs/phase2_metrics.json
"""
import json
import re
from collections import Counter
from pathlib import Path
import pandas as pd

RAW = Path("data/raw/phase2")
OUT = Path("outputs"); OUT.mkdir(exist_ok=True)

lines = (RAW / "off_au_products.txt").read_text(encoding="utf-8").splitlines()
vocab = lines[0].split("\t")[1].split(";")
cols = lines[1].split("\t")[1].split("|")
p = pd.DataFrame([l.split("|") for l in lines[2:] if l], columns=cols)
def b36(i):
    d = "0123456789abcdefghijklmnopqrstuvwxyz"; s = ""
    while True:
        i, r = divmod(i, 36); s = d[r] + s
        if i == 0: return s
idx = {b36(i): t for i, t in enumerate(vocab)}
p["ingredients"] = p["ingredient_ids"].map(lambda s: [idx[x] for x in s.split() if x in idx])

# ---------- data quality checks on the product master ----------
dq = []
def chk(name, n, action): dq.append({"check": name, "rows_flagged": int(n), "action": action})
chk("Duplicate product code (GTIN)", p["code"].duplicated().sum(), "drop duplicate")
chk("Missing product name", (p["name"].str.strip() == "").sum(), "keep, show code")
chk("Missing brand", (p["brand"].str.strip() == "").sum(), "keep, brand = Unknown")
chk("Invalid barcode length (not 8/12/13/14 digits)", (~p["code"].str.len().isin([8, 12, 13, 14])).sum(), "keep, flag")
chk("No ingredient list", (p["ingredients"].map(len) == 0).sum(), "excluded from roll-up")
chk("Non-standard allergen value in Contains field",
    p["allergens_declared"].str.split(";").map(lambda xs: any(x and (":" in x or len(x) > 30) for x in xs)).sum(),
    "keep, flag for clean-up")
p = p.drop_duplicates("code")
p["brand"] = p["brand"].str.strip().replace("", "Unknown")

# ---------- allergen roll-up rules (FSANZ mandatory allergens) ----------
RULES = {
    "milk": (r"(^|-)(milk|cream|butter|cheese|whey|casein|caseinate|caseinates|lactose|yoghurt|yogurt|ghee|buttermilk|milkfat|curd)s?($|-)",
             r"(coconut|cocoa|peanut|shea|almond|oat|soy|soya|rice|nut|cashew|macadamia|hazelnut|plant|vegan|dairy-free)-(milk|cream|butter|yogurt|yoghurt|cheese)|cream-of-tartar|dairy-free|culture"),
    "gluten": (r"(wheat|barley|rye|(^|-)oats?($|-)|(^|-)oat-|spelt|gluten|malt|semolina|triticale|kamut)",
               r"buckwheat|gluten-free|maltodextrin|maltitol|maltose|isomalt|goat"),
    "eggs": (r"(^|-)eggs?($|-)|(^|-)egg-|albumen", r"eggplant"),
    "soybeans": (r"(^|-)(soy|soya|soybean|soybeans|tofu|edamame)($|-)", None),
    "peanuts": (r"peanut", None),
    "nuts": (r"(almond|hazelnut|cashew|walnut|pecan|pistachio|macadamia|brazil-nut|pine-nut|tree-nut)", r"coconut|nutmeg|peanut"),
    "sesame-seeds": (r"sesame|tahini", None),
    "fish": (r"(^|-)(fish|salmon|tuna|anchovy|anchovies|cod|sardines?)($|-)", None),
    "crustaceans": (r"(prawn|shrimp|crab|lobster|crustacean)", None),
    "lupin": (r"lupin", None),
    "sulphur-dioxide-and-sulphites": (r"(sulphite|sulfite|sulphur-dioxide|sulfur-dioxide|metabisulphite|metabisulfite|(^|-)e22[0-8])", None),
}
PRECAUTION = re.compile(r"may-contain|manufactured-on|equipment|traces|processes-")
ALT = re.compile(r"(coconut|soy|soya|almond|oat|rice|cashew|plant|vegan|dairy-free)-(milk|cream|yogurt|yoghurt|cheese|butter)")
BARE_DAIRY = {"milk", "cream", "yogurt", "yoghurt", "cheese", "butter"}
def derive(ings):
    out = set()
    # A dairy-free alternative (e.g. coconut-yogurt) also carries the generic parent tag "yogurt";
    # in that case the bare parent tags are not evidence of milk.
    if any(ALT.search(t) for t in ings):
        ings = [t for t in ings if t not in BARE_DAIRY]
    for t in ings:
        if PRECAUTION.search(t): continue
        for a, (pos, neg) in RULES.items():
            if re.search(pos, t) and not (neg and re.search(neg, t)):
                out.add(a)
    return out
sp = lambda s: {x for x in s.split(";") if x}
p["declared"] = p["allergens_declared"].map(sp)
p["traces"] = p["traces_declared"].map(sp)
p["derived"] = p["ingredients"].map(derive)
p["gap"] = [sorted(d - c) for d, c in zip(p["derived"], p["declared"])]
p["has_gap"] = p["gap"].map(len) > 0

# ---------- BOM and where-used ----------
GENERIC = {"added-sugar", "disaccharide", "oil-and-fat", "vegetable-oil-and-fat", "dairy", "vegetable", "cereal", "plant",
           "fruit", "flour", "root-vegetable", "onion-family-vegetable", "cereal-flour", "condiment", "spice", "monosaccharide",
           "fruit-vegetable", "ferment", "nut", "seed", "acid", "herb", "vitamins", "microbial-culture", "vegetable-oil",
           "colour", "flavouring", "natural-flavouring", "emulsifier", "thickener", "preservative", "antioxidant",
           "acidity-regulator", "starch", "juice", "tree-nut", "cocoa", "legume", "pulse", "sweetener", "stabiliser",
           "raising-agent", "mineral", "salt-and-pepper", "e322", "e322i"}
bom = p[["code", "category", "ingredients"]].explode("ingredients").dropna()
bom = bom[~bom["ingredients"].isin(GENERIC) & ~bom["ingredients"].str.contains(PRECAUTION)]
bom = bom.rename(columns={"ingredients": "ingredient"})
where_used = (bom.groupby("ingredient").agg(products=("code", "nunique"), categories=("category", "nunique"))
              .sort_values("products", ascending=False).reset_index())
where_used.head(25).to_csv(OUT / "phase2_where_used.csv", index=False)

milk_ings = {t for t in vocab if re.search(RULES["milk"][0], t) and not re.search(RULES["milk"][1], t)}
milk_products = p[p["ingredients"].map(lambda xs: any(x in milk_ings for x in xs))]

# ---------- outputs ----------
allergens = list(RULES)
by_allergen = pd.DataFrame({
    "allergen": allergens,
    "products_containing": [int(p["derived"].map(lambda s: a in s).sum()) for a in allergens],
    "declared_in_contains": [int(p["declared"].map(lambda s: a in s).sum()) for a in allergens],
    "spec_gaps": [int(p["gap"].map(lambda g: a in g).sum()) for a in allergens],
})
by_allergen.to_csv(OUT / "phase2_allergen_specs.csv", index=False)
by_cat = (p.groupby("category").agg(products=("code", "size"), spec_gap_rate=("has_gap", "mean"),
                                    may_contain_rate=("traces", lambda s: (s.map(len) > 0).mean()))
          .round(3).sort_values("products", ascending=False).reset_index())
by_cat.to_csv(OUT / "phase2_category_specs.csv", index=False)
queue = p[p["has_gap"]][["code", "name", "brand", "category", "allergens_declared", "gap"]].copy()
queue["gap"] = queue["gap"].map(", ".join)
queue.to_csv(OUT / "phase2_spec_review_queue.csv", index=False)
pd.DataFrame(dq).to_csv(OUT / "phase2_data_quality.csv", index=False)

fda = json.load(open(RAW / "fda_recall_summary.json"))
m = {
    "products": int(len(p)), "categories": int(p["category"].nunique()), "brands": int(p["brand"].nunique()),
    "bom_lines": int(len(bom)), "distinct_ingredients": int(bom["ingredient"].nunique()),
    "dq_checks": len(dq),
    "allergen_bearing_share": round((p["derived"].map(len) > 0).mean(), 3),
    "products_with_gap": int(p["has_gap"].sum()),
    "gap_rate": round(p["has_gap"].mean(), 3),
    "top_gap_allergen": by_allergen.sort_values("spec_gaps", ascending=False).iloc[0]["allergen"],
    "may_contain_share": round((p["traces"].map(len) > 0).mean(), 3),
    "milk_products": int(len(milk_products)), "milk_categories": int(milk_products["category"].nunique()),
    "milk_share": round(len(milk_products) / len(p), 3),
    "top_ingredient": where_used.iloc[0]["ingredient"], "top_ingredient_products": int(where_used.iloc[0]["products"]),
    "fda_total": fda["total_records"], "fda_allergen": fda["allergen_total"],
    "fda_allergen_share": round(fda["allergen_total"] / fda["total_records"], 3),
    "fda_milk_share_of_allergen": round(fda["per_allergen"]["milk"] / fda["allergen_total"], 3),
    "fda_allergen_class1_share": round(fda["allergen_class"]["Class I"] / fda["allergen_total"], 3),
}
json.dump(m, open(OUT / "phase2_metrics.json", "w"), indent=2)
print(json.dumps(m, indent=2)); print(by_allergen.to_string(index=False)); print(by_cat.to_string(index=False))
print(where_used.head(15).to_string(index=False)); print(pd.DataFrame(dq).to_string(index=False))