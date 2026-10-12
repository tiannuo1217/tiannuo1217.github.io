# Retail Customer Analytics: Retention, Segmentation & an Email A/B Test

**Live case study:** https://tiannuo1217.github.io/retail-customer-analytics.html

Two public retail datasets, one question a CRM team asks every week: which customers are worth the next pound or dollar of marketing, and does the email we send actually change behavior?

## Key findings
- **Value is concentrated, and the segmentation predicts it.** An RFM segmentation built on data up to 9 Jun 2011 put 23% of customers in "Champions"; they produced 71% of revenue over the following six months (a holdout the segmentation never saw).
- **The second purchase is the battleground.** About 20% of new customers order again the month after their first order, and retention stays roughly flat after that.
- **The second order has a window.** 44% of new customers order again within 90 days and 71% within a year; the median wait is 64 days (window functions over each customer's orders).
- **A simple model beats the segments, and drifts.** A logistic regression trained on Dec 2010 data and tested on Jun–Dec 2011 beat the RFM rules (AUC 0.790 vs 0.772; top-20% list covers 70% vs 61% of next-6-month revenue). Its probabilities ran low in the holiday season, so it needs seasonal recalibration. Gradient boosting did not beat it.
- **Holiday shoppers are worth less.** Q4 2010 cohorts generated 22–27% less 12-month revenue per customer than Q2–Q3 cohorts, despite similar first-month spend.
- **The men's email wins.** In a 64,000-customer randomized experiment it lifted conversion from 0.57% to 1.25% and spend per customer by $0.77; spend per buyer didn't change, so the lift is more buyers, not bigger baskets.
- **Targeting is promising but unproven.** A segment-level rule learned on one random half earned ~20% more incremental spend on the other half than a blanket send, but the 95% interval includes zero; confirming it would need ~312,000 customers per arm.

## Methods
| Step | What | Where |
|---|---|---|
| Data quality | 5-rule cleaning funnel (missing IDs, cancellations/returns, invalid prices, non-product codes, duplicates), counted rule by rule | `sql/00_quality_funnel.sql`, `sql/01_clean.sql` |
| Retention | Monthly acquisition cohorts; left-censoring of the first cohort identified and excluded | `sql/02_cohort_retention.sql` |
| LTV | Cumulative revenue per acquired customer, 2010 quarterly cohorts | `sql/03_cohort_ltv.sql` |
| Time to second order | `ROW_NUMBER` / `LAG` window functions, customers with ≥11 months of follow-up | `sql/05_time_to_second_order.sql` |
| Segmentation | RFM with business-readable bands, validated on a 6-month holdout | `sql/04_rfm_base.sql`, `analysis/retail.py` |
| Repurchase model | 12 behavioral features built in SQL; logistic regression vs gradient boosting vs RFM rules; out-of-time test, bootstrap CIs, calibration, permutation importance | `sql/06_customer_features.sql`, `analysis/model.py` |
| Experiment | Sample-ratio and covariate-balance checks, Welch tests with 95% CIs, Holm correction, segment-level effects | `analysis/email_experiment.py` |
| Targeting | Policy learned on a random half, scored on the other half with inverse-propensity weighting; bootstrap CI; follow-up test sizing | `analysis/email_experiment.py` |

## Data
- [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii): 1,067,371 line items, UK online giftware retailer, Dec 2009 – Dec 2011.
- [MineThatData E-Mail Analytics Challenge (Hillstrom, 2008)](https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html): 64,000 customers randomized to a men's email, a women's email or no email.

Raw files are not committed. Download them into `data/raw/`:
```bash
curl -L -o data/raw/online_retail_II.zip "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
unzip data/raw/online_retail_II.zip -d data/raw
python -c "import pandas as pd; x=pd.read_excel('data/raw/online_retail_II.xlsx', sheet_name=None, dtype={'Invoice':str,'StockCode':str}); pd.concat(x.values()).to_csv('data/raw/online_retail_II.csv', index=False)"
curl -L -o data/raw/hillstrom.csv "http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv"
```

## Reproduce
Requires Python 3 with pandas, numpy, scipy, statsmodels, scikit-learn and openpyxl. SQL runs on Python's built-in SQLite.
```bash
python analysis/retail.py data/raw/online_retail_II.csv
python analysis/model.py data/raw/online_retail_II.csv
python analysis/email_experiment.py data/raw/hillstrom.csv
python analysis/build_site_data.py
```
Outputs land in `outputs/` (JSON for the site, tidy CSVs in `outputs/tableau/` for the dashboard).

## Limitations
Public, older datasets from two different businesses; no cost or margin data; RFM bands chosen for interpretability rather than optimized; the experiment observes two weeks of behavior only.

---
Tiannuo Yang · [LinkedIn](https://www.linkedin.com/in/tiannuo-yang)
