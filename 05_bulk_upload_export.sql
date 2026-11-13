-- sql/05_bulk_upload_export.sql
-- Purpose : Turn the Query 1 / Query 2 results into rows for the Amazon Ads
--           Sponsored Products bulk sheet (name-based columns)
-- Run     : psql -d amazon_ppc --csv -f sql/05_bulk_upload_export.sql -o outputs/bulk_upload_sponsored_products.csv
-- Note    : The harvest campaign "SP | Exact | Harvest" / ad group "Exact - Harvest" must exist
--           (create it in the console or add Campaign + Ad Group rows to the sheet first).
--           Always review the file before uploading.

WITH negatives AS (
    SELECT
        'Sponsored Products'                                     AS "Product",
        CASE WHEN recommended_action = 'NEGATIVE PRODUCT TARGET'
             THEN 'Negative Product Targeting' ELSE 'Negative Keyword' END
                                                                 AS "Entity",
        'Create'                                                 AS "Operation",
        campaign_name                                            AS "Campaign Name",
        ad_group_name                                            AS "Ad Group Name",
        CASE WHEN recommended_action = 'NEGATIVE PRODUCT TARGET' THEN NULL ELSE search_term END
                                                                 AS "Keyword Text",
        CASE recommended_action
             WHEN 'NEGATIVE EXACT'  THEN 'negativeExact'
             WHEN 'NEGATIVE PHRASE' THEN 'negativePhrase'
        END                                                      AS "Match Type",
        CASE WHEN recommended_action = 'NEGATIVE PRODUCT TARGET'
             THEN 'asin="' || UPPER(search_term) || '"' END      AS "Product Targeting Expression",
        NULL::numeric                                            AS "Bid",
        'enabled'                                                AS "State",
        'Q1 ' || waste_status                                    AS "Reason"
    FROM vw_negative_candidates
    WHERE recommended_action LIKE 'NEGATIVE%'
),
-- Negative Phrase is applied once per ad group, so drop duplicate rows
negatives_dedup AS (
    SELECT DISTINCT ON ("Campaign Name", "Ad Group Name", "Keyword Text", "Match Type",
                        "Product Targeting Expression") *
    FROM negatives
),
harvest_keywords AS (
    SELECT
        'Sponsored Products', 'Keyword', 'Create',
        'SP | Exact | Harvest', 'Exact - Harvest',
        new_exact_keyword, 'exact', NULL, suggested_exact_bid, 'enabled',
        'Q2 ' || harvest_tier
    FROM vw_harvest_candidates
),
-- Isolation: block each harvested term in every ad group that found it
harvest_isolation AS (
    SELECT DISTINCT
        'Sponsored Products', 'Negative Keyword', 'Create',
        c.campaign_name, f.ad_group_name,
        h.new_exact_keyword, 'negativeExact', NULL, NULL::numeric, 'enabled',
        'Q2 isolation'
    FROM vw_harvest_candidates h
    JOIN fact_search_terms f ON f.customer_search_term = h.new_exact_keyword
    JOIN dim_campaign c      ON c.campaign_id = f.campaign_id
    WHERE c.targeting_strategy IN ('AUTO', 'BROAD', 'PHRASE')
)
SELECT * FROM negatives_dedup
UNION ALL SELECT * FROM harvest_keywords
UNION ALL SELECT * FROM harvest_isolation
ORDER BY "Reason", "Campaign Name", "Ad Group Name", "Keyword Text";
