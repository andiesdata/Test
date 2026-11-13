-- sql/04_impact_summary.sql
-- Purpose : Baseline KPIs and before/after projection used in the README (Section 8)
-- Run     : after 03_dashboard_views.sql
--           psql -d amazon_ppc -f sql/04_impact_summary.sql

\echo '== Baseline (whole account) =='
SELECT
    SUM(impressions)                                            AS impressions,
    SUM(clicks)                                                 AS clicks,
    SUM(spend)                                                  AS spend,
    SUM(orders_7d)                                              AS orders,
    SUM(sales_7d)                                               AS sales,
    ROUND(100.0 * SUM(clicks) / SUM(impressions), 2)            AS ctr_pct,
    ROUND(SUM(spend) / SUM(clicks), 2)                          AS cpc,
    ROUND(100.0 * SUM(orders_7d) / SUM(clicks), 1)              AS cvr_pct,
    ROUND(100.0 * SUM(spend) / SUM(sales_7d), 1)                AS acos_pct,
    ROUND(SUM(sales_7d) / SUM(spend), 2)                        AS roas,
    ROUND(SUM(sales_7d) / SUM(orders_7d), 2)                    AS aov,
    COUNT(DISTINCT customer_search_term)                        AS unique_search_terms
FROM fact_search_terms;

\echo '== Performance by campaign type =='
SELECT
    c.targeting_strategy,
    SUM(f.spend)                                                AS spend,
    SUM(f.sales_7d)                                             AS sales,
    ROUND(100.0 * SUM(f.orders_7d) / SUM(f.clicks), 1)          AS cvr_pct,
    ROUND(100.0 * SUM(f.spend) / NULLIF(SUM(f.sales_7d), 0), 1) AS acos_pct
FROM fact_search_terms f
JOIN dim_campaign c ON c.campaign_id = f.campaign_id
GROUP BY 1
ORDER BY acos_pct;

\echo '== Wasted spend by status and action (Query 1) =='
SELECT
    waste_status,
    recommended_action,
    COUNT(*)                                                    AS rows,
    COUNT(DISTINCT search_term)                                 AS unique_terms,
    SUM(spend)                                                  AS spend,
    SUM(sales)                                                  AS sales
FROM vw_negative_candidates
GROUP BY ROLLUP (1, 2)
ORDER BY 1 NULLS LAST, 2 NULLS LAST;

\echo '== Pareto: share of wasted spend in the top 20% of flagged rows =='
SELECT
    ROUND(100.0 * SUM(spend) FILTER (WHERE rn <= CEIL(0.2 * n)) / SUM(spend), 1) AS top20pct_share
FROM (SELECT spend, ROW_NUMBER() OVER (ORDER BY spend DESC) AS rn, COUNT(*) OVER () AS n
      FROM vw_negative_candidates) t;

\echo '== Waste below the click threshold (1-14 clicks, 0 orders): not actionable per term =='
WITH t AS (
    SELECT f.campaign_id, f.ad_group_name, f.customer_search_term,
           SUM(f.clicks) AS clicks, SUM(f.spend) AS spend, SUM(f.orders_7d) AS orders
    FROM fact_search_terms f
    JOIN dim_campaign c ON c.campaign_id = f.campaign_id
    WHERE c.targeting_strategy <> 'EXACT'
    GROUP BY 1, 2, 3
)
SELECT COUNT(*) AS terms, SUM(spend) AS spend
FROM t
WHERE orders = 0 AND clicks < 15 AND spend < 11.00;

\echo '== Harvest list by tier (Query 2) =='
SELECT
    harvest_tier,
    COUNT(*)                                                    AS keywords,
    SUM(clicks)                                                 AS clicks,
    SUM(spend)                                                  AS spend,
    SUM(orders)                                                 AS orders,
    SUM(sales)                                                  AS sales,
    ROUND(100.0 * SUM(orders) / SUM(clicks), 1)                 AS cvr_pct,
    ROUND(100.0 * SUM(spend) / SUM(sales), 1)                   AS acos_pct,
    ROUND(SUM(sales) / SUM(spend), 2)                           AS roas
FROM vw_harvest_candidates
GROUP BY ROLLUP (1)
ORDER BY 1 NULLS LAST;

\echo '== Before / after projection =='
-- Assumptions (edit here):
--   * every flagged row is removed: its spend AND its attributed sales disappear
--   * part of the freed budget is reinvested in harvested Exact keywords
--   * reinvested budget earns 80% of the ROAS the harvest list showed (haircut for
--     higher bids and diminishing returns)
WITH base AS (
    SELECT SUM(spend) AS spend, SUM(sales_7d) AS sales FROM fact_search_terms
),
waste AS (
    SELECT SUM(spend) AS spend, SUM(sales) AS sales FROM vw_negative_candidates
),
harvest AS (
    SELECT SUM(sales) / SUM(spend) AS roas FROM vw_harvest_candidates
),
assumptions AS (
    SELECT 0.40::numeric AS reinvest_share, 0.80::numeric AS roas_haircut
),
scenarios AS (
    SELECT 1 AS ord, 'Baseline' AS scenario, b.spend, b.sales
    FROM base b
    UNION ALL
    SELECT 2, 'After cutting waste', b.spend - w.spend, b.sales - w.sales
    FROM base b, waste w
    UNION ALL
    SELECT 3, 'Cut waste + reinvest',
           b.spend - w.spend + w.spend * a.reinvest_share,
           b.sales - w.sales + w.spend * a.reinvest_share * h.roas * a.roas_haircut
    FROM base b, waste w, harvest h, assumptions a
)
SELECT
    scenario,
    ROUND(spend, 0)                                             AS spend,
    ROUND(sales, 0)                                             AS sales,
    ROUND(100.0 * spend / sales, 1)                             AS acos_pct,
    ROUND(sales / spend, 2)                                     AS roas,
    ROUND(100.0 * (spend / FIRST_VALUE(spend) OVER (ORDER BY ord) - 1), 1) AS spend_change_pct,
    ROUND(100.0 * (sales / FIRST_VALUE(sales) OVER (ORDER BY ord) - 1), 1) AS sales_change_pct
