"""
Render static PNG previews of the 3 dashboard pages from the same SQL views
Power BI reads (vw_daily_kpis, vw_negative_candidates, vw_search_term_kpis,
vw_harvest_candidates). Used for the README screenshots.

Usage (after sql/03_dashboard_views.sql):
    python scripts/render_dashboard_previews.py --db amazon_ppc
"""

from __future__ import annotations

import argparse
import io
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd
from matplotlib.patches import FancyBboxPatch

# Palette (validated reference palette, light mode)
SURFACE, PAGE = "#fcfcfb", "#f9f9f7"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE = "#2a78d6", "#eb6834"
NEUTRAL = "#c3c2b7"
CRITICAL, GOOD = "#d03b3b", "#0ca30c"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.facecolor": SURFACE,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titleweight": "bold", "axes.titlesize": 11, "axes.titlelocation": "left",
    "axes.titlecolor": INK, "figure.facecolor": PAGE,
})


def q(db: str, sql: str) -> pd.DataFrame:
    out = subprocess.run(["psql", "-d", db, "--csv", "-c", sql], check=True, capture_output=True, text=True)
    return pd.read_csv(io.StringIO(out.stdout))


def tile(fig, rect, label, value, note="", note_color=INK2):
    ax = fig.add_axes(rect)
    ax.set_axis_off()
    ax.add_patch(FancyBboxPatch((0.02, 0.04), 0.96, 0.92, boxstyle="round,pad=0,rounding_size=0.06",
                                transform=ax.transAxes, facecolor=SURFACE, edgecolor=GRID, linewidth=1))
    ax.text(0.09, 0.72, label.upper(), fontsize=8.5, color=INK2, transform=ax.transAxes)
    ax.text(0.09, 0.34, value, fontsize=19, color=INK, transform=ax.transAxes)
    if note:
        ax.text(0.09, 0.12, note, fontsize=8.5, color=note_color, transform=ax.transAxes)


def header(fig, title, subtitle):
    fig.text(0.03, 0.955, title, fontsize=16, weight="bold", color=INK)
    fig.text(0.03, 0.925, subtitle, fontsize=9.5, color=INK2)


def page1(db: str, out: Path) -> None:
    k = q(db, """SELECT SUM(spend) spend, SUM(sales) sales, SUM(clicks) clicks, SUM(orders) orders,
                        SUM(impressions) impr FROM vw_daily_kpis""").iloc[0]
    waste = q(db, "SELECT SUM(spend) w FROM vw_negative_candidates").iloc[0, 0]
    wk = q(db, """SELECT date_trunc('week', report_date)::date wk, SUM(spend) spend, SUM(sales) sales
                  FROM vw_daily_kpis WHERE report_date >= '2026-07-06' AND report_date < '2026-09-28'
                  GROUP BY 1 ORDER BY 1""")
    wk["acos"] = wk.spend / wk.sales
    ct = q(db, """SELECT targeting_strategy t, SUM(spend)/SUM(sales) acos, SUM(spend) spend
                  FROM vw_daily_kpis GROUP BY 1 ORDER BY 2""")

    fig = plt.figure(figsize=(14, 8.4))
    header(fig, "Page 1 · Executive Overview",
           "TerraBloom Botanicals · Sponsored Products · Jul 1 – Sep 28, 2026 · synthetic data")
    tiles = [("Ad spend", f"${k.spend/1000:,.1f}K", ""),
             ("Attributed sales", f"${k.sales/1000:,.1f}K", ""),
             ("ACoS", f"{k.spend/k.sales:.1%}", "▲ above 30% target", CRITICAL),
             ("ROAS", f"{k.sales/k.spend:.2f}", ""),
             ("CVR", f"{k.orders/k.clicks:.1%}", f"CTR {k.clicks/k.impr:.2%}"),
             ("Wasted spend", f"{waste/k.spend:.1%}", f"${waste:,.0f} flagged", CRITICAL)]
    for i, t in enumerate(tiles):
        tile(fig, [0.03 + i * 0.158, 0.78, 0.15, 0.12], t[0], t[1], t[2], t[3] if len(t) > 3 else INK2)

    ax1 = fig.add_axes([0.05, 0.42, 0.42, 0.29])
    ax1.bar(wk.wk.astype(str).str[5:], wk.spend, color=BLUE, width=0.6)
    ax1.set_title("Weekly ad spend")
    ax1.yaxis.set_major_formatter(mtick.StrMethodFormatter("${x:,.0f}"))
    ax1.grid(axis="x", visible=False)
    ax1.tick_params(axis="x", labelsize=8)

    ax2 = fig.add_axes([0.55, 0.42, 0.42, 0.29])
    ax2.plot(wk.wk.astype(str).str[5:], wk.acos, color=BLUE, linewidth=2, marker="o", markersize=5)
    for y, lab, col in [(0.30, "Target 30%", GOOD), (0.40, "Break-even 40%", CRITICAL)]:
        ax2.axhline(y, color=col, linewidth=1, linestyle="--")
        ax2.text(len(wk) - 0.6, y + 0.004, lab, color=INK2, fontsize=8.5, ha="right")
    ax2.set_ylim(0.2, 0.5)
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0))
    ax2.set_title("Weekly ACoS vs target and break-even")
    ax2.grid(axis="x", visible=False)
    ax2.tick_params(axis="x", labelsize=8)

    ax3 = fig.add_axes([0.12, 0.06, 0.35, 0.26])
    ax3.barh(ct.t, ct.acos, color=BLUE, height=0.55)
    for y, v in enumerate(ct.acos):
        ax3.text(v + 0.01, y, f"{v:.1%}", va="center", fontsize=9, color=INK)
    ax3.axvline(0.30, color=GOOD, linestyle="--", linewidth=1)
    ax3.xaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0))
    ax3.set_title("ACoS by campaign type")
    ax3.grid(axis="y", visible=False)

    ax4 = fig.add_axes([0.62, 0.06, 0.35, 0.26])
    ct2 = ct.sort_values("spend")
    ax4.barh(ct2.t, ct2.spend, color=BLUE, height=0.55)
    for y, v in enumerate(ct2.spend):
        ax4.text(v + 200, y, f"${v:,.0f}", va="center", fontsize=9, color=INK)
    ax4.xaxis.set_major_formatter(mtick.StrMethodFormatter("${x:,.0f}"))
    ax4.xaxis.set_major_locator(mtick.MaxNLocator(5))
    ax4.set_title("Spend by campaign type")
    ax4.grid(axis="y", visible=False)

    fig.savefig(out / "page1_executive_overview.png", dpi=150)
    plt.close(fig)


