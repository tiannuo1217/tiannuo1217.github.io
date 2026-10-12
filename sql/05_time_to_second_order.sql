-- How long after the first order does the second order arrive?
-- Window functions number each customer's orders and pull the previous order's timestamp.
-- Only customers first seen in 2010 are kept, so everyone has at least 11 months of follow-up.
WITH ranked AS (
    SELECT
        customer_id,
        order_ts,
        ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_ts)  AS order_number,
        LAG(order_ts) OVER (PARTITION BY customer_id ORDER BY order_ts) AS previous_order_ts
    FROM orders
),
first_orders AS (
    SELECT customer_id, order_ts AS first_order_ts
    FROM ranked
    WHERE order_number = 1
),
second_orders AS (
    SELECT
        customer_id,
        CAST(julianday(order_ts) - julianday(previous_order_ts) AS INTEGER) AS days_to_second_order
    FROM ranked
    WHERE order_number = 2
)
SELECT
    f.customer_id,
    f.first_order_ts,
    s.days_to_second_order          -- NULL when the customer never ordered again
FROM first_orders f
LEFT JOIN second_orders s USING (customer_id)
WHERE f.first_order_ts >= '2010-01-01'
  AND f.first_order_ts <  '2011-01-01';
