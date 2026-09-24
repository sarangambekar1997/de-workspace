-- Lab 01 exercises. Replace each TODO query with your answer.
-- Run:  python run_sql.py exercises.sql     (compare with: python run_sql.py solutions.sql)

-- Q1: Deduplicate orders — create a view `orders` with the latest version of each order_id (by updated_at) and status lowercased. Then compare raw row count, distinct order_ids, and deduplicated rows.
CREATE OR REPLACE VIEW orders AS
SELECT * FROM raw_orders   -- TODO: keep only the latest version per order_id, lowercase status
;

SELECT COUNT(*) AS deduplicated_rows FROM orders;

-- Q2: Data quality report — one row per check with the number of failures: missing customer_id, non-positive quantities, unknown products, non-lowercase statuses, duplicate event deliveries.
SELECT 'TODO' AS check_name, 0 AS failures;

-- Q3: Daily revenue — create a view `order_lines_clean` (valid lines only, no cancelled orders) and report orders and revenue per day.
SELECT 'TODO' AS order_date;

-- Q4: Top 3 products by revenue within each category (use a window function).
SELECT 'TODO' AS category;

-- Q5: Customer lifetime value — customers with orders, average lifetime value, and the percentage of customers with more than one order.
SELECT 'TODO' AS customers_with_orders;

-- Q6: 7-day moving average of daily revenue.
SELECT 'TODO' AS order_date;

-- Q7: Revenue by customer country.
SELECT 'TODO' AS country;

-- Q8: Checkout funnel — distinct customers reaching /, /product, /cart, and /checkout per day, after removing duplicate events.
SELECT 'TODO' AS day;

-- Q9: Late-arriving events — total events, events received more than 1 hour after they happened, their percentage, and the maximum delay.
SELECT 'TODO' AS events;

-- Q10: Sessionize the clickstream — a new session starts after 30 minutes of inactivity. Output one row per customer session with start, end, and page views.
SELECT 'TODO' AS customer_id;