def page2(db: str, out: Path) -> None:
    n = q(db, "SELECT * FROM vw_negative_candidates ORDER BY spend DESC")
    total_spend = q(db, "SELECT SUM(spend) s FROM fact_search_terms").iloc[0, 0]
    cat = q(db, """SELECT CASE
          WHEN search_term ~ '^b0[a-z0-9]{8}$' THEN 'Competitor ASIN'
          WHEN search_term ~ '(supplement|capsule|pill|gumm|curcumin|joint|inflammation|ginger|latte|tea$)' THEN 'Supplement / ingestible'
          WHEN search_term ~ '(hair|shampoo|conditioner|beard)' THEN 'Haircare'
          WHEN search_term ~ '(powder|root|extract|live plant|vera plant|leaves|juice|drink|recipe|diy|vera gel|gel for|gel organic)' THEN 'Raw ingredient / DIY'
          WHEN search_term ~ '(\\mmen\\M|mens|dog|baby|pet)' THEN 'Wrong audience'
          WHEN search_term ~ '(soap bar|body wash|lotion|toner|serum|mask|moisturizer|sunscreen|after sun)' THEN 'Wrong product format'
          WHEN search_term ~ '(acne|medication|prescription)' THEN 'Drug-claim intent'
          WHEN orders > 0 THEN 'Generic head term'
          ELSE 'Other long tail' END c, SUM(spend) s
        FROM vw_negative_candidates GROUP BY 1 ORDER BY 2""")

    fig = plt.figure(figsize=(14, 8.4))
    header(fig, "Page 2 · Wasted Spend Tracker", "Output of Query 1 · ad-group level · synthetic data")
    top20 = n.spend.head(int(len(n) * 0.2 + 0.999)).sum() / n.spend.sum()
    tiles = [("Wasted spend", f"${n.spend.sum():,.0f}", f"{n.spend.sum()/total_spend:.1%} of all spend", CRITICAL),
             ("Rows to act on", f"{len(n)}", f"{n.search_term.nunique()} unique search terms"),
             ("Zero-order spend", f"${n.loc[n.orders == 0, 'spend'].sum():,.0f}", "no sale at all"),
             ("Top 20% of rows", f"{top20:.0%}", "of wasted spend")]
    for i, t in enumerate(tiles):
        tile(fig, [0.03 + i * 0.237, 0.78, 0.225, 0.12], t[0], t[1], t[2], t[3] if len(t) > 3 else INK2)

    top = n.head(15).iloc[::-1]
    labels = [f"{s}  ·  {c.split('|')[1].strip()}" for s, c in zip(top.search_term, top.campaign_name)]
    colors = [ORANGE if a == "PAUSE KEYWORD / CUT BID" else BLUE for a in top.recommended_action]
    ax1 = fig.add_axes([0.25, 0.07, 0.27, 0.63])
    ax1.barh(labels, top.spend, color=colors, height=0.6)
    for y, (v, a) in enumerate(zip(top.spend, top.acos)):
        ax1.text(v + 10, y, f"${v:,.0f} · ACoS {a:.0%}" if pd.notna(a) else f"${v:,.0f} · 0 orders",
                 va="center", fontsize=8, color=INK2)
    ax1.set_xlim(0, top.spend.max() * 1.55)
    ax1.tick_params(axis="y", labelsize=8.5, colors=INK)
    ax1.xaxis.set_major_formatter(mtick.StrMethodFormatter("${x:,.0f}"))
    ax1.set_title("Top 15 rows by wasted spend")
    ax1.grid(axis="y", visible=False)
    ax1.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=BLUE), plt.Rectangle((0, 0), 1, 1, color=ORANGE)],
               labels=["Add negative", "Pause keyword / cut bid"], loc="lower right", frameon=False, fontsize=8.5)

    ax2 = fig.add_axes([0.75, 0.07, 0.22, 0.63])
    ax2.barh(cat.c, cat.s, color=BLUE, height=0.6)
    for y, v in enumerate(cat.s):
        ax2.text(v + 100, y, f"${v:,.0f}", va="center", fontsize=8.5, color=INK)
    ax2.set_xlim(0, cat.s.max() * 1.3)
    ax2.tick_params(axis="y", labelsize=8.5, colors=INK)
    ax2.xaxis.set_major_formatter(mtick.StrMethodFormatter("${x:,.0f}"))
    ax2.xaxis.set_major_locator(mtick.MaxNLocator(4))
    ax2.set_title("Wasted spend by intent")
    ax2.grid(axis="y", visible=False)

    fig.savefig(out / "page2_wasted_spend_tracker.png", dpi=150)
    plt.close(fig)


