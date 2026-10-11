"""Retail customer analytics on UCI Online Retail II.

Loads the raw transactions into SQLite, runs the SQL in ../sql, and writes:
  outputs/retail_results.json   numbers and chart data for the case-study page
  outputs/tableau/*.csv         tidy extracts for the Tableau Public dashboard

Usage: python analysis/retail.py data/raw/online_retail_II.csv
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql"
OUT = ROOT / "outputs"
SNAPSHOT = "2011-06-09"      # segment customers on what we knew at this date...
HOLDOUT_END = "2011-12-10"   # ...then check what they actually spent over the next six months


def run_sql(con, name, **params):
    return pd.read_sql_query((SQL / name).read_text(), con, params=params or None)


def load(con, csv_path):
    raw = pd.read_csv(csv_path, dtype={"Invoice": str, "StockCode": str})
    raw.columns = ["invoice", "stock_code", "description", "quantity",
                   "invoice_date", "price", "customer_id", "country"]
    raw["invoice_date"] = pd.to_datetime(raw["invoice_date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    raw.to_sql("transactions_raw", con, index=False)
    con.executescript((SQL / "01_clean.sql").read_text())
    return raw


def kpis(con, raw):
    orders = pd.read_sql_query("SELECT * FROM orders", con)
    per_cust = orders.groupby("customer_id").agg(n=("invoice", "size"), rev=("order_revenue", "sum"))
    top = per_cust["rev"].sort_values(ascending=False)
    top20_share = top.iloc[: int(round(len(top) * 0.2))].sum() / top.sum()

    identified = raw[raw["customer_id"].notna()]
    inv = identified.drop_duplicates("invoice")
    cancel_rate = inv["invoice"].str.startswith("C").mean()

    return {
        "raw_rows": int(len(raw)),
        "clean_rows": int(pd.read_sql_query("SELECT COUNT(*) n FROM transactions", con)["n"][0]),
        "customers": int(per_cust.shape[0]),
        "orders": int(len(orders)),
        "revenue": float(orders["order_revenue"].sum()),
        "aov": float(orders["order_revenue"].mean()),
        "repeat_rate": float((per_cust["n"] >= 2).mean()),
        "top20_revenue_share": float(top20_share),
        "cancelled_invoice_share": float(cancel_rate),
        "date_min": raw["invoice_date"].min()[:10],
        "date_max": raw["invoice_date"].max()[:10],
    }


def retention(con):
    r = run_sql(con, "02_cohort_retention.sql")
    r.to_csv(OUT / "tableau" / "cohort_retention.csv", index=False)
    heat = r[(r.cohort_month <= "2010-11") & (r.month_index <= 12)]
    cohorts = sorted(heat.cohort_month.unique())
    grid = {c: {int(k): float(v) for k, v in heat[heat.cohort_month == c][["month_index", "retention"]].values}
            for c in cohorts}
    sizes = heat.groupby("cohort_month")["cohort_customers"].first().astype(int).to_dict()

    # Summary excludes Dec 2009: the data starts that month, so its "new" customers include
    # long-standing ones (left-censoring) and it looks far more loyal than a true new cohort.
    clean = r[(r.cohort_month >= "2010-01") & (r.cohort_month <= "2010-11")]
    def avg_at(k):
        s = clean[clean.month_index == k]
        return float(np.average(s.retention, weights=s.cohort_customers))
    dec09 = r[r.cohort_month == "2009-12"].set_index("month_index")["retention"]
    return {
        "cohorts": cohorts,
        "sizes": sizes,
        "grid": grid,
        "avg_m1": avg_at(1), "avg_m3": avg_at(3), "avg_m6": avg_at(6), "avg_m12": avg_at(12),
        "dec2009_m1": float(dec09.get(1, np.nan)), "dec2009_m12": float(dec09.get(12, np.nan)),
    }


def ltv(con):
    l = run_sql(con, "03_cohort_ltv.sql")
    l = l[l.month_index <= 11]
    out = {}
    for q, g in l.groupby("cohort_quarter"):
        g = g.set_index("month_index").reindex(range(12), fill_value=0)
        n = int(l[l.cohort_quarter == q]["cohort_customers"].iloc[0])
        cum = (g["revenue"].cumsum() / n).round(2).tolist()
        out[q] = {"customers": n, "cumulative": cum}
    tidy = [{"cohort_quarter": q, "month_index": i, "cumulative_revenue_per_customer": v}
            for q, d in out.items() for i, v in enumerate(d["cumulative"])]
    pd.DataFrame(tidy).to_csv(OUT / "tableau" / "cohort_ltv.csv", index=False)
    return out


SEGMENTS = ["Champions", "Loyal", "Promising", "Needs attention", "At risk", "Hibernating"]


def segment_of(r, f):
    if r >= 4 and f >= 4:
        return "Champions"
    if (r == 3 and f >= 3) or (r >= 4 and f == 3):
        return "Loyal"
    if r >= 4:
        return "Promising"
    if r == 3:
        return "Needs attention"
    if f >= 3:
        return "At risk"
    return "Hibernating"


def rfm(con):
    d = run_sql(con, "04_rfm_base.sql", snapshot=SNAPSHOT, holdout_end=HOLDOUT_END)
    # Business-readable score bands instead of quintiles: quintiles would split customers with the
    # same order count into different scores, and "ordered in the last 30 days" is easier to act on.
    d["R"] = pd.cut(d.recency_days, [-1, 30, 90, 180, 365, np.inf], labels=[5, 4, 3, 2, 1]).astype(int)
    d["F"] = pd.cut(d.frequency, [0, 1, 2, 4, 9, np.inf], labels=[1, 2, 3, 4, 5]).astype(int)
    d["segment"] = [segment_of(r, f) for r, f in zip(d.R, d.F)]
    d.to_csv(OUT / "tableau" / "rfm_customers.csv", index=False)

    total_cust, total_next = len(d), d.next_6m_revenue.sum()
    rows = []
    for s in SEGMENTS:
        g = d[d.segment == s]
        rows.append({
            "segment": s,
            "customers": int(len(g)),
            "share_customers": float(len(g) / total_cust),
            "share_next6m_revenue": float(g.next_6m_revenue.sum() / total_next),
            "repurchase_rate_next6m": float((g.next_6m_orders > 0).mean()),
            "next6m_revenue_per_customer": float(g.next_6m_revenue.mean()),
            "median_recency_days": float(g.recency_days.median()),
            "median_orders": float(g.frequency.median()),
            "historic_revenue_per_customer": float(g.monetary.mean()),
        })
    pd.DataFrame(rows).to_csv(OUT / "tableau" / "rfm_segments.csv", index=False)
    return {"snapshot": SNAPSHOT, "holdout_end": HOLDOUT_END, "customers": total_cust, "segments": rows}


def main(csv_path):
    (OUT / "tableau").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(":memory:")
    raw = load(con, csv_path)
    funnel = run_sql(con, "00_quality_funnel.sql").to_dict("records")
    result = {
        "funnel": funnel,
        "kpis": kpis(con, raw),
        "retention": retention(con),
        "ltv": ltv(con),
        "rfm": rfm(con),
    }
    (OUT / "retail_results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("funnel", "kpis")}, indent=2))
    ret = result["retention"]
    print({k: ret[k] for k in ret if k.startswith(("avg", "dec"))})
    print({q: (v["customers"], v["cumulative"][0], v["cumulative"][-1]) for q, v in result["ltv"].items()})
    print(pd.DataFrame(result["rfm"]["segments"]).round(3).to_string())


if __name__ == "__main__":
    main(sys.argv[1])
