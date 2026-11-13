-- sql/02_keyword_harvesting.sql
-- Purpose : Find proven converting search terms in discovery campaigns
--           and promote them to Exact match with a data-driven bid
-- Dialect : PostgreSQL 15+

WITH params AS (
    SELECT
        0.30::numeric      AS target_acos,
        2                  AS min_orders,
        8                  AS min_clicks,
        20                 AS min_clicks_confident, -- Tier 1/2 need enough clicks to trust CVR
        1.30::numeric      AS max_bid_uplift,      -- cap: +30% vs historical CPC
        DATE '2026-07-01'  AS start_date,
        DATE '2026-09-28'  AS end_date
),

-- Step 1: Account-level benchmark, so "good" is relative to this account
account_baseline AS (
    SELECT
        SUM(f.orders_7d)::numeric / NULLIF(SUM(f.clicks), 0) AS account_cvr
    FROM fact_search_terms f
    CROSS JOIN params p
    WHERE f.report_date BETWEEN p.start_date AND p.end_date
),

-- Step 2: Search terms discovered by Auto / Broad / Phrase campaigns
source_terms AS (
    SELECT
        LOWER(TRIM(f.customer_search_term))                     AS search_term,
        STRING_AGG(DISTINCT c.campaign_name || ' > ' || f.ad_group_name, ' | ')
                                                                AS source_ad_groups,
        COUNT(DISTINCT f.campaign_id)                           AS n_campaigns_triggered,
        SUM(f.impressions)                                      AS impressions,
        SUM(f.clicks)                                           AS clicks,
        SUM(f.spend)                                            AS spend,
        SUM(f.orders_7d)                                        AS orders,
        SUM(f.sales_7d)                                         AS sales
    FROM fact_search_terms f
    JOIN dim_campaign c ON c.campaign_id = f.campaign_id
    CROSS JOIN params p
    WHERE f.report_date BETWEEN p.start_date AND p.end_date
      AND c.targeting_strategy IN ('AUTO', 'BROAD', 'PHRASE')
      AND f.customer_search_term !~* '^b0[a-z0-9]{8}$'          -- ASINs are handled separately
      AND f.customer_search_term !~* '(terrabloom|terra bloom)' -- brand terms live in Brand Defense
    GROUP BY 1
),

-- Step 3: Keywords already live as Exact (used for the anti-join)
existing_exact AS (
    SELECT DISTINCT LOWER(TRIM(keyword_text)) AS keyword_text
    FROM dim_keyword
    WHERE match_type = 'EXACT'
      AND state = 'ENABLED'
),

-- Step 4: KPIs per candidate
candidates AS (
    SELECT
        s.*,
        ROUND(s.spend           / NULLIF(s.clicks, 0), 2)  AS cpc,
        ROUND(s.orders::numeric / NULLIF(s.clicks, 0), 4)  AS cvr,
        ROUND(s.spend           / NULLIF(s.sales, 0), 4)   AS acos,
        ROUND(s.sales           / NULLIF(s.clicks, 0), 2)  AS rpc
    FROM source_terms s
    LEFT JOIN existing_exact e
           ON e.keyword_text = s.search_term
    CROSS JOIN params p
    WHERE e.keyword_text IS NULL                            -- not yet harvested
      AND s.orders >= p.min_orders
      AND s.clicks >= p.min_clicks
),

-- Step 5: Tier the candidates
tiered AS (
    SELECT
        c.*,
        CASE
            WHEN c.orders >= 5
             AND c.clicks >= p.min_clicks_confident
             AND c.cvr  >= b.account_cvr * 1.5
             AND c.acos <= p.target_acos * 0.75             THEN 'TIER 1 - Scale aggressively'
            WHEN c.orders >= 3
             AND c.clicks >= p.min_clicks_confident
             AND c.cvr  >= b.account_cvr
             AND c.acos <= p.target_acos                    THEN 'TIER 2 - Promote, standard bid'
            WHEN c.acos <= p.target_acos                    THEN 'TIER 3 - Promote, test bid'
            ELSE NULL                                       -- converts but too expensive: not harvested
        END AS harvest_tier
    FROM candidates c
    CROSS JOIN account_baseline b
    CROSS JOIN params p
),

-- Step 6: Launch bid = what a click is worth (RPC x target ACoS), with guardrails
scored AS (
    SELECT
        t.*,
        ROUND(
            CASE
                -- Low-data terms: a few lucky orders inflate RPC, so never bid above current CPC
                WHEN t.harvest_tier LIKE 'TIER 3%'
                    THEN LEAST(t.rpc * p.target_acos, t.cpc)
                -- Proven terms: allow up to +30% vs historical CPC to win better placements
                ELSE LEAST(t.rpc * p.target_acos, t.cpc * p.max_bid_uplift)
            END
        , 2) AS suggested_exact_bid
    FROM tiered t
    CROSS JOIN params p
)

SELECT
    RANK() OVER (ORDER BY harvest_tier, sales DESC)          AS priority,
    search_term                                              AS new_exact_keyword,
    harvest_tier,
    suggested_exact_bid,
    clicks,
    spend,
    orders,
    sales,
    cpc,
    cvr,
    acos,
    rpc,
    n_campaigns_triggered,
    source_ad_groups,
    'ADD EXACT to [SP] Manual-Exact-Harvest; ADD NEGATIVE EXACT in source ad groups'
                                                             AS action
FROM scored
WHERE harvest_tier IS NOT NULL
ORDER BY priority;
