"""
Step 3: Load food incidents into a DuckDB star schema and run KPI queries.
Creates warehouse/ehsq.duckdb and outputs/kpi_*.csv
"""
from pathlib import Path
import duckdb

Path("warehouse").mkdir(exist_ok=True)
con = duckdb.connect("warehouse/ehsq.duckdb")
con.execute("""CREATE OR REPLACE TABLE stg_incidents AS
               SELECT * REPLACE (CAST(CAST(NAICS AS BIGINT) AS VARCHAR) AS NAICS) FROM read_csv_auto('data/processed/food_incidents.csv', all_varchar=false)""")
con.execute(Path("sql/schema.sql").read_text())

# Referential integrity checks
orphans = con.execute("""SELECT count(*) FROM fact_incident f
                         LEFT JOIN dim_date d USING (date_key) WHERE d.date_key IS NULL""").fetchone()[0]
assert orphans == 0, "fact rows without a date"
n_fact = con.execute("SELECT count(*) FROM fact_incident").fetchone()[0]
n_stg = con.execute("SELECT count(*) FROM stg_incidents").fetchone()[0]
assert n_fact == n_stg, f"row count mismatch {n_fact} vs {n_stg}"

KPIS = {
    "kpi_hazard_severity": """
        SELECT h.hazard_category,
               count(*)                                   AS reports,
               sum((amputation_count > 0)::INT)                 AS amputation_reports,
               round(avg((amputation_count > 0)::INT), 3) AS amputation_rate,
               round(avg(osha_inspection_opened), 3) AS inspection_rate
        FROM fact_incident f JOIN dim_hazard h USING (hazard_key)
        GROUP BY 1 ORDER BY reports DESC""",
    "kpi_subsector_year": """
        SELECT i.subsector, d.year, count(*) AS reports
        FROM fact_incident f JOIN dim_date d USING (date_key)
        JOIN (SELECT DISTINCT naics_code, subsector FROM dim_industry) i USING (naics_code)
        GROUP BY 1, 2 ORDER BY 1, 2""",
    "kpi_top_equipment_amputations": """
        SELECT e.equipment_source, count(*) AS amputation_reports
        FROM fact_incident f JOIN dim_event e USING (event_key)
        WHERE amputation_count > 0
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10""",
}
for name, q in KPIS.items():
    con.execute(q).df().to_csv(f"outputs/{name}.csv", index=False)
    print(name); print(con.execute(q).df().head(10).to_string(index=False))
print(f"fact_incident rows: {n_fact:,}; integrity checks passed")
