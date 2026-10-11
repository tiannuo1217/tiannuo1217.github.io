-- Data-quality funnel: how many line items survive each cleaning rule (rules applied cumulatively).
WITH
r0 AS (SELECT * FROM transactions_raw),
r1 AS (SELECT * FROM r0 WHERE customer_id IS NOT NULL),
r2 AS (SELECT * FROM r1 WHERE invoice NOT LIKE 'C%' AND quantity > 0),
r3 AS (SELECT * FROM r2 WHERE price > 0),
r4 AS (SELECT * FROM r3 WHERE stock_code GLOB '[0-9][0-9][0-9][0-9][0-9]*'),
r5 AS (SELECT DISTINCT invoice, stock_code, quantity, price, customer_id, invoice_date, country FROM r4)
SELECT 0 AS step, 'Raw line items'                                  AS rule, COUNT(*) AS rows_remaining FROM r0
UNION ALL SELECT 1, 'Drop rows with no customer ID',                         COUNT(*) FROM r1
UNION ALL SELECT 2, 'Drop cancellations and returns',                        COUNT(*) FROM r2
UNION ALL SELECT 3, 'Drop zero or negative prices',                          COUNT(*) FROM r3
UNION ALL SELECT 4, 'Drop non-product codes (postage, fees, adjustments)',   COUNT(*) FROM r4
UNION ALL SELECT 5, 'Drop exact duplicate rows',                             COUNT(*) FROM r5
ORDER BY step;
