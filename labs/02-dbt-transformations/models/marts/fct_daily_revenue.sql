{{ config(
    materialized = 'incremental',
    unique_key = 'order_date',
    incremental_strategy = 'delete+insert'
) }}

-- Daily revenue, rebuilt incrementally: only the last 3 days are reprocessed on each run
select
    order_date,
    count(distinct order_id)                  as orders,
    count(distinct customer_id)               as customers,
    round(sum(line_amount_usd), 2)            as revenue_usd
from {{ ref('int_order_lines__valid') }}
where line_status = 'valid'
{% if is_incremental() %}
  and order_date >= (select max(order_date) - interval 3 day from {{ this }})
{% endif %}
group by order_date
