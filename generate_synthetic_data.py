"""
Synthetic Amazon Sponsored Products data generator
==================================================

Creates three CSV files that mirror the column layout of real Amazon Ads
console exports for a fictional brand, TerraBloom Botanicals
(Turmeric & Aloe Vera Gentle Foaming Face Cleanser):

    data/raw/sp_search_term_report.csv   daily Search Term Report
    data/raw/sp_campaigns.csv            campaign list
    data/raw/sp_keywords.csv             keyword targets (Broad / Phrase / Exact)

Every search term gets a latent "true" CTR, CPC and conversion rate that
depends on shopper intent (seed keyword, long-tail winner, generic head term,
irrelevant ingredient intent, competitor ASIN, brand, random long tail).
Daily rows are then sampled with Poisson clicks and Binomial orders, so the
data has the same noise you see in a real account.

Usage:
    python scripts/generate_synthetic_data.py --days 90 --seed 42
"""

from __future__ import annotations

import argparse
import itertools
import string
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BRAND = "TerraBloom"
HERO_ASIN = "B0TBLOOM01"
PRICE_SINGLE = 24.99
PRICE_BUNDLE = 42.48          # 2-pack
BUNDLE_SHARE = 0.15

# --------------------------------------------------------------------------
# Campaign structure
# --------------------------------------------------------------------------
CAMPAIGNS = [
    # id, name, strategy, daily budget
    (101, "SP | Auto | Discovery",               "AUTO",    120.0),
    (102, "SP | Broad | Ingredient & Values",    "BROAD",    90.0),
    (103, "SP | Phrase | Core",                  "PHRASE",  110.0),
    (104, "SP | Exact | Core Performers",        "EXACT",   200.0),
    (105, "SP | Exact | Brand Defense",          "EXACT",    20.0),
    (106, "SP | Product | Competitor ASINs",     "PRODUCT",  40.0),
]

AUTO_TARGETS = ["close-match", "loose-match", "substitutes", "complements"]

# Seed keywords (Section 5 of the README) with the match types they launched in
SEED_KEYWORDS = {
    # keyword: (match types, launch bid, true CVR, true CPC)
    "natural face wash":                     (["BROAD", "PHRASE"], 1.10, 0.095, 1.32),
    "herbal face cleanser":                  (["BROAD", "PHRASE"], 0.95, 0.120, 1.05),
    "gentle face wash":                      (["PHRASE"],          1.25, 0.062, 1.55),
    "foaming facial cleanser":               (["PHRASE"],          1.15, 0.085, 1.30),
    "turmeric face wash":                    (["EXACT", "PHRASE"], 1.30, 0.165, 1.28),
    "turmeric face cleanser":                (["EXACT", "PHRASE"], 1.30, 0.158, 1.25),
    "aloe vera face wash":                   (["EXACT", "PHRASE"], 1.20, 0.138, 1.22),
    "turmeric and aloe vera cleanser":       (["EXACT"],           1.10, 0.190, 1.05),
    "green tea face wash":                   (["PHRASE"],          0.90, 0.070, 1.08),
    "vegan face wash":                       (["EXACT", "PHRASE"], 1.20, 0.142, 1.18),
    "cruelty free face cleanser":            (["EXACT", "PHRASE"], 1.15, 0.136, 1.12),
    "alcohol free face wash":                (["EXACT"],           1.00, 0.128, 1.02),
    "plant based facial cleanser":           (["PHRASE"],          0.95, 0.118, 1.00),
    "clean beauty face wash":                (["BROAD"],           0.85, 0.090, 0.95),
    "brightening face wash":                 (["PHRASE"],          1.10, 0.104, 1.25),
    "turmeric face wash for dark spots":     (["EXACT"],           1.25, 0.172, 1.20),
    "face wash for glowing skin":            (["BROAD"],           0.90, 0.088, 1.05),
    "face wash for uneven skin tone":        (["PHRASE"],          0.95, 0.098, 1.08),
    "face wash for sensitive skin":          (["PHRASE"],          1.35, 0.060, 1.62),
    "aloe vera face wash for dry skin":      (["EXACT"],           1.05, 0.150, 1.00),
    "gentle cleanser for oily skin":         (["PHRASE"],          1.00, 0.072, 1.25),
    "face wash for combination skin":        (["BROAD"],           0.90, 0.080, 1.12),
    "vegan turmeric face cleanser":          (["EXACT"],           0.95, 0.195, 0.98),
    "natural turmeric face wash for women":  (["EXACT"],           0.90, 0.176, 0.92),
    "herbal face wash without alcohol":      (["EXACT"],           0.85, 0.168, 0.88),
    "cruelty free turmeric cleanser sensitive skin": (["EXACT"],   0.80, 0.182, 0.85),
}

