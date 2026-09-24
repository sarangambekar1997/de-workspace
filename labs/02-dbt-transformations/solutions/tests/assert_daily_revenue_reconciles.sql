-- Exercise 3: the daily fact and the order fact must report the same total revenue.
-- Returns a row (a failure) when they differ by more than rounding.
with daily as (
    select sum(revenue_usd) as revenue from {{ ref('fct_daily_revenue') }}
),
orders as (
    select sum(order_amount_usd) as revenue from {{ ref('fct_orders') }}
    where status != 'cancelled'
)

select daily.revenue as daily_revenue, orders.revenue as order_revenue
from daily, orders
where abs(daily.revenue - orders.revenue) > 1
