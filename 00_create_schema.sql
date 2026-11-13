-- sql/00_create_schema.sql
-- Purpose : Create the raw (landing) and analytics (star schema) layers
-- Dialect : PostgreSQL 15+
-- Run     : psql -d amazon_ppc -f sql/00_create_schema.sql

DROP SCHEMA IF EXISTS raw CASCADE;
CREATE SCHEMA raw;

-- ---------------------------------------------------------------------------
-- RAW LAYER: column names mirror the Amazon Ads console export 1:1.
-- Everything lands as TEXT, so a malformed export never breaks the load.
-- ---------------------------------------------------------------------------
CREATE TABLE raw.sp_search_term_report (
    "Date"                                      TEXT,
    "Portfolio name"                            TEXT,
    "Currency"                                  TEXT,
    "Campaign Name"                             TEXT,
    "Ad Group Name"                             TEXT,
    "Targeting"                                 TEXT,
    "Match Type"                                TEXT,
    "Customer Search Term"                      TEXT,
    "Impressions"                               TEXT,
    "Clicks"                                    TEXT,
    "Click-Thru Rate (CTR)"                     TEXT,
    "Cost Per Click (CPC)"                      TEXT,
    "Spend"                                     TEXT,
    "7 Day Total Sales "                        TEXT,   -- trailing space is how Amazon exports it
    "Total Advertising Cost of Sales (ACOS) "   TEXT,
    "Total Return on Advertising Spend (ROAS)"  TEXT,
    "7 Day Total Orders (#)"                    TEXT,
    "7 Day Total Units (#)"                     TEXT,
    "7 Day Conversion Rate"                     TEXT
);

CREATE TABLE raw.sp_campaigns (
    campaign_id       TEXT,
    "Campaign Name"   TEXT,
    "Targeting Type"  TEXT,
    "Daily Budget"    TEXT,
    "State"           TEXT,
    "Portfolio name"  TEXT
);

CREATE TABLE raw.sp_keywords (
    keyword_id       TEXT,
    campaign_id      TEXT,
    "Ad Group Name"  TEXT,
    "Keyword Text"   TEXT,
    "Match Type"     TEXT,
    "Bid"            TEXT,
    "State"          TEXT
);

-- ---------------------------------------------------------------------------
-- ANALYTICS LAYER: typed star schema used by every query and the dashboard
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_search_terms CASCADE;
DROP TABLE IF EXISTS dim_keyword       CASCADE;
DROP TABLE IF EXISTS dim_campaign      CASCADE;
DROP TABLE IF EXISTS dim_product       CASCADE;

CREATE TABLE dim_campaign (
    campaign_id         INT PRIMARY KEY,
    campaign_name       TEXT NOT NULL UNIQUE,
    targeting_strategy  TEXT NOT NULL
        CHECK (targeting_strategy IN ('AUTO', 'BROAD', 'PHRASE', 'EXACT', 'PRODUCT')),
    daily_budget        NUMERIC(10, 2),
    state               TEXT
);

CREATE TABLE dim_keyword (
    keyword_id     INT PRIMARY KEY,
    campaign_id    INT REFERENCES dim_campaign (campaign_id),
    ad_group_name  TEXT,
    keyword_text   TEXT NOT NULL,
    match_type     TEXT CHECK (match_type IN ('BROAD', 'PHRASE', 'EXACT')),
    bid            NUMERIC(6, 2),
    state          TEXT
);

CREATE TABLE dim_product (
    asin              TEXT PRIMARY KEY,
    product_name      TEXT,
    price             NUMERIC(8, 2),
    cogs              NUMERIC(8, 2),
    fba_fee           NUMERIC(8, 2),
    referral_fee_pct  NUMERIC(5, 4),
    -- Break-even ACoS = contribution margin before ads / price
    break_even_acos   NUMERIC(6, 4) GENERATED ALWAYS AS
        ((price - cogs - fba_fee - price * referral_fee_pct) / price) STORED
);

CREATE TABLE fact_search_terms (
    id                    BIGSERIAL PRIMARY KEY,
    report_date           DATE NOT NULL,
    campaign_id           INT  NOT NULL REFERENCES dim_campaign (campaign_id),
    ad_group_name         TEXT NOT NULL,
    targeting             TEXT,
    match_type            TEXT,
    customer_search_term  TEXT NOT NULL,
    impressions           INT           NOT NULL DEFAULT 0,
    clicks                INT           NOT NULL DEFAULT 0,
    spend                 NUMERIC(10, 2) NOT NULL DEFAULT 0,
    orders_7d             INT           NOT NULL DEFAULT 0,
    units_7d              INT           NOT NULL DEFAULT 0,
    sales_7d              NUMERIC(10, 2) NOT NULL DEFAULT 0
);

CREATE INDEX idx_fst_date      ON fact_search_terms (report_date);
CREATE INDEX idx_fst_campaign  ON fact_search_terms (campaign_id);
CREATE INDEX idx_fst_term      ON fact_search_terms (LOWER(customer_search_term));
