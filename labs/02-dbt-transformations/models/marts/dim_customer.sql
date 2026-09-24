select
    customer_id,
    email,
    first_name,
    country,
    signup_date
from {{ ref('stg_raw__customers') }}
