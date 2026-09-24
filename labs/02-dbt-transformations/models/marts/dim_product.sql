select product_id, sku, product_name, category, list_price
from {{ ref('stg_raw__products') }}
