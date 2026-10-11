-- Clean transaction table used by every downstream query.
DROP TABLE IF EXISTS transactions;
CREATE TABLE transactions AS
SELECT DISTINCT
    invoice,
    stock_code,
    quantity,
    price,
    quantity * price          AS revenue,
    CAST(customer_id AS INTEGER) AS customer_id,
    invoice_date,
    substr(invoice_date, 1, 7) AS order_month,
    country
FROM transactions_raw
WHERE customer_id IS NOT NULL
  AND invoice NOT LIKE 'C%'
  AND quantity > 0
  AND price > 0
  AND stock_code GLOB '[0-9][0-9][0-9][0-9][0-9]*';

-- One row per order (invoice).
DROP TABLE IF EXISTS orders;
CREATE TABLE orders AS
SELECT
    invoice,
    customer_id,
    MIN(invoice_date)  AS order_ts,
    MIN(order_month)   AS order_month,
    SUM(revenue)       AS order_revenue
FROM transactions
GROUP BY invoice, customer_id;
