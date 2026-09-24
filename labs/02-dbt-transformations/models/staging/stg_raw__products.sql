select
    product_id::integer         as product_id,
    sku,
    name                        as product_name,
    category,
    unit_price::decimal(10, 2)  as list_price
from {{ source('raw', 'products') }}
