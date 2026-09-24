-- Exercise 6: revenue by the country the customer lived in when they ordered.
-- Joins each order to the customer version that was valid at order time (a point-in-time join).
with customer_versions as (
    select
        customer_id,
        country,
        -- The first recorded version also covers the time before the snapshot started
        case
            when row_number() over (partition by customer_id order by dbt_valid_from) = 1
                then timestamp '1900-01-01'
            else dbt_valid_from
        end                                           as valid_from,
        coalesce(dbt_valid_to, timestamp '9999-12-31') as valid_to
    from {{ ref('snap_customers') }}
),
orders as (
    select * from {{ ref('fct_orders') }}
    where status != 'cancelled'
)

select
    coalesce(v.country, 'unknown')            as country_at_order,
    count(*)                                  as orders,
    round(sum(o.order_amount_usd), 2)         as revenue_usd
from orders o
left join customer_versions v
    on  v.customer_id = o.customer_id
    and o.order_ts >= v.valid_from
    and o.order_ts <  v.valid_to
group by 1
order by revenue_usd desc
