-- sql/00_load_data.sql
-- Purpose : Load the Amazon CSV exports into the raw layer, then clean and type
--           them into the analytics star schema
-- Run     : from the repository root
--           psql -d amazon_ppc -f sql/00_load_data.sql

\echo 'Loading raw CSV exports...'
TRUNCATE raw.sp_search_term_report, raw.sp_campaigns, raw.sp_keywords;
\copy raw.sp_search_term_report FROM 'data/raw/sp_search_term_report.csv' WITH (FORMAT csv, HEADER true)
\copy raw.sp_campaigns          FROM 'data/raw/sp_campaigns.csv'          WITH (FORMAT csv, HEADER true)
\copy raw.sp_keywords           FROM 'data/raw/sp_keywords.csv'           WITH (FORMAT csv, HEADER true)

\echo 'Transforming into the analytics layer...'
TRUNCATE fact_search_terms, dim_keyword, dim_product, dim_campaign RESTART IDENTITY CASCADE;

-- Campaigns
INSERT INTO dim_campaign (campaign_id, campaign_name, targeting_strategy, daily_budget, state)
SELECT campaign_id::INT,
       TRIM("Campaign Name"),
       UPPER(TRIM("Targeting Type")),
       "Daily Budget"::NUMERIC,
       UPPER("State")
FROM raw.sp_campaigns;

-- Keywords
INSERT INTO dim_keyword (keyword_id, campaign_id, ad_group_name, keyword_text, match_type, bid, state)
SELECT keyword_id::INT,
       campaign_id::INT,
       TRIM("Ad Group Name"),
       LOWER(TRIM("Keyword Text")),
       UPPER(TRIM("Match Type")),
       "Bid"::NUMERIC,
       UPPER("State")
FROM raw.sp_keywords;

-- Product economics (from finance; not part of the Amazon Ads export)
INSERT INTO dim_product (asin, product_name, price, cogs, fba_fee, referral_fee_pct)
VALUES ('B0TBLOOM01', 'TerraBloom Turmeric & Aloe Vera Gentle Foaming Face Cleanser 150ml',
        24.99, 6.25, 5.00, 0.15);

-- Search term facts: parse Amazon formats ("Jul 01, 2026", "$1,234.56", "12.5%")
INSERT INTO fact_search_terms (report_date, campaign_id, ad_group_name, targeting, match_type,
                               customer_search_term, impressions, clicks, spend,
                               orders_7d, units_7d, sales_7d)
SELECT TO_DATE(r."Date", 'Mon DD, YYYY'),
       c.campaign_id,
       TRIM(r."Ad Group Name"),
       TRIM(r."Targeting"),
       NULLIF(UPPER(TRIM(r."Match Type")), '-'),
       LOWER(TRIM(r."Customer Search Term")),
       COALESCE(NULLIF(REPLACE(r."Impressions", ',', ''), ''), '0')::INT,
       COALESCE(NULLIF(REPLACE(r."Clicks", ',', ''), ''), '0')::INT,
       COALESCE(NULLIF(REGEXP_REPLACE(r."Spend", '[$,]', '', 'g'), ''), '0')::NUMERIC,
       COALESCE(NULLIF(REPLACE(r."7 Day Total Orders (#)", ',', ''), ''), '0')::INT,
       COALESCE(NULLIF(REPLACE(r."7 Day Total Units (#)", ',', ''), ''), '0')::INT,
       COALESCE(NULLIF(REGEXP_REPLACE(r."7 Day Total Sales ", '[$,]', '', 'g'), ''), '0')::NUMERIC
FROM raw.sp_search_term_report r
JOIN dim_campaign c ON c.campaign_name = TRIM(r."Campaign Name");

ANALYZE fact_search_terms;

\echo 'Load summary:'
SELECT COUNT(*)                                   AS fact_rows,
       COUNT(DISTINCT customer_search_term)       AS unique_search_terms,
       MIN(report_date)                           AS first_day,
       MAX(report_date)                           AS last_day,
       SUM(spend)                                 AS spend,
       SUM(sales_7d)                              AS sales
FROM fact_search_terms;
