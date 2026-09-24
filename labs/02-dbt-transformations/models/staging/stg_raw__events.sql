-- One row per event: drop duplicate deliveries of the same event_id
select
    event_id::bigint            as event_id,
    customer_id::integer        as customer_id,
    event_type,
    page,
    event_ts::timestamp         as event_ts,
    received_ts::timestamp      as received_ts
from {{ source('raw', 'events') }}
qualify row_number() over (partition by event_id order by received_ts) = 1