BRAND_TERMS = ["terrabloom", "terrabloom turmeric cleanser", "terra bloom face wash",
               "terrabloom face wash", "terrabloom aloe cleanser"]

# Long-tail winners that were never added as keywords (the harvest opportunity)
HARVEST_CANDIDATES = [
    "turmeric face wash for acne scars", "turmeric foaming cleanser", "turmeric facial cleanser vegan",
    "aloe vera facial cleanser sensitive skin", "aloe face wash alcohol free", "natural turmeric cleanser",
    "turmeric face wash for women", "turmeric gel cleanser", "vegan face wash for sensitive skin",
    "vegan facial cleanser for dry skin", "cruelty free face wash for women", "cruelty free vegan cleanser",
    "alcohol free facial cleanser for sensitive skin", "herbal turmeric face wash", "ayurvedic turmeric face wash",
    "turmeric brightening cleanser", "turmeric face wash for hyperpigmentation", "turmeric cleanser for dark spots",
    "aloe vera cleanser for oily skin", "turmeric aloe face wash", "plant based turmeric cleanser",
    "natural face wash without alcohol", "turmeric face wash for glowing skin", "vegan brightening face wash",
    "turmeric face wash sensitive skin", "organic turmeric face cleanser", "natural aloe vera face wash",
    "turmeric face wash for oily skin", "turmeric cleanser for women", "gentle turmeric face wash",
    "turmeric face cleanser for dry skin", "vegan aloe vera cleanser", "herbal face wash for women",
    "turmeric face wash 2 pack", "cruelty free alcohol free cleanser", "turmeric face wash for teens",
    "turmeric and honey face wash", "clean vegan face wash", "turmeric vitamin c face wash",
    "turmeric face wash for uneven skin tone", "aloe vera foaming cleanser", "botanical turmeric cleanser",
    "turmeric face wash for combination skin", "fragrance free turmeric cleanser",
]

# Generic head terms: volume, but expensive and low-converting for a small brand
GENERIC_HEAD = [
    "face wash", "facial cleanser", "face cleanser", "gentle foaming cleanser", "face wash for women",
    "hydrating facial cleanser", "daily face wash", "foaming face wash", "gel cleanser",
    "cleanser for sensitive skin", "best face wash", "face wash for dry skin", "face wash for oily skin",
    "skin care", "korean face wash", "dermatologist recommended face wash",
]

# Ingredient words that pull in the wrong shopper intent
IRRELEVANT_PATTERNS = {
    "turmeric": ["capsules", "supplement", "supplement 1500mg", "pills", "gummies", "tea", "powder",
                 "powder organic", "root", "extract", "curcumin with black pepper", "for joint pain",
                 "for inflammation", "and ginger capsules", "latte mix", "soap bar", "face mask", "body wash",
                 "lotion", "toner", "serum", "for dogs", "recipe", "diy face mask"],
    "aloe vera": ["gel for hair", "gel", "plant", "live plant", "juice", "drink", "gel for sunburn",
                  "shampoo", "conditioner", "capsules", "supplement", "for dogs", "soap bar",
                  "moisturizer", "sunscreen", "after sun", "leaves", "gel organic pure"],
    "": ["acne medication face wash", "acne treatment for teens", "prescription acne cleanser",
         "face wash for men", "mens face wash oily skin", "face wash for men oily skin", "baby face wash",
         "dog shampoo natural", "face wash free sample", "turmeric shampoo", "curcumin capsules",
         "ginger supplement", "face wash for men acne", "body wash for men", "beard wash"],
}

# Building blocks for the random long tail
LT_ADJ = ["natural", "organic", "gentle", "herbal", "vegan", "clean", "daily", "mild", "hydrating",
          "soothing", "brightening", "plant based", "cruelty free", "alcohol free", "fragrance free",
          "korean", "ayurvedic", "botanical", "non drying", "low ph", ""]
LT_ING = ["turmeric", "aloe", "aloe vera", "green tea", "chamomile", "tea tree", "vitamin c", "honey",
          "rose", "charcoal", "salicylic acid", "niacinamide", "", ""]
LT_PROD = ["face wash", "facial cleanser", "face cleanser", "cleanser", "foaming face wash",
           "gel cleanser", "facial wash", "face soap", "cleansing foam"]
