-- Revenue per acquired customer by month since first order, for quarterly cohorts (input to cumulative LTV curves).
WITH first_order AS (
    SELECT customer_id, MIN(order_month) AS cohort_month
    FROM orders
    GROUP BY customer_id
),
tagged AS (
    SELECT
        f.cohort_month,
        substr(f.cohort_month, 1, 4) || '-Q' ||
            ((CAST(substr(f.cohort_month, 6, 2) AS INTEGER) + 2) / 3) AS cohort_quarter,
        o.customer_id,
        (CAST(substr(o.order_month, 1, 4) AS INTEGER) - CAST(substr(f.cohort_month, 1, 4) AS INTEGER)) * 12
      + (CAST(substr(o.order_month, 6, 2) AS INTEGER) - CAST(substr(f.cohort_month, 6, 2) AS INTEGER)) AS month_index,
        o.order_revenue
    FROM orders o
    JOIN first_order f USING (customer_id)
    WHERE f.cohort_month BETWEEN '2010-01' AND '2010-12'
      AND o.order_month < '2011-12'
)
SELECT
    t.cohort_quarter,
    t.month_index,
    SUM(t.order_revenue) AS revenue,
    q.customers          AS cohort_customers
FROM tagged t
JOIN (
    SELECT cohort_quarter, COUNT(DISTINCT customer_id) AS customers FROM tagged GROUP BY cohort_quarter
) q USING (cohort_quarter)
GROUP BY t.cohort_quarter, t.month_index
ORDER BY t.cohort_quarter, t.month_index;
