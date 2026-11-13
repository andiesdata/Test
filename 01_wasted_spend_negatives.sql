-- sql/01_wasted_spend_negatives.sql
-- Purpose : Identify search terms that burn budget without profitable return
-- Output  : Ad-group-level negative keyword list, ready for Amazon Bulk Operations
-- Dialect : PostgreSQL 15+

WITH params AS (
    SELECT
        0.30::numeric        AS target_acos,
        0.40::numeric        AS break_even_acos,     -- see dim_product.break_even_acos
        27.50::numeric       AS avg_order_value,
        15                   AS min_clicks_no_order,
        20                   AS min_clicks_bleeder,
        1.75::numeric        AS bleeder_multiplier,  -- 1.75 x 40% = ACoS >= 70%
        DATE '2026-07-01'    AS start_date,
        DATE '2026-09-28'    AS end_date
),

-- Step 1: Aggregate to ad-group x search-term grain (where negatives are applied)
term_perf AS (
    SELECT
        c.campaign_id,
        c.campaign_name,
        c.targeting_strategy,
        f.ad_group_name,
        LOWER(TRIM(f.customer_search_term))  AS search_term,
        SUM(f.impressions)                   AS impressions,
        SUM(f.clicks)                        AS clicks,
        SUM(f.spend)                         AS spend,
        SUM(f.orders_7d)                     AS orders,
        SUM(f.sales_7d)                      AS sales
    FROM fact_search_terms f
    JOIN dim_campaign c  ON c.campaign_id = f.campaign_id
    CROSS JOIN params p
    WHERE f.report_date BETWEEN p.start_date AND p.end_date
      AND c.targeting_strategy <> 'EXACT'          -- Exact terms are managed via bids, not negatives
    GROUP BY 1, 2, 3, 4, 5
),

-- Step 2: Derive core KPIs with safe division, and flag the term's nature
term_kpis AS (
    SELECT
        t.*,
        ROUND(t.clicks::numeric  / NULLIF(t.impressions, 0), 4) AS ctr,
        ROUND(t.spend            / NULLIF(t.clicks, 0), 2)      AS cpc,
        ROUND(t.orders::numeric  / NULLIF(t.clicks, 0), 4)      AS cvr,
        ROUND(t.spend            / NULLIF(t.sales, 0), 4)       AS acos,
        ROUND(t.sales            / NULLIF(t.spend, 0), 2)       AS roas,
        (t.search_term ~ '^b0[a-z0-9]{8}$')                     AS is_asin,
        (t.search_term ~ '(terrabloom|terra bloom)')            AS is_brand,
        -- Irrelevant intent = the whole query family is off-target -> block with Negative Phrase
        (t.search_term ~ '\m(supplements?|capsules?|pills?|gummies|powder|curcumin|root|extract|latte|joint|inflammation|hair|shampoo|conditioner|juice|drink|live plant|aloe vera plant|leaves|recipe|diy|dogs?|pets?|medication|prescription|sample)\M')
                                                                AS is_irrelevant_intent,
        -- Search term IS one of our own Broad/Phrase keywords -> fix the keyword, don't negate it
        EXISTS (SELECT 1
                FROM dim_keyword k
                WHERE k.campaign_id   = t.campaign_id
                  AND k.ad_group_name = t.ad_group_name
                  AND k.keyword_text  = t.search_term
                  AND k.state = 'ENABLED')                      AS is_own_keyword
    FROM term_perf t
),

-- Step 3: Classify every term with a CASE WHEN decision tree (order matters)
classified AS (
    SELECT
        k.*,
        CASE
            WHEN k.is_brand
                THEN 'BRAND_PROTECTED'
            WHEN k.orders = 0
             AND (k.clicks >= p.min_clicks_no_order
                  OR k.spend >= p.avg_order_value * p.break_even_acos)
                THEN 'WASTE_ZERO_CONVERSION'
            WHEN k.orders > 0
             AND k.clicks >= p.min_clicks_bleeder
             AND k.acos  >= p.break_even_acos * p.bleeder_multiplier
                THEN 'WASTE_UNPROFITABLE'
            WHEN k.orders > 0 AND k.acos > p.target_acos
                THEN 'OPTIMIZE_BID'
            WHEN k.orders = 0
                THEN 'INSUFFICIENT_DATA'
            ELSE 'HEALTHY'
        END AS waste_status
    FROM term_kpis k
    CROSS JOIN params p
),

-- Step 4: Translate status into an executable action
actions AS (
    SELECT
        cl.*,
        CASE
            WHEN waste_status NOT IN ('WASTE_ZERO_CONVERSION', 'WASTE_UNPROFITABLE')
                                                    THEN 'NO ACTION'
            WHEN is_asin                            THEN 'NEGATIVE PRODUCT TARGET'
            WHEN is_own_keyword                     THEN 'PAUSE KEYWORD / CUT BID'
            WHEN is_irrelevant_intent               THEN 'NEGATIVE PHRASE'
            ELSE                                         'NEGATIVE EXACT'
        END AS recommended_action
    FROM classified cl
)

SELECT
    campaign_name,
    ad_group_name,
    search_term,
    waste_status,
    recommended_action,
    clicks,
    spend,
    orders,
    sales,
    cpc,
    cvr,
    acos,
    -- Share of total wasted spend, used to prioritize the review
    ROUND(100.0 * spend / SUM(spend) OVER (), 2)                     AS pct_of_wasted_spend,
    SUM(spend) OVER (ORDER BY spend DESC
                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_wasted_spend
FROM actions
WHERE recommended_action <> 'NO ACTION'
ORDER BY spend DESC;
