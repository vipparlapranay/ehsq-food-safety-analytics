-- EHSQ star schema (DuckDB). Grain of fact table: one severe injury report.
CREATE OR REPLACE TABLE dim_date AS
SELECT DISTINCT CAST(EventDate AS DATE) AS date_key,
       year(CAST(EventDate AS DATE))    AS year,
       quarter(CAST(EventDate AS DATE)) AS quarter,
       month(CAST(EventDate AS DATE))   AS month
FROM stg_incidents;

CREATE OR REPLACE TABLE dim_industry AS
SELECT DISTINCT NAICS AS naics_code, substr(NAICS, 1, 4) AS naics_4, Subsector AS subsector
FROM stg_incidents;

CREATE OR REPLACE TABLE dim_hazard AS
SELECT row_number() OVER (ORDER BY Hazard) AS hazard_key, Hazard AS hazard_category
FROM (SELECT DISTINCT Hazard FROM stg_incidents);

CREATE OR REPLACE TABLE dim_event AS
SELECT row_number() OVER (ORDER BY EventTitle, SourceTitle) AS event_key,
       EventTitle AS event_type, SourceTitle AS equipment_source
FROM (SELECT DISTINCT EventTitle, SourceTitle FROM stg_incidents);

CREATE OR REPLACE TABLE dim_injury AS
SELECT row_number() OVER (ORDER BY NatureTitle, "Part of Body Title") AS injury_key,
       NatureTitle AS injury_nature, "Part of Body Title" AS body_part
FROM (SELECT DISTINCT NatureTitle, "Part of Body Title" FROM stg_incidents);

CREATE OR REPLACE TABLE fact_incident AS
SELECT s.ID AS incident_id,
       CAST(s.EventDate AS DATE) AS date_key,
       s.NAICS AS naics_code,
       s.State AS state,
       h.hazard_key, e.event_key, i.injury_key,
       s.Hospitalized AS hospitalised_count,
       s.Amputation   AS amputation_count,
       s."Loss of Eye" AS loss_of_eye_count,
       s.Inspected    AS osha_inspection_opened
FROM stg_incidents s
JOIN dim_hazard h ON h.hazard_category = s.Hazard
JOIN dim_event  e ON e.event_type = s.EventTitle AND e.equipment_source = s.SourceTitle
JOIN dim_injury i ON i.injury_nature = s.NatureTitle AND i.body_part = s."Part of Body Title";