FROM scenarios
ORDER BY ord;

\echo '== Assumed ROAS on reinvested budget =='
SELECT ROUND(SUM(sales) / SUM(spend) * 0.80, 2) AS assumed_roas FROM vw_harvest_candidates;

\echo '== Wasted spend by intent category (dashboard treemap) =='
SELECT
    CASE
        WHEN search_term ~ '^b0[a-z0-9]{8}$'                                   THEN 'Competitor ASIN'
        WHEN search_term ~ '(supplement|capsule|pill|gumm|curcumin|joint|inflammation|ginger|latte|tea$)'
                                                                                THEN 'Supplement / ingestible'
        WHEN search_term ~ '(hair|shampoo|conditioner|beard)'                   THEN 'Haircare'
        WHEN search_term ~ '(powder|root|extract|live plant|vera plant|leaves|juice|drink|recipe|diy|vera gel|gel for|gel organic)'
                                                                                THEN 'Raw ingredient / DIY'
        WHEN search_term ~ '(\mmen\M|mens|dog|baby|pet)'                        THEN 'Wrong audience'
        WHEN search_term ~ '(soap bar|body wash|lotion|toner|serum|mask|moisturizer|sunscreen|after sun)'
                                                                                THEN 'Wrong product format'
        WHEN search_term ~ '(acne|medication|prescription)'                     THEN 'Drug-claim intent'
        WHEN orders > 0                                                         THEN 'Generic head term (unprofitable)'
        ELSE                                                                         'Other long tail'
    END                                                         AS intent_category,
    COUNT(DISTINCT search_term)                                 AS terms,
    SUM(spend)                                                  AS spend,
    ROUND(100.0 * SUM(spend) / SUM(SUM(spend)) OVER (), 1)      AS pct_of_waste
FROM vw_negative_candidates
GROUP BY 1
ORDER BY spend DESC;

\echo '== Wasted spend by source campaign type =='
SELECT c.targeting_strategy,
       SUM(n.spend)                                             AS spend,
       ROUND(100.0 * SUM(n.spend) / SUM(SUM(n.spend)) OVER (), 1) AS pct_of_waste
FROM vw_negative_candidates n
JOIN dim_campaign c ON c.campaign_name = n.campaign_name
GROUP BY 1
ORDER BY spend DESC;

\echo '== Keyword cluster economics: values-based long tail vs generic head terms =='
SELECT
    CASE
        WHEN search_term ~ '(vegan|cruelty free|alcohol free|without alcohol|herbal|plant based)'
         AND search_term ~ '(turmeric|aloe)'                    THEN '1. Ingredient + value claim'
        WHEN search_term ~ '(turmeric|aloe)'                    THEN '2. Ingredient only'
        WHEN search_term IN ('face wash', 'facial cleanser', 'face cleanser', 'gentle face wash',
                             'gentle foaming cleanser', 'face wash for women', 'daily face wash',
                             'foaming face wash', 'gel cleanser', 'face wash for sensitive skin',
                             'cleanser for sensitive skin', 'best face wash', 'face wash for dry skin',
                             'face wash for oily skin', 'korean face wash', 'hydrating facial cleanser',
                             'dermatologist recommended face wash', 'skin care')
                                                                THEN '3. Generic head term'
        ELSE '4. Other'
    END                                                         AS cluster,
    COUNT(*)                                                    AS terms,
    SUM(clicks)                                                 AS clicks,
    ROUND(SUM(spend) / SUM(clicks), 2)                          AS cpc,
    ROUND(100.0 * SUM(orders) / SUM(clicks), 1)                 AS cvr_pct,
    ROUND(100.0 * SUM(spend) / NULLIF(SUM(sales), 0), 1)        AS acos_pct
FROM vw_search_term_kpis
WHERE search_term !~ '(terrabloom|terra bloom|^b0)'
  AND search_term !~ '(supplement|capsule|pill|powder|shampoo|hair|juice|plant|serum|toner|soap bar|tea$)'
GROUP BY 1
ORDER BY 1;

\echo '== Cannibalization: converting search terms served by 3+ campaigns =='
SELECT COUNT(*) FILTER (WHERE n_campaigns >= 3)                 AS terms_in_3plus_campaigns,
       ROUND(100.0 * SUM(sales) FILTER (WHERE n_campaigns >= 3) / SUM(sales), 1) AS pct_of_sales
FROM vw_search_term_kpis
WHERE orders > 0;
