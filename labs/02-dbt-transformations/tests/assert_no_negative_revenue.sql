-- Singular test: fails if any order has negative revenue
select order_id, order_amount_usd
from {{ ref('fct_orders') }}
where order_amount_usd < 0
