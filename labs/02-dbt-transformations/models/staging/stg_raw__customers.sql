select
    customer_id::integer        as customer_id,
    email,
    first_name,
    country,
    signup_date::date           as signup_date,
    updated_at::timestamp       as updated_at
from {{ source('raw', 'customers') }}
