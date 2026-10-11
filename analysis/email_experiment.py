"""Readout of the Hillstrom (MineThatData, 2008) randomized e-mail experiment.

64,000 customers were randomly assigned to a men's merchandise e-mail, a women's merchandise
e-mail, or no e-mail; visits, conversions and spend were tracked for the next two weeks.

Writes outputs/experiment_results.json and outputs/tableau/experiment_*.csv.

Usage: python analysis/email_experiment.py data/raw/hillstrom.csv
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
ARMS = {"Mens E-Mail": "Men's email", "Womens E-Mail": "Women's email", "No E-Mail": "No email"}
TREATMENTS = ["Men's email", "Women's email"]
METRICS = {"visit": "Visit rate", "conversion": "Conversion rate", "spend": "Spend per customer"}
SEED = 42


def diff_ci(a, b):
    """Difference in means (a - b) with a Welch 95% CI and two-sided p-value.
    For 0/1 outcomes this equals the unpooled two-proportion z-test at this sample size."""
    d = a.mean() - b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    p = stats.ttest_ind(a, b, equal_var=False).pvalue
    return d, d - 1.96 * se, d + 1.96 * se, p


def history_group(row):
    if row.mens and row.womens:
        return "Bought both"
    return "Bought men's only" if row.mens else "Bought women's only"


def main(csv_path):
    (OUT / "tableau").mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path)
    df["arm"] = df["segment"].map(ARMS)
    df["history_group"] = df.apply(history_group, axis=1)
    df["customer_type"] = np.where(df.newbie == 1, "New (first purchase in last 12 months)", "Existing")
    df["cell"] = df.history_group + " · " + np.where(df.newbie == 1, "new", "existing")

    # 1. Sample-ratio check: did randomization deliver the intended 1/3 splits?
    counts = df.arm.value_counts().reindex(ARMS.values())
    srm_p = stats.chisquare(counts).pvalue

    # 2. Covariate balance: standardized mean difference of each pre-period variable vs control.
    X = pd.get_dummies(df[["recency", "history", "mens", "womens", "newbie", "zip_code", "channel"]],
                       columns=["zip_code", "channel"], dtype=float)
    ctrl = df.arm == "No email"
    smd = {}
    for t in TREATMENTS:
        tr = df.arm == t
        pooled = np.sqrt((X[tr].var() + X[ctrl].var()) / 2)
        smd[t] = float(((X[tr].mean() - X[ctrl].mean()).abs() / pooled).max())

    # 3. Average treatment effects, Holm-adjusted across the 6 tests (2 e-mails x 3 metrics).
    base = {m: float(df.loc[ctrl, m].mean()) for m in METRICS}
    effects = []
    for t in TREATMENTS:
        for m in METRICS:
            d, lo, hi, p = diff_ci(df.loc[df.arm == t, m], df.loc[ctrl, m])
            effects.append({"treatment": t, "metric": m, "control": base[m],
                            "treated": float(df.loc[df.arm == t, m].mean()),
                            "lift": float(d), "ci_low": float(lo), "ci_high": float(hi),
                            "relative_lift": float(d / base[m]), "p_value": float(p)})
    adj = multipletests([e["p_value"] for e in effects], method="holm")[1]
    for e, a in zip(effects, adj):
        e["p_holm"] = float(a)

    # 4. Who responds? Spend lift by past-purchase history and customer tenure.
    hetero = []
    for cell, g in df.groupby("cell"):
        c = g[g.arm == "No email"]
        for t in TREATMENTS:
            for m in ("conversion", "spend"):
                d, lo, hi, p = diff_ci(g.loc[g.arm == t, m], c[m])
                hetero.append({"cell": cell, "treatment": t, "metric": m, "n_per_arm": int(len(c)),
                               "lift": float(d), "ci_low": float(lo), "ci_high": float(hi), "p_value": float(p)})

    # 5. Targeting policy, learned on one random half and scored on the other (no peeking).
    rng = np.random.default_rng(SEED)
    train = rng.random(len(df)) < 0.5
    tr, te = df[train], df[~train]
    means = tr.groupby(["cell", "arm"])["spend"].mean().unstack()
    best_arm = means.idxmax(axis=1).to_dict()
    propensity = te.arm.value_counts(normalize=True)

    def policy_value(choose):
        """Inverse-propensity estimate of spend per customer if every test customer got choose(cell)."""
        hit = te.arm.values == te.cell.map(choose).values
        return float(np.mean(te.spend.values * hit / te.arm.map(propensity).values))

    policies = {
        "No email": policy_value(lambda c: "No email"),
        "Women's email to everyone": policy_value(lambda c: "Women's email"),
        "Men's email to everyone": policy_value(lambda c: "Men's email"),
        "Targeted (best email per segment)": policy_value(best_arm.get),
    }
    # Bootstrap the test half to see whether targeting really beats the best blanket send.
    boot = []
    idx = np.arange(len(te))
    spend, arm, cell = te.spend.values, te.arm.values, te.cell.values
    w = te.arm.map(propensity).values
    best_vec = np.array([best_arm[c] for c in cell])
    for _ in range(2000):
        s = rng.choice(idx, len(idx), replace=True)
        v_t = np.mean(spend[s] * (arm[s] == best_vec[s]) / w[s])
        v_m = np.mean(spend[s] * (arm[s] == "Men's email") / w[s])
        boot.append(v_t - v_m)
    boot = np.array(boot)

    # 6. Follow-up sizing: customers per arm for 80% power (two-sided, alpha 0.05) to detect the
    #    targeting gain on spend, which is noisy because 99% of customers spend nothing.
    spend_sd = float(np.sqrt((df.loc[df.arm == "Men's email", "spend"].var() + df.loc[ctrl, "spend"].var()) / 2))
    def n_per_arm(delta):
        return int(np.ceil(2 * (stats.norm.ppf(0.975) + stats.norm.ppf(0.8)) ** 2 * spend_sd ** 2 / delta ** 2))
    gain = float(np.mean(boot))
    converter_aov = df[df.conversion == 1].groupby("arm")["spend"].mean().round(2).to_dict()

    result = {
        "n": int(len(df)),
        "spend_sd": spend_sd,
        "followup_n_per_arm": {"targeting_gain": n_per_arm(gain), "gain": gain},
        "converter_aov": converter_aov,
        "arm_counts": {k: int(v) for k, v in counts.items()},
        "srm_p_value": float(srm_p),
        "max_abs_smd": smd,
        "baseline": base,
        "effects": effects,
        "heterogeneity": hetero,
        "policy": {
            "best_arm_by_cell": best_arm,
            "spend_per_customer": policies,
            "incremental_per_1000_vs_no_email": {k: (v - policies["No email"]) * 1000 for k, v in policies.items()},
            "targeted_minus_mens_all": float(np.mean(boot)),
            "targeted_minus_mens_all_ci": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
            "emails_sent_share": float(np.mean(te.cell.map(best_arm) != "No email")),
        },
    }
    (OUT / "experiment_results.json").write_text(json.dumps(result, indent=2))
    pd.DataFrame(effects).to_csv(OUT / "tableau" / "experiment_effects.csv", index=False)
    pd.DataFrame(hetero).to_csv(OUT / "tableau" / "experiment_segments.csv", index=False)

    print(counts.to_dict(), "SRM p=%.3f" % srm_p, "max SMD", smd)
    print(pd.DataFrame(effects).round(4).to_string())
    h = pd.DataFrame(hetero)
    print(h[h.metric == "spend"].round(3).to_string())
    print(h[h.metric == "conversion"].round(4).to_string())
    print(json.dumps(result["policy"], indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
