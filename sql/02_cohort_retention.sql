-- Monthly acquisition cohorts: share of each cohort that orders again k months after its first order.
-- December 2011 is excluded because the data stops on 9 Dec 2011 (partial month).
WITH first_order AS (
    SELECT customer_id, MIN(order_month) AS cohort_month
    FROM orders
    GROUP BY customer_id
),
activity AS (
    SELECT DISTINCT o.customer_id, f.cohort_month, o.order_month
    FROM orders o
    JOIN first_order f USING (customer_id)
    WHERE o.order_month < '2011-12'
),
indexed AS (
    SELECT
        cohort_month,
        customer_id,
        (CAST(substr(order_month, 1, 4) AS INTEGER) - CAST(substr(cohort_month, 1, 4) AS INTEGER)) * 12
      + (CAST(substr(order_month, 6, 2) AS INTEGER) - CAST(substr(cohort_month, 6, 2) AS INTEGER)) AS month_index
    FROM activity
),
cohort_size AS (
    SELECT cohort_month, COUNT(*) AS customers
    FROM first_order
    GROUP BY cohort_month
)
SELECT
    i.cohort_month,
    i.month_index,
    c.customers                                  AS cohort_customers,
    COUNT(DISTINCT i.customer_id)                AS active_customers,
    ROUND(1.0 * COUNT(DISTINCT i.customer_id) / c.customers, 4) AS retention
FROM indexed i
JOIN cohort_size c USING (cohort_month)
GROUP BY i.cohort_month, i.month_index
ORDER BY i.cohort_month, i.month_index;
