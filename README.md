# Food Manufacturing EHSQ Analytics: OSHA Severe Injury Reports (2015–2025)

An end-to-end EHSQ (Environment, Health, Safety & Quality) analytics project on **105,996 OSHA Severe Injury Reports** (Jan 2015 – Nov 2025), focused on **6,862 incidents in food & beverage manufacturing** (NAICS 311 and 3121).

It follows the incident data model used by EHSQ platforms such as Intelex (incident → classification → investigation → KPI reporting), built with open tools.

## Key findings

| Metric | Value |
|---|---|
| Food & beverage manufacturing severe injury reports | **6,862** (6.5% of all reports) |
| Amputation rate, food & beverage mfg | **46.2%**, **2.6×** non-manufacturing industries (17.5%) |
| Moving machinery + maintenance/cleaning hazards | **58.1%** of reports, **76.9%** of amputations |
| Finger / hand injuries | **50.3%** of reports |
| Meat & poultry processing share | **31.9%** of food reports (2,188) |
| Top equipment in amputations | Butchering machinery (338), specialised food processing machinery (328), packaging machinery (220) |
| Bakeries & tortillas amputation rate | **56.3%**, the highest sub-sector |
| OSHA follow-up inspection rate | **45.8%** |
| Yearly reports, 2021–24 avg vs 2015–19 avg | **−13.8%** (679 → 586 per year) |

### Recommended corrective actions (CAPA)
1. **Lockout/tagout verification** for cleaning, sanitation and jam clearing: 1,655 reports, 57% resulting in amputation.
2. **Machine guarding audits** on butchering, mixing, packaging and conveyor equipment: 2,335 reports, 64% amputation rate.
3. **Powered vehicle traffic separation** (forklifts, pallet jacks) in warehouses and dispatch: 807 reports.
4. **Slip controls** on wet production floors: 901 reports.

## Pipeline

```
data/raw/January2015toNovember2025.csv   (download from osha.gov/severe-injury-reports)
  └─ src/01_clean_and_validate.py   12 data quality checks → outputs/data_quality_report.csv
  └─ src/02_ehsq_analysis.py        industry benchmark, narrative hazard classification (88% classified), breakdowns
  └─ src/03_build_warehouse.py      DuckDB star schema (sql/schema.sql) + KPI queries + integrity checks
  └─ src/04_build_dashboard.py      packs incidents into JSON → dashboard/index.html (from dashboard/template.html)
```

## Food Plant Safety Command Centre (dashboard)
Open `dashboard/index.html` in any browser (internet needed for the chart library and fonts). Everything is interactive and filters together:
- **Filters:** sub-sector, year range, and hazard (click any Pareto bar or risk-matrix cell)
- **KPI strip:** reports, amputation rate vs benchmark, controllable share of amputations, finger/hand share, hospitalisation and inspection rates
- **Hazard Pareto:** amputations, all injuries and cumulative % by hazard
- **US dot map:** every incident plotted on an Albers equal-area projection, amputations highlighted
- **Risk matrix:** amputations by sub-sector × hazard heatmap
- **Equipment and body-part breakdowns**
- **CAPA plan:** priorities re-ranked live from the filtered data, with controls following the hierarchy of controls and an owner for each
- **Case file:** real OSHA incident narratives sampled per hazard
- **Data quality log:** all 12 checks with rows flagged and the action taken

**Star schema:** `fact_incident` (6,862 rows) with `dim_date`, `dim_industry`, `dim_hazard`, `dim_event` (event type + equipment), `dim_injury` (nature + body part). The tables load directly into Power BI.

**Data quality checks (12):** duplicate IDs (5 removed), duplicate rows, unparseable or future dates, missing or malformed NAICS (180 flagged), missing state, out-of-range coordinates (100 nulled), missing or negative severity counts (8 filled), no severity outcome, and missing narratives.

**Hazard classification:** rule-based NLP (regex) on the free-text incident narratives, mapped to 7 hazard categories. I spot-checked a random sample of 300 narratives to tune the rules.

## Run it
```bash
pip install -r requirements.txt
python src/01_clean_and_validate.py data/raw/January2015toNovember2025.csv
python src/02_ehsq_analysis.py
python src/03_build_warehouse.py
python src/04_build_dashboard.py
```

## Limitations
- OSHA SIR mainly covers federal-OSHA jurisdictions. Several state-plan states (e.g. California, Washington) are under-represented, so the data is not a full national count.
- "Inspection opened" is OSHA's regulatory follow-up. It is a proxy for an investigation trigger, not the employer's internal CAPA record.
- Hazard categories are rule-based and approximate (first matching rule wins).

## Next phase
Add FDA food recall enforcement data (openFDA) and Open Food Facts recipe/allergen data to cover the quality and recipe-specification (PLM) side.
