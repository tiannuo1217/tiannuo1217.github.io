-- Recency / frequency / monetary inputs as of a snapshot date, plus what each customer spent in the
-- following six months (used to check whether the segments actually predict future value).
WITH calibration AS (
    SELECT
        customer_id,
        CAST(julianday(:snapshot) - julianday(MAX(order_ts)) AS INTEGER) AS recency_days,
        COUNT(*)                                                       AS frequency,
        SUM(order_revenue)                                             AS monetary
    FROM orders
    WHERE order_ts < :snapshot
    GROUP BY customer_id
),
holdout AS (
    SELECT customer_id, SUM(order_revenue) AS next_6m_revenue, COUNT(*) AS next_6m_orders
    FROM orders
    WHERE order_ts >= :snapshot AND order_ts < :holdout_end
    GROUP BY customer_id
)
SELECT
    c.*,
    COALESCE(h.next_6m_revenue, 0) AS next_6m_revenue,
    COALESCE(h.next_6m_orders, 0)  AS next_6m_orders
FROM calibration c
LEFT JOIN holdout h USING (customer_id);