def page3(db: str, out: Path) -> None:
    t = q(db, """SELECT s.search_term, s.clicks, s.spend, s.cvr, s.acos,
                        (h.new_exact_keyword IS NOT NULL) harvest
                 FROM vw_search_term_kpis s
                 LEFT JOIN vw_harvest_candidates h ON h.new_exact_keyword = s.search_term
                 WHERE s.clicks >= 15 AND s.orders > 0""")
    base_cvr = q(db, "SELECT SUM(orders_7d)::numeric/SUM(clicks) FROM fact_search_terms").iloc[0, 0]
    t["harvest"] = t.harvest.astype(str).str.lower().isin(["t", "true"])
    t["acos_c"] = t.acos.clip(upper=1.2)

    fig = plt.figure(figsize=(14, 8.4))
    header(fig, "Page 3 · Keyword Performance Matrix",
           "Search terms with ≥ 15 clicks and ≥ 1 order · bubble size = spend · ACoS capped at 120% · synthetic data")
    ax = fig.add_axes([0.07, 0.09, 0.88, 0.78])
    for flag, col, lab in [(False, NEUTRAL, "Other search terms"), (True, BLUE, "Harvest candidate (Query 2)")]:
        d = t[t.harvest == flag]
        ax.scatter(d.cvr, d.acos_c, s=(d.spend / t.spend.max()) * 900 + 12, color=col, alpha=0.8,
                   edgecolor=SURFACE, linewidth=1.5, label=lab, zorder=3 if flag else 2)
    ax.axvline(base_cvr, color=INK2, linewidth=1, linestyle="--")
    ax.axhline(0.30, color=INK2, linewidth=1, linestyle="--")
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("Conversion rate (CVR)")
    ax.set_ylabel("ACoS")
    xmax = t.cvr.max() * 1.05
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, 1.25)
    for x, y, txt, ha in [(xmax * 0.98, 0.03, "STARS · harvest, raise bids", "right"),
                          (0.003, 0.03, "HIDDEN GEMS · test higher bids", "left"),
                          (xmax * 0.98, 1.2, "OVER-BID · lower bid to RPC × 30%", "right"),
                          (0.003, 1.2, "BLEEDERS · negate or pause", "left")]:
        ax.text(x, y, txt, ha=ha, fontsize=9, color=INK2, weight="bold")
    for term in ["herbal face cleanser", "turmeric face wash for glowing skin", "gentle face wash",
                 "face wash for sensitive skin", "turmeric face wash", "vegan turmeric face cleanser"]:
        r = t[t.search_term == term]
        if len(r):
            ax.annotate(term, (r.cvr.iloc[0], r.acos_c.iloc[0]), xytext=(8, 6), textcoords="offset points",
                        fontsize=8.5, color=INK)
    ax.legend(loc="upper center", frameon=False, ncol=2, fontsize=9, markerscale=0.6)
    ax.text(base_cvr, 1.255, f" account CVR {base_cvr:.1%}", fontsize=8, color=INK2, va="bottom")
    ax.text(0.003, 0.305, "target ACoS 30%", fontsize=8, color=INK2, va="bottom")

    fig.savefig(out / "page3_keyword_matrix.png", dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="amazon_ppc")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parents[1] / "dashboard" / "screenshots")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    page1(a.db, a.out)
    page2(a.db, a.out)
    page3(a.db, a.out)
    print("Saved previews to", a.out)


if __name__ == "__main__":
    main()