LT_SUF = ["", "for women", "for sensitive skin", "for dry skin", "for oily skin", "for acne prone skin",
          "for dark spots", "for glowing skin", "for teens", "travel size", "2 pack", "for combination skin",
          "pump bottle", "unscented", "for mature skin", "for redness", "sulfate free", "paraben free"]

ING_CVR_FACTOR = {"turmeric": 1.35, "aloe": 1.15, "aloe vera": 1.20, "green tea": 0.85, "chamomile": 0.90,
                  "tea tree": 0.45, "vitamin c": 0.70, "honey": 0.85, "rose": 0.80, "charcoal": 0.35,
                  "salicylic acid": 0.30, "niacinamide": 0.45, "": 0.80}


def rand_asin(rng: np.random.Generator) -> str:
    chars = list(string.ascii_lowercase + string.digits)
    return "b0" + "".join(rng.choice(chars, 8))


def build_term_universe(rng: np.random.Generator) -> pd.DataFrame:
    """One row per (search term, campaign, ad group, targeting) with latent rates and total clicks."""
    rows = []

    def add(term, cat, cvr, cpc, ctr, placements):
        # placements: list of (campaign_id, ad_group, targeting, match_type, expected_clicks)
        for camp, ag, tgt, mt, clicks in placements:
            rows.append(dict(term=term, category=cat, cvr=cvr, cpc=cpc, ctr=ctr,
                             campaign_id=camp, ad_group=ag, targeting=tgt, match_type=mt,
                             exp_clicks=clicks))

    def auto_tgt():
        return rng.choice(AUTO_TARGETS, p=[0.45, 0.30, 0.15, 0.10])

    # 1. Seed keywords: the keyword itself as a search term, served by its own campaigns + Auto
    for kw, (mts, _bid, cvr, cpc) in SEED_KEYWORDS.items():
        vol = rng.uniform(600, 1500) if "EXACT" in mts else rng.uniform(350, 1000)
        ctr = rng.uniform(0.006, 0.011)
        pl = []
        for mt in mts:
            camp = {"EXACT": 104, "PHRASE": 103, "BROAD": 102}[mt]
            ag = {"EXACT": "Exact - Core", "PHRASE": "Phrase - Core", "BROAD": "Broad - Ingredient & Values"}[mt]
            share = 0.75 if mt == "EXACT" else 0.55
            pl.append((camp, ag, kw, mt, vol * share))
        pl.append((101, "Auto - All", auto_tgt(), "-", vol * 0.20))
        add(kw, "SEED", cvr, cpc, ctr, pl)

    # 2. Brand terms
    for t in BRAND_TERMS:
        vol = rng.uniform(120, 400)
        add(t, "BRAND", rng.uniform(0.26, 0.34), rng.uniform(0.45, 0.65), rng.uniform(0.04, 0.08),
            [(105, "Brand - Exact", "terrabloom", "EXACT", vol * 0.85),
             (101, "Auto - All", "close-match", "-", vol * 0.15)])

    # 3. Harvest candidates: live only in discovery campaigns
    for t in HARVEST_CANDIDATES:
        vol = rng.lognormal(np.log(55), 0.55)
        cvr = float(np.clip(rng.normal(0.165, 0.035), 0.07, 0.26))
        cpc = rng.uniform(0.82, 1.18)
        pl = [(101, "Auto - All", auto_tgt(), "-", vol * rng.uniform(0.4, 0.7))]
        if "turmeric" in t or "aloe" in t:
            pl.append((102, "Broad - Ingredient & Values", "turmeric face wash" if "turmeric" in t
                       else "aloe vera face wash", "BROAD", vol * rng.uniform(0.2, 0.4)))
        if rng.random() < 0.45:
            pl.append((103, "Phrase - Core", "vegan face wash" if "vegan" in t else "turmeric face wash",
                       "PHRASE", vol * rng.uniform(0.15, 0.3)))
        add(t, "HARVEST", cvr, cpc, rng.uniform(0.007, 0.012), pl)

    # 4. Generic head terms
    for t in GENERIC_HEAD:
        vol = rng.uniform(100, 420)
        cvr = rng.uniform(0.035, 0.095)
        cpc = rng.uniform(1.35, 1.85)
        add(t, "GENERIC", cvr, cpc, rng.uniform(0.003, 0.006),
            [(101, "Auto - All", auto_tgt(), "-", vol * 0.35),
             (102, "Broad - Ingredient & Values", "natural face wash", "BROAD", vol * 0.40),
             (103, "Phrase - Core", "gentle face wash" if "gentle" in t else "face wash for sensitive skin"
              if "sensitive" in t else "foaming facial cleanser", "PHRASE", vol * 0.25)])

    # 5. Irrelevant intent
    irrelevant = []
    for ing, sufs in IRRELEVANT_PATTERNS.items():
        for s in sufs:
            irrelevant.append(f"{ing} {s}".strip())
            if ing == "turmeric" and rng.random() < 0.6:
                irrelevant.append(f"organic {ing} {s}")
            if ing == "aloe vera" and rng.random() < 0.6:
                irrelevant.append(f"{s} aloe vera" if s in ("shampoo", "conditioner", "moisturizer", "sunscreen")
                                  else f"pure {ing} {s}")
    for t in sorted(set(irrelevant)):
        vol = rng.lognormal(np.log(26), 0.7)
        cvr = 0.0 if rng.random() < 0.85 else rng.uniform(0.005, 0.02)
        source = (102, "Broad - Ingredient & Values", "turmeric face wash" if "turmeric" in t or "curcumin" in t
                  else "aloe vera face wash", "BROAD")
        add(t, "IRRELEVANT", cvr, rng.uniform(0.95, 1.45), rng.uniform(0.002, 0.005),
            [(101, "Auto - All", rng.choice(["loose-match", "complements", "substitutes"]), "-", vol * 0.55),
             (*source, vol * 0.45)])

    # 6. Competitor ASINs (search term = an ASIN when Amazon shows our ad on a product page)
    for _ in range(140):
        a = rand_asin(rng)
        vol = rng.lognormal(np.log(14), 0.7)
        cvr = rng.choice([0.0, rng.uniform(0.02, 0.06), rng.uniform(0.08, 0.16)], p=[0.45, 0.35, 0.20])
        pl = [(101, "Auto - All", rng.choice(["substitutes", "complements"]), "-", vol * 0.6),
              (106, "Product - Competitors", f'asin="{a.upper()}"', "-", vol * 0.4)]
        add(a, "ASIN", cvr, rng.uniform(0.70, 1.10), rng.uniform(0.002, 0.004), pl)

    # 7. Random long tail
    combos = [" ".join(w for w in (a, i, p, s) if w)
              for a, i, p, s in itertools.product(LT_ADJ, LT_ING, LT_PROD, LT_SUF)]
    taken = {r["term"] for r in rows}
    combos = [c for c in dict.fromkeys(combos) if c not in taken]
    picks = rng.choice(len(combos), size=6400, replace=False)
    for idx in picks:
        t = combos[idx]
        ing = next((i for i in sorted(LT_ING, key=len, reverse=True) if i and i in t), "")
        cvr = 0.11 * ING_CVR_FACTOR[ing] * rng.lognormal(0, 0.35)
        if any(v in t for v in ("vegan", "cruelty free", "alcohol free", "herbal", "plant based")):
            cvr *= 1.15
        vol = rng.lognormal(np.log(0.9), 1.0)
        camp = rng.choice([101, 102, 103], p=[0.55, 0.30, 0.15])
        ag, tgt, mt = {101: ("Auto - All", auto_tgt(), "-"),
                       102: ("Broad - Ingredient & Values", "natural face wash", "BROAD"),
                       103: ("Phrase - Core", "turmeric face wash" if "turmeric" in t else "natural face wash",
                             "PHRASE")}[camp]
        add(t, "LONG_TAIL", float(min(cvr, 0.30)), rng.uniform(0.85, 1.45), rng.uniform(0.004, 0.010),
            [(camp, ag, tgt, mt, vol)])

    return pd.DataFrame(rows)


