"""
Fetch the Phase 2 data snapshot (run once; needs internet).

1. Open Food Facts: Australian products in 12 categories, with ingredient tags and
   declared allergens, from the search API (search.openfoodfacts.org).
   Writes data/raw/phase2/off_au_products.txt in a compact format:
     line 1  #VOCAB<TAB>ingredient tags used by 5+ products, ';'-separated
     line 2  #COLS<TAB>column names
     rows    code|name|brand|category|allergens_declared|traces_declared|ingredients_n|
             ingredient_tags_n|ingredient_ids (base-36 index into VOCAB)|allergens_detected
2. openFDA food enforcement: recall counts by cause, allergen, year and class.
   Writes data/raw/phase2/fda_recall_summary.json

The committed snapshot was fetched on 27 Oct 2026 (2,724 products; 29,512 recall records).
"""
import json
import time
from collections import Counter
from pathlib import Path
import requests

OUT = Path("data/raw/phase2"); OUT.mkdir(parents=True, exist_ok=True)
CATS = ["cheeses", "yogurts", "milks", "ice-creams-and-sorbets", "spreads", "biscuits", "chocolates",
        "breakfast-cereals", "breads", "chips-and-fries", "sauces", "fruit-juices"]
FIELDS = "code,product_name,product_name_en,brands,ingredients_tags,allergens_tags,traces_tags,ingredients_n"

def b36(i):
    d = "0123456789abcdefghijklmnopqrstuvwxyz"; s = ""
    while True:
        i, r = divmod(i, 36); s = d[r] + s
        if i == 0: return s

def fetch_off():
    seen = {}
    for c in CATS:
        for page in range(1, 13):
            q = f'countries_tags:"en:australia" AND categories_tags:"en:{c}"'
            j = requests.get("https://search.openfoodfacts.org/search",
                             params={"q": q, "page_size": 100, "page": page, "fields": FIELDS}, timeout=60).json()
            hits = j.get("hits") or []
            for h in hits:
                if h.get("ingredients_tags") and h["code"] not in seen:
                    seen[h["code"]] = {**h, "cat": c}
            if not hits or page * 100 >= j.get("count", 0):
                break
            time.sleep(0.5)
    prods = list(seen.values())
    freq = Counter(t for h in prods for t in set(h["ingredients_tags"]))
    vocab = [t for t, n in sorted(freq.items(), key=lambda x: -x[1]) if n >= 5]
    vid = {t: b36(i) for i, t in enumerate(vocab)}
    st = lambda t: t.split(":", 1)[1] if t.startswith("en:") else t
    clean = lambda x: str(x or "").replace("|", " ").replace("\n", " ")
    rows = []
    for h in prods:
        rows.append("|".join([h["code"], clean(h.get("product_name_en") or h.get("product_name"))[:45],
                              clean((h.get("brands") or [""])[0])[:25], h["cat"],
                              ";".join(st(t) for t in h.get("allergens_tags") or []),
                              ";".join(st(t) for t in h.get("traces_tags") or []),
                              str(h.get("ingredients_n") or ""), str(len(h["ingredients_tags"])),
                              " ".join(vid[t] for t in dict.fromkeys(h["ingredients_tags"]) if t in vid), ""]))
    cols = "code|name|brand|category|allergens_declared|traces_declared|ingredients_n|ingredient_tags_n|ingredient_ids|allergens_detected"
    (OUT / "off_au_products.txt").write_text(
        "#VOCAB\t" + ";".join(st(t) for t in vocab) + "\n#COLS\t" + cols + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"Open Food Facts: {len(rows)} products")

def fetch_fda():
    A = "https://api.fda.gov/food/enforcement.json"
    get = lambda **p: requests.get(A, params=p, timeout=60).json()
    total = lambda s: get(search=s, limit=1).get("meta", {}).get("results", {}).get("total", 0)
    def by_year(s=None):
        j = get(**({"search": s} if s else {}), count="report_date"); y = Counter()
        for r in j.get("results", []): y[r["time"][:4]] += r["count"]
        return dict(sorted(y.items()))
    nuts = "almond OR almonds OR cashew OR cashews OR walnut OR walnuts OR pecan OR pecans OR hazelnut OR hazelnuts OR pistachio OR pistachios OR \"tree nut\" OR \"tree nuts\""
    alg = ("reason_for_recall:(undeclared AND (milk OR dairy OR egg OR eggs OR peanut OR peanuts OR soy OR soya OR wheat "
           f"OR gluten OR {nuts} OR fish OR shellfish OR shrimp OR crab OR lobster OR sesame OR allergen OR allergens))")
    per = {"milk": "(milk OR dairy)", "soy": "(soy OR soya)", "wheat": "(wheat OR gluten)", "peanut": "(peanut OR peanuts)",
           "tree_nuts": f"({nuts})", "egg": "(egg OR eggs)", "sesame": "sesame", "shellfish": "(shellfish OR shrimp OR crab OR lobster)", "fish": "fish"}
    out = {"source": "openFDA Food Enforcement API, product-level recall records",
           "total_records": get(limit=1)["meta"]["results"]["total"], "allergen_total": total(alg),
           "all_by_year": by_year(), "allergen_by_year": by_year(alg),
           "per_allergen": {k: total(f"reason_for_recall:(undeclared AND {v})") for k, v in per.items()},
           "reasons": {"listeria": total("reason_for_recall:listeria"), "undeclared_any": total("reason_for_recall:undeclared"),
                       "salmonella": total("reason_for_recall:salmonella"),
                       "foreign_material": total("reason_for_recall:(foreign OR metal OR plastic OR glass)"),
                       "e_coli": total("reason_for_recall:(coli)")},
           "allergen_class": {r["term"]: r["count"] for r in get(search=alg, count="classification.exact")["results"]}}
    out["reasons"]["allergen_undeclared"] = out["allergen_total"]
    (OUT / "fda_recall_summary.json").write_text(json.dumps(out, indent=2))
    print(f"openFDA: {out['total_records']} records, {out['allergen_total']} undeclared-allergen")

if __name__ == "__main__":
    fetch_off(); fetch_fda()
