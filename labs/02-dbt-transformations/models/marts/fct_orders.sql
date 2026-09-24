-- One row per order with totals from valid lines
select
    order_id,
    customer_id,
    min(order_ts)                                             as order_ts,
    min(order_date)                                           as order_date,
    min(status)                                               as status,
    min(currency)                                             as currency,
    count(*) filter (where line_status = 'valid')             as valid_lines,
    count(*) filter (where line_status not in ('valid', 'cancelled_order')) as invalid_lines,
    coalesce(sum(line_amount_usd) filter (where line_status = 'valid'), 0) as order_amount_usd
from {{ ref('int_order_lines__valid') }}
group by order_id, customer_id