def simulate_days(universe: pd.DataFrame, start: date, days: int, rng: np.random.Generator) -> pd.DataFrame:
    dates = [start + timedelta(d) for d in range(days)]
    # mild weekly seasonality (weekends +10%) and a gentle upward trend
    weights = np.array([(1.10 if dt.weekday() >= 5 else 0.97) * (0.92 + 0.16 * i / days)
                        for i, dt in enumerate(dates)])
    weights /= weights.sum()

    out = []
    for r in universe.itertuples(index=False):
        lam = r.exp_clicks * weights
        clicks = rng.poisson(lam)
        for d_idx in np.nonzero(clicks)[0]:
            c = int(clicks[d_idx])
            impressions = max(c, int(rng.poisson(c / r.ctr)))
            spend = round(c * r.cpc * rng.lognormal(0, 0.12), 2)
            orders = int(rng.binomial(c, min(r.cvr, 0.95)))
            bundles = int(rng.binomial(orders, BUNDLE_SHARE)) if orders else 0
            units = orders + bundles
            sales = round((orders - bundles) * PRICE_SINGLE + bundles * PRICE_BUNDLE, 2)
            out.append((dates[d_idx], r.campaign_id, r.ad_group, r.targeting, r.match_type, r.term,
                        impressions, c, spend, orders, units, sales))
    return pd.DataFrame(out, columns=["date", "campaign_id", "ad_group", "targeting", "match_type",
                                      "search_term", "impressions", "clicks", "spend", "orders",
                                      "units", "sales"])


