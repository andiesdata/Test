-- sql/03_dashboard_views.sql
-- Purpose : Views consumed by the Power BI dashboard
-- Run     : from the repository root (it reads the two analysis queries from disk,
--           so the dashboard and the exported action lists always share one logic)
--           psql -d amazon_ppc -f sql/03_dashboard_views.sql

DROP VIEW IF EXISTS vw_daily_kpis, vw_search_term_kpis, vw_negative_candidates, vw_harvest_candidates CASCADE;

-- Page 1: daily KPIs by campaign
CREATE VIEW vw_daily_kpis AS
SELECT
    f.report_date,
    c.campaign_name,
    c.targeting_strategy,
    SUM(f.impressions)                                          AS impressions,
    SUM(f.clicks)                                               AS clicks,
    SUM(f.spend)                                                AS spend,
    SUM(f.orders_7d)                                            AS orders,
    SUM(f.sales_7d)                                             AS sales,
    ROUND(SUM(f.spend) / NULLIF(SUM(f.sales_7d), 0), 4)         AS acos,
    ROUND(SUM(f.sales_7d) / NULLIF(SUM(f.spend), 0), 2)         AS roas
FROM fact_search_terms f
JOIN dim_campaign c ON c.campaign_id = f.campaign_id
GROUP BY 1, 2, 3;

-- Page 3: one row per search term (all campaigns), with quadrant for the scatter matrix
CREATE VIEW vw_search_term_kpis AS
WITH agg AS (
    SELECT
        f.customer_search_term                                  AS search_term,
        SUM(f.impressions) AS impressions, SUM(f.clicks) AS clicks, SUM(f.spend) AS spend,
        SUM(f.orders_7d)   AS orders,      SUM(f.sales_7d) AS sales,
        COUNT(DISTINCT f.campaign_id)                           AS n_campaigns
    FROM fact_search_terms f
    GROUP BY 1
),
baseline AS (
    SELECT SUM(orders_7d)::numeric / SUM(clicks) AS account_cvr FROM fact_search_terms
)
SELECT
    a.*,
    ROUND(a.clicks::numeric / NULLIF(a.impressions, 0), 4)      AS ctr,
    ROUND(a.spend / NULLIF(a.clicks, 0), 2)                     AS cpc,
    ROUND(a.orders::numeric / NULLIF(a.clicks, 0), 4)           AS cvr,
    ROUND(a.spend / NULLIF(a.sales, 0), 4)                      AS acos,
    CASE
        WHEN a.clicks < 15                                         THEN 'Not enough data'
        WHEN a.orders::numeric / a.clicks >= b.account_cvr
         AND a.spend <= 0.30 * a.sales                             THEN 'Star'
        WHEN a.orders::numeric / a.clicks <  b.account_cvr
         AND a.spend <= 0.30 * a.sales                             THEN 'Hidden Gem'
        WHEN a.orders::numeric / a.clicks >= b.account_cvr         THEN 'Over-bid'
        ELSE                                                            'Bleeder'
    END                                                         AS quadrant
FROM agg a
CROSS JOIN baseline b;

-- Page 2: action list from Query 1
\set q1 `cat sql/01_wasted_spend_negatives.sql`
CREATE VIEW vw_negative_candidates AS
:q1

-- Harvest list from Query 2
\set q2 `cat sql/02_keyword_harvesting.sql`
CREATE VIEW vw_harvest_candidates AS
:q2
