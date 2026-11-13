#!/usr/bin/env bash
# One-command rebuild: data -> database -> analysis -> exports -> dashboard previews
# Usage: ./run_all.sh [database_name]
set -euo pipefail
DB="${1:-amazon_ppc}"
cd "$(dirname "$0")"

python scripts/generate_synthetic_data.py --days 90 --seed 42
createdb "$DB" 2>/dev/null || true
psql -q -v ON_ERROR_STOP=1 -d "$DB" -f sql/00_create_schema.sql
psql -q -v ON_ERROR_STOP=1 -d "$DB" -f sql/00_load_data.sql
psql -q -v ON_ERROR_STOP=1 -d "$DB" -f sql/03_dashboard_views.sql

mkdir -p outputs
psql -d "$DB" --csv -f sql/01_wasted_spend_negatives.sql -o outputs/negative_keywords.csv
psql -d "$DB" --csv -f sql/02_keyword_harvesting.sql     -o outputs/harvest_exact_keywords.csv
psql -d "$DB" --csv -f sql/05_bulk_upload_export.sql     -o outputs/bulk_upload_sponsored_products.csv
psql -d "$DB" -f sql/04_impact_summary.sql > outputs/impact_summary.txt

python scripts/render_dashboard_previews.py --db "$DB"
echo "Done. See outputs/ and dashboard/screenshots/"
