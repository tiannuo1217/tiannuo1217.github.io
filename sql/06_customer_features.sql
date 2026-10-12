-- One row per customer: behavior known before :snapshot (features) and whether they ordered in the
-- six months after it (label). Running it at two snapshots gives a train set and a later test set.
WITH history AS (
    SELECT * FROM orders WHERE order_ts < :snapshot
),
gaps AS (
    SELECT
        customer_id,
        julianday(order_ts)
          - julianday(LAG(order_ts) OVER (PARTITION BY customer_id ORDER BY order_ts)) AS gap_days
    FROM history
),
gap_stats AS (
    SELECT customer_id, AVG(gap_days) AS avg_days_between_orders
    FROM gaps
    WHERE gap_days IS NOT NULL
    GROUP BY customer_id
),
basket AS (
    SELECT
        customer_id,
        COUNT(DISTINCT stock_code)                                  AS distinct_products,
        MAX(CASE WHEN country = 'United Kingdom' THEN 1 ELSE 0 END) AS is_uk
    FROM transactions
    WHERE invoice_date < :snapshot
    GROUP BY customer_id
),
cancellations AS (
    SELECT CAST(customer_id AS INTEGER) AS customer_id, COUNT(DISTINCT invoice) AS cancelled_orders
    FROM transactions_raw
    WHERE customer_id IS NOT NULL AND invoice LIKE 'C%' AND invoice_date < :snapshot
    GROUP BY 1
),
features AS (
    SELECT
        customer_id,
        CAST(julianday(:snapshot) - julianday(MAX(order_ts)) AS INTEGER)    AS recency_days,
        CAST(julianday(:snapshot) - julianday(MIN(order_ts)) AS INTEGER)    AS tenure_days,
        COUNT(*)                                                            AS frequency,
        SUM(order_revenue)                                                  AS monetary,
        AVG(order_revenue)                                                  AS avg_order_value,
        SUM(CASE WHEN order_ts >= date(:snapshot, '-90 days') THEN order_revenue ELSE 0 END) AS revenue_last_90d,
        AVG(CASE WHEN CAST(strftime('%m', order_ts) AS INTEGER) >= 10 THEN 1.0 ELSE 0.0 END) AS q4_order_share
    FROM history
    GROUP BY customer_id
),
label AS (
    SELECT customer_id, SUM(order_revenue) AS next_6m_revenue
    FROM orders
    WHERE order_ts >= :snapshot AND order_ts < :label_end
    GROUP BY customer_id
)
SELECT
    f.*,
    g.avg_days_between_orders,
    b.distinct_products,
    b.is_uk,
    COALESCE(c.cancelled_orders, 0)                AS cancelled_orders,
    CASE WHEN l.customer_id IS NULL THEN 0 ELSE 1 END AS repurchased,
    COALESCE(l.next_6m_revenue, 0)                 AS next_6m_revenue
FROM features f
LEFT JOIN gap_stats g      USING (customer_id)
LEFT JOIN basket b         USING (customer_id)
LEFT JOIN cancellations c  USING (customer_id)
LEFT JOIN label l          USING (customer_id);
