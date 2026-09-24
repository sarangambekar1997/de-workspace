select
    order_id::bigint            as order_id,
    line_no::integer            as line_no,
    product_id::integer         as product_id,
    quantity::integer           as quantity,
    unit_price::decimal(10, 2)  as unit_price
from {{ source('raw', 'order_items') }}
