# Power BI Build Guide

The PNG previews in `screenshots/` are rendered by `scripts/render_dashboard_previews.py`
from the same SQL views Power BI reads. Follow these steps to build the interactive
`.pbix` version on top of the same data.

## 1. Connect

1. Run `./run_all.sh` (or the steps in the main README) so the database and views exist.
2. Power BI Desktop → **Get data → PostgreSQL database**
   - Server: `localhost:5432` · Database: `amazon_ppc` · Mode: **Import**
3. Select these tables/views:
   `fact_search_terms`, `dim_campaign`, `dim_product`, `vw_daily_kpis`,
   `vw_negative_candidates`, `vw_harvest_candidates`, `vw_search_term_kpis`

## 2. Model

| From | To | Cardinality |
|---|---|---|
| `fact_search_terms[campaign_id]` | `dim_campaign[campaign_id]` | Many → One |
| `vw_daily_kpis[campaign_name]` | `dim_campaign[campaign_name]` | Many → One |
| `vw_negative_candidates[campaign_name]` | `dim_campaign[campaign_name]` | Many → One |

Add a date table (`CALENDAR(DATE(2026,7,1), DATE(2026,9,28))`) and relate it to
`fact_search_terms[report_date]` and `vw_daily_kpis[report_date]`.
Paste the measures from `measures.dax`.

## 3. Pages

### Page 1: Executive Overview
- **Slicers (one row on top):** date range, `dim_campaign[targeting_strategy]`
- **Cards:** Spend, Sales, ACoS (with `ACoS Status` as subtitle), ROAS, CVR (CTR below), Wasted Spend %
- **Column chart:** weekly Spend
- **Line chart (separate visual):** weekly ACoS with constant lines at 30% (target) and 40% (break-even).
  Keep spend and ACoS in two visuals; don't use a dual-axis combo chart.
- **Bar charts:** ACoS by campaign type (constant line at 30%), Spend by campaign type

### Page 2: Wasted Spend Tracker
- **Cards:** Wasted Spend, Wasted Spend %, Rows To Act On, Zero-Order Spend
- **Bar chart:** top 15 rows by `spend`, legend = `recommended_action`
- **Bar chart:** wasted spend by intent category (add the CASE from `sql/04_impact_summary.sql`
  as a calculated column, or as a column in the view)
- **Table:** full `vw_negative_candidates` with conditional formatting on `recommended_action`
- **Drill-through:** to a daily trend page filtered on `search_term`

### Page 3: Keyword Performance Matrix
- **Scatter:** x = `cvr`, y = `acos`, size = `spend`, details = `search_term`,
  filter `clicks >= 15` and `orders > 0`
- **Constant lines:** x = account CVR, y = 30%
- **Legend:** in harvest list vs not (merge `vw_harvest_candidates` on `search_term`)
- **Table:** `vw_harvest_candidates` with `harvest_tier` and `suggested_exact_bid`

## 4. Export

Save as `dashboard/amazon_ppc_optimization.pbix`, then replace or add to the PNGs in
`screenshots/` with real Power BI screenshots.
