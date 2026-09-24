-- Order lines joined to orders and products; invalid lines are flagged, not silently dropped
with lines as (
    select * from {{ ref('stg_raw__order_items') }}
),
orders as (
    select * from {{ ref('stg_raw__orders') }}
),
products as (
    select * from {{ ref('stg_raw__products') }}
),
rates as (
    select * from {{ ref('currency_rates') }}
)

select
    l.order_id,
    l.line_no,
    o.customer_id,
    o.order_ts,
    cast(o.order_ts as date)                              as order_date,
    o.status,
    o.currency,
    l.product_id,
    p.category,
    l.quantity,
    l.unit_price,
    l.quantity * l.unit_price                             as line_amount,
    l.quantity * l.unit_price * r.rate_to_usd             as line_amount_usd,
    case
        when p.product_id is null then 'unknown_product'
        when l.quantity <= 0      then 'non_positive_quantity'
        when o.status = 'cancelled' then 'cancelled_order'
        else 'valid'
    end                                                   as line_status
from lines l
join orders o        using (order_id)
left join products p using (product_id)
left join rates r    on r.currency = o.currency
