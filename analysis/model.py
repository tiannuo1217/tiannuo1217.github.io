"""Predict which customers will order again in the next six months, and check it out of time.

Train: features as of 9 Dec 2010, label = ordered between 9 Dec 2010 and 9 Jun 2011.
Test:  features as of 9 Jun 2011, label = ordered between 9 Jun 2011 and 10 Dec 2011.
The test period is later in time and includes the holiday season, so it is a realistic check of
whether a model trained on the past still works when it is deployed.

Writes outputs/model_results.json and outputs/tableau/model_*.csv.

Usage: python analysis/model.py data/raw/online_retail_II.csv
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retail import OUT, load, run_sql, segment_of  # noqa: E402

TRAIN = ("2010-12-09", "2011-06-09")
TEST = ("2011-06-09", "2011-12-10")
SEED = 42

FEATURES = {
    "log_recency_days": "Days since last order",
    "log_frequency": "Number of orders",
    "log_monetary": "Total spend",
    "log_avg_order_value": "Average order value",
    "log_revenue_last_90d": "Spend in last 90 days",
    "log_tenure_days": "Days since first order",
    "log_avg_days_between_orders": "Average days between orders",
    "single_order": "Only one order so far",
    "log_distinct_products": "Distinct products bought",
    "cancel_rate": "Share of orders cancelled",
    "q4_order_share": "Share of orders in Oct–Dec",
    "is_uk": "UK customer",
}


def build(con, snapshot, label_end):
    d = run_sql(con, "06_customer_features.sql", snapshot=snapshot, label_end=label_end)
    d["single_order"] = (d.frequency == 1).astype(int)
    # Customers with one order have no gap; use their tenure so "long since they started, never back" stays high.
    d["avg_days_between_orders"] = d.avg_days_between_orders.fillna(d.tenure_days)
    d["cancel_rate"] = d.cancelled_orders / (d.cancelled_orders + d.frequency)
    for col in ["recency_days", "frequency", "monetary", "avg_order_value", "revenue_last_90d",
                "tenure_days", "avg_days_between_orders", "distinct_products"]:
        d["log_" + col] = np.log1p(d[col].clip(lower=0))
    # Same recency/frequency bands as the RFM segmentation, so the baseline is exactly that rule.
    r = pd.cut(d.recency_days, [-1, 30, 90, 180, 365, np.inf], labels=[5, 4, 3, 2, 1]).astype(int)
    f = pd.cut(d.frequency, [0, 1, 2, 4, 9, np.inf], labels=[1, 2, 3, 4, 5]).astype(int)
    d["segment"] = [segment_of(a, b) for a, b in zip(r, f)]
    return d


def gains(y, score, steps=20):
    """Share of y (buyers, or revenue if y is spend) captured when contacting the top x% by score."""
    order = np.argsort(-score, kind="stable")
    hits = np.cumsum(np.asarray(y, dtype=float)[order])
    n, total = len(y), hits[-1]
    xs = [i / steps for i in range(steps + 1)]
    return [0.0] + [float(hits[max(0, int(round(x * n)) - 1)] / total) for x in xs[1:]]


def capture(y, score, revenue, top=0.2):
    k = int(round(len(y) * top))
    idx = np.argsort(-score, kind="stable")[:k]
    return float(np.asarray(y)[idx].sum() / np.sum(y)), float(np.asarray(revenue)[idx].sum() / np.sum(revenue))


def main(csv_path):
    con = sqlite3.connect(":memory:")
    load(con, csv_path)
    train, test = build(con, *TRAIN), build(con, *TEST)
    X_cols = list(FEATURES)
    Xtr, ytr, Xte, yte = train[X_cols], train.repurchased, test[X_cols], test.repurchased

    # Baseline: score each customer with their RFM segment's repurchase rate in the training period.
    seg_rate = train.groupby("segment").repurchased.mean()
    rfm_score = test.segment.map(seg_rate).fillna(ytr.mean()).values

    logit = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
    gbm = HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, max_leaf_nodes=15,
                                         min_samples_leaf=40, l2_regularization=1.0, random_state=SEED)
    logit.fit(Xtr, ytr)
    gbm.fit(Xtr, ytr)
    scores = {"RFM rules": rfm_score,
              "Logistic regression": logit.predict_proba(Xte)[:, 1],
              "Gradient boosting": gbm.predict_proba(Xte)[:, 1]}

    metrics = {}
    for name, s in scores.items():
        cap_buyers, cap_rev = capture(yte, s, test.next_6m_revenue)
        metrics[name] = {
            "auc": float(roc_auc_score(yte, s)),
            "pr_auc": float(average_precision_score(yte, s)),
            "brier": float(brier_score_loss(yte, s)),
            "top20_capture_buyers": cap_buyers,
            "top20_capture_revenue": cap_rev,
            "gains": gains(yte, s),
            "revenue_gains": gains(test.next_6m_revenue.values, s),
        }

    # Does the model beat the RFM rule by more than noise? Paired bootstrap on the test customers.
    rng = np.random.default_rng(SEED)
    y_arr = yte.values
    rev = test.next_6m_revenue.values
    diffs = {"Logistic regression": [], "Gradient boosting": []}
    rev_diffs = {"Logistic regression": [], "Gradient boosting": []}
    for _ in range(500):
        i = rng.integers(0, len(y_arr), len(y_arr))
        if y_arr[i].min() == y_arr[i].max():
            continue
        base = roc_auc_score(y_arr[i], rfm_score[i])
        base_rev = capture(y_arr[i], rfm_score[i], rev[i])[1]
        for m in diffs:
            diffs[m].append(roc_auc_score(y_arr[i], scores[m][i]) - base)
            rev_diffs[m].append(capture(y_arr[i], scores[m][i], rev[i])[1] - base_rev)
    for m, d in diffs.items():
        metrics[m]["auc_gain_vs_rfm"] = float(np.mean(d))
        metrics[m]["auc_gain_ci"] = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
        metrics[m]["revenue_capture_gain_vs_rfm"] = float(np.mean(rev_diffs[m]))
        metrics[m]["revenue_capture_gain_ci"] = [float(np.percentile(rev_diffs[m], 2.5)), float(np.percentile(rev_diffs[m], 97.5))]

    # Calibration of the logistic model: predicted vs. actual repurchase rate by score decile.
    p = scores["Logistic regression"]
    dec = pd.qcut(pd.Series(p).rank(method="first"), 10, labels=False)
    calib = (pd.DataFrame({"decile": dec + 1, "pred": p, "actual": y_arr})
             .groupby("decile").agg(predicted=("pred", "mean"), actual=("actual", "mean"), customers=("pred", "size"))
             .reset_index())

    # What drives the logistic model: permutation importance on the test set (drop in AUC when shuffled).
    imp = permutation_importance(logit, Xte, yte, scoring="roc_auc", n_repeats=10, random_state=SEED)
    coef = logit.named_steps["logisticregression"].coef_[0]
    importance = sorted([{"feature": FEATURES[c], "auc_drop": float(imp.importances_mean[k]),
                          "direction": "higher → more likely" if coef[k] > 0 else "higher → less likely"}
                         for k, c in enumerate(X_cols)], key=lambda r: -r["auc_drop"])

    # Putting it to work: inside the At-risk segment, does the score separate who will come back?
    at_risk = test[test.segment == "At risk"].assign(score=p[test.segment.eq("At risk").values])
    half = at_risk.score >= at_risk.score.median()
    at_risk_split = {
        "customers": int(len(at_risk)),
        "top_half_repurchase": float(at_risk[half].repurchased.mean()),
        "bottom_half_repurchase": float(at_risk[~half].repurchased.mean()),
        "top_half_revenue_share": float(at_risk[half].next_6m_revenue.sum() / at_risk.next_6m_revenue.sum()),
    }

    result = {
        "train": {"snapshot": TRAIN[0], "label_end": TRAIN[1], "customers": int(len(train)), "base_rate": float(ytr.mean())},
        "test": {"snapshot": TEST[0], "label_end": TEST[1], "customers": int(len(test)), "base_rate": float(yte.mean())},
        "metrics": metrics,
        "calibration": calib.to_dict("records"),
        "importance": importance,
        "at_risk_split": at_risk_split,
    }
    (OUT / "model_results.json").write_text(json.dumps(result, indent=2))
    pd.DataFrame({m: v["gains"] for m, v in metrics.items()}).assign(
        share_targeted=[i / 20 for i in range(21)]).to_csv(OUT / "tableau" / "model_gains.csv", index=False)
    calib.to_csv(OUT / "tableau" / "model_calibration.csv", index=False)

    print("train", result["train"], "\ntest", result["test"])
    for m, v in metrics.items():
        print(f"{m:22s} AUC {v['auc']:.3f}  PR-AUC {v['pr_auc']:.3f}  Brier {v['brier']:.3f}  "
              f"top20 buyers {v['top20_capture_buyers']:.1%}  top20 revenue {v['top20_capture_revenue']:.1%}  "
              f"gain {v.get('auc_gain_vs_rfm', 0):+.3f} {v.get('auc_gain_ci', '')}  rev gain {v.get('revenue_capture_gain_vs_rfm', 0):+.3f} {v.get('revenue_capture_gain_ci', '')}")
    print(calib.round(3).to_string())
    print(pd.DataFrame(importance).round(4).to_string())
    print(at_risk_split)


if __name__ == "__main__":
    main(sys.argv[1])
