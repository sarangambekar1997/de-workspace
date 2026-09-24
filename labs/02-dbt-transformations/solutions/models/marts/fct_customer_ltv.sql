-- Exercise 2: one row per customer with lifetime order metrics
with orders as (
    select * from {{ ref('fct_orders') }}
    where status != 'cancelled'
      and customer_id is not null
)

select
    c.customer_id,
    c.country,
    min(o.order_date)                             as first_order_date,
    max(o.order_date)                             as last_order_date,
    count(o.order_id)                             as orders,
    coalesce(sum(o.order_amount_usd), 0)          as lifetime_value_usd,
    count(o.order_id) > 1                         as is_repeat_customer
from {{ ref('dim_customer') }} c
left join orders o using (customer_id)
group by c.customer_id, c.country
