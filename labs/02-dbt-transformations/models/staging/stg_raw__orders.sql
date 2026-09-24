-- One row per order: keep the latest version and normalize status casing
with source as (
    select * from {{ source('raw', 'orders') }}
)

select
    order_id::bigint            as order_id,
    customer_id::integer        as customer_id,
    order_ts::timestamp         as order_ts,
    lower(status)               as status,
    currency,
    updated_at::timestamp       as updated_at
from source
qualify row_number() over (partition by order_id order by updated_at desc) = 1
