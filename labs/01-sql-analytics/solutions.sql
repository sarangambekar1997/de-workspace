-- Reference solutions for Lab 01. Try exercises.sql first.
-- Run:  python run_sql.py solutions.sql

-- Q1: Deduplicate orders — keep the latest version of each order, with status normalized to lowercase
CREATE OR REPLACE VIEW orders AS
SELECT order_id, customer_id, order_ts, LOWER(status) AS status, currency, updated_at
FROM raw_orders
QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY updated_at DESC) = 1;

SELECT
    (SELECT COUNT(*) FROM raw_orders)                 AS raw_rows,
    (SELECT COUNT(DISTINCT order_id) FROM raw_orders) AS distinct_orders,
    (SELECT COUNT(*) FROM orders)                     AS deduplicated_rows;

-- Q2: Data quality report — count each type of problem
SELECT 'orders missing customer_id' AS check_name, COUNT(*) AS failures
FROM orders WHERE customer_id IS NULL
UNION ALL
SELECT 'order lines with non-positive quantity', COUNT(*)
FROM order_items WHERE quantity <= 0
UNION ALL
SELECT 'order lines with unknown product', COUNT(*)
FROM order_items oi LEFT JOIN products p USING (product_id) WHERE p.product_id IS NULL
UNION ALL
SELECT 'raw orders with non-lowercase status', COUNT(*)
FROM raw_orders WHERE status <> LOWER(status)
UNION ALL
SELECT 'duplicate event deliveries', COUNT(*) - COUNT(DISTINCT event_id)
FROM events;

-- Q3: Daily revenue — valid lines only, excluding cancelled orders
CREATE OR REPLACE VIEW order_lines_clean AS
SELECT o.order_id, o.customer_id, CAST(o.order_ts AS DATE) AS order_date, o.status,
       oi.product_id, oi.quantity, oi.unit_price, oi.quantity * oi.unit_price AS line_revenue
FROM orders o
JOIN order_items oi USING (order_id)
JOIN products p USING (product_id)            -- drops orphan product lines
WHERE oi.quantity > 0
  AND o.status <> 'cancelled';

SELECT order_date, COUNT(DISTINCT order_id) AS orders, SUM(line_revenue) AS revenue
FROM order_lines_clean
GROUP BY order_date
ORDER BY order_date
LIMIT 10;

-- Q4: Top 3 products by revenue within each category
SELECT category, name, revenue, rnk
FROM (
    SELECT p.category, p.name, SUM(l.line_revenue) AS revenue,
           RANK() OVER (PARTITION BY p.category ORDER BY SUM(l.line_revenue) DESC) AS rnk
    FROM order_lines_clean l
    JOIN products p USING (product_id)
    GROUP BY p.category, p.name
)
WHERE rnk <= 3
ORDER BY category, rnk;

-- Q5: Customer lifetime value and repeat purchase rate
WITH per_customer AS (
    SELECT customer_id,
           COUNT(DISTINCT order_id) AS orders,
           SUM(line_revenue)        AS lifetime_value,
           MIN(order_date)          AS first_order_date
    FROM order_lines_clean
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT
    COUNT(*)                                                    AS customers_with_orders,
    ROUND(AVG(lifetime_value), 2)                               AS avg_lifetime_value,
    ROUND(100.0 * COUNT(*) FILTER (WHERE orders > 1) / COUNT(*), 1) AS pct_repeat_customers
FROM per_customer;

-- Q6: 7-day moving average of daily revenue
WITH daily AS (
    SELECT order_date, SUM(line_revenue) AS revenue
    FROM order_lines_clean
    GROUP BY order_date
)
SELECT order_date, revenue,
       ROUND(AVG(revenue) OVER (ORDER BY order_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS revenue_7d_avg
FROM daily
ORDER BY order_date
LIMIT 10;

-- Q7: Revenue by country — customers' current country
SELECT c.country, COUNT(DISTINCT l.order_id) AS orders, SUM(l.line_revenue) AS revenue
FROM order_lines_clean l
JOIN customers c USING (customer_id)
GROUP BY c.country
ORDER BY revenue DESC;

-- Q8: Checkout funnel — distinct customers reaching each page per day (deduplicated events)
WITH dedup AS (
    SELECT * FROM events
    QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY received_ts) = 1
)
SELECT CAST(event_ts AS DATE) AS day,
       COUNT(DISTINCT customer_id) FILTER (WHERE page = '/')         AS home,
       COUNT(DISTINCT customer_id) FILTER (WHERE page = '/product')  AS product,
       COUNT(DISTINCT customer_id) FILTER (WHERE page = '/cart')     AS cart,
       COUNT(DISTINCT customer_id) FILTER (WHERE page = '/checkout') AS checkout
FROM dedup
GROUP BY day
ORDER BY day
LIMIT 5;

-- Q9: Late-arriving events — share received more than 1 hour after they happened
SELECT
    COUNT(*)                                                         AS events,
    COUNT(*) FILTER (WHERE received_ts - event_ts > INTERVAL 1 HOUR) AS late_events,
    ROUND(100.0 * COUNT(*) FILTER (WHERE received_ts - event_ts > INTERVAL 1 HOUR) / COUNT(*), 2) AS pct_late,
    MAX(received_ts - event_ts)                                      AS max_delay
FROM events;

-- Q10: Sessionize clickstream — a new session starts after 30 minutes of inactivity
WITH dedup AS (
    SELECT * FROM events
    QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY received_ts) = 1
),
flagged AS (
    SELECT *,
           CASE WHEN event_ts - LAG(event_ts) OVER (PARTITION BY customer_id ORDER BY event_ts)
                     <= INTERVAL 30 MINUTE THEN 0 ELSE 1 END AS is_new_session
    FROM dedup
),
sessions AS (
    SELECT *, SUM(is_new_session) OVER (PARTITION BY customer_id ORDER BY event_ts
                                         ROWS UNBOUNDED PRECEDING) AS session_number
    FROM flagged
)
SELECT customer_id, session_number,
       MIN(event_ts) AS session_start, MAX(event_ts) AS session_end, COUNT(*) AS page_views
FROM sessions
GROUP BY customer_id, session_number
ORDER BY customer_id, session_number
LIMIT 10;
