-- Setup: expose the generated files as typed views.
-- Run once:  python run_sql.py setup.sql

CREATE OR REPLACE VIEW customers AS
SELECT * FROM read_csv('../data/output/customers.csv', header = true, columns = {
    'customer_id': 'INTEGER', 'email': 'VARCHAR', 'first_name': 'VARCHAR',
    'country': 'VARCHAR', 'signup_date': 'DATE', 'updated_at': 'TIMESTAMP'
});

CREATE OR REPLACE VIEW products AS
SELECT * FROM read_csv('../data/output/products.csv', header = true, columns = {
    'product_id': 'INTEGER', 'sku': 'VARCHAR', 'name': 'VARCHAR',
    'category': 'VARCHAR', 'unit_price': 'DECIMAL(10,2)'
});

CREATE OR REPLACE VIEW raw_orders AS
SELECT * FROM read_csv('../data/output/orders.csv', header = true, columns = {
    'order_id': 'BIGINT', 'customer_id': 'INTEGER', 'order_ts': 'TIMESTAMP',
    'status': 'VARCHAR', 'currency': 'VARCHAR', 'updated_at': 'TIMESTAMP'
});

CREATE OR REPLACE VIEW order_items AS
SELECT * FROM read_csv('../data/output/order_items.csv', header = true, columns = {
    'order_id': 'BIGINT', 'line_no': 'INTEGER', 'product_id': 'INTEGER',
    'quantity': 'INTEGER', 'unit_price': 'DECIMAL(10,2)'
});

CREATE OR REPLACE VIEW events AS
SELECT
    event_id::BIGINT         AS event_id,
    customer_id::INTEGER     AS customer_id,
    event_type,
    page,
    event_ts::TIMESTAMP      AS event_ts,
    received_ts::TIMESTAMP   AS received_ts
FROM read_json('../data/output/events.jsonl', format = 'newline_delimited');

-- Q0: Sanity check — row counts per table
SELECT 'customers' AS tbl, COUNT(*) AS n FROM customers
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'raw_orders', COUNT(*) FROM raw_orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL SELECT 'events', COUNT(*) FROM events;