def to_amazon_layout(df: pd.DataFrame, campaigns: pd.DataFrame) -> pd.DataFrame:
    """Rename and add the derived columns exactly as the Amazon Ads console exports them."""
    df = df.merge(campaigns[["campaign_id", "Campaign Name"]], on="campaign_id").sort_values(
        ["date", "Campaign Name", "search_term"])
    out = pd.DataFrame({
        "Date": pd.to_datetime(df["date"]).dt.strftime("%b %d, %Y"),
        "Portfolio name": "TerraBloom Cleanser",
        "Currency": "USD",
        "Campaign Name": df["Campaign Name"],
        "Ad Group Name": df["ad_group"],
        "Targeting": df["targeting"],
        "Match Type": df["match_type"],
        "Customer Search Term": df["search_term"],
        "Impressions": df["impressions"],
        "Clicks": df["clicks"],
        "Click-Thru Rate (CTR)": (df["clicks"] / df["impressions"] * 100).round(4).astype(str) + "%",
        "Cost Per Click (CPC)": (df["spend"] / df["clicks"]).round(2),
        "Spend": df["spend"],
        "7 Day Total Sales ": df["sales"],
        "Total Advertising Cost of Sales (ACOS) ": [
            f"{s / v * 100:.2f}%" if v else "" for s, v in zip(df["spend"], df["sales"])],
        "Total Return on Advertising Spend (ROAS)": [
            round(v / s, 2) if s else 0 for s, v in zip(df["spend"], df["sales"])],
        "7 Day Total Orders (#)": df["orders"],
        "7 Day Total Units (#)": df["units"],
        "7 Day Conversion Rate": (df["orders"] / df["clicks"] * 100).round(4).astype(str) + "%",
    })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--start", type=str, default="2026-07-01")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "raw")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)

    campaigns = pd.DataFrame(CAMPAIGNS, columns=["campaign_id", "Campaign Name", "Targeting Type", "Daily Budget"])
    campaigns["State"] = "enabled"
    campaigns["Portfolio name"] = "TerraBloom Cleanser"

    universe = build_term_universe(rng)
    daily = simulate_days(universe, date.fromisoformat(args.start), args.days, rng)
    report = to_amazon_layout(daily, campaigns)

    # Keyword targets that exist in the account (no negatives yet: that is the problem)
    kw_rows = []
    for kw, (mts, bid, _cvr, _cpc) in SEED_KEYWORDS.items():
        for mt in mts:
            camp = {"EXACT": 104, "PHRASE": 103, "BROAD": 102}[mt]
            ag = {"EXACT": "Exact - Core", "PHRASE": "Phrase - Core", "BROAD": "Broad - Ingredient & Values"}[mt]
            kw_rows.append((camp, ag, kw, mt, bid, "enabled"))
    for kw in ["terrabloom"]:
        kw_rows.append((105, "Brand - Exact", kw, "EXACT", 0.60, "enabled"))
    keywords = pd.DataFrame(kw_rows, columns=["campaign_id", "Ad Group Name", "Keyword Text",
                                              "Match Type", "Bid", "State"])
    keywords.insert(0, "keyword_id", range(1, len(keywords) + 1))

    report.to_csv(args.out / "sp_search_term_report.csv", index=False)
    campaigns.to_csv(args.out / "sp_campaigns.csv", index=False)
    keywords.to_csv(args.out / "sp_keywords.csv", index=False)

    print(f"rows={len(report):,}  unique_terms={report['Customer Search Term'].nunique():,}  "
          f"impr={report['Impressions'].sum():,}  clicks={report['Clicks'].sum():,}  "
          f"spend=${report['Spend'].sum():,.0f}  sales=${report['7 Day Total Sales '].sum():,.0f}  "
          f"orders={report['7 Day Total Orders (#)'].sum():,}  "
          f"ACoS={report['Spend'].sum() / report['7 Day Total Sales '].sum():.1%}")


if __name__ == "__main__":
    main()
